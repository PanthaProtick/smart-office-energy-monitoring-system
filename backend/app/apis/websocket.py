import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(uuid.uuid4())
    await manager.connect(client_id, websocket)
    try:
        while True:
            # Receive incoming message from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                message_type = message.get("type")

                # Handle client-side subscribe/unsubscribe commands
                if message_type == "subscribe":
                    event_type = message.get("event_type")
                    if (
                        event_type in manager.subscriptions
                        and client_id not in manager.subscriptions[event_type]
                    ):
                        manager.subscriptions[event_type].append(client_id)

                elif message_type == "unsubscribe":
                    event_type = message.get("event_type")
                    if event_type in manager.subscriptions:
                        if client_id in manager.subscriptions[event_type]:
                            manager.subscriptions[event_type].remove(client_id)

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(client_id)
