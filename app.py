from flask import Flask, request, Response
import requests
from urllib.parse import urlparse, urljoin, quote, unquote
import re
import traceback
import time
from threading import Lock
import gc
from collections import OrderedDict
import threading

app = Flask(__name__)

# --- CONFIGURAZIONE CACHE OTTIMIZZATA PER RIDURRE FREEZE ---
CACHE_TTL = 45  # Aumentato da 30 a 45 secondi
MAX_CACHE_SIZE = 100  # Aumentato da 50 a 100 elementi
MAX_TS_SIZE = 8 * 1024 * 1024  # Aumentato a 8MB per segmento
MAX_TOTAL_CACHE_SIZE = 200 * 1024 * 1024  # Aumentato a 200MB totali

# Cache LRU (Least Recently Used) ottimizzate
class LRUCache:
    def __init__(self, max_size, max_item_size=None):
        self.max_size = max_size
        self.max_item_size = max_item_size
        self.cache = OrderedDict()
        self.lock = Lock()
        self.current_size = 0
    
    def get(self, key):
        with self.lock:
            if key in self.cache:
                timestamp, value = self.cache[key]
                if time.time() - timestamp < CACHE_TTL:
                    self.cache.move_to_end(key)
                    return value
                else:
                    self._remove_item(key)
            return None
    
    def put(self, key, value):
        with self.lock:
            value_size = len(value) if isinstance(value, (bytes, str)) else 0
            if self.max_item_size and value_size > self.max_item_size:
                return
            
            if key in self.cache:
                self._remove_item(key)
            
            while len(self.cache) >= self.max_size or self.current_size + value_size > MAX_TOTAL_CACHE_SIZE:
                if not self.cache:
                    break
                self._remove_oldest()
            
            self.cache[key] = (time.time(), value)
            self.current_size += value_size
    
    def _remove_item(self, key):
        if key in self.cache:
            _, value = self.cache[key]
            value_size = len(value) if isinstance(value, (bytes, str)) else 0
            self.current_size -= value_size
            del self.cache[key]
    
    def _remove_oldest(self):
        if self.cache:
            oldest_key = next(iter(self.cache))
            self._remove_item(oldest_key)
    
    def cleanup_expired(self):
        with self.lock:
            current_time = time.time()
            expired_keys = [
                key for key, (timestamp, _) in self.cache.items()
                if current_time - timestamp >= CACHE_TTL
            ]
            for key in expired_keys:
                self._remove_item(key)
    
    def clear(self):
        with self.lock:
            self.cache.clear()
            self.current_size = 0

