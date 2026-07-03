import json
from typing import Dict, List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Maps client_id -> WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        # Maps event_type -> list of subscribed client_ids
        self.subscriptions: Dict[str, List[str]] = {
            "device_updated": [],
            "power_updated": [],
            "alert_created": [],
        }

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        # default: subscribe to all event types
        for event_type in self.subscriptions:
            if client_id not in self.subscriptions[event_type]:
                self.subscriptions[event_type].append(client_id)

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        # remove from all subscriptions
        for event_type in self.subscriptions:
            if client_id in self.subscriptions[event_type]:
                self.subscriptions[event_type].remove(client_id)

    async def broadcast(self, event_type: str, payload: dict):
        """Broadcast an event to all subscribed clients."""
        message = {
            "type": event_type,
            "data": payload,
        }
        message_json = json.dumps(message)

        # Get list of subscribed clients for this event type
        subscribed_clients = self.subscriptions.get(event_type, [])
        disconnected_clients = []

        for client_id in subscribed_clients:
            if client_id in self.active_connections:
                try:
                    websocket = self.active_connections[client_id]
                    await websocket.send_text(message_json)
                except Exception:
                    # Connection might have been closed
                    disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    async def send_personal_message(self, client_id: str, message: str):
        """Send a message to a specific client."""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(message)
            except Exception:
                self.disconnect(client_id)


# Global manager instance
manager = ConnectionManager()
