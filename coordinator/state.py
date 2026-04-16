"""
coordinator/state.py — Shared state for the SafeSphere coordinator.
Used to avoid circular imports between main.py and routes.
"""
from fastapi import WebSocket

_dashboard_ws: list[WebSocket] = []
_user_ws: dict[str, list[WebSocket]] = {}  # user_id → [ws connections]

def is_user_connected(user_id: str) -> bool:
    """Check if the user has an active WebSocket session."""
    return user_id in _user_ws and len(_user_ws[user_id]) > 0
