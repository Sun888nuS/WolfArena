import type { GameEvent, PublicPlayer } from "../../types/game";

export type ReviewTab = "timeline" | "night" | "speeches" | "votes" | "roles";

export interface ReviewTimelineItem {
  event: GameEvent;
  index: number;
  description: string;
}

export function buildReviewTimeline(
  events: GameEvent[],
  playersById: Map<string, PublicPlayer>,
): ReviewTimelineItem[] {
  return events
    .map((event, index) => ({
      event,
      index,
      description: describeReviewEvent(event, playersById),
    }))
    .filter(({ description }) => description !== "");
}

export function filterReviewItems(
  items: ReviewTimelineItem[],
  tab: ReviewTab,
): ReviewTimelineItem[] {
  if (tab === "night") return items.filter(({ event }) => isNightReviewEvent(event.type));
  if (tab === "speeches") return items.filter(({ event }) => event.type === "day.speech_recorded");
  if (tab === "votes") return items.filter(({ event }) => isVoteReviewEvent(event.type));
  return items;
}

export function hasForcedFinish(events: GameEvent[]): boolean {
  return events.some((event) => event.type === "game.forced_finish");
}

export function describeReviewEvent(
  event: GameEvent,
  playersById: Map<string, PublicPlayer>,
): string {
  const payload = event.payload;
  if (event.type === "role.assigned") return "";
  if (event.type === "game.created") return "创建 12 人标准局。";
  if (event.type === "night.started") return `第 ${payload.round ?? event.round_no} 轮夜晚开始。`;
  if (event.type === "night.werewolf_kill_intent_recorded") {
    return payload.target_id
      ? `刀人意向：${playerName(String(payload.target_id), playersById)}`
      : "狼人提交了刀人意向。";
  }
  if (event.type === "night.werewolf_consensus_required") {
    return `狼队意向不一致：${formatIntentMap(payload.intents, playersById)}`;
  }
  if (event.type === "night.werewolf_kill_selected") {
    return `狼人选择袭击 ${playerName(String(payload.target_id ?? ""), playersById)}`;
  }
  if (event.type === "night.seer_checked") {
    return `预言家查验 ${playerName(String(payload.target_id ?? ""), playersById)}，结果为 ${alignmentLabel(String(payload.alignment ?? ""))}`;
  }
  if (event.type === "night.witch_acted") {
    return describeWitchEvent(payload, playersById);
  }
  if (event.type === "night.hunter_status_confirmed") {
    return Boolean(payload.can_shoot) ? "猎人确认可以开枪。" : "猎人确认本轮不能开枪。";
  }
  if (event.type === "night.idiot_confirmed") return "白痴确认身份。";
  if (event.type === "night.resolved") {
    const dead = payload.dead_player_ids;
    const reasons = isRecord(payload.death_reasons) ? payload.death_reasons : {};
    if (!Array.isArray(dead) || dead.length === 0) return "昨夜平安夜。";
    return `昨夜死亡：${dead
      .map((id) => {
        const playerId = String(id);
        const reason = typeof reasons[playerId] === "string" ? `（${deathReasonLabel(reasons[playerId])}）` : "";
        return `${playerName(playerId, playersById)}${reason}`;
      })
      .join("、")}`;
  }
  if (event.type === "death.reaction_resolved") {
    return payload.hunter_shot === false ? "猎人没有开枪。" : "死亡技能结算完成。";
  }
  if (event.type === "death.hunter_shot") {
    return `猎人开枪带走 ${playerName(String(payload.target_id ?? ""), playersById)}`;
  }
  if (event.type === "death.idiot_revealed") return "白痴翻牌，继续发言但失去投票权。";
  if (event.type === "sheriff.election_started") return "警长竞选开始。";
  if (event.type === "sheriff.candidates_set") {
    return `警上玩家：${formatPlayerList(payload.candidate_ids, playersById)}`;
  }
  if (event.type === "sheriff.vote_recorded") {
    return payload.target_id
      ? `警长票投给 ${playerName(String(payload.target_id), playersById)}${formatVoteReason(payload)}`
      : `警长投票弃票${formatVoteReason(payload)}`;
  }
  if (event.type === "sheriff.vote_resolved") {
    const tied = payload.tied_player_ids;
    const result = payload.sheriff_id
      ? `${playerName(String(payload.sheriff_id), playersById)} 当选警长`
      : Array.isArray(tied) && tied.length > 0
        ? `平票：${formatPlayerList(tied, playersById)}`
        : "无人当选警长";
    return `${result}。${formatTally(payload.tally, playersById)}`;
  }
  if (event.type === "sheriff.assigned") {
    return `${playerName(String(payload.sheriff_id ?? ""), playersById)} 获得警徽。`;
  }
  if (event.type === "sheriff.badge_lost") {
    return `警徽流失${payload.reason ? `（${sheriffBadgeLostReasonLabel(String(payload.reason))}）` : ""}。`;
  }
  if (event.type === "sheriff.handed_off") {
    return `警徽移交给 ${playerName(String(payload.target_id ?? ""), playersById)}`;
  }
  if (event.type === "day.speech_recorded") return String(payload.speech ?? "");
  if (event.type === "day.vote_recorded") {
    return payload.target_id
      ? `放逐票投给 ${playerName(String(payload.target_id), playersById)}${formatVoteReason(payload)}`
      : `放逐投票弃票${formatVoteReason(payload)}`;
  }
  if (event.type === "day.vote_resolved") {
    const tied = payload.tied_player_ids;
    const result = payload.exiled_player_id
      ? `${playerName(String(payload.exiled_player_id), playersById)} 被放逐`
      : Array.isArray(tied) && tied.length > 0
        ? `平票：${formatPlayerList(tied, playersById)}`
        : "无人出局";
    return `${result}。${formatTally(payload.tally, playersById)}`;
  }
  if (event.type === "day.pk_started") {
    return `进入 PK：${formatPlayerList(payload.tied_player_ids, playersById)}`;
  }
  if (event.type === "day.no_exile") return "再次平票或无人得票，今日无人出局。";
  if (event.type === "day.werewolf_self_exploded") return "狼人自爆出局，跳过白天进入黑夜。";
  if (event.type === "game.win_checked") {
    return payload.winner ? `胜者：${winnerLabel(String(payload.winner))}` : "";
  }
  if (event.type === "game.next_round_started") {
    return `进入第 ${payload.round ?? event.round_no} 轮。`;
  }
  if (event.type === "game.forced_finish") return "玩家手动结束对局，复盘展示当前已有记录。";
  return "";
}

