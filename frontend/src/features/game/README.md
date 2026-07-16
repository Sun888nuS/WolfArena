# frontend/src/features/game

狼人杀主游戏界面目录，负责当前可玩的桌面体验：开局、恢复对局、WebSocket 快照、真人行动、主持播报、背景音乐、固定语音、模型配置、事件流和复盘入口。

## 文件分工

- `GamePage.tsx` 是主页面组件，连接后端快照、订阅 WebSocket、自动推进游戏、提交真人行动，并渲染玩家桌面、行动面板、辅助面板、事件流、规则弹窗、模型设置和复盘弹窗。
- `useBackgroundAudio.ts` 根据游戏阶段选择 `day`、`night`、`vote` 背景音乐，处理音量、淡入淡出、发言降音和浏览器自动播放限制。

## 关键数据来源

- HTTP 请求来自 `frontend/src/services/game.ts`。
- 快照和提交行动类型来自 `frontend/src/types/game.ts`。
- 主持语音由 `snapshot.host_cue.voice_key` 和 `features/voice/useHostVoice.ts` 播放。
- 复盘弹窗来自 `frontend/src/features/review/`。

## 常见修改入口

- 改游戏桌面、玩家卡片、行动面板、事件流或规则弹窗：改 `GamePage.tsx`。
- 改提交给后端的行动 payload：改 `GamePage.tsx` 的 `buildPayload`，并同步 `types/game.ts` 和后端 `SubmitActionRequest`。
- 改阶段、身份、阵营、死亡原因或事件文案：改 `GamePage.tsx` 中的 label/describe 函数，必要时同步复盘文案。
- 改背景音乐逻辑：改 `useBackgroundAudio.ts`，必要时同步后端 `backend/app/voice/background_audio.py`。
- 改样式：当前主要在 `frontend/src/app/styles.css`。

## 拆分建议

`GamePage.tsx` 已经很大。后续扩展时建议逐步拆出：

- `components/`：`PlayerTable`、`PlayerCard`、`ActionPanel`、`EventFeed`、`RulesDialog`、`LlmSettingsDialog`。
- `hooks/`：恢复游戏、WebSocket 订阅、自动推进和本地设置持久化。
- `labels.ts`：阶段、身份、阵营、事件类型文案。
- `payload.ts`：真人行动表单到后端请求体的转换。
