from flask import Flask, request, Response
import requests
from urllib.parse import urlparse, urljoin, quote, unquote, quote_plus
import re
import traceback
import json
import base64
import os
import random
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
    chosen_proxy = random.choice(PROXY_LIST)
    return {'http': chosen_proxy, 'https': chosen_proxy}

setup_proxies()

# --- Önbellek Yapılandırması ---
M3U8_CACHE = TTLCache(maxsize=200, ttl=30)
TS_CACHE = LRUCache(maxsize=1000)
KEY_CACHE = LRUCache(maxsize=200)

# --- Dinamik DaddyLive URL Alıcısı ---
DADDYLIVE_BASE_URL = None
LAST_FETCH_TIME = 0
FETCH_INTERVAL = 3600

def get_daddylive_base_url():
    global DADDYLIVE_BASE_URL, LAST_FETCH_TIME
    current_time = time.time()
    if DADDYLIVE_BASE_URL and (current_time - LAST_FETCH_TIME < FETCH_INTERVAL):
        return DADDYLIVE_BASE_URL
    try:
        print("GitHub'dan dinamik DaddyLive temel URL'si alınıyor...")
        github_url = 'https://raw.githubusercontent.com/thecrewwh/dl_url/refs/heads/main/dl.xml'
        response = requests.get(github_url, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(github_url), verify=VERIFY_SSL)
        response.raise_for_status()
        content = response.text
        match = re.search(r'src\s*=\s*"([^"]*)"', content)
        if match:
            base_url = match.group(1)
            if not base_url.endswith('/'):
                base_url += '/'
            DADDYLIVE_BASE_URL = base_url
            LAST_FETCH_TIME = current_time
            print(f"Dinamik DaddyLive temel URL'si güncellendi: {DADDYLIVE_BASE_URL}")
            return DADDYLIVE_BASE_URL
    except requests.RequestException as e:
        print(f"Dinamik DaddyLive URL'si alınırken hata: {e}. Yedek kullanılıyor.")
    DADDYLIVE_BASE_URL = "https://daddylive.sx/"
    print(f"Yedek DaddyLive URL'si kullanılıyor: {DADDYLIVE_BASE_URL}")
    return DADDYLIVE_BASE_URL

get_daddylive_base_url()

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

def extract_channel_id(url):
    match_premium = re.search(r'/premium(\d+)/mono\.m3u8$', url)
    if match_premium:
        return match_premium.group(1)
    match_player = re.search(r'/(?:watch|stream|cast|player)/stream-(\d+)\.php', url)
    if match_player:
        return match_player.group(1)
    match_oha = re.search(r'oha\.to/play/(\d+)/index\.m3u8$', url)
    if match_oha:
        return match_oha.group(1)
    return None

def process_daddylive_url(url):
    daddy_base_url = get_daddylive_base_url()
    daddy_domain = urlparse(daddy_base_url).netloc
    match_premium = re.search(r'/premium(\d+)/mono\.m3u8$', url)
    if match_premium:
        channel_id = match_premium.group(1)
        new_url = f"{daddy_base_url}watch/stream-{channel_id}.php"
        print(f"URL premium'dan işlendi: {url} -> {new_url}")
        return new_url
    match_oha = re.search(r'oha\.to/play/(\d+)/index\.m3u8$', url)
    if match_oha:
        channel_id = match_oha.group(1)
        new_url = f"{daddy_base_url}watch/stream-{channel_id}.php"
        print(f"URL oha.to'dan işlendi: {url} -> {new_url}")
        return new_url
    if daddy_domain in url and any(p in url for p in ['/watch/', '/stream/', '/cast/', '/player/']):
        return url
    if url.isdigit():
        return f"{daddy_base_url}watch/stream-{url}.php"
    return url

