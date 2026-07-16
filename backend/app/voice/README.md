# backend/app/voice

音频资源接口目录，负责向前端提供白名单内的背景音乐和固定主持语音文件。

## 文件分工

- `background_audio.py` 挂载 `/api/voice/background`，提供 `day`、`night`、`vote` 三类背景音乐及 manifest。
- `host_voice.py` 挂载 `/api/voice/host/fixed`，提供固定主持语音文件及 manifest。
- `__init__.py` 保留包初始化。

## 资源查找

两个路由都会在本地开发路径和容器路径之间查找音频资源。请求时只允许访问代码中列出的 key，避免把任意文件路径暴露给前端。

## 常见修改入口

- 新增背景音乐类型：改 `background_audio.py` 的白名单，并同步 `frontend/src/services/game.ts` 和 `features/game/useBackgroundAudio.ts`。
- 新增固定主持语音：改 `host_voice.py` 的白名单，并在 `sessions/snapshots.py` 里使用对应 `voice_key`。
- 调整前端播放队列、音量或自动推进等待：改 `frontend/src/features/voice/useHostVoice.ts` 和 `frontend/src/features/game/useBackgroundAudio.ts`。

## 维护边界

`voice` 只提供音频资源，不判断游戏阶段，也不修改游戏状态。什么时候播放由 `sessions` 生成的 `host_cue` 和前端播放 hooks 决定。
