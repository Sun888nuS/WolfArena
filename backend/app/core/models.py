"""确定性规则引擎的核心领域模型。"""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class Alignment(StrEnum):
    """玩家阵营枚举。"""

    VILLAGERS = "villagers"
    WEREWOLVES = "werewolves"


class Role(StrEnum):
    """12 人标准局支持的游戏角色。"""

    WEREWOLF = "werewolf"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    IDIOT = "idiot"
    VILLAGER = "villager"

    @property
    def alignment(self) -> Alignment:
        """根据角色返回所属阵营。"""
        if self is Role.WEREWOLF:
            return Alignment.WEREWOLVES
        return Alignment.VILLAGERS

    @property
    def is_power_role(self) -> bool:
        """返回该角色是否属于神民。"""
        return self in {Role.SEER, Role.WITCH, Role.HUNTER, Role.IDIOT}


class Phase(StrEnum):
    """游戏阶段枚举。"""

    NIGHT = "night"
    SHERIFF_ELECTION = "sheriff_election"
    DAY_SPEECH = "day_speech"
    DAY_VOTE = "day_vote"
    EXILE_PK_SPEECH = "exile_pk_speech"
    EXILE_PK_VOTE = "exile_pk_vote"
    GAME_OVER = "game_over"


class EventVisibility(StrEnum):
    """事件可见范围枚举。"""

    PUBLIC = "public"
    PRIVATE = "private"
    WEREWOLVES = "werewolves"


class Winner(StrEnum):
    """获胜阵营枚举。"""

    VILLAGERS = "villagers"
    WEREWOLVES = "werewolves"


class DeathReason(StrEnum):
    """玩家出局原因。"""

    WEREWOLF_KILL = "werewolf_kill"
    WITCH_POISON = "witch_poison"
    EXILE = "exile"
    HUNTER_SHOT = "hunter_shot"
    SELF_EXPLODE = "self_explode"


class EventType(StrEnum):
    """领域事件类型枚举。"""

    GAME_CREATED = "game.created"
    ROLE_ASSIGNED = "role.assigned"
    NIGHT_STARTED = "night.started"
    WEREWOLF_KILL_INTENT_RECORDED = "night.werewolf_kill_intent_recorded"
    WEREWOLF_CONSENSUS_REQUIRED = "night.werewolf_consensus_required"
    WEREWOLF_KILL_SELECTED = "night.werewolf_kill_selected"
    SEER_CHECKED = "night.seer_checked"
    WITCH_ACTED = "night.witch_acted"
    HUNTER_STATUS_CONFIRMED = "night.hunter_status_confirmed"
    IDIOT_CONFIRMED = "night.idiot_confirmed"
    NIGHT_RESOLVED = "night.resolved"
    DEATH_REACTION_RESOLVED = "death.reaction_resolved"
    HUNTER_SHOT = "death.hunter_shot"
    IDIOT_REVEALED = "death.idiot_revealed"
    SHERIFF_ELECTION_STARTED = "sheriff.election_started"
    SHERIFF_CANDIDATES_SET = "sheriff.candidates_set"
    SHERIFF_VOTE_RECORDED = "sheriff.vote_recorded"
    SHERIFF_VOTE_RESOLVED = "sheriff.vote_resolved"
    SHERIFF_ASSIGNED = "sheriff.assigned"
    SHERIFF_BADGE_LOST = "sheriff.badge_lost"
    SHERIFF_HANDED_OFF = "sheriff.handed_off"
    WEREWOLF_SELF_EXPLODED = "day.werewolf_self_exploded"
    SPEECH_RECORDED = "day.speech_recorded"
    VOTE_RECORDED = "day.vote_recorded"
    VOTE_RESOLVED = "day.vote_resolved"
    PK_STARTED = "day.pk_started"
    NO_EXILE = "day.no_exile"
    WIN_CHECKED = "game.win_checked"
    NEXT_ROUND_STARTED = "game.next_round_started"
    GAME_FORCED_FINISH = "game.forced_finish"


@dataclass(slots=True)
class PlayerState:
    """单个玩家的可变规则状态。"""

    player_id: str
    name: str
    role: Role
    seat: int
    is_human: bool = False
    alive: bool = True
    can_vote: bool = True
    can_speak_after_death: bool = False
    revealed_role: bool = False
    dead_reason: DeathReason | None = None

    @property
    def alignment(self) -> Alignment:
        """返回玩家所属阵营。"""
        return self.role.alignment

    @property
    def can_speak(self) -> bool:
        """返回玩家当前是否可以参与白天发言。"""
        return self.alive or self.can_speak_after_death


@dataclass(slots=True)
class GameEvent:
    """游戏事件记录，用于公开信息、私有信息和复盘。"""

    event_type: EventType
    round_no: int
    phase: Phase
    visibility: EventVisibility
    payload: dict[str, object]
    actor_id: str | None = None
    recipients: tuple[str, ...] = ()


@dataclass(slots=True)
class WitchState:
    """女巫药剂状态。"""

    has_antidote: bool = True
    has_poison: bool = True


@dataclass(slots=True)
class NightActionBuffer:
    """夜晚结算前暂存的所有夜间行动。"""

    werewolf_actor_id: str | None = None
    werewolf_target_id: str | None = None
    werewolf_intents: dict[str, str] = field(default_factory=dict)
    werewolf_intent_round: int = 1
    seer_actor_id: str | None = None
    seer_target_id: str | None = None
    witch_actor_id: str | None = None
    witch_save: bool = False
    witch_poison_target_id: str | None = None
    hunter_actor_id: str | None = None
    idiot_actor_id: str | None = None


@dataclass(slots=True)
class VoteRecord:
    """单个玩家的一次投票记录。"""

    voter_id: str
    target_id: str | None
    weight: float = 1.0
    public_reason: str = ""
    reasoning_score: int | None = None


@dataclass(slots=True)
class VoteResult:
    """投票结算结果。"""

    tally: dict[str, float]
    exiled_player_id: str | None
    tied_player_ids: tuple[str, ...] = ()
    no_exile: bool = False


@dataclass(slots=True)
class GameState:
    """规则引擎持有的完整真相状态。"""

    players: list[PlayerState]
    game_id: str = field(default_factory=lambda: uuid4().hex)
    round_no: int = 1
    phase: Phase = Phase.NIGHT
    events: list[GameEvent] = field(default_factory=list)
    witch_state: WitchState = field(default_factory=WitchState)
    night_actions: NightActionBuffer = field(default_factory=NightActionBuffer)
    votes: dict[str, VoteRecord] = field(default_factory=dict)
    sheriff_votes: dict[str, VoteRecord] = field(default_factory=dict)
    seer_results: dict[str, dict[str, Alignment]] = field(default_factory=dict)
    vote_history: list[VoteResult] = field(default_factory=list)
    winner: Winner | None = None
    hunter_shot_used: bool = False
    idiot_revealed: bool = False
    sheriff_id: str | None = None
    sheriff_badge_lost: bool = False
    sheriff_election_done: bool = False
    sheriff_election_self_explode_count: int = 0
    sheriff_candidate_ids: tuple[str, ...] = ()
    sheriff_tied_candidate_ids: tuple[str, ...] = ()
    pk_tied_player_ids: tuple[str, ...] = ()
    last_dead_player_ids: tuple[str, ...] = ()
    last_exiled_player_id: str | None = None

    @property
    def is_over(self) -> bool:
        """返回游戏是否已经结束且已有胜利阵营。"""
        return self.phase is Phase.GAME_OVER and self.winner is not None
