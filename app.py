from fastapi import FastAPI, Request, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from urllib.parse import urlparse, urljoin, quote, unquote
import re
import os
import httpx

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Proxy Server</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
            h1 { color: #28a745; }
            .status { background: #d4edda; padding: 20px; border-radius: 5px; display: inline-block; }
        </style>
    </head>
    <body>
        <div class="status">
            <h1>🟢 Proxy Attivo</h1>
            <p>Server in funzione in modalità async</p>
        </div>
    </body>
    </html>
    """

def detect_m3u_type(content: str) -> str:
    if "#EXTM3U" in content and "#EXTINF" in content:
        return "m3u8"
    return "m3u"

def replace_key_uri(line: str, headers_query: str) -> str:
    match = re.search(r'URI="([^"]+)"', line)
    if match:
        key_url = match.group(1)
        proxied_key_url = f"/proxy/key?url={quote(key_url)}&{headers_query}"
        return line.replace(key_url, proxied_key_url)
    return line

@app.get("/proxy")
async def proxy(url: str, request: Request):
    try:
        server_ip = request.client.host + f":{request.url.port or 80}"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            lines = r.text.splitlines()
            modified_lines = []

            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    modified_lines.append(f"http://{server_ip}/proxy/m3u?url={line}")
                else:
                    modified_lines.append(line)

            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)

            return Response(
                content="\n".join(modified_lines),
                media_type="application/vnd.apple.mpegurl",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
    except httpx.HTTPError as e:
        return PlainTextResponse(f"Errore HTTP: {str(e)}", status_code=500)

@app.get("/proxy/m3u")
async def proxy_m3u(url: str, request: Request):
    headers = {
        unquote(k[2:]).replace("_", "-"): unquote(v)
        for k, v in request.query_params.items()
        if k.lower().startswith("h_")
    }

    default_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/33.0 Mobile/15E148 Safari/605.1.15",
        "Referer": "https://vavoo.to/",
        "Origin": "https://vavoo.to"
    }

    headers = {**default_headers, **headers}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers, follow_redirects=True)
            r.raise_for_status()
            m3u_content = r.text
            final_url = str(r.url)

            file_type = detect_m3u_type(m3u_content)
            if file_type == "m3u":
                return Response(content=m3u_content, media_type="audio/x-mpegurl")

            parsed_url = urlparse(final_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path.rsplit('/', 1)[0]}/"
            headers_query = "&".join([f"h_{quote(k)}={quote(v)}" for k, v in headers.items()])

            modified_lines = []
            for line in m3u_content.splitlines():
                line = line.strip()
                if line.startswith("#EXT-X-KEY") and 'URI="' in line:
                    line = replace_key_uri(line, headers_query)
                elif line and not line.startswith("#"):
                    segment_url = urljoin(base_url, line)
                    line = f"/proxy/ts?url={quote(segment_url)}&{headers_query}"
                modified_lines.append(line)

            return Response("\n".join(modified_lines), media_type="application/vnd.apple.mpegurl")

    except httpx.HTTPError as e:
        return PlainTextResponse(f"Errore HTTP: {str(e)}", status_code=500)

@app.get("/proxy/ts")
async def proxy_ts(url: str, request: Request):
    headers = {
        unquote(k[2:]).replace("_", "-"): unquote(v)
        for k, v in request.query_params.items()
        if k.lower().startswith("h_")
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers, follow_redirects=True)
            r.raise_for_status()
            return StreamingResponse(r.aiter_bytes(), media_type="video/mp2t")
    except httpx.HTTPError as e:
        return PlainTextResponse(f"Errore TS: {str(e)}", status_code=500)

@app.get("/proxy/key")
async def proxy_key(url: str, request: Request):
    headers = {
        unquote(k[2:]).replace("_", "-"): unquote(v)
        for k, v in request.query_params.items()
        if k.lower().startswith("h_")
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers, follow_redirects=True)
            r.raise_for_status()
            return Response(content=r.content, media_type="application/octet-stream")
    except httpx.HTTPError as e:
        return PlainTextResponse(f"Errore chiave AES-128: {str(e)}", status_code=500)