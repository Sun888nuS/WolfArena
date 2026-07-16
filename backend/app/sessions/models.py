"""游戏会话 API 数据结构。"""

from typing import Literal

from pydantic import BaseModel, Field


class StartGameRequest(BaseModel):
    """创建新游戏的请求体。"""

    seed: int | None = None  # 可选随机种子，方便测试复现
    player_name: str = Field(default="Sunny", max_length=32)  # 真人玩家昵称


class StartGameResponse(BaseModel):
    """创建游戏后的简要响应。"""

    game_id: str  # 游戏 id
    human_player_id: str  # 真人玩家 id


class GameListResponse(BaseModel):
    """当前进程内仍存在的游戏列表响应。"""

    game_ids: list[str] = Field(default_factory=list)  # 游戏 id 列表


class SubmitActionRequest(BaseModel):
    """真人玩家提交行动的请求体。"""

    action_type: Literal[
        "werewolf_kill",
        "seer_check",
        "witch_action",
        "hunter_shot",
        "idiot_reveal",
        "sheriff_vote",
        "sheriff_run",
        "sheriff_order",
        "sheriff_handoff",
        "werewolf_self_explode",
        "speak",
        "vote",
        "abstain",
    ]
    target_id: str | None = None  # 通用目标玩家 id
    speech: str = Field(default="", max_length=240)  # 白天发言
    save: bool = False  # 女巫是否救人
    poison_target_id: str | None = None  # 女巫毒药目标
    reveal: bool = True  # 白痴被放逐时是否翻牌
    direction: Literal["clockwise", "counterclockwise"] | None = None  # 警长指定发言方向


class PublicPlayerResponse(BaseModel):
    """前端可见的玩家状态。"""

    player_id: str  # 玩家 id
    name: str  # 玩家昵称
    seat: int  # 座位号
    alive: bool  # 是否存活
    is_human: bool  # 是否真人
    role: str | None = None  # 当前前端视角可见的角色
    alignment: str | None = None  # 当前前端视角可见的阵营
    can_vote: bool = True  # 是否仍有投票权
    can_speak: bool = True  # 是否仍可发言
    revealed_role: bool = False  # 是否已公开翻牌
    dead_reason: str | None = None  # 出局原因
    has_sheriff_badge: bool = False  # 是否持有警徽


class EventResponse(BaseModel):
    """序列化后的游戏事件响应。"""

    type: str  # 事件类型
    round_no: int  # 轮次
    phase: str  # 事件发生阶段
    actor_id: str | None  # 行动者 id
    visibility: str  # 可见范围
    payload: dict[str, object]  # 事件负载


class PendingActionResponse(BaseModel):
    """当前等待真人玩家完成的行动。"""

    action_type: str  # 等待提交的动作类型
    player_id: str  # 需要行动的真人玩家 id
    prompt: str  # 前端展示提示语
    legal_targets: list[str] = Field(default_factory=list)  # 合法目标列表
    can_save: bool = False  # 女巫是否可救人
    can_poison: bool = False  # 女巫是否可毒人
    attacked_player_id: str | None = None  # 女巫可见刀口
    can_skip: bool = False  # 特殊行动是否允许不发动


class GodStepResponse(BaseModel):
    """前端流程进度条中的一个步骤。"""

    key: str  # 步骤 key
    label: str  # 中文展示名
    status: Literal["done", "active", "pending"]  # 步骤状态


class HostCueResponse(BaseModel):
    """中央主持播报的玩家可见文案和节奏控制。"""

    cue_id: str = ""  # 播报节点稳定 id，用于前端同步语音和自动推进
    message: str = ""  # 主持主文案
    follow_up_message: str | None = None  # 同一流程节点内的补充播报，例如闭眼
    voice_key: str | None = None  # 主文案固定语音 key
    follow_up_voice_key: str | None = None  # 补充播报固定语音 key
    voice_pause_ms: int = 0  # 主语音结束后到补充语音开始前的停顿
    hold_ms: int = 650  # 前端自动推进前建议停留时间
    visible: bool = True  # False 时前端保留上一条玩家可见播报
    blocks_auto_advance: bool = True  # 是否等待语音队列结束后再自动推进


class AssistantPanelItemResponse(BaseModel):
    """真人视角的游戏辅助面板条目。"""

    label: str
    value: str
    tone: Literal["default", "good", "bad", "warning", "muted"] = "default"


class AssistantPanelResponse(BaseModel):
    """根据真人身份生成的局内辅助面板。"""

    role: str
    title: str
    summary: str = ""
    items: list[AssistantPanelItemResponse] = Field(default_factory=list)


class GameSnapshotResponse(BaseModel):
    """单局游戏的前端完整快照。"""

    game_id: str  # 游戏 id
    human_player_id: str  # 真人玩家 id
    phase: str  # 当前阶段
    round_no: int  # 当前轮次
    winner: str | None  # 胜者阵营
    players: list[PublicPlayerResponse]  # 玩家列表
    events: list[EventResponse]  # 真人视角可见事件
    review_events: list[EventResponse] = Field(default_factory=list)  # 游戏结束后可见的全量复盘事件
    pending_action: PendingActionResponse | None  # 待真人行动
    known_werewolves: list[str] = Field(default_factory=list)  # 真人狼人可见队友
    seer_results: dict[str, str] = Field(default_factory=dict)  # 真人预言家查验结果
    llm_status: str = "unknown"  # LLM 配置状态
    god_message: str = ""  # 兼容旧前端的主持播报文案
    host_cue: HostCueResponse = Field(default_factory=HostCueResponse)  # 中央主持播报
    god_steps: list[GodStepResponse] = Field(default_factory=list)  # 流程进度
    assistant_panel: AssistantPanelResponse = Field(
        default_factory=lambda: AssistantPanelResponse(role="", title="游戏辅助")
    )
    current_actor_id: str | None = None  # 当前高亮行动者
    sheriff_id: str | None = None  # 当前警长 id
    sheriff_badge_lost: bool = False  # 警徽是否流失
    pk_tied_player_ids: list[str] = Field(default_factory=list)  # 当前 PK 玩家
