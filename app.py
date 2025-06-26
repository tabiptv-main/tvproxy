from flask import Flask, request, Response
import requests
from urllib.parse import urlparse, urljoin, quote, unquote
import os
import re
from cachetools import TTLCache, LRUCache
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

VERIFY_SSL = os.environ.get('VERIFY_SSL', 'false').lower() not in ('false', '0', 'no')
if not VERIFY_SSL:
    print("UYARI: SSL sertifika doğrulaması KAPALI. Güvenlik riski olabilir.")
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 30))
print(f"İstek zaman aşımı {REQUEST_TIMEOUT} saniye olarak ayarlandı.")

SERVER_BASE_URL = os.environ.get('SERVER_BASE_URL', 'https://tabiptv-tvproxy.hf.space')
print(f"Sunucu temel URL'si: {SERVER_BASE_URL}")

# --- Dinamik Başlık Yönetimi ---
def get_dynamic_headers(target_url):
    parsed = urlparse(target_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': '*/*',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'tr,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
        'DNT': '1',
        'Origin': domain,
        'Referer': domain + '/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site'
    }

# --- Önbellek Yapılandırması ---
M3U8_CACHE = TTLCache(maxsize=200, ttl=60)
TS_CACHE = LRUCache(maxsize=1000)
KEY_CACHE = LRUCache(maxsize=200)

def detect_m3u_type(content):
    return "m3u8" if "#EXTM3U" in content and "#EXTINF" in content else "m3u"

def replace_key_uri(line, headers_query, base_domain):
    match = re.search(r'URI="([^"]+)"', line)
    if match:
        key_url = match.group(1)
        proxied_key_url = f"{SERVER_BASE_URL}/proxy/key?url={quote(key_url)}&{headers_query}"
        return line.replace(key_url, proxied_key_url)
    return line

def get_headers_from_request():
    return {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

@app.route('/proxy/m3u')
def proxy_m3u():
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Hata: 'url' parametresi eksik", 400

    # Önbellek kontrolü
    cache_key = f"{m3u_url}|{request.query_string.decode()}"
    if cache_key in M3U8_CACHE:
        print(f"Önbellek HIT: M3U8 {m3u_url}")
        return Response(
            M3U8_CACHE[cache_key], 
            content_type="application/vnd.apple.mpegurl",
            headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'}
        )

    print(f"Önbellek MISS: M3U8 {m3u_url}")

    # Dinamik başlıkları oluştur
    dynamic_headers = get_dynamic_headers(m3u_url)
    custom_headers = get_headers_from_request()
    headers = {**dynamic_headers, **custom_headers}
    
    try:
        session = requests.Session()
        session.max_redirects = 5
        session.headers.update(headers)
        
        print(f"M3U8 isteği gönderiliyor: {m3u_url}")
        response = session.get(
            m3u_url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            verify=VERIFY_SSL,
            stream=True
        )
        response.raise_for_status()
        
        final_url = response.url
        print(f"Son URL: {final_url}")
        
        m3u_content = response.text
        file_type = detect_m3u_type(m3u_content)
        
        if file_type == "m3u":
            M3U8_CACHE[cache_key] = m3u_content
            return Response(
                m3u_content, 
                content_type="application/vnd.apple.mpegurl",
                headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'}
            )

        # M3U8 işleme
        parsed_url = urlparse(final_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{os.path.dirname(parsed_url.path)}/"
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in headers.items()])

        modified_lines = []
        for line in m3u_content.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-KEY") and 'URI="' in line:
                line = replace_key_uri(line, headers_query, base_domain)
            elif line and not line.startswith("#"):
                segment_url = urljoin(base_url, line)
                line = f"{SERVER_BASE_URL}/proxy/ts?url={quote(segment_url)}&{headers_query}"
            modified_lines.append(line)

        modified_content = "\n".join(modified_lines)
        M3U8_CACHE[cache_key] = modified_content
        
        return Response(
            modified_content, 
            content_type="application/vnd.apple.mpegurl",
            headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'}
        )

    except requests.RequestException as e:
        print(f"M3U8 hatası: {str(e)}")
        return f"M3U8 indirme hatası: {str(e)}", 502
    except Exception as e:
        print(f"Beklenmeyen hata: {str(e)}")
        return f"Sunucu hatası: {str(e)}", 500

@app.route('/proxy/ts')
def proxy_ts():
    ts_url = request.args.get('url', '').strip()
    if not ts_url:
        return "Hata: 'url' parametresi eksik", 400

    filename = os.path.basename(urlparse(ts_url).path)
    
    if ts_url in TS_CACHE:
        print(f"Önbellek HIT: TS {filename}")
        return Response(
            TS_CACHE[ts_url],
            content_type="video/mp2t",
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    print(f"Önbellek MISS: TS {filename}")
    
    # Dinamik başlıkları oluştur
    dynamic_headers = get_dynamic_headers(ts_url)
    custom_headers = get_headers_from_request()
    headers = {**dynamic_headers, **custom_headers}

    try:
        response = requests.get(
            ts_url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            verify=VERIFY_SSL
        )
        response.raise_for_status()

        def generate():
            chunks = []
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    chunks.append(chunk)
                    yield chunk
            TS_CACHE[ts_url] = b"".join(chunks)

        return Response(
            generate(),
            content_type="video/mp2t",
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except requests.RequestException as e:
        print(f"TS hatası ({filename}): {str(e)}")
        return f"TS segment hatası: {str(e)}", 502

@app.route('/proxy/key')
def proxy_key():
    key_url = request.args.get('url', '').strip()
    if not key_url:
        return "Hata: 'url' parametresi eksik", 400

    filename = os.path.basename(urlparse(key_url).path)
    
    if key_url in KEY_CACHE:
        print(f"Önbellek HIT: KEY {filename}")
        return Response(
            KEY_CACHE[key_url],
            content_type="application/octet-stream",
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    print(f"Önbellek MISS: KEY {filename}")
    
    # Dinamik başlıkları oluştur
    dynamic_headers = get_dynamic_headers(key_url)
    custom_headers = get_headers_from_request()
    headers = {**dynamic_headers, **custom_headers}

    try:
        response = requests.get(
            key_url,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            verify=VERIFY_SSL
        )
        response.raise_for_status()
        
        key_content = response.content
        KEY_CACHE[key_url] = key_content
        
        return Response(
            key_content,
            content_type="application/octet-stream",
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except requests.RequestException as e:
        print(f"KEY hatası ({filename}): {str(e)}")
        return f"Anahtar indirme hatası: {str(e)}", 502

@app.route('/')
def index():
    return f"Proxy ÇALIŞIYOR - Sunucu: {SERVER_BASE_URL}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 7860))
    print(f"Proxy başlatılıyor: port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