# Inizializza cache ottimizzate
ts_cache = LRUCache(MAX_CACHE_SIZE, MAX_TS_SIZE)
key_cache = LRUCache(MAX_CACHE_SIZE // 2)

# Timer per pulizia periodica
last_cleanup = time.time()
CLEANUP_INTERVAL = 60

def periodic_cleanup():
    global last_cleanup
    current_time = time.time()
    if current_time - last_cleanup > CLEANUP_INTERVAL:
        ts_cache.cleanup_expired()
        key_cache.cleanup_expired()
        gc.collect()
        last_cleanup = current_time

def download_with_progressive_timeout(url, headers, max_retries=3):
    """Download con timeout progressivi e retry intelligente per ridurre freeze"""
    timeouts = [(3, 8), (5, 12), (8, 15)]  # (connect, read) timeout progressivi
    
    for attempt in range(max_retries):
        try:
            timeout = timeouts[min(attempt, len(timeouts)-1)]
            response = requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
            response.raise_for_status()
            return response
        except requests.Timeout:
            if attempt < max_retries - 1:
                time.sleep(0.3 * (attempt + 1))
                continue
            raise
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise e

def extract_segment_number(ts_url):
    """Estrae il numero del segmento dall'URL"""
    match = re.search(r'(\d+)\.ts', ts_url)
    return int(match.group(1)) if match else None

def prefetch_next_segment(current_ts_url, headers):
    """Pre-carica il segmento successivo in background per ridurre freeze"""
    try:
        segment_num = extract_segment_number(current_ts_url)
        if segment_num is not None:
            next_segment_url = current_ts_url.replace(f'{segment_num}.ts', f'{segment_num + 1}.ts')
            
            if ts_cache.get(next_segment_url):
                return
            
            def background_fetch():
                try:
                    response = requests.get(next_segment_url, headers=headers, timeout=(3, 8), stream=True)
                    if response.status_code == 200:
                        data = b''.join(response.iter_content(chunk_size=32768))
                        if len(data) <= MAX_TS_SIZE:
                            ts_cache.put(next_segment_url, data)
                except:
                    pass
            
            threading.Thread(target=background_fetch, daemon=True).start()
    except:
        pass

def detect_m3u_type(content):
    if "#EXTM3U" in content and "#EXTINF" in content:
        return "m3u8"
    return "m3u"

def replace_key_uri(line, headers_query):
    match = re.search(r'URI="([^"]+)"', line)
    if match:
        key_url = match.group(1)
        proxied_key_url = f"/proxy/key?url={quote(key_url)}&{headers_query}"
        return line.replace(key_url, proxied_key_url)
    return line

def resolve_m3u8_link(url, headers=None):
    if not url:
        print("Errore: URL non fornito.")
        return {"resolved_url": None, "headers": {}}
    
    print(f"Tentativo di risoluzione URL: {url}")
    current_headers = headers if headers else {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0+Safari/537.36'}

    initial_response_text = None
    final_url_after_redirects = None

    try:
        with requests.Session() as session:
            session.timeout = 8  # Aumentato da 5 a 8 secondi
            
            print(f"Passo 1: Richiesta a {url}")
            response = session.get(url, headers=current_headers, allow_redirects=True, timeout=8)
            response.raise_for_status()
            initial_response_text = response.text
            final_url_after_redirects = response.url
            print(f"Passo 1 completato. URL finale dopo redirect: {final_url_after_redirects}")

            print("Tentativo con logica iframe...")
            try:
                iframes = re.findall(r'iframe src="([^"]+)', initial_response_text)
                if not iframes:
                    raise ValueError("Nessun iframe src trovato.")

                url2 = iframes[0]
                print(f"Passo 2 (Iframe): Trovato iframe URL: {url2}")

                referer_raw = urlparse(url2).scheme + "://" + urlparse(url2).netloc + "/"
                origin_raw = urlparse(url2).scheme + "://" + urlparse(url2).netloc
                current_headers['Referer'] = referer_raw
                current_headers['Origin'] = origin_raw
                print(f"Passo 3 (Iframe): Richiesta a {url2}")
                response = session.get(url2, headers=current_headers, timeout=8)
                response.raise_for_status()
                iframe_response_text = response.text
                print("Passo 3 (Iframe) completato.")

                channel_key_match = re.search(r'(?s) channelKey = \"([^"]*)', iframe_response_text)
                auth_ts_match = re.search(r'(?s) authTs\s*= \"([^"]*)', iframe_response_text)
                auth_rnd_match = re.search(r'(?s) authRnd\s*= \"([^"]*)', iframe_response_text)
                auth_sig_match = re.search(r'(?s) authSig\s*= \"([^"]*)', iframe_response_text)
                auth_host_match = re.search(r'\}\s*fetchWithRetry\(\s*\'([^\']*)', iframe_response_text)
                server_lookup_match = re.search(r'n fetchWithRetry\(\s*\'([^\']*)', iframe_response_text)

                if not all([channel_key_match, auth_ts_match, auth_rnd_match, auth_sig_match, auth_host_match, server_lookup_match]):
                    raise ValueError("Impossibile estrarre tutti i parametri dinamici dall'iframe response.")

                channel_key = channel_key_match.group(1)
                auth_ts = auth_ts_match.group(1)
                auth_rnd = auth_rnd_match.group(1)
                auth_sig = quote(auth_sig_match.group(1))
                auth_host = auth_host_match.group(1)
                server_lookup = server_lookup_match.group(1)

                print("Passo 4 (Iframe): Parametri dinamici estratti.")

                auth_url = f'{auth_host}{channel_key}&ts={auth_ts}&rnd={auth_rnd}&sig={auth_sig}'
                print(f"Passo 5 (Iframe): Richiesta di autenticazione a {auth_url}")
                auth_response = session.get(auth_url, headers=current_headers, timeout=8)
                auth_response.raise_for_status()
                print("Passo 5 (Iframe) completato.")

                server_lookup_url = f"https://{urlparse(url2).netloc}{server_lookup}{channel_key}"
                print(f"Passo 6 (Iframe): Richiesta server lookup a {server_lookup_url}")
                server_lookup_response = session.get(server_lookup_url, headers=current_headers, timeout=8)
                server_lookup_response.raise_for_status()
                server_lookup_data = server_lookup_response.json()
                print("Passo 6 (Iframe) completato.")

                server_key = server_lookup_data.get('server_key')
                if not server_key:
                    raise ValueError("'server_key' non trovato nella risposta di server lookup.")
                print(f"Passo 7 (Iframe): Estratto server_key: {server_key}")

                host_match = re.search('(?s)m3u8 =.*?:.*?:.*?".*?".*?"([^"]*)', iframe_response_text)
                if not host_match:
                    raise ValueError("Impossibile trovare l'host finale per l'm3u8.")
                host = host_match.group(1)
                print(f"Passo 8 (Iframe): Trovato host finale per m3u8: {host}")

                final_stream_url = (
                    f'https://{server_key}{host}{server_key}/{channel_key}/mono.m3u8'
                )

                stream_headers = {
                    'User-Agent': current_headers.get('User-Agent', ''),
                    'Referer': referer_raw,
                    'Origin': origin_raw,
                    'Accept': '*/*',
                    'Accept-Encoding': 'identity',
                    'Connection': 'keep-alive',
                    'Cache-Control': 'no-cache'
                }
                
                return {
                    "resolved_url": final_stream_url,
                    "headers": stream_headers
                }

            except (ValueError, requests.exceptions.RequestException) as e:
                print(f"Logica iframe fallita: {e}")
                print("Tentativo fallback: verifica se l'URL iniziale era un M3U8 diretto...")

                if initial_response_text and initial_response_text.strip().startswith('#EXTM3U'):
                    print("Fallback riuscito: Trovato file M3U8 diretto.")
                    return {
                        "resolved_url": final_url_after_redirects,
                        "headers": current_headers
                    }
                else:
                    print("Fallback fallito: La risposta iniziale non era un M3U8 diretto.")
                    return {
                        "resolved_url": url,
                        "headers": current_headers
                    }

    except requests.exceptions.RequestException as e:
        print(f"Errore durante la richiesta HTTP iniziale: {e}")
        return {"resolved_url": url, "headers": current_headers}
    except Exception as e:
        print(f"Errore generico durante la risoluzione: {e}")
        return {"resolved_url": url, "headers": current_headers}

@app.route('/proxy/m3u')
def proxy_m3u():
    periodic_cleanup()
    
    m3u_url = request.args.get('url', '').strip()
    if not m3u_url:
        return "Errore: Parametro 'url' mancante", 400

    default_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/33.0 Mobile/15E148 Safari/605.1.15",
        "Referer": "https://vavoo.to/",
        "Origin": "https://vavoo.to",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache"
    }

    request_headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }
    headers = {**default_headers, **request_headers}

    processed_url = m3u_url
    match_premium_m3u8 = re.search(r'/premium(\d+)/mono\.m3u8$', m3u_url)

    if match_premium_m3u8:
        channel_number = match_premium_m3u8.group(1)
        transformed_url = f"https://daddylive.dad/embed/stream-{channel_number}.php"
        print(f"URL {m3u_url} corrisponde al pattern premium. Trasformato in: {transformed_url}")
        processed_url = transformed_url
    else:
        print(f"URL {m3u_url} non corrisponde al pattern premium/mono.m3u8. Utilizzo URL originale.")

    try:
        print(f"Chiamata a resolve_m3u8_link per URL processato: {processed_url}")
        result = resolve_m3u8_link(processed_url, headers)

        if not result["resolved_url"]:
            return "Errore: Impossibile risolvere l'URL in un M3U8 valido.", 500

        resolved_url = result["resolved_url"]
        current_headers_for_proxy = result["headers"]

        print(f"Risoluzione completata. URL M3U8 finale: {resolved_url}")

        print(f"Fetching M3U8 content from resolved URL: {resolved_url}")
        m3u_response = requests.get(resolved_url, headers=current_headers_for_proxy, allow_redirects=True, timeout=8)
        m3u_response.raise_for_status()
        m3u_content = m3u_response.text
        final_url = m3u_response.url

        file_type = detect_m3u_type(m3u_content)

        if file_type == "m3u":
            return Response(m3u_content, content_type="application/vnd.apple.mpegurl")

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
        return Response(modified_m3u8_content, content_type="application/vnd.apple.mpegurl")

    except requests.RequestException as e:
        print(f"Errore durante il download o la risoluzione del file: {str(e)}")
        return f"Errore durante il download o la risoluzione del file M3U/M3U8: {str(e)}", 500
    except Exception as e:
        print(f"Errore generico nella funzione proxy_m3u: {str(e)}")
        return f"Errore generico durante l'elaborazione: {str(e)}", 500

