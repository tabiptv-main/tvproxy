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
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 30))
SERVER_BASE_URL = os.environ.get('SERVER_BASE_URL', 'https://tvproxy-xpwt.onrender.com')

M3U8_CACHE = TTLCache(maxsize=200, ttl=60)
TS_CACHE = LRUCache(maxsize=1000)
KEY_CACHE = LRUCache(maxsize=200)

def get_dynamic_headers(target_url):
    parsed = urlparse(target_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    referrer = request.referrer or domain
    parsed_ref = urlparse(referrer)
    base_ref_domain = f"{parsed_ref.scheme}://{parsed_ref.netloc}" if parsed_ref.scheme and parsed_ref.netloc else domain

    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': '*/*',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'tr,en;q=0.9',
        'DNT': '1',
        'Origin': base_ref_domain,
        'Referer': base_ref_domain + '/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site'
    }

def detect_m3u_type(content):
    return "m3u8" if "#EXTM3U" in content and "#EXTINF" in content else "m3u"

def replace_key_uri(line, headers_query):
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

    cache_key = f"{m3u_url}|{request.query_string.decode()}"
    if cache_key in M3U8_CACHE:
        return Response(M3U8_CACHE[cache_key], content_type="application/vnd.apple.mpegurl",
                        headers={'Content-Disposition': 'attachment; filename="index.m3u8"'})

    dynamic_headers = get_dynamic_headers(m3u_url)
    custom_headers = get_headers_from_request()
    headers = {**dynamic_headers, **custom_headers}

    try:
        response = requests.get(m3u_url, headers=headers, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        m3u_content = response.text
        file_type = detect_m3u_type(m3u_content)

        if file_type == "m3u":
            M3U8_CACHE[cache_key] = m3u_content
            return Response(m3u_content, content_type="application/vnd.apple.mpegurl",
                            headers={'Content-Disposition': 'attachment; filename="index.m3u8"'})

        parsed_url = urlparse(m3u_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{os.path.dirname(parsed_url.path)}/"
        headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in headers.items()])

        modified_lines = []
        for line in m3u_content.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-KEY") and 'URI="' in line:
                line = replace_key_uri(line, headers_query)
            elif line and not line.startswith("#"):
                segment_url = urljoin(base_url, line)
                line = f"{SERVER_BASE_URL}/proxy/ts?url={quote(segment_url)}&{headers_query}"
            modified_lines.append(line)

        modified_content = "\n".join(modified_lines)
        M3U8_CACHE[cache_key] = modified_content

        return Response(modified_content, content_type="application/vnd.apple.mpegurl",
                        headers={'Content-Disposition': 'attachment; filename="index.m3u8"'})

    except Exception as e:
        return f"Proxy hatası: {str(e)}", 502

@app.route('/proxy/ts')
def proxy_ts():
    ts_url = request.args.get('url', '').strip()
    if not ts_url:
        return "Hata: 'url' parametresi eksik", 400

    filename = os.path.basename(urlparse(ts_url).path)
    if ts_url in TS_CACHE:
        return Response(TS_CACHE[ts_url], content_type="video/mp2t",
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    dynamic_headers = get_dynamic_headers(ts_url)
    custom_headers = get_headers_from_request()
    headers = {**dynamic_headers, **custom_headers}

    try:
        response = requests.get(ts_url, headers=headers, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        content = response.content
        TS_CACHE[ts_url] = content
        return Response(content, content_type="video/mp2t",
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    except Exception as e:
        return f"TS segment hatası: {str(e)}", 502

@app.route('/proxy/key')
def proxy_key():
    key_url = request.args.get('url', '').strip()
    if not key_url:
        return "Hata: 'url' parametresi eksik", 400

    filename = os.path.basename(urlparse(key_url).path)
    if key_url in KEY_CACHE:
        return Response(KEY_CACHE[key_url], content_type="application/octet-stream",
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    dynamic_headers = get_dynamic_headers(key_url)
    custom_headers = get_headers_from_request()
    headers = {**dynamic_headers, **custom_headers}

    try:
        response = requests.get(key_url, headers=headers, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        key_content = response.content
        KEY_CACHE[key_url] = key_content
        return Response(key_content, content_type="application/octet-stream",
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    except Exception as e:
        return f"Anahtar indirme hatası: {str(e)}", 502

@app.route('/')
def index():
    return f"Proxy çalışıyor - {SERVER_BASE_URL}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, threaded=True)
