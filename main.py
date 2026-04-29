import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()

TARGET_BASE = os.getenv("TARGET_DOMAIN", "").rstrip("/")

STRIP_HEADERS = {
    "host", "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailer", "transfer-encoding",
    "upgrade", "forwarded", "x-forwarded-host", "x-forwarded-proto",
    "x-forwarded-port",
}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def relay(request: Request, path: str):
    if not TARGET_BASE:
        return Response(content="Misconfigured: TARGET_DOMAIN is not set", status_code=500)

    target_url = TARGET_BASE + "/" + path
    if request.url.query:
        target_url += "?" + request.url.query

    headers = {}
    client_ip = None

    for key, value in request.headers.items():
        k = key.lower()
        if k in STRIP_HEADERS:
            continue
        if k.startswith("x-vercel-"):
            continue
        if k == "x-real-ip":
            client_ip = value
            continue
        if k == "x-forwarded-for":
            if not client_ip:
                client_ip = value
            continue
        headers[k] = value

    if client_ip:
        headers["x-forwarded-for"] = client_ip

    method = request.method
    body = await request.body() if method not in ("GET", "HEAD") else None

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=60) as client:
            upstream = await client.request(
                method=method,
                url=target_url,
                headers=headers,
                content=body,
            )

        response_headers = {
            k: v for k, v in upstream.headers.items()
            if k.lower() not in ("transfer-encoding", "content-encoding")
        }

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    except Exception as err:
        print(f"relay error: {err}")
        return Response(content="Bad Gateway: Tunnel Failed", status_code=502)
