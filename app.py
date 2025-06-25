from flask import Flask, request, Response
import requests
from urllib.parse import urlparse, urljoin, quote, unquote
import os
import time
from cachetools import TTLCache, LRUCache
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

# --- Genel Yapılandırma ---
VERIFY_SSL = os.environ.get('VERIFY_SSL', 'false').lower() not in ('false', '0', 'no')
if not VERIFY_SSL:
    print("UYARI: SSL sertifika doğrulaması KAPALI. Güvenlik riski olabilir.")
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 30))
print(f"İstek zaman aşımı {REQUEST_TIMEOUT} saniye olarak ayarlandı.")

# Sunucu temel URL'si
SERVER_BASE_URL = os.environ.get('SERVER_BASE_URL', 'https://tabiptv-tfms.hf.space')
print(f"Sunucu temel URL'si: {SERVER_BASE_URL}")

# --- Proxy Yapılandırması ---
PROXY_LIST = []

def setup_proxies():
    global PROXY_LIST
    proxies_found = []
    socks_proxy_list_str = os.environ.get('SOCKS5_PROXY')
    if socks_proxy_list_str:
        raw_socks_list = [p.strip() for p in socks_proxy_list_str.split(',') if p.strip()]
        for proxy in raw_socks_list:
            final_proxy_url = 'socks5h' + proxy[len('socks5'):] if proxy.startswith('socks5://') else proxy
            proxies_found.append(final_proxy_url)
        print(f"{len(raw_socks_list)} SOCKS5 proxy bulundu.")
    http_proxy_list_str = os.environ.get('HTTP_PROXY')
    if http_proxy_list_str:
        http_proxies = [p.strip() for p in http_proxy_list_str.split(',') if p.strip()]
        proxies_found.extend(http_proxies)
        print(f"{len(http_proxies)} HTTP proxy bulundu.")
    https_proxy_list_str = os.environ.get('HTTPS_PROXY')
    if https_proxy_list_str:
        https_proxies = [p.strip() for p in https_proxy_list_str.split(',') if p.strip()]
        proxies_found.extend(https_proxies)
        print(f"{len(https_proxies)} HTTPS proxy bulundu.")
    PROXY_LIST = proxies_found
    if PROXY_LIST:
        print(f"Toplam {len(PROXY_LIST)} proxy yapılandırıldı.")
    else:
        print("Hiçbir proxy yapılandırılmadı.")

def get_proxy_for_url(url):
    if not PROXY_LIST:
        return None
    try:
        parsed_url = urlparse(url)
        if 'github.com' in parsed_url.netloc:
            print(f"GitHub isteği algılandı ({url}), proxy atlanacak.")
            return None
    except Exception:
        pass
    import random
    chosen_proxy = random.choice(PROXY_LIST)
    print(f"Kullanılan proxy: {chosen_proxy}")
    return {'http': chosen_proxy, 'https': chosen_proxy}

setup_proxies()

# --- Önbellek Yapılandırması ---
M3U8_CACHE = TTLCache(maxsize=200, ttl=30)
TS_CACHE = LRUCache(maxsize=1000)
KEY_CACHE = LRUCache(maxsize=200)

def detect_m3u_type(content):
    if "#EXTM3U" in content and "#EXTINF" in content:
        return "m3u8"
    return "m3u"

def replace_key_uri(line, headers_query):
    match = re.search(r'URI="([^"]+)"', line)
    if match:
        key_url = match.group(1)
        proxied_key_url = f"{SERVER_BASE_URL}/proxy/key?url={quote(key_url)}&{headers_query}"
        return line.replace(key_url, proxied_key_url)
    return line

def ensure_ts_extension(segment_url):
    """Segment URL'sinin .ts uzantısıyla bittiğinden emin ol."""
    if not segment_url.lower().endswith('.ts'):
        return f"{segment_url}.ts"
    return segment_url

