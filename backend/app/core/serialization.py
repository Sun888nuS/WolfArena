"""规则引擎状态的 JSON 安全序列化工具。"""

from app.core.models import (
    Alignment,
    DeathReason,
    EventType,
    EventVisibility,
    GameEvent,
    GameState,
    NightActionBuffer,
    Phase,
    PlayerState,
    Role,
    VoteRecord,
    VoteResult,
    Winner,
    WitchState,
)


def serialize_game_state(state: GameState) -> dict[str, object]:
    """把 GameState 转换成 LangGraph 可保存的 JSON 安全字典。"""
    return {
        "game_id": state.game_id,
        "round_no": state.round_no,
        "phase": state.phase.value,
        "winner": state.winner.value if state.winner else None,
        "players": [
            {
                "player_id": player.player_id,
                "name": player.name,
                "role": player.role.value,
                "seat": player.seat,
                "is_human": player.is_human,
                "alive": player.alive,
                "can_vote": player.can_vote,
                "can_speak_after_death": player.can_speak_after_death,
                "revealed_role": player.revealed_role,
                "dead_reason": player.dead_reason.value if player.dead_reason else None,
            }
            for player in state.players
        ],
        "events": [
            {
                "event_type": event.event_type.value,
                "round_no": event.round_no,
                "phase": event.phase.value,
                "visibility": event.visibility.value,
                "payload": event.payload,
                "actor_id": event.actor_id,
                "recipients": list(event.recipients),
            }
            for event in state.events
        ],
        "witch_state": {
            "has_antidote": state.witch_state.has_antidote,
            "has_poison": state.witch_state.has_poison,
        },
        "night_actions": {
            "werewolf_actor_id": state.night_actions.werewolf_actor_id,
            "werewolf_target_id": state.night_actions.werewolf_target_id,
            "werewolf_intents": state.night_actions.werewolf_intents,
            "werewolf_intent_round": state.night_actions.werewolf_intent_round,
            "seer_actor_id": state.night_actions.seer_actor_id,
            "seer_target_id": state.night_actions.seer_target_id,
            "witch_actor_id": state.night_actions.witch_actor_id,
            "witch_save": state.night_actions.witch_save,
            "witch_poison_target_id": state.night_actions.witch_poison_target_id,
            "hunter_actor_id": state.night_actions.hunter_actor_id,
            "idiot_actor_id": state.night_actions.idiot_actor_id,
        },
        "votes": {
            voter_id: {
                "voter_id": vote.voter_id,
                "target_id": vote.target_id,
                "weight": vote.weight,
                "public_reason": vote.public_reason,
                "reasoning_score": vote.reasoning_score,
            }
            for voter_id, vote in state.votes.items()
        },
        "sheriff_votes": {
            voter_id: {
                "voter_id": vote.voter_id,
                "target_id": vote.target_id,
                "weight": vote.weight,
                "public_reason": vote.public_reason,
                "reasoning_score": vote.reasoning_score,
            }
            for voter_id, vote in state.sheriff_votes.items()
        },
        "seer_results": {
            seer_id: {target_id: alignment.value for target_id, alignment in results.items()}
            for seer_id, results in state.seer_results.items()
        },
        "vote_history": [
            {
                "tally": result.tally,
                "exiled_player_id": result.exiled_player_id,
                "tied_player_ids": list(result.tied_player_ids),
                "no_exile": result.no_exile,
            }
            for result in state.vote_history
        ],
        "hunter_shot_used": state.hunter_shot_used,
        "idiot_revealed": state.idiot_revealed,
        "sheriff_id": state.sheriff_id,
        "sheriff_badge_lost": state.sheriff_badge_lost,
        "sheriff_election_done": state.sheriff_election_done,
        "sheriff_election_self_explode_count": state.sheriff_election_self_explode_count,
        "sheriff_candidate_ids": list(state.sheriff_candidate_ids),
        "sheriff_tied_candidate_ids": list(state.sheriff_tied_candidate_ids),
        "pk_tied_player_ids": list(state.pk_tied_player_ids),
        "last_dead_player_ids": list(state.last_dead_player_ids),
        "last_exiled_player_id": state.last_exiled_player_id,
    }


