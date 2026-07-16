/** 前端可见的单个玩家状态。 */
export interface PublicPlayer {
  player_id: string; // 玩家 id
  name: string; // 玩家昵称
  seat: number; // 座位号
  alive: boolean; // 是否存活
  is_human: boolean; // 是否真人玩家
  role: string | null; // 当前视角可见的身份
  alignment: string | null; // 当前视角可见的阵营
  can_vote: boolean; // 是否仍有投票权
  can_speak: boolean; // 是否仍可发言
  revealed_role: boolean; // 是否已公开翻牌
  dead_reason: string | null; // 出局原因
  has_sheriff_badge: boolean; // 是否持有警徽
}

/** 真人玩家视角可见的一条领域事件。 */
export interface GameEvent {
  type: string; // 事件类型
  round_no: number; // 事件发生轮次
  phase: string; // 事件发生阶段
  actor_id: string | null; // 行动者 id
  visibility: string; // 事件可见范围
  payload: Record<string, unknown>; // 事件负载
}

/** 后端正在等待真人玩家完成的行动。 */
export interface PendingAction {
  action_type: string; // 行动类型
  player_id: string; // 需要行动的玩家 id
  prompt: string; // 操作提示
  legal_targets: string[]; // 可选择目标 id 列表
  can_save: boolean; // 女巫是否可以救人
  can_poison: boolean; // 女巫是否可以毒人
  attacked_player_id: string | null; // 女巫可见的刀口玩家 id
  can_skip: boolean; // 特殊行动是否可跳过
}

/** 主持流程进度条的单个步骤。 */
export interface GodStep {
  key: string; // 步骤唯一 key
  label: string; // 中文展示名
  status: "done" | "active" | "pending"; // 步骤状态
}

/** 中央主持播报及自动推进节奏。 */
export interface HostCue {
  cue_id: string; // 播报节点稳定 id，用于同步文字、语音和自动推进
  message: string; // 主持主文案
  follow_up_message: string | null; // 同一节点内的补充播报，例如闭眼
  voice_key: string | null; // 主文案固定语音 key
  follow_up_voice_key: string | null; // 补充播报固定语音 key
  voice_pause_ms: number; // 主语音结束后到补充语音开始前的停顿
  hold_ms: number; // 自动推进前建议停留时间
  visible: boolean; // false 时保留上一条玩家可见播报
  blocks_auto_advance: boolean; // 是否等待语音队列结束后再自动推进
}

/** 单局游戏的完整前端快照。 */
/** 真人视角的游戏辅助面板条目。 */
export interface AssistantPanelItem {
  label: string;
  value: string;
  tone: "default" | "good" | "bad" | "warning" | "muted";
}

/** 根据真人身份生成的局内辅助面板。 */
export interface AssistantPanelData {
  role: string;
  title: string;
  summary: string;
  items: AssistantPanelItem[];
}

export interface GameSnapshot {
  game_id: string; // 游戏 id
  human_player_id: string; // 真人玩家 id
  phase: string; // 当前阶段
  round_no: number; // 当前轮次
  winner: string | null; // 胜者阵营
  players: PublicPlayer[]; // 玩家列表
  events: GameEvent[]; // 可见事件流
  review_events: GameEvent[]; // 游戏结束后的全量复盘事件流
  pending_action: PendingAction | null; // 待真人行动
  known_werewolves: string[]; // 真人狼人可见队友
  seer_results: Record<string, string>; // 真人预言家查验结果
  llm_status: string; // 大模型配置状态
  god_message: string; // 兼容旧前端的主持播报文案
  host_cue?: HostCue; // 中央主持播报
  god_steps: GodStep[]; // 流程进度条
  assistant_panel: AssistantPanelData; // 真人视角游戏辅助面板
  current_actor_id: string | null; // 当前高亮行动者 id
  sheriff_id: string | null; // 当前警长 id
  sheriff_badge_lost: boolean; // 警徽是否流失
  pk_tied_player_ids: string[]; // 当前 PK 玩家
}

/** AI 玩家公开发言的 WebSocket 流式预览消息。 */
export interface AgentReplyStreamMessage {
  type:
    | "agent_reply_started"
    | "agent_reply_delta"
    | "agent_reply_completed"
    | "agent_reply_failed"; // 流式发言消息类型
  game_id: string; // 游戏 id
  player_id: string; // 正在发言的 AI 玩家 id
  stream_id: string; // 单次发言流 id
  text: string; // 当前已生成的发言文本
  node: string; // 触发发言的图节点
  round_no: number; // 发生轮次
  phase: string; // 发生阶段
}

/** 真人玩家提交行动时发送给后端的请求体。 */
export interface SubmitActionPayload {
  action_type: string; // 行动类型
  target_id?: string | null; // 通用目标玩家 id
  speech?: string; // 白天发言内容
  save?: boolean; // 女巫是否使用解药
  poison_target_id?: string | null; // 女巫毒药目标 id
  reveal?: boolean; // 白痴是否翻牌
  direction?: "clockwise" | "counterclockwise"; // 警长指定发言方向
}