export function eventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    "game.created": "创建对局",
    "night.started": "夜晚开始",
    "night.werewolf_kill_intent_recorded": "狼人意向",
    "night.werewolf_consensus_required": "狼队统一",
    "night.werewolf_kill_selected": "狼人行动",
    "night.seer_checked": "预言家查验",
    "night.witch_acted": "女巫行动",
    "night.hunter_status_confirmed": "猎人确认",
    "night.idiot_confirmed": "白痴确认",
    "night.resolved": "夜晚结算",
    "death.reaction_resolved": "死亡结算",
    "death.hunter_shot": "猎人开枪",
    "death.idiot_revealed": "白痴翻牌",
    "sheriff.election_started": "警长竞选",
    "sheriff.candidates_set": "警上名单",
    "sheriff.vote_recorded": "警长投票",
    "sheriff.vote_resolved": "警长结算",
    "sheriff.assigned": "警长产生",
    "sheriff.badge_lost": "警徽流失",
    "sheriff.handed_off": "警徽移交",
    "day.speech_recorded": "玩家发言",
    "day.vote_recorded": "投票",
    "day.vote_resolved": "投票结算",
    "day.pk_started": "平票 PK",
    "day.no_exile": "无人出局",
    "day.werewolf_self_exploded": "狼人自爆",
    "game.win_checked": "胜负检查",
    "game.next_round_started": "新回合",
    "game.forced_finish": "手动结束",
  };
  return labels[type] ?? "游戏事件";
}

export function phaseLabel(phase?: string): string {
  if (phase === "night") return "夜晚";
  if (phase === "sheriff_election") return "警长竞选";
  if (phase === "day_speech") return "白天发言";
  if (phase === "day_vote") return "白天投票";
  if (phase === "exile_pk_speech") return "PK 发言";
  if (phase === "exile_pk_vote") return "PK 投票";
  if (phase === "game_over") return "游戏结束";
  return "未开始";
}

