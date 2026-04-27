"""FastAPI auth gateway: validates sk- keys, forwards to copilot-api, logs."""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Deque

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from . import SETTINGS
from . import keystore


app = FastAPI(title="copilot-Subscription-to-Public-Api gateway")
client = httpx.AsyncClient(base_url=SETTINGS.upstream_url, timeout=httpx.Timeout(600.0))

# in-memory sliding window of request timestamps per key for RPM enforcement
_rpm_window: dict[int, Deque[float]] = defaultdict(deque)


def _log_event(entry: dict) -> None:
    entry["ts"] = time.time()
    with SETTINGS.usage_log.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(None, 1)[1].strip()
        if token:
            return token
    qp = request.query_params
    return (qp.get("key") or qp.get("api_key") or "").strip()


def _check_auth(request: Request) -> keystore.ApiKey:
    token = _extract_token(request)
    if not token:
        raise HTTPException(401, "missing api key (Authorization: Bearer sk-...)")
    key = keystore.lookup(token)
    if not key:
        _log_event({
            "event": "auth_fail",
            "ip": request.client.host if request.client else None,
            "path": request.url.path,
        })
        raise HTTPException(401, "invalid or revoked api key")
    return key


def _enforce_rpm(key: keystore.ApiKey) -> None:
    if key.max_rpm <= 0:
        return
    window = _rpm_window[key.id]
    cutoff = time.time() - 60.0
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= key.max_rpm:
        raise HTTPException(429, f"rate limit exceeded ({key.max_rpm} rpm)")
    window.append(time.time())


def _decode(raw: bytes):
    if not raw:
        return None, None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None, None
    try:
        return text, json.loads(text)
    except Exception:
        return text, None


def _summarize(parsed) -> dict:
    if not isinstance(parsed, dict):
        return {}
    s: dict = {}
    if "model" in parsed:
        s["model"] = parsed.get("model")
    if "stream" in parsed:
        s["stream"] = bool(parsed.get("stream"))
    msgs = parsed.get("messages") or parsed.get("input")
    if isinstance(msgs, list):
        s["message_count"] = len(msgs)
    return s


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/usage-summary")
async def usage_summary(request: Request, limit: int = 100):
    _check_auth(request)  # require key but don't restrict by name
    if not SETTINGS.usage_log.exists():
        return {"total_requests": 0, "auth_failures": 0, "recent": []}
    lines = SETTINGS.usage_log.read_text().splitlines()
    entries = [json.loads(l) for l in lines if l.strip()]
    requests_ = [e for e in entries if e.get("event") == "request"]
    auth_fails = [e for e in entries if e.get("event") == "auth_fail"]
    return {
        "total_requests": len(requests_),
        "auth_failures": len(auth_fails),
        "last_event_ts": entries[-1]["ts"] if entries else None,
        "recent": entries[-limit:],
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!doctype html><meta charset=utf-8>
<title>c2p gateway</title>
<style>body{font-family:system-ui;max-width:640px;margin:3rem auto;padding:0 1rem;color:#222}</style>
<h1>copilot-Subscription-to-Public-Api</h1>
<p>This is a private gateway. Use an OpenAI-compatible client with the API
key your administrator gave you.</p>
<p>Base URL: <code id=u></code></p>
<p>Tracker: <code>/usage-summary?key=sk-...</code></p>
<script>document.getElementById('u').textContent=location.origin+'/v1'</script>
"""


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy(path: str, request: Request):
    if path in ("healthz", "usage-summary", ""):
        raise HTTPException(404)

    key = _check_auth(request)
    body = await request.body()
    body_text, body_json = _decode(body)
    summary = _summarize(body_json)

    # model allow-list
    if key.models and summary.get("model") and summary["model"] not in key.models:
        raise HTTPException(403, f"model '{summary['model']}' not allowed for this key")

    _enforce_rpm(key)

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "authorization", "content-length")}
    headers["authorization"] = "Bearer dummy"

    upstream_url = "/" + path
    if request.url.query:
        upstream_url += "?" + request.url.query

    started = time.time()
    truncated_in = bool(body_text and len(body_text) > SETTINGS.max_request_log
                        and body_json is None)
    _log_event({
        "event": "request",
        "key": key.name,
        "method": request.method,
        "path": "/" + path,
        "ip": request.client.host if request.client else None,
        "bytes_in": len(body),
        "summary": summary,
        "request_body": (body_json if body_json is not None
                         else (body_text[:SETTINGS.max_request_log] if body_text else None)),
        "request_truncated": truncated_in,
    })

    try:
        req = client.build_request(
            request.method, upstream_url, content=body, headers=headers
        )
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        _log_event({"event": "upstream_error", "key": key.name, "error": str(e)})
        return JSONResponse({"error": {"message": f"upstream error: {e}",
                                       "type": "upstream_error"}}, status_code=502)

    excluded = {"content-encoding", "transfer-encoding", "connection", "content-length"}
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
    captured = bytearray()

    async def gen():
        try:
            async for chunk in resp.aiter_raw():
                if len(captured) < SETTINGS.max_response_log:
                    captured.extend(chunk[: SETTINGS.max_response_log - len(captured)])
                yield chunk
        finally:
            await resp.aclose()
            snippet_text, snippet_json = _decode(bytes(captured))
            _log_event({
                "event": "response",
                "key": key.name,
                "path": "/" + path,
                "status": resp.status_code,
                "duration_ms": int((time.time() - started) * 1000),
                "response_body": (snippet_json if snippet_json is not None else snippet_text),
                "response_truncated": len(captured) >= SETTINGS.max_response_log,
            })

    return StreamingResponse(gen(), status_code=resp.status_code, headers=out_headers)