@app.route('/proxy/resolve')
def proxy_resolve():
    periodic_cleanup()
    
    url = request.args.get('url', '').strip()
    if not url:
        return "Errore: Parametro 'url' mancante", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    try:
        result = resolve_m3u8_link(url, headers)
        
        if not result["resolved_url"]:
            return "Errore: Impossibile risolvere l'URL", 500
            
        headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in result["headers"].items()])
        
        return Response(
            f"#EXTM3U\n"
            f"#EXTINF:-1,Canale Risolto\n"
            f"/proxy/m3u?url={quote(result['resolved_url'])}&{headers_query}",
            content_type="application/vnd.apple.mpegurl"
        )
        
    except Exception as e:
        return f"Errore durante la risoluzione dell'URL: {str(e)}", 500

@app.route('/proxy/ts')
def proxy_ts():
    """Proxy TS ottimizzato per ridurre freeze"""
    periodic_cleanup()
    
    ts_url = request.args.get('url', '').strip()
    if not ts_url:
        return "Errore: Parametro 'url' mancante", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    # Controlla cache prima
    cached_data = ts_cache.get(ts_url)
    if cached_data:
        # Avvia pre-fetching del segmento successivo
        prefetch_next_segment(ts_url, headers)
        return Response(cached_data, content_type="video/mp2t")

    try:
        # Usa download con retry progressivo
        response = download_with_progressive_timeout(ts_url, headers)
        
        # Buffer più grande per ridurre operazioni I/O
        data = b''
        chunk_size = 32768  # 32KB invece di 8KB
        
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:  # Filtra chunk vuoti
                data += chunk
                if len(data) > MAX_TS_SIZE:
                    break
        
        # Cache sempre se possibile
        if len(data) <= MAX_TS_SIZE and data:
            ts_cache.put(ts_url, data)
        
        # Avvia pre-fetching del segmento successivo
        prefetch_next_segment(ts_url, headers)
        
        return Response(data, content_type="video/mp2t")
    
    except requests.RequestException as e:
        # Fallback: prova a servire dalla cache anche se scaduta
        all_cached = [(k, v) for k, v in ts_cache.cache.items() if ts_url in k]
        if all_cached:
            _, (_, cached_data) = all_cached[0]
            return Response(cached_data, content_type="video/mp2t")
        
        return f"Segmento temporaneamente non disponibile: {str(e)}", 503