def resolve_m3u8_link(url, headers=None):
    if not url:
        print("Hata: URL sağlanmadı.")
        return {"resolved_url": None, "headers": {}}
    current_headers = headers.copy() if headers else {}
    clean_url = url
    extracted_headers = {}
    if '&h_' in url or '%26h_' in url:
        print("URL'de başlık parametreleri algılandı - Çıkarılıyor...")
        temp_url = url.replace('%26', '&') if 'vavoo.to' in url.lower() and '%26' in url else url
        if '%26h_' in temp_url:
            temp_url = unquote(unquote(temp_url))
        url_parts = temp_url.split('&h_', 1)
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
                    print(f"Başlık çıkarılırken hata {param}: {e}")
    print(f"URL çözümleniyor (DaddyLive): {clean_url}")
    daddy_base_url = get_daddylive_base_url()
    daddy_origin = urlparse(daddy_base_url).scheme + "://" + urlparse(daddy_base_url).netloc
    daddylive_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        'Referer': daddy_base_url,
        'Origin': daddy_origin
    }
    final_headers_for_resolving = {**current_headers, **extracted_headers, **daddylive_headers}
    try:
        print("Dinamik temel URL alınıyor...")
        github_url = 'https://raw.githubusercontent.com/thecrewwh/dl_url/refs/heads/main/dl.xml'
        main_url_req = requests.get(github_url, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(github_url), verify=VERIFY_SSL)
        main_url_req.raise_for_status()
        main_url = main_url_req.text
        baseurl = re.findall('src = "([^"]*)', main_url)[0]
        print(f"Temel URL alındı: {baseurl}")
        channel_id = extract_channel_id(clean_url)
        if not channel_id:
            print(f"Kanal ID'si çıkarılamadı: {clean_url}")
            return {"resolved_url": clean_url, "headers": final_headers_for_resolving}
        print(f"Kanal ID'si çıkarıldı: {channel_id}")
        stream_url = f"{baseurl}stream/stream-{channel_id}.php"
        print(f"Yayın URL'si oluşturuldu: {stream_url}")
        final_headers_for_resolving['Referer'] = baseurl + '/'
        final_headers_for_resolving['Origin'] = baseurl
        print(f"Adım 1: {stream_url} adresine istek yapılıyor")
        response = requests.get(stream_url, headers=final_headers_for_resolving, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(stream_url), verify=VERIFY_SSL)
        response.raise_for_status()
        iframes = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>\s*<button[^>]*>\s*Player\s*2\s*<\/button>', response.text)
        if not iframes:
            print("Player 2 bağlantısı bulunamadı")
            return {"resolved_url": clean_url, "headers": final_headers_for_resolving}
        print(f"Adım 2: Player 2 bağlantısı bulundu: {iframes[0]}")
        url2 = iframes[0]
        url2 = baseurl + url2
        url2 = url2.replace('//cast', '/cast')
        final_headers_for_resolving['Referer'] = url2
        final_headers_for_resolving['Origin'] = url2
        print(f"Adım 3: Player 2 isteği: {url2}")
        response = requests.get(url2, headers=final_headers_for_resolving, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(url2), verify=VERIFY_SSL)
        response.raise_for_status()
        iframes = re.findall(r'iframe src="([^"]*)', response.text)
        if not iframes:
            print("Player 2 sayfasında iframe bulunamadı")
            return {"resolved_url": clean_url, "headers": final_headers_for_resolving}
        iframe_url = iframes[0]
        print(f"Adım 4: Iframe bulundu: {iframe_url}")
        print(f"Adım 5: Iframe isteği: {iframe_url}")
        response = requests.get(iframe_url, headers=final_headers_for_resolving, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(iframe_url), verify=VERIFY_SSL)
        response.raise_for_status()
        iframe_content = response.text
        try:
            channel_key = re.findall(r'(?s) channelKey = \"([^"]*)', iframe_content)[0]
            auth_ts_b64 = re.findall(r'(?s)c = atob\("([^"]*)', iframe_content)[0]
            auth_ts = base64.b64decode(auth_ts_b64).decode('utf-8')
            auth_rnd_b64 = re.findall(r'(?s)d = atob\("([^"]*)', iframe_content)[0]
            auth_rnd = base64.b64decode(auth_rnd_b64).decode('utf-8')
            auth_sig_b64 = re.findall(r'(?s)e = atob\("([^"]*)', iframe_content)[0]
            auth_sig = base64.b64decode(auth_sig_b64).decode('utf-8')
            auth_sig = quote_plus(auth_sig)
            auth_host_b64 = re.findall(r'(?s)a = atob\("([^"]*)', iframe_content)[0]
            auth_host = base64.b64decode(auth_host_b64).decode('utf-8')
            auth_php_b64 = re.findall(r'(?s)b = atob\("([^"]*)', iframe_content)[0]
            auth_php = base64.b64decode(auth_php_b64).decode('utf-8')
            print(f"Parametreler çıkarıldı: channel_key={channel_key}")
        except (IndexError, Exception) as e:
            print(f"Parametre çıkarma hatası: {e}")
            return {"resolved_url": clean_url, "headers": final_headers_for_resolving}
        auth_url = f'{auth_host}{auth_php}?channel_id={channel_key}&ts={auth_ts}&rnd={auth_rnd}&sig={auth_sig}'
        print(f"Adım 6: Kimlik doğrulama: {auth_url}")
        auth_response = requests.get(auth_url, headers=final_headers_for_resolving, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(auth_url), verify=VERIFY_SSL)
        auth_response.raise_for_status()
        host = re.findall('(?s)m3u8 =.*?:.*?:.*?".*?".*?"([^"]*)', iframe_content)[0]
        server_lookup = re.findall(r'n fetchWithRetry\(\s*\'([^\']*)', iframe_content)[0]
        server_lookup_url = f"https://{urlparse(iframe_url).netloc}{server_lookup}{channel_key}"
        print(f"Adım 7: Sunucu araması: {server_lookup_url}")
        lookup_response = requests.get(server_lookup_url, headers=final_headers_for_resolving, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(server_lookup_url), verify=VERIFY_SSL)
        lookup_response.raise_for_status()
        server_data = lookup_response.json()
        server_key = server_data['server_key']
        print(f"Sunucu anahtarı alındı: {server_key}")
        referer_raw = f'https://{urlparse(iframe_url).netloc}'
        clean_m3u8_url = f'https://{server_key}{host}{server_key}/{channel_key}/mono.m3u8'
        print(f"Temiz M3U8 URL'si oluşturuldu: {clean_m3u8_url}")
        final_headers_for_fetch = {
            'User-Agent': final_headers_for_resolving.get('User-Agent'),
            'Referer': referer_raw,
            'Origin': referer_raw
        }
        return {
            "resolved_url": clean_m3u8_url,
            "headers": final_headers_for_fetch
        }
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ProxyError) as e:
        print(f"ZAMAN AŞIMI VEYA PROXY HATASI: {e}")
        print("Bu genellikle yavaş, çalışmayan veya engellenmiş bir SOCKS5 proxy'sinden kaynaklanır.")
        print("ÖNERİ: Proxy'lerin aktif olduğunu kontrol edin. REQUEST_TIMEOUT'u artırın (ör. 30 saniye).")
        return {"resolved_url": clean_url, "headers": final_headers_for_resolving}
    except Exception as e:
        print(f"Çözümleme sırasında hata: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return {"resolved_url": clean_url, "headers": final_headers_for_resolving}

@app.route('/proxy/m3u')
def proxy_m3u():
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Hata: 'url' parametresi eksik", 400
    cache_key_headers = "&".join(sorted([f"{k}={v}" for k, v in request.args.items() if k.lower().startswith("h_")]))
    cache_key = f"{m3u_url}|{cache_key_headers}"
    if cache_key in M3U8_CACHE:
        print(f"Önbellek HIT: M3U8 {m3u_url}")
        return Response(M3U8_CACHE[cache_key], content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'})
    print(f"Önbellek MISS: M3U8 {m3u_url}")
    daddy_base_url = get_daddylive_base_url()
    daddy_origin = urlparse(daddy_base_url).scheme + "://" + urlparse(daddy_base_url).netloc
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Referer": daddy_base_url,
        "Origin": daddy_origin
    }
    request_headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }
    headers = {**default_headers, **request_headers}
    processed_url = process_daddylive_url(m3u_url)
    try:
        print(f"resolve_m3u8_link çağrılıyor: {processed_url}")
        result = resolve_m3u8_link(processed_url, headers)
        if not result["resolved_url"]:
            return "Hata: URL geçerli bir M3U8'e çözülemedi.", 500
        resolved_url = result["resolved_url"]
        current_headers_for_proxy = result["headers"]
        print(f"Çözümleme tamamlandı. Son M3U8 URL'si: {resolved_url}")
        print(f"Fetch için kullanılan başlıklar: {current_headers_for_proxy}")
        if not resolved_url.endswith('.m3u8'):
            print(f"Çözülen URL bir M3U8 değil: {resolved_url}")
            return "Hata: Kanal için geçerli bir M3U8 alınamadı", 500
        print(f"Temiz URL'den M3U8 içeriği alınıyor: {resolved_url}")
        m3u_response = requests.get(resolved_url, headers=current_headers_for_proxy, allow_redirects=True, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(resolved_url), verify=VERIFY_SSL)
        m3u_response.raise_for_status()
        m3u_content = m3u_response.text
        final_url = m3u_response.url
        file_type = detect_m3u_type(m3u_content)
        if file_type == "m3u":
            return Response(m3u_content, content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'})
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
                line = f"{SERVER_BASE_URL}/proxy/ts?url={quote(segment_url)}&{headers_query}"
            modified_m3u8.append(line)
        modified_m3u8_content = "\n".join(modified_m3u8)
        M3U8_CACHE[cache_key] = modified_m3u8_content
        return Response(modified_m3u8_content, content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'})
    except requests.RequestException as e:
        print(f"İndirme veya çözümleme sırasında hata: {str(e)}")
        return f"M3U/M3U8 dosyası indirilirken veya çözümlenirken hata: {str(e)}", 500
    except Exception as e:
        print(f"proxy_m3u fonksiyonunda genel hata: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return f"Elbette hata: {str(e)}", 500

@app.route('/proxy/resolve')
def proxy_resolve():
    url = request.args.get('url', '').strip()
    if not url:
        return "Hata: 'url' parametresi eksik", 400
    daddy_base_url = get_daddylive_base_url()
    daddy_origin = urlparse(daddy_base_url).scheme + "://" + urlparse(daddy_base_url).netloc
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Referer": daddy_base_url,
        "Origin": daddy_origin
    }
    request_headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }
    headers = {**default_headers, **request_headers}
    try:
        processed_url = process_daddylive_url(url)
        result = resolve_m3u8_link(processed_url, headers)
        if not result["resolved_url"]:
            return "Hata: URL çözülemedi", 500
        headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in result["headers"].items()])
        return Response(
            f"#EXTM3U\n"
            f"#EXTINF:-1,Çözülen Kanal\n"
            f"{SERVER_BASE_URL}/proxy/m3u?url={quote(result['resolved_url'])}&{headers_query}",
            content_type="application/vnd.apple.mpegurl",
            headers={'Content-Disposition': 'attachment; filename="playlist.m3u8"'}
        )
    except Exception as e:
        print(f"URL çözümleme hatası: {str(e)}")
        return f"URL çözülürken hata: {str(e)}", 500

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
    try:
        response = requests.get(ts_url, headers=headers, stream=True, allow_redirects=True, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(ts_url), verify=VERIFY_SSL)
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

