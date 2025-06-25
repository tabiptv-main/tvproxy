from flask import Flask, request, Response
import requests
from urllib.parse import urlparse, urljoin, quote, unquote
import os
import random
from dotenv import load_dotenv
from cachetools import TTLCache, LRUCache

load_dotenv()

app = Flask(__name__)

# Cache sistemleri
M3U8_CACHE = TTLCache(maxsize=200, ttl=5)
TS_CACHE = LRUCache(maxsize=1000)
KEY_CACHE = LRUCache(maxsize=200)

# Proxy ayarları
OHA_PROXY = os.getenv('OHA_PROXY', None)
OHA_SSL_VERIFY = os.getenv('OHA_SSL_VERIFY', 'false').lower() == 'true'

if not OHA_SSL_VERIFY:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _get_proxy_dict(proxy_env_var):
    if not proxy_env_var:
        return None
    proxy_list = [p.strip() for p in proxy_env_var.split(',')]
    selected_proxy = random.choice(proxy_list)
    return {'http': selected_proxy, 'https': selected_proxy}

def get_proxy_config_for_url(url):
    parsed_url = urlparse(url.lower())
    if "oha.to" in parsed_url.netloc and OHA_PROXY:
        return {"proxies": _get_proxy_dict(OHA_PROXY), "verify": OHA_SSL_VERIFY}
    return {"proxies": None, "verify": True}

def detect_m3u_type(content):
    return "m3u8" if "#EXTM3U" in content and "#EXTINF" in content else "m3u"

def replace_key_uri(line, headers_query):
    import re
    match = re.search(r'URI="([^"]+)"', line)
    if match:
        key_url = match.group(1)
        proxied_key_url = f"/proxy/key?url={quote(key_url)}&{headers_query}"
        return line.replace(key_url, proxied_key_url)
    return line

@app.route('/proxy/m3u')
def proxy_m3u():
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url or 'oha.to' not in m3u_url:
        return "Yalnızca oha.to bağlantıları desteklenmektedir", 403

    cache_key_headers = "&".join(sorted([f"{k}={v}" for k, v in request.args.items() if k.lower().startswith("h_")]))
    cache_key = f"{m3u_url}|{cache_key_headers}"

    if cache_key in M3U8_CACHE:
        return Response(M3U8_CACHE[cache_key], content_type="application/vnd.apple.mpegurl; charset=utf-8")

    # Varsayılan header
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/33.0 Mobile/15E148 Safari/605.1.15",
        "Referer": "https://oha.to/",
        "Origin": "https://oha.to"
    }

    # İsteğe bağlı gelen header'ları da al
    headers.update({
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    })

    proxy_config = get_proxy_config_for_url(m3u_url)
    try:
        response = requests.get(m3u_url, headers=headers, proxies=proxy_config['proxies'],
                                allow_redirects=True, timeout=(10, 20), verify=proxy_config['verify'])
        response.raise_for_status()
        m3u_content = response.text
        final_url = response.url

        file_type = detect_m3u_type(m3u_content)
        if file_type == "m3u":
            return Response(m3u_content, content_type="application/vnd.apple.mpegurl; charset=utf-8")

        # Base URL belirle
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
        M3U8_CACHE[cache_key] = modified_m3u8_content
        return Response(modified_m3u8_content, content_type="application/vnd.apple.mpegurl; charset=utf-8")

    except requests.HTTPError as e:
        return f"HTTP Hatası: {e.response.status_code} - {e.response.reason}", 500
    except Exception as e:
        return f"Genel Hata: {str(e)}", 500

@app.route('/proxy/ts')
def proxy_ts():
    ts_url = request.args.get('url', '').strip()
    if not ts_url or 'oha.to' not in ts_url:
        return "Yalnızca oha.to segmentleri desteklenmektedir", 403

    if ts_url in TS_CACHE:
        return Response(TS_CACHE[ts_url], content_type="video/mp2t")

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    proxy_config = get_proxy_config_for_url(ts_url)
    try:
        response = requests.get(ts_url, headers=headers, proxies=proxy_config['proxies'],
                                allow_redirects=True, timeout=(10, 30), verify=proxy_config['verify'])
        response.raise_for_status()
        TS_CACHE[ts_url] = response.content
        return Response(response.content, content_type="video/mp2t")
    except Exception as e:
        return f"TS segment indirilemedi: {str(e)}", 500

@app.route('/proxy/key')
def proxy_key():
    key_url = request.args.get('url', '').strip()
    if not key_url or 'oha.to' not in key_url:
        return "Yalnızca oha.to anahtarları desteklenmektedir", 403

    if key_url in KEY_CACHE:
        return Response(KEY_CACHE[key_url], content_type="application/octet-stream")

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    proxy_config = get_proxy_config_for_url(key_url)
    try:
        response = requests.get(key_url, headers=headers, proxies=proxy_config['proxies'],
                                allow_redirects=True, timeout=(10, 20), verify=proxy_config['verify'])
        response.raise_for_status()
        KEY_CACHE[key_url] = response.content
        return Response(response.content, content_type="application/octet-stream")
    except Exception as e:
        return f"Anahtar alınamadı: {str(e)}", 500

@app.route('/')
def index():
    return "oha.to proxy servisi çalışıyor."

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=7860, debug=False)
