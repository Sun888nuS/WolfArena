"""核心规则层自定义异常。"""


class GameCoreError(ValueError):
    """确定性规则引擎异常的基类。"""


class InvalidActionError(GameCoreError):
    """玩家行动违反规则时抛出。"""


class InvalidPhaseError(GameCoreError):
    """玩家在错误阶段提交行动时抛出。"""