@app.route('/proxy/m3u')
def proxy_m3u():
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Hata: 'url' parametresi eksik", 400

    # Önbellek anahtarı oluştur
    cache_key_headers = "&".join(sorted([f"{k}={v}" for k, v in request.args.items() if k.lower().startswith("h_")]))
    cache_key = f"{m3u_url}|{cache_key_headers}"
    if cache_key in M3U8_CACHE:
        print(f"Önbellek HIT: M3U8 {m3u_url}")
        return Response(M3U8_CACHE[cache_key], content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'})

    print(f"Önbellek MISS: M3U8 {m3u_url}")

    # URL'den başlıkları çıkar
    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
        "Referer": "https://oha.to/",
        "Origin": "https://oha.to",
        "Accept": "application/vnd.apple.mpegurl, text/html, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9"
    }
    headers = {**default_headers, **headers}

    try:
        print(f"M3U8 içeriği alınıyor: {m3u_url}")
        print(f"Kullanılan başlıklar: {headers}")
        m3u_response = requests.get(m3u_url, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(m3u_url), verify=VERIFY_SSL)
        print(f"Sunucu yanıtı: {m3u_response.status_code}")
        m3u_response.raise_for_status()
        m3u_content = m3u_response.text
        final_url = m3u_response.url
        print(f"Nihai URL: {final_url}")

        file_type = detect_m3u_type(m3u_content)
        if file_type == "m3u":
            return Response(m3u_content, content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'})

        # M3U8 içeriğini işle
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
                segment_url = ensure_ts_extension(segment_url)  # .ts uzantısını garanti et
                line = f"{SERVER_BASE_URL}/proxy/ts?url={quote(segment_url)}&{headers_query}"
            modified_m3u8.append(line)

        modified_m3u8_content = "\n".join(modified_m3u8)
        M3U8_CACHE[cache_key] = modified_m3u8_content
        return Response(modified_m3u8_content, content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'})

    except requests.RequestException as e:
        print(f"İndirme hatası: {m3u_url} - {str(e)}")
        return f"M3U/M3U8 indirilirken hata: {str(e)}", 500
    except Exception as e:
        print(f"Genel hata: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return f"Elbette hata: {str(e)}", 500

@app.route('/proxy/ts')
def proxy_ts():
    ts_url = request.args.get('url', '').strip()
    if not ts_url:
        return "Hata: 'url' parametresi eksik", 400
    if ts_url in TS_CACHE:
        print(f"Önbellek HIT: TS {ts_url}")
        return Response(TS_CACHE[ts_url], content_type="video/mp2t")
    print(f"Önbellek MISS: TS {ts_url}")
    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
        "Referer": "https://oha.to/",
        "Origin": "https://oha.to",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9"
    }
    headers = {**default_headers, **headers}
    try:
        print(f"TS içeriği alınıyor: {ts_url}")
        response = requests.get(ts_url, headers=headers, stream=True, allow_redirects=True, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(ts_url), verify=VERIFY_SSL)
        print(f"TS sunucu yanıtı: {response.status_code}")
        response.raise_for_status()
        def generate_and_cache():
            content_parts = []
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content_parts.append(chunk)
                    yield chunk
            ts_content = b"".join(content_parts)
            if ts_content:
                TS_CACHE[ts_url] = ts_content
                print(f"TS segmenti önbelleğe alındı ({len(ts_content)} bayt): {ts_url}")
        return Response(generate_and_cache(), content_type="video/mp2t")
    except requests.RequestException as e:
        print(f"TS segmenti indirilirken hata: {ts_url} - {str(e)}")
        return f"TS segmenti indirilirken hata: {str(e)}", 500

@app.route('/proxy/key')
def proxy_key():
    key_url = request.args.get('url', '').strip()
    if not key_url:
        return "Hata: 'url' parametresi eksik", 400
    if key_url in KEY_CACHE:
        print(f"Önbellek HIT: KEY {key_url}")
        return Response(KEY_CACHE[key_url], content_type="application/octet-stream")
    print(f"Önbellek MISS: KEY {key_url}")
    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
        "Referer": "https://oha.to/",
        "Origin": "https://oha.to",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9"
    }
    headers = {**default_headers, **headers}
    try:
        print(f"KEY içeriği alınıyor: {key_url}")
        response = requests.get(key_url, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(key_url), verify=VERIFY_SSL)
        print(f"KEY sunucu yanıtı: {response.status_code}")
        response.raise_for_status()
        key_content = response.content
        KEY_CACHE[key_url] = key_content
        return Response(key_content, content_type="application/octet-stream")
    except requests.RequestException as e:
        print(f"AES-128 anahtarı indirilirken hata: {key_url} - {str(e)}")
        return f"AES-128 anahtarı indirilirken hata: {str(e)}", 500

@app.route('/')
def index():
    return f"Proxy ÇALIŞIYOR - Sunucu: {SERVER_BASE_URL}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 7860))
    print(f"Proxy ÇALIŞIYOR - Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
