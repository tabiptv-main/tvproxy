from flask import Flask, request, Response
import requests
from urllib.parse import urlparse, urljoin, quote, unquote
import re
import json
import os

app = Flask(__name__)

# Configurazione proxy per newkso.ru e daddy_php_sites
NEWKSO_PROXY_HTTP = os.getenv('NEWKSO_PROXY_HTTP', None)  # es: 'http://proxy.example.com:8080'
NEWKSO_PROXY_HTTPS = os.getenv('NEWKSO_PROXY_HTTPS', None) # es: 'https://proxy.example.com:8080'
NEWKSO_PROXY_SOCKS5 = os.getenv('NEWKSO_PROXY_SOCKS5', None) # es: 'socks5://user:pass@host:port' (requires PySocks: pip install "requests[socks]")

def get_newkso_proxies():
    """Restituisce il dizionario dei proxy per newkso.ru e daddy_php_sites se configurati"""
    proxies = {}
    if NEWKSO_PROXY_SOCKS5:
        proxies['http'] = NEWKSO_PROXY_SOCKS5
        proxies['https'] = NEWKSO_PROXY_SOCKS5
    else:
        if NEWKSO_PROXY_HTTP:
            proxies['http'] = NEWKSO_PROXY_HTTP
        if NEWKSO_PROXY_HTTPS:
            proxies['https'] = NEWKSO_PROXY_HTTPS
    return proxies if proxies else None

def detect_m3u_type(content):
    """Rileva se è un M3U (lista IPTV) o un M3U8 (flusso HLS)"""
    if "#EXTM3U" in content and "#EXTINF" in content:
        return "m3u8"
    return "m3u"

def replace_key_uri(line, headers_query):
    """Sostituisce l'URI della chiave AES-128 con il proxy"""
    match = re.search(r'URI="([^"]+)"', line)
    if match:
        key_url = match.group(1)
        proxied_key_url = f"/proxy/key?url={quote(key_url)}&{headers_query}"
        return line.replace(key_url, proxied_key_url)
    return line

def is_proxied_domain(url):
    """Restituisce True se l'URL è per newkso.ru o per daddy_php_sites"""
    daddy_php_domains = [
        "new.newkso.ru/wind/",
        "new.newkso.ru/ddy6/",
        "new.newkso.ru/zeko/",
        "new.newkso.ru/nfs/",
        "new.newkso.ru/dokko1/",
    ]
    parsed = urlparse(url.lower())
    if "newkso.ru" in parsed.netloc:
        return True
    for domain in daddy_php_domains:
        if domain in url.lower():
            return True
    return False

