"""多 Agent 游戏 API 测试。"""

import asyncio
import re

from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.engine import WerewolfEngine
from app.core.models import Phase, Role
from app.main import create_app
from app.sessions.manager import GameSessionManager
from app.sessions.snapshots import build_snapshot_response


def test_manager_does_not_recover_after_restart() -> None:
    """新的会话管理器不应恢复上一进程中的游戏。"""

    async def scenario() -> None:
        """创建两套管理器，验证内存会话不会跨实例恢复。"""
        first = GameSessionManager()
        start = await first.create_game(seed=7, player_name="Tester")
        game_id = start.game_id

        second = GameSessionManager()

        assert game_id not in second.list_game_ids()
        await first.close()
        await second.close()

    asyncio.run(scenario())


def test_start_game_returns_pending_human_action_or_finished_game() -> None:
    """创建游戏后应返回可直接渲染的快照。"""
    client = TestClient(create_app())

    response = client.post("/api/games", json={"seed": 42, "player_name": "Tester"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["game_id"]
    assert payload["human_player_id"] == "p1"
    assert len(payload["players"]) == 12
    assert payload["phase"] == "night"
    assert "events" in payload
    assert payload["god_message"]
    assert payload["god_steps"]
    assert payload["pending_action"] is None


def test_start_game_uses_non_numeric_ai_names() -> None:
    """AI 展示名不应看起来像座位号或机器编号。"""
    client = TestClient(create_app())

    response = client.post("/api/games", json={"seed": 42, "player_name": "Tester"})

    assert response.status_code == 200
    payload = response.json()
    human = next(player for player in payload["players"] if player["is_human"])
    ai_players = [player for player in payload["players"] if not player["is_human"]]

    assert human["name"] == "Tester"
    assert len({player["name"] for player in ai_players}) == len(ai_players)
    assert all(not re.search(r"\d", player["name"]) for player in ai_players)
    assert all(not player["name"].upper().startswith("AI") for player in ai_players)


def test_advance_game_progresses_host_flow() -> None:
    """系统主持人应能推进一个 AI 或规则节点。"""
    client = TestClient(create_app())
    start = client.post("/api/games", json={"seed": 42, "player_name": "Tester"}).json()

    response = client.post(f"/api/games/{start['game_id']}/advance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["game_id"] == start["game_id"]
    assert payload["god_message"]


def test_list_games_returns_in_memory_game_id() -> None:
    """内存注册表应暴露当前进程中的游戏 id。"""
    client = TestClient(create_app())
    start = client.post("/api/games", json={"seed": 42, "player_name": "Tester"}).json()

    response = client.get("/api/games")

    assert response.status_code == 200
    assert start["game_id"] in response.json()["game_ids"]


def test_pending_action_survives_snapshot_reload() -> None:
    """真人待行动状态应能在同进程快照重载后保留。"""
    client = TestClient(create_app())
    snapshot = _start_game_with_pending(client, "seer_check")
    game_id = snapshot["game_id"]

    response = client.get(f"/api/games/{game_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pending_action"] == snapshot["pending_action"]
    assert payload["current_actor_id"] is None


def test_snapshot_does_not_highlight_night_power_role() -> None:
    """夜晚神职行动不应通过 current_actor_id 暴露身份。"""
    engine = WerewolfEngine(_names(), human_player_id="p1", seed=42)
    engine.state.phase = Phase.NIGHT

    snapshot = build_snapshot_response(
        engine.state,
        game_id=engine.state.game_id,
        human_player_id="p1",
        pending_action=None,
        public_memory={},
        private_memories={},
        wolf_shared_memory={},
        speech_order=[],
        speech_index=0,
        vote_order=[],
        vote_index=0,
        last_node="seer_action",
    )

    assert any(player.role is Role.SEER for player in engine.state.players)
    assert snapshot.current_actor_id is None


def test_snapshot_marks_sheriff_badge_holder() -> None:
    """玩家快照应直接标出警徽持有者，避免前端忘记展示。"""
    engine = WerewolfEngine(_names(), human_player_id="p1", seed=43)
    sheriff_id = engine.state.players[3].player_id
    engine.state.sheriff_id = sheriff_id

    snapshot = build_snapshot_response(
        engine.state,
        game_id=engine.state.game_id,
        human_player_id="p1",
        pending_action=None,
        public_memory={},
        private_memories={},
        wolf_shared_memory={},
        speech_order=[],
        speech_index=0,
        vote_order=[],
        vote_index=0,
        last_node="day_speech_start",
    )

    assert [
        player.player_id
        for player in snapshot.players
        if player.has_sheriff_badge
    ] == [sheriff_id]


def test_human_role_stays_fixed_after_dawn() -> None:
    """真人身份一旦开局确定，推进到天亮后也不应变化。"""
    client = TestClient(create_app())
    start = client.post("/api/games", json={"seed": 1, "player_name": "Tester"}).json()
    game_id = start["game_id"]
    initial_role = _human_role(start)
    current = start

    for _ in range(80):
        assert _human_role(current) == initial_role
        if current["phase"] != "night":
            break
        pending = current.get("pending_action")
        if pending is None:
            current = client.post(f"/api/games/{game_id}/advance").json()
            continue
        if pending["action_type"] in {"werewolf_kill", "seer_check"}:
            payload = {
                "action_type": pending["action_type"],
                "target_id": pending["legal_targets"][0],
            }
        elif pending["action_type"] == "witch_action":
            payload = {"action_type": "witch_action", "save": False}
        else:
            payload = {"action_type": pending["action_type"]}
        current = client.post(f"/api/games/{game_id}/actions", json=payload).json()

    assert current["phase"] != "night"
    assert _human_role(current) == initial_role


def test_submit_speech_action_progresses_snapshot() -> None:
    """游戏等待真人发言时，提交发言应推进快照。"""
    client = TestClient(create_app())

    start = _start_game_with_pending(client, "speak")
    game_id = start["game_id"]
    snapshot = start

    response = client.post(
        f"/api/games/{game_id}/actions",
        json={"action_type": "speak", "speech": "我先听大家发言。"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["game_id"] == game_id
    assert len(payload["events"]) >= len(snapshot["events"])


def test_invalid_action_returns_400() -> None:
    """提交与待行动不匹配的动作应返回 400。"""
    client = TestClient(create_app())

    start = client.post("/api/games", json={"seed": 3, "player_name": "Tester"}).json()
    game_id = start["game_id"]

    response = client.post(
        f"/api/games/{game_id}/actions",
        json={"action_type": "vote", "target_id": "p2"},
    )

    assert response.status_code == 400


def test_online_agent_configuration_error_returns_503(monkeypatch) -> None:
    """未配置在线模型密钥时，AI 行动应明确返回 503。"""
    import app.sessions.manager as manager_module

    client = TestClient(create_app())
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    manager_module.manager._runtime = manager_module.manager._runtime.__class__(
        pending_sink=manager_module.manager._set_pending_action,
        agent_factory=None,
    )
    client = TestClient(create_app())

    start = client.post("/api/games", json={"seed": 42, "player_name": "Tester"}).json()
    response = None
    for _ in range(8):
        response = client.post(f"/api/games/{start['game_id']}/advance")
        if response.status_code == 503:
            break

    assert response is not None
    assert response.status_code == 503


def _drive_until_action(
    client: TestClient,
    game_id: str,
    snapshot: dict,
    action_type: str,
) -> dict:
    """持续提交无害行动，直到出现指定的真人待行动。"""
    current = snapshot
    for _ in range(80):
        pending = current.get("pending_action")
        if pending and pending["action_type"] == action_type:
            return current
        if pending is None:
            current = client.post(f"/api/games/{game_id}/advance").json()
            continue
        if pending["action_type"] == "werewolf_kill":
            payload = {
                "action_type": "werewolf_kill",
                "target_id": pending["legal_targets"][0],
            }
        elif pending["action_type"] == "seer_check":
            payload = {
                "action_type": "seer_check",
                "target_id": pending["legal_targets"][0],
            }
        elif pending["action_type"] == "witch_action":
            payload = {"action_type": "witch_action", "save": False}
        elif pending["action_type"] == "vote":
            payload = {
                "action_type": "vote",
                "target_id": pending["legal_targets"][0],
            }
        elif pending["action_type"] == "sheriff_vote":
            payload = {
                "action_type": "sheriff_vote",
                "target_id": pending["legal_targets"][0] if pending["legal_targets"] else None,
            }
        elif pending["action_type"] == "sheriff_order":
            payload = {
                "action_type": "sheriff_order",
                "direction": "counterclockwise",
            }
        elif pending["action_type"] == "hunter_shot":
            payload = {"action_type": "hunter_shot", "target_id": None}
        elif pending["action_type"] == "idiot_reveal":
            payload = {"action_type": "idiot_reveal", "reveal": True}
        elif pending["action_type"] == "sheriff_handoff":
            payload = {
                "action_type": "sheriff_handoff",
                "target_id": pending["legal_targets"][0] if pending["legal_targets"] else None,
            }
        else:
            payload = {"action_type": pending["action_type"], "speech": "继续观察。"}
        current = client.post(f"/api/games/{game_id}/actions", json=payload).json()
    raise AssertionError(f"Did not reach pending action: {action_type}")


def _start_game_with_pending(client: TestClient, action_type: str) -> dict:
    """寻找能走到指定真人待行动的确定性 seed。"""
    for seed in range(1, 80):
        start = client.post(
            "/api/games",
            json={"seed": seed, "player_name": "Tester"},
        ).json()
        game_id = start["game_id"]
        try:
            return _drive_until_action(client, game_id, start, action_type)
        except AssertionError:
            continue
    raise AssertionError(f"No seed reached pending action: {action_type}")


def _human_role(snapshot: dict) -> str:
    """返回当前快照中真人玩家可见身份。"""
    human = next(
        player
        for player in snapshot["players"]
        if player["player_id"] == snapshot["human_player_id"]
    )
    return str(human["role"])


def _names() -> list[str]:
    """返回 12 人标准局测试昵称。"""
    return [
        "Tester",
        "AI A",
        "AI B",
        "AI C",
        "AI D",
        "AI E",
        "AI F",
        "AI G",
        "AI H",
        "AI I",
        "AI J",
        "AI K",
    ]
