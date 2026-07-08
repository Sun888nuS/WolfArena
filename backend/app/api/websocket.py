"""游戏快照 WebSocket API。"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.exceptions import GameCoreError
from app.sessions.manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/games/{game_id}")
async def game_socket(websocket: WebSocket, game_id: str) -> None:
    """向连接的前端持续推送某局游戏的最新快照。"""
    try:
        session = await manager.get(game_id)
    except GameCoreError:
        await websocket.close(code=4404)
        return

    try:
        await session.subscribe(websocket)
    except WebSocketDisconnect:
        return