export function roleLabel(role: string): string {
  if (role === "werewolf") return "狼人";
  if (role === "seer") return "预言家";
  if (role === "witch") return "女巫";
  if (role === "hunter") return "猎人";
  if (role === "idiot") return "白痴";
  if (role === "villager") return "村民";
  return "未知身份";
}

export function alignmentLabel(alignment: string): string {
  if (alignment === "werewolves") return "狼人阵营";
  if (alignment === "villagers") return "好人阵营";
  return "未知阵营";
}

export function winnerLabel(winner: string | null): string {
  if (winner === "werewolves") return "狼人阵营";
  if (winner === "villagers") return "好人阵营";
  return "未决出胜者";
}

export function deathReasonLabel(reason: string): string {
  if (reason === "werewolf_kill") return "狼人袭击";
  if (reason === "witch_poison") return "女巫毒杀";
  if (reason === "exile") return "放逐";
  if (reason === "hunter_shot") return "猎人开枪";
  if (reason === "self_explode") return "狼人自爆";
  return "出局";
}

export function playerName(playerId: string, playersById: Map<string, PublicPlayer>): string {
  const player = playersById.get(playerId);
  return player ? `${player.seat} 号 ${player.name}` : playerId || "无";
}

function isNightReviewEvent(type: string): boolean {
  return type.startsWith("night.") || type.startsWith("death.");
}

function isVoteReviewEvent(type: string): boolean {
  return [
    "sheriff.vote_recorded",
    "sheriff.vote_resolved",
    "day.vote_recorded",
    "day.vote_resolved",
    "day.pk_started",
    "day.no_exile",
  ].includes(type);
}

function describeWitchEvent(
  payload: Record<string, unknown>,
  playersById: Map<string, PublicPlayer>,
): string {
  const usedSave = Boolean(payload.save);
  const savedPlayer = typeof payload.saved_player_id === "string" ? payload.saved_player_id : "";
  const attackedPlayer = typeof payload.attacked_player_id === "string" ? payload.attacked_player_id : "";
  const poisonTarget = typeof payload.poison_target_id === "string" ? payload.poison_target_id : "";
  const parts = [];
  if (usedSave) {
    parts.push(`女巫使用解药救了 ${playerName(savedPlayer || attackedPlayer, playersById)}`);
  }
  if (poisonTarget) {
    parts.push(`女巫毒杀 ${playerName(poisonTarget, playersById)}`);
  }
  if (parts.length) return `${parts.join("，")}。`;
  return "女巫没有使用药。";
}

function formatPlayerList(value: unknown, playersById: Map<string, PublicPlayer>): string {
  if (!Array.isArray(value) || value.length === 0) return "无";
  return value.map((id) => playerName(String(id), playersById)).join("、");
}

function formatIntentMap(value: unknown, playersById: Map<string, PublicPlayer>): string {
  if (!isRecord(value) || Object.keys(value).length === 0) return "暂无明细";
  return Object.entries(value)
    .map(([actorId, targetId]) => `${playerName(actorId, playersById)} -> ${playerName(String(targetId), playersById)}`)
    .join("、");
}

function formatTally(value: unknown, playersById: Map<string, PublicPlayer>): string {
  if (!isRecord(value) || Object.keys(value).length === 0) return "票型：无人得票";
  const rows = Object.entries(value)
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .map(([targetId, count]) => `${playerName(targetId, playersById)} ${formatVoteCount(Number(count))} 票`);
  return `票型：${rows.join("、")}`;
}

function formatVoteCount(count: number): string {
  return Number.isInteger(count) ? String(count) : count.toFixed(1).replace(/\.0$/, "");
}

function formatVoteReason(payload: Record<string, unknown>): string {
  const reason = String(payload.public_reason ?? "").trim();
  const score = payload.reasoning_score;
  const parts = [
    reason ? `理由：${reason}` : "",
    typeof score === "number" ? `评分：${score}` : "",
  ].filter(Boolean);
  return parts.length ? `（${parts.join("；")}）` : "";
}

function sheriffBadgeLostReasonLabel(reason: string): string {
  if (reason === "tie") return "平票";
  if (reason === "sheriff_dead") return "警长出局";
  if (reason === "self_explode") return "狼人自爆";
  if (reason === "no_candidate") return "无人上警";
  if (reason === "no_vote") return "无人得票";
  return reason;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
