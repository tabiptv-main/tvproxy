import os
from flask import Flask, request, Response
import requests
from urllib.parse import urlparse, urljoin, quote, unquote
import re
import json

app = Flask(__name__)

class DLHDExtractor:
    """Versione semplificata del DLHD extractor per Flask"""
    
    def __init__(self):
        self.base_headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    def extract_stream_url(self, channel_url, **kwargs):
        """Estrae l'URL dello stream DLHD"""
        try:
            player_url = kwargs.get("player_url")
            stream_url = kwargs.get("stream_url")
            
            if not player_url:
                player_url = self._extract_player_url_from_channel(channel_url)
            
            if not player_url:
                raise Exception("Impossibile estrarre l'URL del player")
            
            # Prova prima con vecloud
            try:
                return self._handle_vecloud(player_url, channel_url)
            except:
                pass
            
            # Fallback al metodo standard
            return self._handle_standard_auth(player_url, channel_url, stream_url)
            
        except Exception as e:
            raise Exception(f"Estrazione fallita: {str(e)}")
    
    def _extract_player_url_from_channel(self, channel_url):
        """Estrae l'URL del player dalla pagina del canale"""
        try:
            player_origin = self._get_origin(channel_url)
            headers = {
                "referer": player_origin + "/",
                "origin": player_origin,
                "user-agent": self.base_headers["user-agent"]
            }
            
            response = requests.get(channel_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            return self._extract_player_url(response.text)
        except:
            return None
    
    def _extract_player_url(self, html_content):
        """Estrae l'URL del player iframe dall'HTML"""
        try:
            iframe_match = re.search(
                r'<iframe[^>]*src=["\']([^"\']+)["\'][^>]*allowfullscreen',
                html_content,
                re.IGNORECASE
            )
            
            if not iframe_match:
                iframe_match = re.search(
                    r'<iframe[^>]*src=["\']([^"\']*(premiumtv|daddylivehd|vecloud)[^"\']*)["\']',
                    html_content,
                    re.IGNORECASE
                )
            
            if iframe_match:
                return iframe_match.group(1).strip()
            
            return None
        except:
            return None
    
    def _handle_vecloud(self, player_url, channel_referer):
        """Gestisce gli URL vecloud"""
        stream_id_match = re.search(r'/stream/([a-zA-Z0-9-]+)', player_url)
        if not stream_id_match:
            raise Exception("Impossibile estrarre l'ID dello stream da vecloud")
        
        stream_id = stream_id_match.group(1)
        
        response = requests.get(player_url, headers={
            "referer": channel_referer,
            "user-agent": self.base_headers["user-agent"]
        }, timeout=10)
        
        player_url = response.url
        player_parsed = urlparse(player_url)
        player_origin = f"{player_parsed.scheme}://{player_parsed.netloc}"
        
        api_url = f"{player_origin}/api/source/{stream_id}?type=live"
        
        api_headers = {
            "referer": player_url,
            "origin": player_origin,
            "user-agent": self.base_headers["user-agent"],
            "content-type": "application/json"
        }
        
        api_data = {
            "r": channel_referer,
            "d": player_parsed.netloc
        }
        
        api_response = requests.post(api_url, headers=api_headers, json=api_data, timeout=10)
        api_result = api_response.json()
        
        if not api_result.get("success"):
            raise Exception("Richiesta API vecloud fallita")
        
        stream_url = api_result.get("player", {}).get("source_file")
        if not stream_url:
            raise Exception("URL dello stream non trovato nella risposta vecloud")
        
        return {
            "stream_url": stream_url,
            "headers": {
                "referer": player_origin + "/",
                "origin": player_origin,
                "user-agent": self.base_headers["user-agent"]
            }
        }
    
    def _handle_standard_auth(self, player_url, channel_url, stream_url=None):
        """Gestisce l'autenticazione standard DLHD"""
        player_origin = self._get_origin(player_url)
        
        headers = {
            "referer": player_origin + "/",
            "origin": player_origin,
            "user-agent": self.base_headers["user-agent"]
        }
        
        response = requests.get(player_url, headers=headers, timeout=10)
        player_content = response.text
        
        auth_data = self._extract_auth_data(player_content)
        if not auth_data:
            raise Exception("Impossibile estrarre i dati di autenticazione")
        
        auth_url_base = self._extract_auth_url_base(player_content)
        if not auth_url_base:
            auth_url_base = player_origin
        
        auth_url = (f"{auth_url_base}/auth.php?channel_id={auth_data['channel_key']}"
                   f"&ts={auth_data['auth_ts']}&rnd={auth_data['auth_rnd']}"
                   f"&sig={quote(auth_data['auth_sig'])}")
        
        auth_response = requests.get(auth_url, headers=headers, timeout=10)
        auth_result = auth_response.json()
        
        if auth_result.get("status") != "ok":
            raise Exception("Autenticazione fallita")
        
        if not stream_url:
            stream_url = self._lookup_server(player_origin, auth_url_base, auth_data, headers)
        
        return {
            "stream_url": stream_url,
            "headers": {
                "referer": player_url,
                "origin": player_origin,
                "user-agent": self.base_headers["user-agent"]
            }
        }
    
    def _extract_auth_data(self, html_content):
        """Estrae i dati di autenticazione dalla pagina del player"""
        try:
            channel_key_match = re.search(r'var\s+channelKey\s*=\s*["\']([^"\'\']+)["\']', html_content)
            auth_ts_match = re.search(r'var\s+authTs\s*=\s*["\']([^"\'\']+)["\']', html_content)
            auth_rnd_match = re.search(r'var\s+authRnd\s*=\s*["\']([^"\'\']+)["\']', html_content)
            auth_sig_match = re.search(r'var\s+authSig\s*=\s*["\']([^"\'\']+)["\']', html_content)
            
            if not all([channel_key_match, auth_ts_match, auth_rnd_match, auth_sig_match]):
                return {}
            
            return {
                "channel_key": channel_key_match.group(1),
                "auth_ts": auth_ts_match.group(1),
                "auth_rnd": auth_rnd_match.group(1),
                "auth_sig": auth_sig_match.group(1)
            }
        except:
            return {}
    
    def _extract_auth_url_base(self, html_content):
        """Estrae la base URL di autenticazione"""
        try:
            auth_url_match = re.search(
                r'fetchWithRetry\([\'"]([^\'"]*\/auth\.php)',
                html_content
            )
            
            if auth_url_match:
                auth_url = auth_url_match.group(1)
                return auth_url.split('/auth.php')[0]
            
            domain_match = re.search(
                r'[\'"]https://([^/\'"]+)(?:/[^\'"]*)?/auth\.php',
                html_content
            )
            
            if domain_match:
                return f"https://{domain_match.group(1)}"
            
            return None
        except:
            return None
    
    def _lookup_server(self, lookup_url_base, auth_url_base, auth_data, headers):
        """Lookup delle informazioni del server"""
        try:
            server_lookup_url = f"{lookup_url_base}/server_lookup.php?channel_id={quote(auth_data['channel_key'])}"
            
            server_response = requests.get(server_lookup_url, headers=headers, timeout=10)
            server_data = server_response.json()
            server_key = server_data.get("server_key")
            
            if not server_key:
                raise Exception("Impossibile ottenere la chiave del server")
            
            auth_domain_parts = urlparse(auth_url_base).netloc.split('.')
            domain_suffix = '.'.join(auth_domain_parts[1:]) if len(auth_domain_parts) > 1 else auth_domain_parts[0]
            
            if '/' in server_key:
                parts = server_key.split('/')
                return f"https://{parts[0]}.{domain_suffix}/{server_key}/{auth_data['channel_key']}/mono.m3u8"
            else:
                return f"https://{server_key}new.{domain_suffix}/{server_key}/{auth_data['channel_key']}/mono.m3u8"
        
        except Exception as e:
            raise Exception(f"Lookup del server fallito: {str(e)}")
    
    def _get_origin(self, url):
        """Estrae l'origin dall'URL"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

# Istanza globale dell'extractor
dlhd_extractor = DLHDExtractor()

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
        # Ottieni l'IP del server
        server_ip = request.host
        
        # Scarica la lista M3U originale
        response = requests.get(m3u_url, timeout=(10, 30)) # Timeout connessione 10s, lettura 30s
        response.raise_for_status()
        m3u_content = response.text
        
        # Modifica solo le righe che contengono URL (non iniziano con #)
        modified_lines = []
        for line in m3u_content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                # Per tutti i link, usa il proxy normale
                modified_line = f"http://{server_ip}/proxy/m3u?url={line}"
                modified_lines.append(modified_line)
            else:
                # Mantieni invariate le righe di metadati
                modified_lines.append(line)
        
        modified_content = '\n'.join(modified_lines)

        # Estrai il nome del file dall'URL originale
        parsed_m3u_url = urlparse(m3u_url)
        original_filename = os.path.basename(parsed_m3u_url.path)
        
        return Response(modified_content, content_type="application/vnd.apple.mpegurl", headers={'Content-Disposition': f'attachment; filename="{original_filename}"'})
        
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

    # Rilevamento automatico DaddyLive
    daddylive_domains = ['daddylive.dad', 'daddylive.sx', 'thedaddy.to']
    parsed_url = urlparse(m3u_url)
    
    # Se l'URL è di DaddyLive, reindirizza all'endpoint DLHD
    if any(domain in parsed_url.netloc.lower() for domain in daddylive_domains):
        # Converti /embed/ in /stream/ se presente
        converted_url = m3u_url.replace('/embed/', '/stream/')
        
        # Mantieni tutti i parametri originali ma usa l'URL convertito
        query_params = request.args.to_dict()
        query_params['url'] = converted_url  # Aggiorna l'URL con la conversione
        query_string = '&'.join([f"{k}={quote(str(v))}" for k, v in query_params.items()])
        dlhd_url = f"/proxy/dlhd?{query_string}"
        
        return Response(
            status=302,
            headers={'Location': dlhd_url}
        )

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    try:
        response = requests.get(m3u_url, headers=headers, allow_redirects=True)
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
    """ Proxy per segmenti .TS con headers personalizzati """
    ts_url = request.args.get('url', '').strip()
    if not ts_url:
        return "Errore: Parametro 'url' mancante", 400

    headers = {
        unquote(key[2:]).replace("_", "-"): unquote(value).strip()
        for key, value in request.args.items()
        if key.lower().startswith("h_")
    }

    try:
        response = requests.get(ts_url, headers=headers, stream=True, allow_redirects=True)
        response.raise_for_status()
        return Response(response.iter_content(chunk_size=1024), content_type="video/mp2t")
    
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
        response = requests.get(key_url, headers=headers, allow_redirects=True)
        response.raise_for_status()
        return Response(response.content, content_type="application/octet-stream")
    
    except requests.RequestException as e:
        return f"Errore durante il download della chiave AES-128: {str(e)}", 500

@app.route('/proxy/dlhd')
def proxy_dlhd():
    """Endpoint per estrarre e proxare stream DLHD"""
    channel_url = request.args.get('url', '').strip()
    if not channel_url:
        return "Errore: Parametro 'url' mancante", 400
    
    # Converti /embed/ in /stream/ se presente
    channel_url = channel_url.replace('/embed/', '/stream/')
    
    try:
        # Estrai parametri opzionali
        player_url = request.args.get('player_url')
        stream_url = request.args.get('stream_url')
        
        # Estrai l'URL dello stream usando l'extractor
        result = dlhd_extractor.extract_stream_url(
            channel_url,
            player_url=player_url,
            stream_url=stream_url
        )
        
        extracted_stream_url = result['stream_url']
        stream_headers = result['headers']
        
        # Costruisci la query string per gli header
        headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in stream_headers.items()])
        
        # Reindirizza al proxy M3U8 con gli header appropriati
        proxied_url = f"/proxy/m3u?url={quote(extracted_stream_url)}&{headers_query}"
        
        return Response(
            status=302,
            headers={'Location': proxied_url}
        )
        
    except Exception as e:
        return f"Errore durante l'estrazione DLHD: {str(e)}", 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=7860, debug=False)
