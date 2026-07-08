"""多 Agent 狼人杀 REST API。"""

from fastapi import APIRouter, HTTPException

from app.core.exceptions import GameCoreError
from app.llm.base import LlmProviderError
from app.sessions.manager import HUMAN_PLAYER_ID, manager
from app.sessions.models import (
    GameListResponse,
    GameSnapshotResponse,
    StartGameRequest,
    StartGameResponse,
    SubmitActionRequest,
)

router = APIRouter(prefix="/games", tags=["games"])


@router.post("", response_model=GameSnapshotResponse)
async def start_game(request: StartGameRequest) -> GameSnapshotResponse:
    """创建并启动一局新的进程内游戏。"""
    return await manager.create_game(seed=request.seed, player_name=request.player_name)


@router.get("", response_model=GameListResponse)
async def list_games() -> GameListResponse:
    """返回当前后端进程中仍存在的游戏 id。"""
    return GameListResponse(game_ids=manager.list_game_ids())


@router.get("/{game_id}", response_model=GameSnapshotResponse)
async def get_game(game_id: str) -> GameSnapshotResponse:
    """返回某局游戏的最新前端快照。"""
    try:
        session = await manager.get(game_id)
        return await session.snapshot()
    except GameCoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{game_id}/actions", response_model=GameSnapshotResponse)
async def submit_action(
    game_id: str,
    request: SubmitActionRequest,
) -> GameSnapshotResponse:
    """提交真人玩家行动，并继续推进游戏。"""
    try:
        session = await manager.get(game_id)
        return await session.submit_action(request)
    except GameCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LlmProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{game_id}/advance", response_model=GameSnapshotResponse)
async def advance_game(game_id: str) -> GameSnapshotResponse:
    """让系统主持人推进一个 AI 或规则节点。"""
    try:
        session = await manager.get(game_id)
        return await session.advance()
    except GameCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LlmProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{game_id}/role", response_model=StartGameResponse)
async def get_human_role_context(game_id: str) -> StartGameResponse:
    """返回当前真人玩家的稳定 game_id 和 player_id。"""
    try:
        await manager.get(game_id)
    except GameCoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StartGameResponse(game_id=game_id, human_player_id=HUMAN_PLAYER_ID)
