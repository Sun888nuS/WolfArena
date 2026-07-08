/** 大模型配置的脱敏健康状态。 */
export interface LlmConfigStatus {
  provider: string; // provider 名称
  base_url: string; // 中转站基础地址
  model: string; // 当前模型名
  api_key_configured: boolean; // 是否已配置密钥
  api_key_preview: string; // 脱敏后的密钥预览
  timeout_seconds: number; // 请求超时时间
  status?: string; // 前端可展示的简短状态
}

/** 更新大模型运行时配置时提交的请求体。 */
export interface UpdateLlmConfigPayload {
  base_url: string; // OpenAI-compatible API 基础地址
  model: string; // 模型名称
  api_key?: string; // API Key；留空时后端保留当前密钥
}

/** 健康检查接口响应。 */
export interface HealthResponse {
  status: string; // 服务状态
  app_name: string; // 应用名
  app_version: string; // 应用版本
  app_env: string; // 运行环境
  checked_at: string; // 检查时间
  llm: LlmConfigStatus; // 大模型配置状态
}
