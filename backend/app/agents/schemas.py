"""AI 结构化决策数据结构。"""

from typing import Literal

from pydantic import BaseModel, Field


ActionType = Literal[
    "werewolf_kill_intent",
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


class AgentDecision(BaseModel):
    """单个 AI 玩家返回的结构化候选决策。"""

    action_type: ActionType  # 动作类型
    target_id: str | None = Field(default=None)  # 通用目标玩家 id
    speech: str = Field(default="", max_length=240)  # 白天公开发言
    public_reason: str = Field(default="", max_length=240)  # 可公开展示的理由
    thought_summary: str = Field(default="", max_length=240)  # 简短私有策略摘要
    memory_note: str = Field(default="", max_length=240)  # 写入合法记忆的短备注
    suspicion_scores: dict[str, int] = Field(default_factory=dict)  # 对合法目标的怀疑分
    confidence: int = Field(default=50, ge=0, le=100)  # 决策置信度
    save: bool = False  # 女巫是否使用解药
    poison_target_id: str | None = None  # 女巫毒药目标
    direction: Literal["clockwise", "counterclockwise"] | None = None  # 警长指定的发言方向
