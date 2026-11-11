"""Session-protected gateway to the internal, unmodified Mosaik editor."""
import asyncio
from html import escape
from html.parser import HTMLParser
import logging
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect
from fastapi_app.authentication.auth import require_login

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_ASSET_BYTES = 32 * 1024 * 1024


class EditorHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []

    def tag(self, tag, attrs, ending):
        rendered = []
        for name, value in attrs:
            if value is not None and name in {"src", "href", "action"}:
                if value.startswith("/") and not value.startswith(("//", "/mosaik/")):
                    value = "/mosaik" + value
            rendered.append(name if value is None else '%s="%s"' % (name, escape(value, quote=True)))
        self.parts.append("<" + tag + (" " + " ".join(rendered) if rendered else "") + ending)

    def handle_starttag(self, tag, attrs):
        self.tag(tag, attrs, ">")

    def handle_startendtag(self, tag, attrs):
        self.tag(tag, attrs, "/>")

    def handle_endtag(self, tag):
        self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append("&" + name + ";")

    def handle_charref(self, name):
        self.parts.append("&#" + name + ";")

    def handle_comment(self, data):
        self.parts.append("<!--" + data + "-->")

    def handle_decl(self, decl):
        self.parts.append("<!" + decl + ">")


def upstream_url(connection, path):
    base = httpx.URL(connection.app.state.settings.mosaik_gui_url)
    # Keep authority fixed even for paths containing // or an encoded URL.
    return base.copy_with(raw_path=("/" + path).encode("utf-8") +
                          (b"?" + connection.scope["query_string"] if connection.scope["query_string"] else b""))


@router.get("/mosaik", include_in_schema=False)
def editor_redirect(user=Depends(require_login)):
    return RedirectResponse("/mosaik/", status_code=307, headers={"Cache-Control": "no-store"})


async def proxy_asset(request, path):
    try:
        # Never pass application cookies/credentials or reuse an upstream cookie jar.
        async with httpx.AsyncClient(trust_env=False, timeout=20) as client:
            async with client.stream(request.method, upstream_url(request, path),
                                     headers={"Accept-Encoding": "identity"}) as upstream:
                body = bytearray()
                async for chunk in upstream.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_ASSET_BYTES:
                        raise HTTPException(502, "Mosaik editor asset exceeds the proxy limit")
                headers = {"Cache-Control": "private, no-store", "Vary": "Cookie",
                           "X-Content-Type-Options": "nosniff"}
                content_type = upstream.headers.get("content-type", "application/octet-stream")
                headers["Content-Type"] = content_type
                if "location" in upstream.headers:
                    target = httpx.URL(urljoin(str(upstream.url), upstream.headers["location"]))
                    if (target.scheme, target.host, target.port) != (upstream.url.scheme, upstream.url.host, upstream.url.port):
                        raise HTTPException(502, "Unexpected Mosaik editor redirect")
                    headers["Location"] = "/mosaik" + target.raw_path.decode("ascii")
                if content_type.split(";", 1)[0].strip() == "text/html":
                    document = EditorHTML()
                    document.feed(body.decode("utf-8"))
                    document.close()
                    body = "".join(document.parts).encode("utf-8")
                return Response(bytes(body), status_code=upstream.status_code, headers=headers)
    except (httpx.HTTPError, UnicodeError):
        logger.warning("Mosaik editor HTTP upstream is unavailable")
        raise HTTPException(502, "Mosaik editor is unavailable")


@router.api_route("/mosaik/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def editor_http(request: Request, path: str, user=Depends(require_login)):
    return await proxy_asset(request, path)


# The maintained image embeds absolute /_app/ asset and /ws socket URLs.
@router.api_route("/_app/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def editor_assets(request: Request, path: str, user=Depends(require_login)):
    return await proxy_asset(request, "_app/" + path)


def same_origin(websocket):
    expected_scheme = "https" if websocket.url.scheme == "wss" else "http"
    try:
        origin = urlsplit(websocket.headers.get("origin", ""))
        return (origin.scheme == expected_scheme and origin.hostname == websocket.url.hostname
                and (origin.port or (443 if origin.scheme == "https" else 80)) ==
                (websocket.url.port or (443 if expected_scheme == "https" else 80))
                and not origin.username and not origin.password and not origin.path
                and not origin.query and not origin.fragment)
    except ValueError:
        return False


@router.websocket("/ws")
@router.websocket("/mosaik/ws")
async def editor_socket(websocket: WebSocket):
    from websockets.exceptions import WebSocketException
    from websockets.legacy.client import connect
    try:
        await run_in_threadpool(require_login, websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return
    if not same_origin(websocket):
        await websocket.close(code=1008)
        return
    target = upstream_url(websocket, "ws")
    target = target.copy_with(scheme="wss" if target.scheme == "https" else "ws")
    try:
        async with connect(str(target), open_timeout=10, close_timeout=5,
                           max_size=10 * 1024 * 1024) as upstream:
            await websocket.accept()

            async def browser_to_editor():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    await upstream.send(message.get("text") if message.get("text") is not None else message["bytes"])

            async def editor_to_browser():
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)

            tasks = [asyncio.create_task(browser_to_editor()), asyncio.create_task(editor_to_browser())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.close(code=1000)
    except (OSError, WebSocketException, asyncio.TimeoutError):
        logger.warning("Mosaik editor WebSocket upstream is unavailable")
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close(code=1011)
    except WebSocketDisconnect:
        pass
