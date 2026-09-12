import sys
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routes import api_router
from backend.routes.health import health_check as perform_health_check
from backend.websocket import manager

# Suppress harmless Windows asyncio Proactor connection reset tracebacks during HTTP Range video streaming
if sys.platform == 'win32':
    try:
        import socket
        import asyncio.proactor_events as pe

        def _safe_call_connection_lost(self, exc):
            if getattr(self, '_called_connection_lost', False):
                return
            try:
                if hasattr(self, '_protocol') and self._protocol:
                    self._protocol.connection_lost(exc)
            except Exception:
                pass
            finally:
                if hasattr(self, '_sock') and self._sock is not None:
                    if hasattr(self._sock, 'shutdown') and getattr(self._sock, 'fileno', lambda: -1)() != -1:
                        try:
                            self._sock.shutdown(socket.SHUT_RDWR)
                        except (ConnectionResetError, OSError):
                            pass
                    try:
                        self._sock.close()
                    except (ConnectionResetError, OSError):
                        pass
                    self._sock = None
                server = getattr(self, '_server', None)
                if server is not None:
                    try:
                        server._detach(self)
                    except Exception:
                        pass
                    self._server = None
                self._called_connection_lost = True

        pe._ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost
    except Exception:
        pass

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet (SIH26124 Prototype)",
    version="0.1.0",
    debug=settings.DEBUG,
)

# CORS middleware for frontend dashboards and map clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from urllib.parse import unquote
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse


def stream_media_file(file_path: Path, request: Request):
    """Serve video and evidence assets supporting RFC 7233 HTTP 206 Range streaming and safe disconnects."""
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Requested media file not found.")

    suffix = file_path.suffix.lower()
    is_video = suffix in {".mp4", ".webm", ".mov", ".mkv", ".m4v"}

    if not is_video:
        return FileResponse(str(file_path))

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range") or request.headers.get("Range")

    if not range_header:
        return FileResponse(
            str(file_path),
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes"}
        )

    # Parse Range: bytes=START-END
    try:
        raw_range = range_header.replace("bytes=", "").strip()
        parts = raw_range.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
    except Exception:
        start = 0
        end = file_size - 1

    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    content_length = (end - start) + 1

    def iter_file(path_to_file: Path, offset: int, length: int, chunk_size: int = 64 * 1024):
        try:
            with open(path_to_file, "rb") as f:
                f.seek(offset)
                remaining = length
                while remaining > 0:
                    read_bytes = min(chunk_size, remaining)
                    data = f.read(read_bytes)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
        except (GeneratorExit, ConnectionResetError, BrokenPipeError, OSError):
            return

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": "video/mp4",
        "Cache-Control": "public, max-age=3600",
    }

    return StreamingResponse(
        iter_file(file_path, start, content_length),
        status_code=206,
        headers=headers,
        media_type="video/mp4",
    )


def resolve_asset_path(raw_path: str) -> Path | None:
    """Find the exact file path across data/outputs, frontend/videos, data/uploads and jobs."""
    clean = unquote(raw_path).replace("\\", "/").strip("/")
    
    # Safely strip leading route prefixes if they were included in path
    changed = True
    while changed:
        changed = False
        for prefix in ("videos/", "evidence/", "data/outputs/", "data/"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip("/")
                changed = True
                break

    base_name = Path(clean).name

    candidates = [
        Path("data/outputs") / clean,
        Path("data/outputs/unified_evidence") / clean,
        Path("data/outputs/unified_evidence") / base_name,
        Path("data/outputs/jobs") / clean,
        Path("data/outputs/jobs") / base_name,
        Path("data/outputs") / base_name,
        Path("frontend/videos") / clean,
        Path("frontend/videos/jobs") / base_name,
        Path("frontend/videos") / base_name,
        Path("data/videos") / clean,
        Path("data/videos") / base_name,
        Path("data/uploads") / clean,
        Path("data/uploads") / base_name,
        Path("data") / clean,
    ]

    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand
    return None


@app.get("/videos/{file_path:path}")
async def serve_video_stream(file_path: str, request: Request):
    """Dedicated video streaming endpoint with full HTTP 206 Range support."""
    resolved = resolve_asset_path(file_path)
    if resolved:
        return stream_media_file(resolved, request)
    raise HTTPException(status_code=404, detail=f"Video '{file_path}' not found.")


@app.get("/evidence/{file_path:path}")
async def serve_evidence_stream(file_path: str, request: Request):
    """Dedicated evidence file streaming endpoint with full HTTP 206 Range support."""
    resolved = resolve_asset_path(file_path)
    if resolved:
        return stream_media_file(resolved, request)
    raise HTTPException(status_code=404, detail=f"Evidence '{file_path}' not found.")


# Serve frontend static assets (CSS, JS)
frontend_dir = Path("frontend")
if (frontend_dir / "css").exists():
    app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
if (frontend_dir / "js").exists():
    app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")

# Include all API routes
app.include_router(api_router)


@app.on_event("startup")
async def startup_event():
    """Configure asyncio event loop exception filters for clean Windows execution."""
    if sys.platform == 'win32':
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            orig_handler = loop.get_exception_handler()

            def _quiet_exception_handler(current_loop, context):
                exc = context.get("exception")
                msg = str(context.get("message", ""))
                if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
                    return
                if "10054" in msg or "10054" in str(exc) or "connection was forcibly closed" in msg.lower():
                    return
                if orig_handler:
                    orig_handler(current_loop, context)
                else:
                    current_loop.default_exception_handler(context)

            loop.set_exception_handler(_quiet_exception_handler)
        except Exception:
            pass


@app.get("/")
def root():
    """Root entry point serving CitySense urban intelligence dashboard."""
    index_file = frontend_dir / "index.html"
    if index_file.exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(index_file))
    return {
        "project": "BusSense-AI",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/dashboard")
def dashboard_page():
    """Direct dashboard entry point."""
    index_file = frontend_dir / "index.html"
    if index_file.exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(index_file))
    return {"project": "BusSense-AI", "status": "online"}


@app.get("/api-info")
def api_info():
    """API metadata and connection routes."""
    return {
        "project": "BusSense-AI",
        "description": "Mobile Urban Intelligence Platform Using Public Transport Fleet",
        "mode": "Simulated Hackathon Prototype",
        "status": "online",
        "docs_url": "/docs",
        "health_url": "/health",
        "api_health": "/api/health",
        "websockets": {
            "events": "/ws/events",
            "buses": "/ws/buses",
            "general": "/ws",
        },
    }


@app.get("/health", tags=["Health"])
def health_endpoint(response: Response):
    """Direct root health check endpoint checking PostgreSQL and PostGIS connectivity."""
    return perform_health_check(response=response)


# ==============================================================================
# WEBSOCKET ENDPOINTS
# ==============================================================================

@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """Dedicated WebSocket channel for real-time urban sensing events (road defects, incidents, congestion)."""
    await manager.connect(websocket, channel="events")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "channel": "events", "received": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/buses")
async def websocket_buses_endpoint(websocket: WebSocket):
    """Dedicated WebSocket channel for real-time bus telemetry and fleet GPS movements."""
    await manager.connect(websocket, channel="buses")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "channel": "buses", "received": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws")
async def websocket_general_endpoint(websocket: WebSocket):
    """Multiplexed WebSocket channel receiving all telemetry and event streams."""
    await manager.connect(websocket, channel="general")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "channel": "general", "received": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