def resolve_m3u8_link(url, headers=None):
    """
    Risolve un URL M3U8 supportando header e proxy per newkso.ru e daddy_php_sites.
    """
    if not url:
        print("Errore: URL non fornito.")
        return {"resolved_url": None, "headers": {}}

    print(f"Tentativo di risoluzione URL: {url}")
    
    # Inizializza gli header di default
    current_headers = headers if headers else {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
    }
    
    clean_url = url
    extracted_headers = {}

    # Siti Daddy PHP
    daddy_php_sites = [
        "https://new.newkso.ru/wind/",
        "https://new.newkso.ru/ddy6/",
        "https://new.newkso.ru/zeko/",
        "https://new.newkso.ru/nfs/",
        "https://new.newkso.ru/dokko1/",
    ]
    
    # Estrazione header da URL
    if '&h_' in url or '%26h_' in url:
        print("Rilevati parametri header nell'URL - Estrazione in corso...")
        if '%26h_' in url:
            if 'vavoo.to' in url.lower():
                url = url.replace('%26', '&')
            else:
                url = unquote(unquote(url))
        url_parts = url.split('&h_', 1)
        clean_url = url_parts[0]
        header_params = '&h_' + url_parts[1]
        for param in header_params.split('&'):
            if param.startswith('h_'):
                try:
                    key_value = param[2:].split('=', 1)
                    if len(key_value) == 2:
                        key = unquote(key_value[0]).replace('_', '-')
                        value = unquote(key_value[1])
                        extracted_headers[key] = value
                except Exception as e:
                    print(f"Errore nell'estrazione dell'header {param}: {e}")
        current_headers.update(extracted_headers)
    else:
        print("URL pulito rilevato - Nessuna estrazione header necessaria")

    # Gestione .php Daddy
    if clean_url.endswith('.php'):
        print(f"Rilevato URL .php {clean_url}")
        channel_id_match = re.search(r'stream-(\d+)\.php', clean_url)
        if channel_id_match:
            channel_id = channel_id_match.group(1)
            print(f"Channel ID estratto: {channel_id}")

            newkso_headers_for_php_resolution = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
                'Referer': 'https://forcedtoplay.xyz/',
                'Origin': 'https://forcedtoplay.xyz/'
            }

            # Tennis Channels
            if channel_id.startswith("15") and len(channel_id) == 4:
                tennis_suffix = channel_id[2:]
                folder_name = f"wikiten{tennis_suffix}"
                test_url = f"https://new.newkso.ru/wikihz/{folder_name}/mono.m3u8"
                print(f"Tentativo canale Tennis: {test_url}")
                try:
                    proxies = get_newkso_proxies() # Il proxy è sempre necessario per newkso.ru
                    response = requests.head(test_url, headers=newkso_headers_for_php_resolution, 
                                           proxies=proxies, timeout=2.5, allow_redirects=True)
                    if response.status_code == 200:
                        print(f"Stream Tennis trovato: {test_url}")
                        return {"resolved_url": test_url, "headers": newkso_headers_for_php_resolution}
                except requests.RequestException as e:
                    print(f"Errore HEAD per Tennis stream {test_url}: {e}")
            
            # Daddy Channels
            else:
                folder_name = f"premium{channel_id}"
                for site in daddy_php_sites:
                    test_url = f"{site}{folder_name}/mono.m3u8"
                    print(f"Tentativo canale Daddy: {test_url}")
                    try:
                        proxies = get_newkso_proxies() # Il proxy è sempre necessario per newkso.ru
                        response = requests.head(test_url, headers=newkso_headers_for_php_resolution, 
                                               proxies=proxies, timeout=2.5, allow_redirects=True)
                        if response.status_code == 200:
                            print(f"Stream Daddy trovato: {test_url}")
                            return {"resolved_url": test_url, "headers": newkso_headers_for_php_resolution}
                    except requests.RequestException as e:
                        print(f"Errore HEAD per Daddy stream {test_url}: {e}")

    # Fallback: richiesta normale
    try:
        with requests.Session() as session:
            # Determina se usare il proxy per la richiesta finale
            proxies = None
            if is_proxied_domain(clean_url):
                proxies = get_newkso_proxies()
                if proxies:
                    print(f"DEBUG [resolve_m3u8_link]: Proxy in uso per {clean_url}", flush=True)
            print(f"Passo 1: Richiesta a {clean_url}")
            response = session.get(clean_url, headers=current_headers, proxies=proxies, 
                                 allow_redirects=True, timeout=(5, 15))
            response.raise_for_status()
            initial_response_text = response.text
            final_url_after_redirects = response.url
            print(f"Passo 1 completato. URL finale dopo redirect: {final_url_after_redirects}")

            if initial_response_text and initial_response_text.strip().startswith('#EXTM3U'):
                print("Trovato file M3U8 diretto.")
                return {
                    "resolved_url": final_url_after_redirects,
                    "headers": current_headers
                }
            else:
                print("La risposta iniziale non era un M3U8 diretto.")
                return {
                    "resolved_url": clean_url,
                    "headers": current_headers
                }

    except requests.RequestException as e:
        print(f"Errore durante la richiesta HTTP iniziale: {e}")
        return {"resolved_url": clean_url, "headers": current_headers}
    except Exception as e:
        print(f"Errore generico durante la risoluzione: {e}")
        return {"resolved_url": clean_url, "headers": current_headers}