def deserialize_game_state(data: dict[str, object]) -> GameState:
    """从 JSON 安全字典恢复 GameState。"""
    players_data = _require_list(data, "players")
    players = [
        PlayerState(
            player_id=str(player["player_id"]),
            name=str(player["name"]),
            role=Role(str(player["role"])),
            seat=int(player["seat"]),
            is_human=bool(player["is_human"]),
            alive=bool(player["alive"]),
            can_vote=bool(player.get("can_vote", player["alive"])),
            can_speak_after_death=bool(player.get("can_speak_after_death", False)),
            revealed_role=bool(player.get("revealed_role", False)),
            dead_reason=DeathReason(str(player["dead_reason"])) if player.get("dead_reason") else None,
        )
        for player in players_data
    ]
    state = GameState(
        players=players,
        game_id=str(data["game_id"]),
        round_no=int(data["round_no"]),
        phase=Phase(str(data["phase"])),
        winner=Winner(str(data["winner"])) if data.get("winner") else None,
    )
    state.events = [
        GameEvent(
            event_type=EventType(str(event["event_type"])),
            round_no=int(event["round_no"]),
            phase=Phase(str(event["phase"])),
            visibility=EventVisibility(str(event["visibility"])),
            payload=dict(event["payload"]),
            actor_id=str(event["actor_id"]) if event.get("actor_id") else None,
            recipients=tuple(str(item) for item in event.get("recipients", [])),
        )
        for event in _require_list(data, "events")
    ]
    witch_state = dict(data.get("witch_state") or {})
    state.witch_state = WitchState(
        has_antidote=bool(witch_state.get("has_antidote", True)),
        has_poison=bool(witch_state.get("has_poison", True)),
    )
    night_actions = dict(data.get("night_actions") or {})
    state.night_actions = NightActionBuffer(
        werewolf_actor_id=_optional_str(night_actions.get("werewolf_actor_id")),
        werewolf_target_id=_optional_str(night_actions.get("werewolf_target_id")),
        werewolf_intents={
            str(actor_id): str(target_id)
            for actor_id, target_id in dict(night_actions.get("werewolf_intents") or {}).items()
        },
        werewolf_intent_round=int(night_actions.get("werewolf_intent_round", 1)),
        seer_actor_id=_optional_str(night_actions.get("seer_actor_id")),
        seer_target_id=_optional_str(night_actions.get("seer_target_id")),
        witch_actor_id=_optional_str(night_actions.get("witch_actor_id")),
        witch_save=bool(night_actions.get("witch_save", False)),
        witch_poison_target_id=_optional_str(night_actions.get("witch_poison_target_id")),
        hunter_actor_id=_optional_str(night_actions.get("hunter_actor_id")),
        idiot_actor_id=_optional_str(night_actions.get("idiot_actor_id")),
    )
    state.votes = _deserialize_votes(dict(data.get("votes") or {}))
    state.sheriff_votes = _deserialize_votes(dict(data.get("sheriff_votes") or {}))
    seer_results = dict(data.get("seer_results") or {})
    state.seer_results = {
        str(seer_id): {
            str(target_id): Alignment(str(alignment))
            for target_id, alignment in dict(results).items()
        }
        for seer_id, results in seer_results.items()
    }
    state.vote_history = [
        VoteResult(
            tally={str(target_id): float(count) for target_id, count in dict(result["tally"]).items()},
            exiled_player_id=_optional_str(result.get("exiled_player_id")),
            tied_player_ids=tuple(str(item) for item in result.get("tied_player_ids", [])),
            no_exile=bool(result.get("no_exile", False)),
        )
        for result in _require_list(data, "vote_history")
    ]
    state.hunter_shot_used = bool(data.get("hunter_shot_used", False))
    state.idiot_revealed = bool(data.get("idiot_revealed", False))
    state.sheriff_id = _optional_str(data.get("sheriff_id"))
    state.sheriff_badge_lost = bool(data.get("sheriff_badge_lost", False))
    state.sheriff_election_done = bool(data.get("sheriff_election_done", False))
    state.sheriff_election_self_explode_count = int(data.get("sheriff_election_self_explode_count", 0))
    state.sheriff_candidate_ids = tuple(str(item) for item in data.get("sheriff_candidate_ids", []))
    state.sheriff_tied_candidate_ids = tuple(str(item) for item in data.get("sheriff_tied_candidate_ids", []))
    state.pk_tied_player_ids = tuple(str(item) for item in data.get("pk_tied_player_ids", []))
    state.last_dead_player_ids = tuple(str(item) for item in data.get("last_dead_player_ids", []))
    state.last_exiled_player_id = _optional_str(data.get("last_exiled_player_id"))
    return state


def _deserialize_votes(votes: dict[str, object]) -> dict[str, VoteRecord]:
    """恢复投票记录。"""
    records: dict[str, VoteRecord] = {}
    for voter_id, raw_vote in votes.items():
        vote = dict(raw_vote)
        records[str(voter_id)] = VoteRecord(
            voter_id=str(vote["voter_id"]),
            target_id=_optional_str(vote.get("target_id")),
            weight=float(vote.get("weight", 1.0)),
            public_reason=str(vote.get("public_reason", "")),
            reasoning_score=(
                int(vote["reasoning_score"])
                if vote.get("reasoning_score") is not None
                else None
            ),
        )
    return records


def _optional_str(value: object) -> str | None:
    """把非空值转为字符串，同时保留 None。"""
    return str(value) if value is not None else None


def _require_list(data: dict[str, object], key: str) -> list[dict[str, object]]:
    """从序列化状态中读取必要的列表字段。"""
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Serialized game state missing list field: {key}")
    return [dict(item) for item in value]
