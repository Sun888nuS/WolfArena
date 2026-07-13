import type { GameSnapshot, SubmitActionPayload } from "../types/game";
import type { LlmConfigStatus, UpdateLlmConfigPayload } from "../types/health";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000"; // 后端 HTTP 基础地址

/** 创建一局新游戏，并返回初始快照。 */
export async function startGame(playerName: string): Promise<GameSnapshot> {
  const response = await fetch(`${API_BASE_URL}/api/games`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_name: playerName }),
  });
  if (!response.ok) {
    throw new Error(`创建游戏失败：${response.status}`);
  }
  return (await response.json()) as GameSnapshot;
}

/** 拉取当前后端进程中仍存在的游戏 id 列表。 */
export async function listGames(): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/api/games`);
  if (!response.ok) {
    throw new Error(`获取游戏列表失败：${response.status}`);
  }
  const payload = (await response.json()) as { game_ids: string[] };
  return payload.game_ids;
}

/** 根据游戏 id 读取当前快照。 */
export async function getGame(gameId: string): Promise<GameSnapshot> {
  const response = await fetch(`${API_BASE_URL}/api/games/${gameId}`);
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `读取游戏失败：${response.status}`);
  }
  return (await response.json()) as GameSnapshot;
}

/** 请求后端推进一个 LangGraph 节点。 */
export async function advanceGame(gameId: string): Promise<GameSnapshot> {
  const response = await fetch(`${API_BASE_URL}/api/games/${gameId}/advance`, {
    method: "POST",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `推进游戏失败：${response.status}`);
  }
  return (await response.json()) as GameSnapshot;
}

/** 强制结束当前游戏，并保留已有事件用于复盘。 */
export async function finishGame(gameId: string): Promise<GameSnapshot> {
  const response = await fetch(`${API_BASE_URL}/api/games/${gameId}/finish`, {
    method: "POST",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `结束游戏失败：${response.status}`);
  }
  return (await response.json()) as GameSnapshot;
}

/** 提交真人玩家行动，并返回恢复后的游戏快照。 */
export async function submitAction(
  gameId: string,
  payload: SubmitActionPayload,
): Promise<GameSnapshot> {
  const response = await fetch(`${API_BASE_URL}/api/games/${gameId}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `提交行动失败：${response.status}`);
  }
  return (await response.json()) as GameSnapshot;
}

/** 读取后端当前使用的大模型运行时配置。 */
export async function getLlmConfig(): Promise<LlmConfigStatus> {
  const response = await fetch(`${API_BASE_URL}/api/llm/config`);
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `读取模型配置失败：${response.status}`);
  }
  return (await response.json()) as LlmConfigStatus;
}

/** 更新后端后续 Agent 调用使用的大模型运行时配置。 */
export async function updateLlmConfig(payload: UpdateLlmConfigPayload): Promise<LlmConfigStatus> {
  const response = await fetch(`${API_BASE_URL}/api/llm/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `保存模型配置失败：${response.status}`);
  }
  return (await response.json()) as LlmConfigStatus;
}

/** 根据 HTTP 基础地址拼出同源 WebSocket 快照订阅地址。 */
export function gameWebSocketUrl(gameId: string): string {
  const base = new URL(API_BASE_URL);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = `/ws/games/${gameId}`;
  base.search = "";
  return base.toString();
}
