import type { HealthResponse } from "../types/health";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/** 读取后端健康检查和脱敏配置状态。 */
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  if (!response.ok) {
    throw new Error(`健康检查失败：${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}
