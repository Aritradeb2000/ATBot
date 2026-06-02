"""
ATBot — Live WebSocket
Provides real-time updates for watchlist prices, signals, and alerts
to the Next.js frontend.
"""

import json
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.data.scheduler import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🟢 WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"🔴 WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"WebSocket broadcast error: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint that streams live cache data every 5 seconds.
    """
    await manager.connect(websocket)
    try:
        # Send initial full state
        cache = get_cache()
        await websocket.send_text(json.dumps({
            "type": "INITIAL_STATE",
            "indices": cache.get("indices"),
            "india_vix": cache.get("india_vix"),
            "market_breadth": cache.get("market_breadth")
        }))

        # Stream updates every 5 seconds
        while True:
            await asyncio.sleep(5)
            # In a production app, we would only broadcast if data has actually changed.
            # For v1, broadcasting from the cache is sufficient.
            updated_cache = get_cache()
            payload = {
                "type": "HEARTBEAT",
                "indices": updated_cache.get("indices"),
                "india_vix": updated_cache.get("india_vix")
            }
            await websocket.send_text(json.dumps(payload))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