@app.route('/proxy/key')
def proxy_key():
    key_url = request.args.get('url', '').strip()
    if not key_url:
        return "Errore: Parametro 'url' mancante per la chiave", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    cached_key = key_cache.get(key_url)
    if cached_key:
        return Response(cached_key, content_type="application/octet-stream")

    try:
        response = download_with_progressive_timeout(key_url, headers)
        key_cache.put(key_url, response.content)
        return Response(response.content, content_type="application/octet-stream")
    
    except requests.RequestException as e:
        return f"Errore durante il download della chiave AES-128: {str(e)}", 500

@app.route('/cache/stats')
def cache_stats():
    return {
        "ts_cache_size": len(ts_cache.cache),
        "ts_cache_bytes": ts_cache.current_size,
        "key_cache_size": len(key_cache.cache),
        "key_cache_bytes": key_cache.current_size,
        "total_bytes": ts_cache.current_size + key_cache.current_size,
        "max_total_bytes": MAX_TOTAL_CACHE_SIZE,
        "cache_ttl": CACHE_TTL,
        "max_ts_size": MAX_TS_SIZE,
        "active_threads": threading.active_count()
    }

@app.route('/cache/clear')
def clear_cache():
    ts_cache.clear()
    key_cache.clear()
    gc.collect()
    return "Cache svuotata con successo"

@app.route('/proxy/health')
def health_check():
    """Endpoint per monitorare la salute del proxy"""
    return {
        "status": "ok",
        "cache_hit_rate": len(ts_cache.cache) / max(1, len(ts_cache.cache) + 1),
        "memory_usage": ts_cache.current_size,
        "active_connections": threading.active_count(),
        "cache_ttl": CACHE_TTL,
        "max_cache_size": MAX_CACHE_SIZE
    }

@app.route('/')
def index():
    return "Proxy started with anti-freeze optimizations!"

if __name__ == '__main__':
    print("Proxy started with anti-freeze optimizations!")
    app.run(host="0.0.0.0", port=7860, debug=False)
