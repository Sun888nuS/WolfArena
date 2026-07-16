# frontend/src/features/voice

固定主持语音播放目录，负责按照后端快照里的 `host_cue` 播放白名单语音，并在语音结束后通知游戏页继续自动推进。

## 文件分工

- `useHostVoice.ts` 根据 `GameSnapshot.host_cue` 播放主语音和补充语音，处理音量、启停、播放队列、浏览器自动播放限制和语音结束回调。

## 数据来源

- 音频地址由 `frontend/src/services/game.ts` 的 `hostVoiceUrl` 生成。
- 可用语音 key 由后端 `backend/app/voice/host_voice.py` 白名单控制。
- 具体哪个节点播放哪个语音，由后端 `backend/app/sessions/snapshots.py` 生成 `host_cue`。

## 常见修改入口

- 调整播放顺序、等待时间或自动推进完成回调：改 `useHostVoice.ts`。
- 新增固定主持语音：先改后端 `host_voice.py` 白名单和资源文件，再在 `sessions/snapshots.py` 使用新的 `voice_key`。
- 调整语音开关、音量 UI 或状态展示：通常改 `features/game/GamePage.tsx`。

## 维护边界

语音只是输出方式。真人行动仍通过 `services/game.ts` 提交到后端，并由后端规则校验。
