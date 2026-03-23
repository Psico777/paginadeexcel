"""
EMFOX OMS v2 - WebSocket Manager
==================================
Manages real-time connections per project room.
Broadcasts product changes, cursor positions, and sync status.
"""

import json
import asyncio
from typing import Dict, Set, Optional
from fastapi import WebSocket
from datetime import datetime, timezone


class ConnectionManager:
    """
    Manages WebSocket connections organized by project rooms.
    Each project_id is a 'room' - only users in the same project
    receive broadcasts from each other.
    """

    def __init__(self):
        # {project_id: {websocket: user_info}}
        self.rooms: Dict[int, Dict[WebSocket, dict]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, project_id: int, user_name: str = "Anónimo"):
        """Accept connection and add to project room."""
        await websocket.accept()
        async with self._lock:
            if project_id not in self.rooms:
                self.rooms[project_id] = {}
            self.rooms[project_id][websocket] = {
                "user_name": user_name,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            }

        # Notify room about new user
        await self.broadcast_to_room(project_id, {
            "type": "user_joined",
            "user": user_name,
            "online_count": len(self.rooms.get(project_id, {})),
            "online_users": self._get_user_list(project_id),
        }, exclude=None)

    async def disconnect(self, websocket: WebSocket, project_id: int):
        """Remove connection from project room."""
        user_name = "Anónimo"
        async with self._lock:
            if project_id in self.rooms:
                info = self.rooms[project_id].pop(websocket, None)
                if info:
                    user_name = info["user_name"]
                if not self.rooms[project_id]:
                    del self.rooms[project_id]

        # Notify remaining users
        if project_id in self.rooms:
            await self.broadcast_to_room(project_id, {
                "type": "user_left",
                "user": user_name,
                "online_count": len(self.rooms.get(project_id, {})),
                "online_users": self._get_user_list(project_id),
            }, exclude=None)

    async def broadcast_to_room(
        self, project_id: int, message: dict,
        exclude: Optional[WebSocket] = None
    ):
        """Send message to all connections in a project room."""
        room = self.rooms.get(project_id, {})
        dead = []
        data = json.dumps(message, default=str)

        for ws in room:
            if ws == exclude:
                continue
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            async with self._lock:
                if project_id in self.rooms:
                    self.rooms[project_id].pop(ws, None)

    def _get_user_list(self, project_id: int) -> list:
        """Get list of connected user names in a room."""
        room = self.rooms.get(project_id, {})
        return [info["user_name"] for info in room.values()]

    def get_online_count(self, project_id: int) -> int:
        return len(self.rooms.get(project_id, {}))


# Singleton
ws_manager = ConnectionManager()
