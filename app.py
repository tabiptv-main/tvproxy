from flask import Flask, request, Response
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urljoin, quote, unquote
import re
import os
import certifi  # <-- Import aggiunto

app = Flask(__name__)

# Sessione requests ottimizzata per alta concorrenza
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=0.1,
    status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=100,
    max_retries=retry_strategy
)
session.mount("http://", adapter)
session.mount("https://", adapter)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Proxy Server - High Performance</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
            h1 { color: #28a745; }
            .status { background: #d4edda; padding: 20px; border-radius: 5px; display: inline-block; }
            .info { background: #cce5ff; padding: 15px; border-radius: 5px; margin-top: 20px; display: inline-block; }
        </style>
    </head>
    <body>
        <div class="status">
            <h1>🟢 Proxy Attivo - High Performance</h1>
            <p>Server in funzione sulla porta 7860</p>
        </div>
        <div class="info">
            <h3>📊 Capacità</h3>
            <p>Ottimizzato per 100+ client simultanei</p>
            <p>Worker asincroni con gevent</p>
        </div>
    </body>
    </html>
    """

def detect_m3u_type(content):
    """ Rileva se è un M3U (lista IPTV) o un M3U8 (flusso HLS) """
    if "#EXTM3U" in content and "#EXTINF" in content:
        return "m3u8"
    return "m3u"

def replace_key_uri(line, headers_query):
    """ Sostituisce l'URI della chiave AES-128 con il proxy """
    match = re.search(r'URI="([^"]+)"', line)
    if match:
        key_url = match.group(1)
        proxied_key_url = f"/proxy/key?url={quote(key_url)}&{headers_query}"
        return line.replace(key_url, proxied_key_url)
    return line

@app.route('/proxy')
def proxy():
    """Proxy per liste M3U che aggiunge automaticamente /proxy/m3u?url= con IP prima dei link"""
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Errore: Parametro 'url' mancante", 400

    try:
        server_ip = request.host
        response = session.get(m3u_url, timeout=(10, 30), verify=certifi.where())
        response.raise_for_status()
        m3u_content = response.text

        modified_lines = []
        for line in m3u_content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                modified_line = f"http://{server_ip}/proxy/m3u?url={line}"
                modified_lines.append(modified_line)
            else:
                modified_lines.append(line)

        modified_content = '\n'.join(modified_lines)
        parsed_m3u_url = urlparse(m3u_url)
        original_filename = os.path.basename(parsed_m3u_url.path)

        return Response(
            modified_content,
            content_type="application/vnd.apple.mpegurl",
            headers={'Content-Disposition': f'attachment; filename="{original_filename}"'}
        )

    except requests.RequestException as e:
        return f"Errore durante il download della lista M3U: {str(e)}", 500
    except Exception as e:
        return f"Errore generico: {str(e)}", 500

@app.route('/proxy/m3u')
def proxy_m3u():
    """ Proxy per file M3U e M3U8 con supporto per redirezioni e header personalizzati """
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Errore: Parametro 'url' mancante", 400

    default_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/33.0 Mobile/15E148 Safari/605.1.15",
        "Referer": "https://vavoo.to/",
        "Origin": "https://vavoo.to"
    }

    headers = {**default_headers, **{
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }}

    try:
        response = session.get(
            m3u_url, headers=headers, allow_redirects=True, timeout=(10, 60), verify=certifi.where()
        )
        response.raise_for_status()
        final_url = response.url
        m3u_content = response.text

        file_type = detect_m3u_type(m3u_content)

        if file_type == "m3u":
            return Response(m3u_content, content_type="audio/x-mpegurl")

        parsed_url = urlparse(final_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path.rsplit('/', 1)[0]}/"

        headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in headers.items()])

        modified_m3u8 = []
        for line in m3u_content.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-KEY") and 'URI="' in line:
                line = replace_key_uri(line, headers_query)
            elif line and not line.startswith("#"):
                segment_url = urljoin(base_url, line)
                line = f"/proxy/ts?url={quote(segment_url)}&{headers_query}"
            modified_m3u8.append(line)

        modified_m3u8_content = "\n".join(modified_m3u8)

        return Response(modified_m3u8_content, content_type="application/vnd.apple.mpegurl")

    except requests.RequestException as e:
        return f"Errore durante il download del file M3U/M3U8: {str(e)}", 500

@app.route('/proxy/ts')
def proxy_ts():
    """ Proxy per segmenti .TS con headers personalizzati e streaming ottimizzato """
    ts_url = request.args.get('url', '').strip()
    if not ts_url:
        return "Errore: Parametro 'url' mancante", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    try:
        response = session.get(
            ts_url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=(5, 30),
            verify=certifi.where()
        )
        response.raise_for_status()

        def generate():
            try:
                for chunk in response.iter_content(chunk_size=16384):
                    if chunk:
                        yield chunk
            except Exception:
                pass
            finally:
                response.close()

        return Response(
            generate(),
            content_type="video/mp2t",
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            }
        )

    except requests.RequestException as e:
        return f"Errore durante il download del segmento TS: {str(e)}", 500

@app.route('/proxy/key')
def proxy_key():
    """ Proxy per la chiave AES-128 con header personalizzati """
    key_url = request.args.get('url', '').strip()
    if not key_url:
        return "Errore: Parametro 'url' mancante per la chiave", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    try:
        response = session.get(
            key_url, headers=headers, allow_redirects=True, timeout=(10, 30), verify=certifi.where()
        )
        response.raise_for_status()
        return Response(
            response.content,
            content_type="application/octet-stream",
            headers={'Cache-Control': 'max-age=3600'}
        )

    except requests.RequestException as e:
        return f"Errore durante il download della chiave AES-128: {str(e)}", 500

@app.route('/health')
def health():
    """Endpoint per health check"""
    return {"status": "healthy", "workers": "gevent", "capacity": "100+ clients"}, 200

if __name__ == '__main__':
    print("Proxy Attivo - Server High Performance avviato sulla porta 7860")
    app.run(host="0.0.0.0", port=7860, debug=False)
