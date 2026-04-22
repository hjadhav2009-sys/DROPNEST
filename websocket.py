"""WebSocket endpoint for live nesting progress."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Active connections per job_id
_connections: dict = {}


def broadcast(job_id: str, data: dict):
    """Send progress update to all listeners for a job."""
    for ws in _connections.get(job_id, []):
        try:
            asyncio.get_event_loop().create_task(ws.send_json(data))
        except Exception:
            pass


@router.websocket("/ws/progress/{job_id}")
async def ws_progress(websocket: WebSocket, job_id: str):
    """Stream nesting progress updates for a given job."""
    await websocket.accept()

    if job_id not in _connections:
        _connections[job_id] = []
    _connections[job_id].append(websocket)

    try:
        while True:
            # Keep connection alive; client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"event": "pong", "job_id": job_id})
    except WebSocketDisconnect:
        pass
    finally:
        if job_id in _connections:
            _connections[job_id].remove(websocket)
            if not _connections[job_id]:
                del _connections[job_id]