@app.route('/proxy')
def proxy():
    """Proxy per liste M3U che aggiunge automaticamente /proxy/m3u?url= con IP prima dei link"""
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Errore: Parametro 'url' mancante", 400

    try:
        server_ip = request.host
        response = requests.get(m3u_url, timeout=(10, 30))
        response.raise_for_status()
        m3u_content = response.text
        
        modified_lines = []
        exthttp_headers_query_params = ""

        for line in m3u_content.splitlines():
            line = line.strip()
            if line.startswith('#EXTHTTP:'):
                try:
                    json_str = line.split(':', 1)[1].strip()
                    headers_dict = json.loads(json_str)
                    temp_params = []
                    for key, value in headers_dict.items():
                        encoded_key = quote(quote(key))
                        encoded_value = quote(quote(str(value)))
                        temp_params.append(f"h_{encoded_key}={encoded_value}")
                    if temp_params:
                        exthttp_headers_query_params = "%26" + "%26".join(temp_params)
                    else:
                        exthttp_headers_query_params = ""
                except Exception as e:
                    print(f"Errore nel parsing di #EXTHTTP '{line}': {e}")
                    exthttp_headers_query_params = ""
                modified_lines.append(line)
            elif line and not line.startswith('#'):
                if 'pluto.tv' in line.lower():
                    modified_lines.append(line)
                    exthttp_headers_query_params = ""
                else:
                    encoded_line = quote(line, safe='')
                    modified_line = f"http://{server_ip}/proxy/m3u?url={encoded_line}{exthttp_headers_query_params}"
                    modified_lines.append(modified_line)
                    exthttp_headers_query_params = ""
            else:
                modified_lines.append(line)
        
        modified_content = '\n'.join(modified_lines)
        parsed_m3u_url = urlparse(m3u_url)
        original_filename = os.path.basename(parsed_m3u_url.path)
        
        return Response(modified_content, content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': f'attachment; filename="{original_filename}"'})
        
    except requests.RequestException as e:
        return f"Errore durante il download della lista M3U: {str(e)}", 500
    except Exception as e:
        return f"Errore generico: {str(e)}", 500

@app.route('/proxy/m3u')
def proxy_m3u():
    """Proxy per file M3U e M3U8 con supporto per proxy newkso.ru e daddy_php_sites"""
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Errore: Parametro 'url' mancante", 400

    default_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/33.0 Mobile/15E148 Safari/605.1.15",
        "Referer": "https://vavoo.to/",
        "Origin": "https://vavoo.to"
    }

    request_headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }
    
    headers = {**default_headers, **request_headers}

    processed_url = m3u_url

    try:
        result = resolve_m3u8_link(processed_url, headers)

        if not result["resolved_url"]:
            return "Errore: Impossibile risolvere l'URL in un M3U8 valido.", 500

        resolved_url = result["resolved_url"]
        current_headers_for_proxy = result["headers"]

        # Determina se usare il proxy per l'URL risolto
        proxies = None
        if is_proxied_domain(resolved_url):
            proxies = get_newkso_proxies()
            if proxies:
                print(f"DEBUG [proxy_m3u]: Proxy in uso per GET {resolved_url}", flush=True)

        m3u_response = requests.get(resolved_url, headers=current_headers_for_proxy, 
                                   proxies=proxies, allow_redirects=True, timeout=(10, 20))
        m3u_response.raise_for_status()
        m3u_response.encoding = m3u_response.apparent_encoding or 'utf-8'
        m3u_content = m3u_response.text
        final_url = m3u_response.url

        file_type = detect_m3u_type(m3u_content)

        if file_type == "m3u":
            return Response(m3u_content, content_type="application/vnd.apple.mpegurl; charset=utf-8")

        parsed_url = urlparse(final_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path.rsplit('/', 1)[0]}/"

        headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in current_headers_for_proxy.items()])

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
        return Response(modified_m3u8_content, content_type="application/vnd.apple.mpegurl; charset=utf-8")

    except requests.RequestException as e:
        return f"Errore durante il download o la risoluzione del file: {str(e)}", 500
    except Exception as e:
        return f"Errore generico nella funzione proxy_m3u: {str(e)}", 500

@app.route('/proxy/ts')
def proxy_ts():
    """Proxy per segmenti .TS con headers personalizzati e supporto proxy newkso.ru e daddy_php_sites"""
    ts_url = request.args.get('url', '').strip()
    if not ts_url:
        return "Errore: Parametro 'url' mancante", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    proxies = None
    if is_proxied_domain(ts_url):
        proxies = get_newkso_proxies()
        if proxies:
            print(f"DEBUG [proxy_ts]: Proxy in uso per {ts_url}", flush=True)

    try:
        response = requests.get(ts_url, headers=headers, proxies=proxies, stream=True, 
                              allow_redirects=True, timeout=(10, 30))
        response.raise_for_status()
        
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        return Response(generate(), content_type="video/mp2t")
    
    except requests.RequestException as e:
        return f"Errore durante il download del segmento TS: {str(e)}", 500

@app.route('/proxy/key')
def proxy_key():
    """Proxy per la chiave AES-128 con header personalizzati e supporto proxy newkso.ru e daddy_php_sites"""
    key_url = request.args.get('url', '').strip()
    if not key_url:
        return "Errore: Parametro 'url' mancante per la chiave", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    proxies = None
    if is_proxied_domain(key_url):
        proxies = get_newkso_proxies()
        if proxies:
            print(f"DEBUG [proxy_key]: Proxy in uso per {key_url}", flush=True)

    try:
        response = requests.get(key_url, headers=headers, proxies=proxies, 
                              allow_redirects=True, timeout=(5, 15))
        response.raise_for_status()
        
        return Response(response.content, content_type="application/octet-stream")
    
    except requests.RequestException as e:
        return f"Errore durante il download della chiave: {str(e)}", 500

@app.route('/')
def index():
    """Pagina principale che mostra un messaggio di benvenuto"""
    return "Proxy started!"

if __name__ == '__main__':
    print("--- SCRIPT INIZIALIZZATO, IN ATTESA DI AVVIARE IL SERVER FLASK ---", flush=True)
    print("--- AVVIO DEL SERVER FLASK (MODALITÀ DEBUG) ---", flush=True)
    app.run(host="0.0.0.0", port=7860, debug=False)