@app.route('/proxy')
def proxy():
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Hata: 'url' parametresi eksik", 400
    try:
        proxy_for_request = get_proxy_for_url(m3u_url)
        response = requests.get(m3u_url, timeout=REQUEST_TIMEOUT, proxies=proxy_for_request, verify=VERIFY_SSL)
        response.raise_for_status()
        m3u_content = response.text
        modified_lines = []
        current_stream_headers_params = []
        for line in m3u_content.splitlines():
            line = line.strip()
            if line.startswith('#EXTHTTP:'):
                try:
                    json_str = line.split(':', 1)[1].strip()
                    headers_dict = json.loads(json_str)
                    for key, value in headers_dict.items():
                        encoded_key = quote(quote(key))
                        encoded_value = quote(quote(str(value)))
                        current_stream_headers_params.append(f"h_{encoded_key}={encoded_value}")
                except Exception as e:
                    print(f"EXTHTTP ayrıştırma hatası '{line}': {e}")
                modified_lines.append(line)
            elif line.startswith('#EXTVLCOPT:'):
                try:
                    options_str = line.split(':', 1)[1].strip()
                    for opt_pair in options_str.split(','):
                        opt_pair = opt_pair.strip()
                        if '=' in opt_pair:
                            key, value = opt_pair.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"')
                            header_key = None
                            if key.lower() == 'http-user-agent':
                                header_key = 'User-Agent'
                            elif key.lower() == 'http-referer':
                                header_key = 'Referer'
                            elif key.lower() == 'http-cookie':
                                header_key = 'Cookie'
                            elif key.lower() == 'http-header':
                                full_header_value = value
                                if ':' in full_header_value:
                                    header_name, header_val = full_header_value.split(':', 1)
                                    header_key = header_name.strip()
                                    value = header_val.strip()
                                else:
                                    print(f"UYARI: Hatalı http-header: {opt_pair}")
                                    continue
                            if header_key:
                                encoded_key = quote(quote(header_key))
                                encoded_value = quote(quote(value))
                                current_stream_headers_params.append(f"h_{encoded_key}={encoded_value}")
                except Exception as e:
                    print(f"EXTVLCOPT ayrıştırma hatası '{line}': {e}")
                modified_lines.append(line)
            elif line and not line.startswith('#'):
                if 'pluto.tv' in line.lower():
                    modified_lines.append(line)
                else:
                    encoded_line = quote(line, safe='')
                    headers_query_string = "%26" + "%26".join(current_stream_headers_params) if current_stream_headers_params else ""
                    modified_line = f"{SERVER_BASE_URL}/proxy/m3u?url={encoded_line}{headers_query_string}"
                    modified_lines.append(modified_line)
                current_stream_headers_params = []
            else:
                modified_lines.append(line)
        modified_content = '\n'.join(modified_lines)
        parsed_m3u_url = urlparse(m3u_url)
        original_filename = os.path.basename(parsed_m3u_url.path)
        if not original_filename.endswith('.m3u8'):
            original_filename = original_filename.rsplit('.', 1)[0] + '.m3u8'
        return Response(modified_content, content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': f'attachment; filename="{original_filename}"'})
    except requests.RequestException as e:
        proxy_used = proxy_for_request['http'] if proxy_for_request else "Yok"
        print(f"Hata: '{m3u_url}' indirilemedi, kullanılan proxy: {proxy_used}")
        return f"M3U listesi indirilirken hata: {str(e)}", 500
    except Exception as e:
        print(f"Genel hata: {str(e)}")
        return f"Genel hata: {str(e)}", 500

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
    try:
        response = requests.get(key_url, headers=headers,

System: allow_redirects=True, timeout=REQUEST_TIMEOUT, proxies=get_proxy_for_url(key_url), verify=VERIFY_SSL)
        response.raise_for_status()
        key_content = response.content
        KEY_CACHE[key_url] = key_content
        return Response(key_content, content_type="application/octet-stream")
    except requests.RequestException as e:
        print(f"AES-128 anahtarı indirilirken hata: {key_url} - {str(e)}")
        return f"AES-128 anahtarı indirilirken hata: {str(e)}", 500

@app.route('/')
def index():
    base_url = get_daddylive_base_url()
    return f"Proxy ÇALIŞIYOR - Temel URL: {base_url}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 7860))
    print(f"Proxy ÇALIŞIYOR - Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
