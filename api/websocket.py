"""WebSocket event fan-out for the dashboard."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def create_websocket_router(server) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/events")
    async def events(websocket: WebSocket):
        await websocket.accept()
        server.event_clients.add(websocket)
        try:
            for event in server.database.events(100):
                await websocket.send_json(event)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            server.event_clients.discard(websocket)

    return router
