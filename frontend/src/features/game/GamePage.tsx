import { useEffect, useMemo, useRef, useState } from "react";

import {
  advanceGame,
  finishGame,
  gameWebSocketUrl,
  getGame,
  getLlmConfig,
  listGames,
  startGame,
  submitAction,
  updateLlmConfig,
} from "../../services/game";
import {
  useBackgroundAudio,
  type BackgroundAudioPlaybackStatus,
} from "./useBackgroundAudio";
import { useHostVoice, type HostVoiceStatus } from "../voice/useHostVoice";
import type { AuthUser } from "../../types/auth";
import type {
  AgentReplyStreamMessage,
  AssistantPanelData,
  GameEvent,
  GameSnapshot,
  PendingAction,
  PublicPlayer,
} from "../../types/game";
import type { LlmConfigStatus } from "../../types/health";
import { GameReviewDialog } from "../review/GameReviewDialog";

/** 女巫操作区的前端临时选择状态。 */
type WitchChoice = "none" | "save" | "poison";
type SpeechDirection = "clockwise" | "counterclockwise" | "";
type SheriffRunChoice = "run" | "stay";
type IdiotRevealChoice = "reveal" | "hide";
type LockedHumanIdentity = { role: string; alignment: string | null };
type StreamingReply = AgentReplyStreamMessage & { status: "streaming" | "done" };
type LlmSettingsForm = { base_url: string; model: string; api_key: string };
type AudioSettings = {
  enabled: boolean;
  volume: number;
  hostVoiceEnabled: boolean;
  hostVoiceVolume: number;
};

// 本地只记录最近游戏 id；后端重启后无法恢复旧局。
const LAST_GAME_ID_KEY_PREFIX = "wolfarena.lastGameId";
const AUDIO_ENABLED_KEY = "wolfarena.audio.enabled";
const AUDIO_VOLUME_KEY = "wolfarena.audio.volume";
const HOST_VOICE_ENABLED_KEY = "wolfarena.hostVoice.enabled";
const HOST_VOICE_VOLUME_KEY = "wolfarena.hostVoice.volume";

/** 狼人杀主页面，负责连接快照、真人操作和桌面展示。 */
export function GamePage({
  currentUser,
  onLogout,
  authLoading,
}: {
  currentUser: AuthUser;
  onLogout: () => Promise<void>;
  authLoading: boolean;
}) {
  const [snapshot, setSnapshot] = useState<GameSnapshot | null>(null);
  const [playerName, setPlayerName] = useState(() => defaultPlayerName(currentUser));
  const [selectedTarget, setSelectedTarget] = useState("");
  const [speech, setSpeech] = useState("");
  const [witchChoice, setWitchChoice] = useState<WitchChoice>("none");
  const [speechDirection, setSpeechDirection] = useState<SpeechDirection>("");
  const [sheriffRunChoice, setSheriffRunChoice] = useState<SheriffRunChoice>("run");
  const [idiotRevealChoice, setIdiotRevealChoice] = useState<IdiotRevealChoice>("reveal");
  const [rulesOpen, setRulesOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewHint, setReviewHint] = useState("");
  const [llmSettingsOpen, setLlmSettingsOpen] = useState(false);
  const [llmConfig, setLlmConfig] = useState<LlmConfigStatus | null>(null);
  const [llmForm, setLlmForm] = useState<LlmSettingsForm>({
    base_url: "",
    model: "",
    api_key: "",
  });
  const [llmSettingsLoading, setLlmSettingsLoading] = useState(false);
  const [llmSettingsError, setLlmSettingsError] = useState("");
  const [audioSettings, setAudioSettings] = useState<AudioSettings>(() => readStoredAudioSettings());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [autoAdvancing, setAutoAdvancing] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);
  const [streamingReply, setStreamingReply] = useState<StreamingReply | null>(null);
  const [hostFollowUpMessage, setHostFollowUpMessage] = useState<{
    gameId: string;
    cueKey: string;
    text: string;
  } | null>(null);
  const activeGameIdRef = useRef<string | null>(null);
  const advanceInFlightRef = useRef(false);
  const reviewHintTimerRef = useRef<number | null>(null);
  const lockedHumanIdentitiesRef = useRef<Map<string, LockedHumanIdentity>>(new Map());
  const lastGameIdKey = useMemo(
    () => `${LAST_GAME_ID_KEY_PREFIX}.${currentUser.id}`,
    [currentUser.id],
  );
  const isStreamingReplyActive = Boolean(
    streamingReply &&
      streamingReply.game_id === snapshot?.game_id &&
      streamingReply.status === "streaming",
  );
  const hostVoice = useHostVoice({
    snapshot,
    enabled: audioSettings.hostVoiceEnabled,
    volume: audioSettings.hostVoiceVolume,
    mutedByStreaming: isStreamingReplyActive,
  });
  const backgroundAudio = useBackgroundAudio({
    snapshot,
    settings: audioSettings,
    voiceDucking: hostVoice.speaking,
  });

  useEffect(() => {
    if (
      (!audioSettings.enabled && !audioSettings.hostVoiceEnabled) ||
      !snapshot ||
      snapshot.phase === "game_over"
    ) {
      return;
    }
    const unlock = () => {
      if (audioSettings.enabled) {
        backgroundAudio.unlock(backgroundAudio.track ?? audioTrackForSnapshot(snapshot), audioSettings.volume);
      }
      if (audioSettings.hostVoiceEnabled) {
        hostVoice.unlock();
      }
    };
    window.addEventListener("pointerdown", unlock, { once: true, capture: true });
    window.addEventListener("keydown", unlock, { once: true, capture: true });
    return () => {
      window.removeEventListener("pointerdown", unlock, { capture: true });
      window.removeEventListener("keydown", unlock, { capture: true });
    };
  }, [
    audioSettings.enabled,
    audioSettings.hostVoiceEnabled,
    audioSettings.volume,
    backgroundAudio.track,
    backgroundAudio.unlock,
    hostVoice.unlock,
    snapshot,
  ]);

  function updateAudioSettings(next: AudioSettings) {
    setAudioSettings(next);
    window.localStorage.setItem(AUDIO_ENABLED_KEY, next.enabled ? "true" : "false");
    window.localStorage.setItem(AUDIO_VOLUME_KEY, String(next.volume));
    window.localStorage.setItem(HOST_VOICE_ENABLED_KEY, next.hostVoiceEnabled ? "true" : "false");
    window.localStorage.setItem(HOST_VOICE_VOLUME_KEY, String(next.hostVoiceVolume));
  }

  function handleAudioSettingsChange(next: AudioSettings) {
    updateAudioSettings(next);
    if (next.enabled) {
      backgroundAudio.unlock(backgroundAudio.track ?? audioTrackForSnapshot(snapshot) ?? "night", next.volume);
    }
    if (next.hostVoiceEnabled) {
      hostVoice.unlock();
    }
  }

  function applySnapshot(
    data: GameSnapshot,
    options: { expectedGameId?: string; makeActive?: boolean } = {},
  ) {
    if (options.expectedGameId && data.game_id !== options.expectedGameId) return;
    if (options.makeActive) {
      activeGameIdRef.current = data.game_id;
    }
    const activeGameId = activeGameIdRef.current;
    if (activeGameId && data.game_id !== activeGameId) return;
    if (!activeGameId) {
      activeGameIdRef.current = data.game_id;
    }
    setSnapshot(withLockedHumanIdentity(data));
    setStreamingReply((current) => (shouldKeepStreamingReply(current, data) ? current : null));
  }

  function withLockedHumanIdentity(data: GameSnapshot): GameSnapshot {
    const human = data.players.find((player) => player.player_id === data.human_player_id);
    if (!human?.role) return data;
    const locked = lockedHumanIdentitiesRef.current.get(data.game_id);
    if (!locked) {
      lockedHumanIdentitiesRef.current.set(data.game_id, {
        role: human.role,
        alignment: human.alignment,
      });
      return data;
    }
    if (locked.role === human.role && locked.alignment === human.alignment) return data;
    return {
      ...data,
      players: data.players.map((player) =>
        player.player_id === data.human_player_id
          ? { ...player, role: locked.role, alignment: locked.alignment }
          : player,
      ),
    };
  }

  // 首次进入页面时尝试恢复同一后端进程中的上一局游戏。
  useEffect(() => {
    let cancelled = false;

    /** 从本地记录或后端列表中恢复最近一局游戏。 */
    async function restoreGame() {
      setError("");
      const storedGameId = window.localStorage.getItem(lastGameIdKey);
      try {
        let gameId = storedGameId;
        if (!gameId) {
          const gameIds = await listGames();
          gameId = gameIds[0] ?? "";
        }
        if (!gameId) return;
        const data = await getGame(gameId);
        if (!cancelled) {
          if (activeGameIdRef.current) return;
          applySnapshot(data, { makeActive: true });
          window.localStorage.setItem(lastGameIdKey, data.game_id);
        }
      } catch {
        if (!cancelled) {
          window.localStorage.removeItem(lastGameIdKey);
        }
      }
    }

    void restoreGame();
    return () => {
      cancelled = true;
    };
  }, [lastGameIdKey]);

  // 有 gameId 后订阅后端 WebSocket 快照推送。
  useEffect(() => {
    if (!snapshot?.game_id) return;
    setSocketConnected(false);
    const socket = new WebSocket(gameWebSocketUrl(snapshot.game_id));
    socket.onopen = () => setSocketConnected(true);
    socket.onclose = () => setSocketConnected(false);
    socket.onerror = () => setSocketConnected(false);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as unknown;
      if (isAgentReplyStreamMessage(data)) {
        if (data.game_id !== snapshot.game_id) return;
        if (data.type === "agent_reply_failed") {
          setStreamingReply(null);
          return;
        }
        const status = data.type === "agent_reply_completed" ? "done" : "streaming";
        setStreamingReply((current) => {
          if (
            current?.type === data.type &&
            current.game_id === data.game_id &&
            current.player_id === data.player_id &&
            current.stream_id === data.stream_id &&
            current.text === data.text &&
            current.node === data.node &&
            current.status === status
          ) {
            return current;
          }
          return { ...data, status };
        });
        return;
      }
      if (isGameSnapshot(data)) {
        applySnapshot(data, { expectedGameId: snapshot.game_id });
      }
    };
    return () => socket.close();
  }, [snapshot?.game_id]);

  const hostCue = snapshot?.host_cue ?? null;
  const hostCueKey = snapshot
    ? [
        snapshot.game_id,
        snapshot.round_no,
        snapshot.phase,
        hostCue?.message ?? snapshot.god_message,
        hostCue?.follow_up_message ?? "",
        snapshot.pending_action?.action_type ?? "",
        snapshot.current_actor_id ?? "",
      ].join("|")
    : "";

  useEffect(() => {
    setHostFollowUpMessage(null);
    if (!snapshot || !hostCue?.visible || !hostCue.follow_up_message || snapshot.pending_action) return;
    if (audioSettings.hostVoiceEnabled && hostCue.voice_key) return;
    const delay = Math.max(450, Math.floor((hostCue.hold_ms || 1200) * 0.55));
    const timer = window.setTimeout(() => {
      setHostFollowUpMessage({
        gameId: snapshot.game_id,
        cueKey: hostCueKey,
        text: hostCue.follow_up_message ?? "",
      });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [
    audioSettings.hostVoiceEnabled,
    hostCueKey,
    hostCue?.visible,
    hostCue?.voice_key,
    hostCue?.follow_up_message,
    hostCue?.hold_ms,
    snapshot?.game_id,
    snapshot?.pending_action,
  ]);

  // 没有真人待行动时自动推进主持流程。
  useEffect(() => {
    if (
      !snapshot ||
      !socketConnected ||
      isStreamingReplyActive ||
      snapshot.pending_action ||
      snapshot.phase === "game_over" ||
      autoAdvancing
    ) {
      return;
    }
    const blocksByVoice = snapshot.host_cue?.blocks_auto_advance ?? false;
    if (blocksByVoice && !hostVoice.readyForAdvance) return;
    const holdMs = blocksByVoice
      ? 220
      : snapshot.host_cue?.visible === false
        ? 150
        : snapshot.host_cue?.hold_ms ?? 650;
    const timer = window.setTimeout(() => {
      void handleAdvance();
    }, holdMs);
    return () => window.clearTimeout(timer);
  }, [snapshot, socketConnected, isStreamingReplyActive, autoAdvancing, hostVoice.readyForAdvance]);

  useEffect(() => {
    if (!streamingReply || streamingReply.status !== "done") return;
    const streamId = streamingReply.stream_id;
    const timer = window.setTimeout(() => {
      setStreamingReply((current) => (current?.stream_id === streamId ? null : current));
    }, 800);
    return () => window.clearTimeout(timer);
  }, [streamingReply?.stream_id, streamingReply?.status]);

  useEffect(() => {
    return () => {
      if (reviewHintTimerRef.current !== null) {
        window.clearTimeout(reviewHintTimerRef.current);
      }
    };
  }, []);

  const playersById = useMemo(() => {
    const out = new Map<string, PublicPlayer>();
    for (const player of snapshot?.players ?? []) {
      out.set(player.player_id, player);
    }
    return out;
  }, [snapshot]);

  const selectedPlayer = selectedTarget ? playersById.get(selectedTarget) ?? null : null;
  const activeStreamingReply =
    streamingReply && streamingReply.game_id === snapshot?.game_id ? streamingReply : null;
  const hostVoiceFollowUpMessage =
    hostVoice.followUpCueId && hostVoice.followUpCueId === hostCue?.cue_id
      ? hostCue?.follow_up_message ?? ""
      : "";
  const activeHostFollowUpMessage =
    hostVoiceFollowUpMessage ||
    (hostFollowUpMessage &&
    hostFollowUpMessage.gameId === snapshot?.game_id &&
    hostFollowUpMessage.cueKey === hostCueKey
      ? hostFollowUpMessage.text
      : "");
  const isNight = snapshot?.phase === "night";
  const aliveCount = snapshot?.players.filter((player) => player.alive).length ?? 0;

  /** 创建新游戏并重置当前操作表单。 */
  async function handleStart() {
    setLoading(true);
    setError("");
    if (audioSettings.enabled) {
      backgroundAudio.unlock("night", audioSettings.volume);
    }
    if (audioSettings.hostVoiceEnabled) {
      hostVoice.unlock();
    }
    try {
      const data = await startGame(playerName.trim() || "Sunny");
      applySnapshot(data, { makeActive: true });
      window.localStorage.setItem(lastGameIdKey, data.game_id);
      setReviewOpen(false);
      resetActionForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动失败");
    } finally {
      setLoading(false);
    }
  }

  /** 游戏结束后打开复盘；进行中只给出明确提示。 */
  function handleOpenReview() {
    setError("");
    if (!snapshot) {
      showReviewHint("暂无可复盘的游戏");
      return;
    }
    if (snapshot.phase !== "game_over") {
      showReviewHint("游戏结束后可查看复盘");
      return;
    }
    setReviewHint("");
    setReviewOpen(true);
  }

  /** 在复盘按钮旁展示短提示，不占用全局错误区域。 */
  function showReviewHint(message: string) {
    setReviewHint(message);
    if (reviewHintTimerRef.current !== null) {
      window.clearTimeout(reviewHintTimerRef.current);
    }
    reviewHintTimerRef.current = window.setTimeout(() => {
      setReviewHint("");
      reviewHintTimerRef.current = null;
    }, 1500);
  }

  /** 强制结束当前对局，保留已有事件供之后复盘。 */
  async function handleEndGame() {
    if (!snapshot || snapshot.phase === "game_over") return;
    const gameId = snapshot.game_id;
    setLoading(true);
    setError("");
    setReviewOpen(false);
    setStreamingReply(null);
    try {
      const data = await finishGame(gameId);
      applySnapshot(data, { expectedGameId: gameId });
      resetActionForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "结束游戏失败");
    } finally {
      advanceInFlightRef.current = false;
      setAutoAdvancing(false);
      setLoading(false);
    }
  }

  /** 打开模型设置弹窗，并读取后端当前运行时配置。 */
  async function handleOpenLlmSettings() {
    setLlmSettingsOpen(true);
    setLlmSettingsError("");
    setLlmSettingsLoading(true);
    try {
      const config = await getLlmConfig();
      setLlmConfig(config);
      setLlmForm({
        base_url: config.base_url,
        model: config.model,
        api_key: "",
      });
    } catch (err) {
      setLlmSettingsError(err instanceof Error ? err.message : "读取模型配置失败");
    } finally {
      setLlmSettingsLoading(false);
    }
  }

  /** 保存模型设置，后续 AI 玩家调用会使用新配置。 */
  async function handleSaveLlmSettings() {
    setLlmSettingsError("");
    setLlmSettingsLoading(true);
    try {
      const config = await updateLlmConfig({
        base_url: llmForm.base_url.trim(),
        model: llmForm.model.trim(),
        api_key: llmForm.api_key.trim() || undefined,
      });
      setLlmConfig(config);
      setLlmForm({
        base_url: config.base_url,
        model: config.model,
        api_key: "",
      });
      setSnapshot((current) =>
        current
          ? {
              ...current,
              llm_status: llmStatusLabel(config),
            }
          : current,
      );
      setLlmSettingsOpen(false);
    } catch (err) {
      setLlmSettingsError(err instanceof Error ? err.message : "保存模型配置失败");
    } finally {
      setLlmSettingsLoading(false);
    }
  }

  /** 推进一个后端图节点，通常由自动流程定时触发。 */
  async function handleAdvance() {
    if (!snapshot || snapshot.pending_action || snapshot.phase === "game_over") return;
    if (!socketConnected || advanceInFlightRef.current) return;
    const gameId = snapshot.game_id;
    advanceInFlightRef.current = true;
    setAutoAdvancing(true);
    setError("");
    try {
      const data = await advanceGame(gameId);
      applySnapshot(data, { expectedGameId: gameId });
    } catch (err) {
      setError(err instanceof Error ? err.message : "推进流程失败");
    } finally {
      advanceInFlightRef.current = false;
      setAutoAdvancing(false);
    }
  }

  /** 提交当前真人 pending action 对应的表单内容。 */
  async function handleSubmit() {
    if (!snapshot?.pending_action) return;
    setLoading(true);
    setError("");
    try {
      const pending = snapshot.pending_action;
      const gameId = snapshot.game_id;
      const payload = buildPayload(
        pending,
        selectedTarget,
        speech,
        witchChoice,
        speechDirection,
        sheriffRunChoice,
        idiotRevealChoice,
      );
      const data = await submitAction(gameId, payload);
      applySnapshot(data, { expectedGameId: gameId });
      resetActionForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setLoading(false);
    }
  }

  /** 在桌面上选择或取消选择一个合法目标玩家。 */
  function handleSelectPlayer(player: PublicPlayer) {
    if (!canSelectPlayer(snapshot?.pending_action ?? null, player, witchChoice)) return;
    setSelectedTarget((current) => (current === player.player_id ? "" : player.player_id));
  }

  /** 清空真人操作区的临时输入。 */
  function resetActionForm() {
    setSelectedTarget("");
    setSpeech("");
    setWitchChoice("none");
    setSpeechDirection("");
    setSheriffRunChoice("run");
    setIdiotRevealChoice("reveal");
  }

  return (
    <main className={`game-shell ${isNight ? "is-night" : "is-day"}`}>
      <section className="topbar">
        <div>
          <div className="eyebrow">WolfArena AI</div>
          <div className="account-line">
            <span>{currentUser.display_name || currentUser.email}</span>
            <button onClick={() => void onLogout()} disabled={authLoading} type="button">
              退出
            </button>
          </div>
        </div>
        <div className="start-controls" aria-label="开局控制"> 
          <input
            value={playerName}
            onChange={(event) => setPlayerName(event.target.value)}
            placeholder="玩家昵称"
          />
          <button onClick={handleStart} disabled={loading}>
            {snapshot ? "重新开局" : "开始游戏"}
          </button>
          <button className="secondary-button" onClick={() => void handleOpenLlmSettings()} type="button">
            设置
          </button>
          <button className="secondary-button" onClick={() => setRulesOpen(true)} type="button">
            查看规则
          </button>
          <div className="review-button-wrap">
            <button className="secondary-button" onClick={handleOpenReview} type="button">
              游戏复盘
            </button>
            {reviewHint ? <span className="review-hint">{reviewHint}</span> : null}
          </div>
          <button
            className="danger-button"
            onClick={() => void handleEndGame()}
            disabled={!snapshot || snapshot.phase === "game_over" || loading}
            type="button"
          >
            结束游戏
          </button>
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="layout">
        <div className="arena-column">
          <GameStatus snapshot={snapshot} aliveCount={aliveCount} />
          <section className="arena-panel">
            <PlayerTable
              snapshot={snapshot}
              players={snapshot?.players ?? []}
              humanPlayerId={snapshot?.human_player_id ?? ""}
              selectedTarget={selectedTarget}
              witchChoice={witchChoice}
              autoAdvancing={autoAdvancing}
              streamingReply={activeStreamingReply}
              hostMessageOverride={activeHostFollowUpMessage}
              sheriffId={snapshot?.sheriff_id ?? null}
              onSelectPlayer={handleSelectPlayer}
            />
            <ActionPanel
              pending={snapshot?.pending_action ?? null}
              playersById={playersById}
              selectedTarget={selectedTarget}
              selectedPlayer={selectedPlayer}
              setSelectedTarget={setSelectedTarget}
              speech={speech}
              setSpeech={setSpeech}
              witchChoice={witchChoice}
              setWitchChoice={(choice) => {
                setWitchChoice(choice);
                if (choice !== "poison") setSelectedTarget("");
              }}
              speechDirection={speechDirection}
              setSpeechDirection={setSpeechDirection}
              sheriffRunChoice={sheriffRunChoice}
              setSheriffRunChoice={setSheriffRunChoice}
              idiotRevealChoice={idiotRevealChoice}
              setIdiotRevealChoice={setIdiotRevealChoice}
              onSubmit={handleSubmit}
              disabled={loading}
              phase={snapshot?.phase}
            />
          </section>
        </div>

        <aside className="side-panel">
          <KnownInfo snapshot={snapshot} playersById={playersById} />
          <AssistantPanel panel={snapshot?.assistant_panel ?? null} />
          <EventFeed
            events={snapshot?.events ?? []}
            playersById={playersById}
            streamingReply={activeStreamingReply}
          />
        </aside>
      </section>

      {rulesOpen ? <RulesDialog onClose={() => setRulesOpen(false)} /> : null}
      {reviewOpen && snapshot?.phase === "game_over" ? (
        <GameReviewDialog
          snapshot={snapshot}
          playersById={playersById}
          onClose={() => setReviewOpen(false)}
        />
      ) : null}
      {llmSettingsOpen ? (
        <LlmSettingsDialog
          config={llmConfig}
          form={llmForm}
          loading={llmSettingsLoading}
          error={llmSettingsError}
          audioSettings={audioSettings}
          audioTrack={backgroundAudio.track}
          audioStatus={backgroundAudio.status}
          hostVoiceStatus={hostVoice.status}
          onChange={setLlmForm}
          onAudioChange={handleAudioSettingsChange}
          onClose={() => setLlmSettingsOpen(false)}
          onSave={() => void handleSaveLlmSettings()}
        />
      ) : null}
    </main>
  );
}

/** 顶部状态条，展示当前对局状态。 */
function GameStatus({
  snapshot,
  aliveCount,
}: {
  snapshot: GameSnapshot | null;
  aliveCount: number;
}) {
  return (
    <div className="game-status">
      <StatusBadge label="阶段" value={phaseLabel(snapshot?.phase)} />
      <StatusBadge label="轮次" value={snapshot ? `第 ${snapshot.round_no} 轮` : "未开始"} />
      <StatusBadge label="存活" value={snapshot ? `${aliveCount} / ${snapshot.players.length}` : "未开始"} />
      <StatusBadge label="胜者" value={winnerLabel(snapshot?.winner)} />
    </div>
  );
}

/** 单个紧凑状态徽章。 */
function StatusBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-badge">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

/** 方形玩家区，负责在上方和左右两端摆放玩家卡，并展示主持播报。 */
function PlayerTable({
  snapshot,
  players,
  humanPlayerId,
  selectedTarget,
  witchChoice,
  autoAdvancing,
  streamingReply,
  hostMessageOverride,
  sheriffId,
  onSelectPlayer,
}: {
  snapshot: GameSnapshot | null;
  players: PublicPlayer[];
  humanPlayerId: string;
  selectedTarget: string;
  witchChoice: WitchChoice;
  autoAdvancing: boolean;
  streamingReply: StreamingReply | null;
  hostMessageOverride: string;
  sheriffId: string | null;
  onSelectPlayer: (player: PublicPlayer) => void;
}) {
  if (players.length === 0) {
    return (
      <div className="table-stage table-stage-empty">
        <div className="empty">
          <strong>等待开局</strong>
        <span>12 人标准局：4 狼人、4 村民、预言家、女巫、猎人、白痴。</span>
        </div>
      </div>
    );
  }

  const currentActorId = shouldHighlightCurrentActor(snapshot)
    ? snapshot?.current_actor_id ?? null
    : null;
  const liveStreamingReply = streamingReply?.status === "streaming" ? streamingReply : null;
  const highlightedActorId = liveStreamingReply?.player_id ?? currentActorId;
  const streamingActor = players.find((player) => player.player_id === liveStreamingReply?.player_id);
  const streamingActorName = streamingActor
    ? `${streamingActor.seat} 号${streamingActor.name}`
    : "AI 玩家";

  return (
    <div className="table-stage" aria-label="玩家座位">
      <HostCenter
        snapshot={snapshot}
        autoAdvancing={autoAdvancing}
        streamingReply={liveStreamingReply}
        streamingActorName={streamingActorName}
        hostMessageOverride={hostMessageOverride}
      />
      {players.map((player, index) => (
        <PlayerCard
          key={player.player_id}
          player={player}
          position={index + 1}
          isHuman={player.player_id === humanPlayerId}
          isCurrent={player.player_id === highlightedActorId}
          isSelected={player.player_id === selectedTarget}
          isSheriff={player.player_id === sheriffId}
          selectable={canSelectPlayer(snapshot?.pending_action ?? null, player, witchChoice)}
          onSelect={() => onSelectPlayer(player)}
        />
      ))}
    </div>
  );
}

/** 方形玩家区中央的主持播报和流程进度。 */
function HostCenter({
  snapshot,
  autoAdvancing,
  streamingReply,
  streamingActorName,
  hostMessageOverride,
}: {
  snapshot: GameSnapshot | null;
  autoAdvancing: boolean;
  streamingReply: StreamingReply | null;
  streamingActorName: string;
  hostMessageOverride: string;
}) {
  const defaultMessage = "点击开始游戏后，主持会自动推进流程。";
  const hostCue = snapshot?.host_cue ?? null;
  const [retainedMessage, setRetainedMessage] = useState(defaultMessage);

  useEffect(() => {
    if (!snapshot) {
      setRetainedMessage(defaultMessage);
      return;
    }
    if (hostCue?.visible === false) return;
    const nextMessage = hostCue?.message || snapshot.god_message;
    if (nextMessage) setRetainedMessage(nextMessage);
  }, [snapshot?.game_id, hostCue?.message, hostCue?.visible, snapshot?.god_message]);

  const message =
    hostMessageOverride ||
    (hostCue?.visible === false
      ? retainedMessage
      : hostCue?.message || snapshot?.god_message || defaultMessage);
  const steps = snapshot?.god_steps ?? [];
  return (
    <section className="host-center">
      <div className="host-kicker">主持播报</div>
      <strong>{streamingReply ? `${streamingActorName} 正在发言` : message}</strong>
      <div className="host-subline">
        {streamingReply
          ? streamingReply.status === "done"
            ? "发言生成完成"
            : "AI 正在实时发言"
          : snapshot?.pending_action
          ? "等待你的行动"
          : snapshot?.phase === "game_over"
            ? "本局已结束"
            : autoAdvancing
              ? "系统正在推进"
              : "流程自动推进中"}
      </div>
      {streamingReply ? (
        <p className="host-streaming-text">{streamingReply.text.trim() || "正在组织发言..."}</p>
      ) : null}
      <div className="god-steps">
        {steps.map((step) => (
          <div className={`god-step ${step.status}`} key={step.key}>
            <span>{step.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/** 单个玩家座位卡片。 */
function PlayerCard({
  player,
  position,
  isHuman,
  isCurrent,
  isSelected,
  isSheriff,
  selectable,
  onSelect,
}: {
  player: PublicPlayer;
  position: number;
  isHuman: boolean;
  isCurrent: boolean;
  isSelected: boolean;
  isSheriff: boolean;
  selectable: boolean;
  onSelect: () => void;
}) {
  const initials = player.name.trim().slice(0, 2).toUpperCase() || String(player.seat);
  const className = [
    "player-card",
    `seat-pos-${position}`,
    player.alive ? "alive" : "dead",
    isHuman ? "human" : "",
    isCurrent ? "current" : "",
    isSelected ? "selected" : "",
    isSheriff ? "sheriff" : "",
    selectable ? "selectable" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      className={className}
      type="button"
      onClick={onSelect}
      disabled={!selectable}
      aria-pressed={isSelected}
    >
      <span className="seat-badge">{player.seat} 号</span>
      {isSheriff ? <span className="sheriff-badge">警徽</span> : null}
      <span className="avatar" aria-hidden="true">
        {initials}
      </span>
      <span className="player-name">{player.name}</span>
      <span className="player-meta">
        {player.is_human ? "真人" : "AI"} · {player.alive ? "存活" : "出局"}
      </span>
      <span className={`role-chip ${player.role ?? "hidden"}`}>
        {player.role ? roleLabel(player.role) : "身份隐藏"}
      </span>
    </button>
  );
}

/** 真人行动面板，根据 pending action 切换输入控件。 */
function ActionPanel(props: {
  pending: PendingAction | null;
  playersById: Map<string, PublicPlayer>;
  selectedTarget: string;
  selectedPlayer: PublicPlayer | null;
  setSelectedTarget: (value: string) => void;
  speech: string;
  setSpeech: (value: string) => void;
  witchChoice: WitchChoice;
  setWitchChoice: (value: WitchChoice) => void;
  speechDirection: SpeechDirection;
  setSpeechDirection: (value: SpeechDirection) => void;
  sheriffRunChoice: SheriffRunChoice;
  setSheriffRunChoice: (value: SheriffRunChoice) => void;
  idiotRevealChoice: IdiotRevealChoice;
  setIdiotRevealChoice: (value: IdiotRevealChoice) => void;
  onSubmit: () => void;
  disabled: boolean;
  phase?: string;
}) {
  const pending = props.pending;
  if (!pending) {
    return (
      <div className="action-panel muted">
        <strong>{props.phase === "game_over" ? "对局结束" : "等待主持流程"}</strong>
        <span>{props.phase === "game_over" ? "右侧可查看本局复盘。" : "轮到你行动时，操作区会自动切换。"}</span>
      </div>
    );
  }

  const submitDisabled = props.disabled || !canSubmit(
    pending,
    props.selectedTarget,
    props.witchChoice,
    props.speechDirection,
    props.sheriffRunChoice,
  );

  return (
    <div className={`action-panel action-${pending.action_type}`}>
      <div className="action-heading">
        <span>{actionTypeLabel(pending.action_type)}</span>
        <strong>{pending.prompt}</strong>
      </div>

      {pending.action_type === "speak" ? (
        <textarea
          value={props.speech}
          onChange={(event) => props.setSpeech(event.target.value)}
          maxLength={240}
          placeholder="输入你的白天发言"
        />
      ) : null}

      {pending.action_type !== "witch_action" && pending.action_type !== "idiot_reveal" && pending.legal_targets.length > 0 ? (
        <TargetSelect
          legalTargets={pending.legal_targets}
          playersById={props.playersById}
          selectedTarget={props.selectedTarget}
          setSelectedTarget={props.setSelectedTarget}
          placeholder={pending.action_type === "vote" || pending.action_type === "sheriff_vote" ? "弃票" : "选择目标"}
        />
      ) : null}

      {pending.action_type === "witch_action" ? (
        <WitchActionControls
          pending={pending}
          playersById={props.playersById}
          selectedTarget={props.selectedTarget}
          setSelectedTarget={props.setSelectedTarget}
          witchChoice={props.witchChoice}
          setWitchChoice={props.setWitchChoice}
        />
      ) : null}

      {pending.action_type === "idiot_reveal" ? (
        <div className="choice-grid">
          <label className={`choice-card ${props.idiotRevealChoice === "reveal" ? "selected" : ""}`}>
            <input
              type="radio"
              name="idiot-reveal"
              checked={props.idiotRevealChoice === "reveal"}
              onChange={() => props.setIdiotRevealChoice("reveal")}
            />
            <strong>{"\u7ffb\u724c"}</strong>
            <span>{"\u7ee7\u7eed\u53d1\u8a00\uff0c\u4f46\u5931\u53bb\u6295\u7968\u6743"}</span>
          </label>
          <label className={`choice-card ${props.idiotRevealChoice === "hide" ? "selected" : ""}`}>
            <input
              type="radio"
              name="idiot-reveal"
              checked={props.idiotRevealChoice === "hide"}
              onChange={() => props.setIdiotRevealChoice("hide")}
            />
            <strong>{"\u4e0d\u7ffb\u724c"}</strong>
            <span>{"\u6b63\u5e38\u51fa\u5c40\uff0c\u4e0d\u516c\u5f00\u8eab\u4efd"}</span>
          </label>
        </div>
      ) : null}

      {pending.action_type === "sheriff_run" ? (
        <div className="choice-grid">
          <label className={`choice-card ${props.sheriffRunChoice === "run" ? "selected" : ""}`}>
            <input
              type="radio"
              name="sheriff-run"
              checked={props.sheriffRunChoice === "run"}
              onChange={() => props.setSheriffRunChoice("run")}
            />
            <strong>上警</strong>
            <span>进入警上名单并发表竞选发言</span>
          </label>
          <label className={`choice-card ${props.sheriffRunChoice === "stay" ? "selected" : ""}`}>
            <input
              type="radio"
              name="sheriff-run"
              checked={props.sheriffRunChoice === "stay"}
              onChange={() => props.setSheriffRunChoice("stay")}
            />
            <strong>不上警</strong>
            <span>留在警下参与警长投票</span>
          </label>
        </div>
      ) : null}

      {pending.action_type === "sheriff_order" ? (
        <div className="choice-grid">
          <label className={`choice-card ${props.speechDirection === "counterclockwise" ? "selected" : ""}`}>
            <input
              type="radio"
              name="sheriff-order"
              checked={props.speechDirection === "counterclockwise"}
              onChange={() => props.setSpeechDirection("counterclockwise")}
            />
            <strong>左边开始</strong>
            <span>逆时针发言，你最后总结</span>
          </label>
          <label className={`choice-card ${props.speechDirection === "clockwise" ? "selected" : ""}`}>
            <input
              type="radio"
              name="sheriff-order"
              checked={props.speechDirection === "clockwise"}
              onChange={() => props.setSpeechDirection("clockwise")}
            />
            <strong>右边开始</strong>
            <span>顺时针发言，你最后总结</span>
          </label>
        </div>
      ) : null}

      <div className="action-footer">
        <span>
          {props.selectedPlayer
            ? `目标：${playerName(props.selectedPlayer.player_id, props.playersById)}`
            : pending.action_type === "sheriff_order"
              ? "请选择本轮发言方向"
            : pending.action_type === "sheriff_run"
              ? props.sheriffRunChoice === "run"
                ? "你将加入警上名单"
                : "你将留在警下投票"
            : pending.action_type === "vote" || pending.action_type === "sheriff_vote"
              ? "未选目标将视为弃票"
              : "未选择目标"}
        </span>
        <button onClick={props.onSubmit} disabled={submitDisabled}>
          {submitLabel(
            pending,
            props.selectedPlayer,
            props.witchChoice,
            props.speechDirection,
            props.sheriffRunChoice,
            props.idiotRevealChoice,
          )}
        </button>
      </div>
    </div>
  );
}

/** 通用目标选择下拉框。 */
function TargetSelect({
  legalTargets,
  playersById,
  selectedTarget,
  setSelectedTarget,
  placeholder,
}: {
  legalTargets: string[];
  playersById: Map<string, PublicPlayer>;
  selectedTarget: string;
  setSelectedTarget: (value: string) => void;
  placeholder: string;
}) {
  return (
    <select value={selectedTarget} onChange={(event) => setSelectedTarget(event.target.value)}>
      <option value="">{placeholder}</option>
      {legalTargets.map((targetId) => {
        const player = playersById.get(targetId);
        return (
          <option key={targetId} value={targetId}>
            {player ? `${player.seat} 号 ${player.name}` : targetId}
          </option>
        );
      })}
    </select>
  );
}

/** 女巫行动控件，提供不用药、解药和毒药三种选择。 */
function WitchActionControls(props: {
  pending: PendingAction;
  playersById: Map<string, PublicPlayer>;
  selectedTarget: string;
  setSelectedTarget: (value: string) => void;
  witchChoice: WitchChoice;
  setWitchChoice: (value: WitchChoice) => void;
}) {
  const attackedName = props.pending.attacked_player_id
    ? playerName(props.pending.attacked_player_id, props.playersById)
    : "无人";

  return (
    <div className="witch-controls">
      <div className="night-intel">
        <span>昨夜被袭击</span>
        <strong>{attackedName}</strong>
      </div>
      <div className="choice-grid">
        <label className={`choice-card ${props.witchChoice === "none" ? "selected" : ""}`}>
          <input
            type="radio"
            name="witch-action"
            checked={props.witchChoice === "none"}
            onChange={() => props.setWitchChoice("none")}
          />
          <strong>不用药</strong>
          <span>保留药剂</span>
        </label>
        <label className={`choice-card ${props.witchChoice === "save" ? "selected" : ""}`}>
          <input
            type="radio"
            name="witch-action"
            checked={props.witchChoice === "save"}
            disabled={!props.pending.can_save}
            onChange={() => props.setWitchChoice("save")}
          />
          <strong>解药</strong>
          <span>{props.pending.can_save ? "救下被袭击者" : "本轮不可用"}</span>
        </label>
        <label className={`choice-card ${props.witchChoice === "poison" ? "selected" : ""}`}>
          <input
            type="radio"
            name="witch-action"
            checked={props.witchChoice === "poison"}
            disabled={!props.pending.can_poison || props.pending.legal_targets.length === 0}
            onChange={() => props.setWitchChoice("poison")}
          />
          <strong>毒药</strong>
          <span>{props.pending.can_poison ? "选择一名目标" : "已用完"}</span>
        </label>
      </div>
      {props.witchChoice === "poison" ? (
        <TargetSelect
          legalTargets={props.pending.legal_targets}
          playersById={props.playersById}
          selectedTarget={props.selectedTarget}
          setSelectedTarget={props.setSelectedTarget}
          placeholder="选择毒杀目标"
        />
      ) : null}
    </div>
  );
}

/** 展示真人当前合法可见的私有信息。 */
function KnownInfo({
  snapshot,
  playersById,
}: {
  snapshot: GameSnapshot | null;
  playersById: Map<string, PublicPlayer>;
}) {
  const human = snapshot ? playersById.get(snapshot.human_player_id) ?? null : null;
  return (
    <div className="known-info">
      <div className="panel-title">
        <span>你的信息</span>
        <strong>{human?.name ?? "未入座"}</strong>
      </div>
      {!snapshot ? <p>开局后显示你的身份、阵营和私有信息。</p> : null}
      {snapshot ? (
        <>
          <div className="identity-row">
            <span>身份</span>
            <strong>{roleLabel(human?.role ?? "")}</strong>
          </div>
          <div className="identity-row">
            <span>阵营</span>
            <strong>{alignmentLabel(human?.alignment ?? "")}</strong>
          </div>
          {snapshot.known_werewolves.length > 0 ? (
            <div className="private-list">
              <span>狼队</span>
              <p>{snapshot.known_werewolves.map((id) => playerName(id, playersById)).join("、")}</p>
            </div>
          ) : null}
          {Object.keys(snapshot.seer_results).length > 0 ? (
            <div className="private-list">
              <span>查验</span>
              <ul>
                {Object.entries(snapshot.seer_results).map(([target, alignment]) => (
                  <li key={target}>
                    {playerName(target, playersById)}：{alignmentLabel(alignment)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** 真人视角的身份辅助面板，替代重复规则卡片。 */
function AssistantPanel({ panel }: { panel: AssistantPanelData | null }) {
  if (!panel) {
    return (
      <div className="assistant-card">
        <div className="panel-title">
          <span>游戏辅助</span>
          <strong>等待开局</strong>
        </div>
        <p>开局后这里会按你的身份显示专属备忘。</p>
      </div>
    );
  }
  return (
    <div className={`assistant-card assistant-${panel.role || "unknown"}`}>
      <div className="panel-title">
        <span>游戏辅助</span>
        <strong>{panel.title}</strong>
      </div>
      {panel.summary ? <p>{panel.summary}</p> : null}
      <div className="assistant-list">
        {panel.items.map((item) => (
          <div className={`assistant-item tone-${item.tone}`} key={`${item.label}-${item.value}`}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 大模型运行时设置弹窗。 */
function LlmSettingsDialog({
  config,
  form,
  loading,
  error,
  audioSettings,
  audioTrack,
  audioStatus,
  hostVoiceStatus,
  onChange,
  onAudioChange,
  onClose,
  onSave,
}: {
  config: LlmConfigStatus | null;
  form: LlmSettingsForm;
  loading: boolean;
  error: string;
  audioSettings: AudioSettings;
  audioTrack: string | null;
  audioStatus: BackgroundAudioPlaybackStatus;
  hostVoiceStatus: HostVoiceStatus;
  onChange: (form: LlmSettingsForm) => void;
  onAudioChange: (settings: AudioSettings) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const canSave = Boolean(form.base_url.trim() && form.model.trim()) && !loading;
  return (
    <div className="rules-overlay" role="dialog" aria-modal="true" aria-labelledby="llm-settings-title">
      <section className="rules-dialog llm-settings-dialog">
        <div className="rules-header">
          <div>
            <span>对局偏好</span>
            <strong id="llm-settings-title">游戏设置</strong>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="关闭设置">
            ×
          </button>
        </div>

        <div className="llm-settings-content">
          <section className="settings-section">
            <div className="settings-section-title">
              <span>声音设置</span>
              <strong>{audioSettings.enabled ? audioTrackLabel(audioTrack) : "已关闭"}</strong>
            </div>
            <label className="audio-toggle">
              <input
                checked={audioSettings.enabled}
                onChange={(event) =>
                  onAudioChange({
                    ...audioSettings,
                    enabled: event.target.checked,
                  })
                }
                type="checkbox"
              />
              <span>开启游戏背景音</span>
            </label>
            <label className="audio-volume-control">
              <span>音量 {Math.round(audioSettings.volume * 100)}%</span>
              <input
                max="100"
                min="0"
                onChange={(event) =>
                  onAudioChange({
                    ...audioSettings,
                    volume: Number(event.target.value) / 100,
                  })
                }
                type="range"
                value={Math.round(audioSettings.volume * 100)}
              />
            </label>
            <p className="settings-note">
              {audioStatusNote(audioStatus)}
            </p>
            <label className="audio-toggle">
              <input
                checked={audioSettings.hostVoiceEnabled}
                onChange={(event) =>
                  onAudioChange({
                    ...audioSettings,
                    hostVoiceEnabled: event.target.checked,
                  })
                }
                type="checkbox"
              />
              <span>开启主持语音</span>
            </label>
            <label className="audio-volume-control">
              <span>主持语音音量 {Math.round(audioSettings.hostVoiceVolume * 100)}%</span>
              <input
                max="100"
                min="0"
                onChange={(event) =>
                  onAudioChange({
                    ...audioSettings,
                    hostVoiceVolume: Number(event.target.value) / 100,
                  })
                }
                type="range"
                value={Math.round(audioSettings.hostVoiceVolume * 100)}
              />
            </label>
            <p className="settings-note">
              {hostVoiceStatusNote(hostVoiceStatus)}
            </p>
          </section>

          <section className="settings-section">
            <div className="settings-section-title">
              <span>AI 服务</span>
              <strong>接口配置</strong>
            </div>
            <label>
              <span>API URL</span>
              <input
                value={form.base_url}
                onChange={(event) => onChange({ ...form, base_url: event.target.value })}
                placeholder="https://api.example.com/v1"
                disabled={loading}
              />
            </label>
            <label>
              <span>模型名称</span>
              <input
                value={form.model}
                onChange={(event) => onChange({ ...form, model: event.target.value })}
                placeholder="gpt-4o-mini"
                disabled={loading}
              />
            </label>
            <label>
              <span>API Key</span>
              <input
                value={form.api_key}
                onChange={(event) => onChange({ ...form, api_key: event.target.value })}
                placeholder={config?.api_key_configured ? "留空保持当前密钥" : "请输入 API Key"}
                type="password"
                disabled={loading}
              />
            </label>

            <div className="llm-settings-meta">
              <span>当前状态</span>
              <strong>{config ? llmStatusLabel(config) : loading ? "读取中" : "未读取"}</strong>
              <span>Key</span>
              <strong>{config?.api_key_preview || "未配置"}</strong>
            </div>
          </section>
        </div>

        <div className="llm-settings-footer">
          {error ? <div className="error llm-settings-error">{error}</div> : null}
          <div className="llm-settings-actions">
            <button className="secondary-button" onClick={onClose} type="button" disabled={loading}>
              关闭
            </button>
            <button onClick={onSave} type="button" disabled={!canSave}>
              {loading ? "保存中" : "保存 AI 配置"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

/** 完整规则弹窗。 */
function RulesDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="rules-overlay" role="dialog" aria-modal="true" aria-labelledby="rules-title">
      <section className="rules-dialog">
        <div className="rules-header">
          <div>
            <span>完整规则</span>
            <strong id="rules-title">12 人标准狼人杀</strong>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="关闭规则">
            ×
          </button>
        </div>

        <div className="rules-content">
          <section>
            <h2>角色配置</h2>
            <ul>
              <li>狼人 4 人：夜晚共同选择一名非狼人玩家袭击；白天可伪装、发言、投票。</li>
              <li>村民 4 人：没有夜间技能，只能依靠发言、票型、死亡信息和逻辑找狼。</li>
              <li>预言家 1 人：每晚查验一名存活玩家，得到“好人阵营”或“狼人阵营”。</li>
              <li>女巫 1 人：有一瓶解药和一瓶毒药；每晚可救被袭击玩家或毒杀一名玩家，同一晚不能同时救毒。</li>
              <li>猎人 1 人：被狼人袭击或白天放逐出局时可以开枪带走一名存活玩家；被女巫毒死不能开枪。</li>
              <li>白痴 1 人：白天被放逐时可以翻牌，之后继续发言但失去投票权。</li>
            </ul>
          </section>

          <section>
            <h2>游戏流程</h2>
            <ol>
              <li>夜晚：狼人提出刀人意向并统一目标，女巫用药，预言家查验，猎人和白痴确认身份。</li>
              <li>天亮：主持公布夜晚死亡情况，并处理猎人开枪、白痴翻牌、警徽移交等死亡反应。</li>
              <li>首个白天：若警徽未流失，进入警长竞选；候选人发言，警下玩家投票。</li>
              <li>白天发言：按座位顺序或警长指定方向发言；有警长时警长最后发言总结。</li>
              <li>投票放逐：存活且有投票权的玩家投票；平票进入 PK，PK 再平票则当日无人出局。</li>
              <li>放逐结算：被放逐玩家出局，并触发猎人、白痴、警徽移交等后续效果。</li>
              <li>若没有阵营胜利，进入下一轮夜晚。</li>
            </ol>
          </section>

          <section>
            <h2>警长与警徽</h2>
            <ul>
              <li>警长只在开局后的第一次白天竞选；竞选成功后，只要警长活着就一直保留警徽。</li>
              <li>警长白天投票权重为 1.5 票。</li>
              <li>每天白天发言前，存活警长可选择从自己左边逆时针开始，或从右边顺时针开始，确保自己最后发言。</li>
              <li>警长出局时可以把警徽移交给一名信任的存活玩家，也可以撕毁警徽。</li>
              <li>警长竞选连续两次平票，警徽流失，本局之后不再竞选。</li>
              <li>第一次警长竞选中狼人自爆会暂停竞选并进入黑夜；下一个白天继续竞选。若连续两次因此自爆，警徽流失。</li>
            </ul>
          </section>

          <section>
            <h2>胜利条件</h2>
            <ul>
              <li>好人阵营胜利：所有狼人出局。</li>
              <li>狼人阵营胜利：所有普通村民出局，或所有神职玩家出局。</li>
            </ul>
          </section>
        </div>
      </section>
    </div>
  );
}

/** 展示真人视角可见事件流。 */
function EventFeed({
  events,
  playersById,
  streamingReply,
}: {
  events: GameEvent[];
  playersById: Map<string, PublicPlayer>;
  streamingReply: StreamingReply | null;
}) {
  const visibleEvents = events
    .map((event, index) => ({
      event,
      index,
      description: describeEvent(event, playersById),
    }))
    .filter(({ description }) => description !== GENERIC_EVENT_DESCRIPTION)
    .reverse();

  return (
    <div className="event-feed">
      <div className="panel-title">
        <span>事件流</span>
        <strong>{visibleEvents.length}</strong>
      </div>
      {visibleEvents.length === 0 && !streamingReply ? <div className="event-empty">暂无事件</div> : null}
      {streamingReply ? (
        <div className={`event-item streaming-reply ${streamingReply.status}`}>
          <span>
            第 {streamingReply.round_no} 轮 · {phaseLabel(streamingReply.phase)} · 玩家发言
          </span>
          <strong>{playerName(streamingReply.player_id, playersById)}</strong>
          <p>{streamingReply.text.trim() || "正在组织发言..."}</p>
        </div>
      ) : null}
      {visibleEvents.map(({ event, index, description }) => (
        <div className="event-item" key={`${event.type}-${index}`}>
          <span>
            第 {event.round_no} 轮 · {phaseLabel(event.phase)} · {eventTypeLabel(event.type)}
          </span>
          <strong>{event.actor_id ? playerName(event.actor_id, playersById) : "系统"}</strong>
          <p>{description}</p>
        </div>
      ))}
    </div>
  );
}

function shouldKeepStreamingReply(
  reply: StreamingReply | null,
  snapshot: GameSnapshot,
): reply is StreamingReply {
  if (!reply || reply.game_id !== snapshot.game_id) return false;
  if (snapshot.events.some((event) => isPersistedSpeechForReply(event, reply))) return false;
  if (reply.status !== "done") return true;
  return true;
}

function isPersistedSpeechForReply(event: GameEvent, reply: StreamingReply): boolean {
  if (event.type !== "day.speech_recorded") return false;
  if (event.actor_id !== reply.player_id) return false;
  if (event.round_no !== reply.round_no || event.phase !== reply.phase) return false;
  const speech = typeof event.payload.speech === "string" ? event.payload.speech : "";
  if (!reply.text.trim()) return true;
  return speech === reply.text || speech.startsWith(reply.text) || reply.text.startsWith(speech);
}

/** 判断桌面上的某名玩家当前是否可被选为目标。 */
function canSelectPlayer(
  pending: PendingAction | null,
  player: PublicPlayer,
  witchChoice: WitchChoice,
): boolean {
  if (!pending || !player.alive) return false;
  if (!pending.legal_targets.includes(player.player_id)) return false;
  if (pending.action_type === "witch_action") {
    return witchChoice === "poison";
  }
  return pending.action_type !== "speak";
}

/** 只有公开发言和投票阶段才允许座位高亮，避免夜间神职行动暴露身份。 */
function shouldHighlightCurrentActor(snapshot: GameSnapshot | null): boolean {
  if (!snapshot?.current_actor_id) return false;
  if (
    snapshot.pending_action &&
    ["speak", "vote", "sheriff_vote"].includes(snapshot.pending_action.action_type)
  ) {
    return true;
  }
  return [
    "sheriff_election",
    "day_speech",
    "day_vote",
    "exile_pk_speech",
    "exile_pk_vote",
  ].includes(snapshot.phase);
}

/** 判断当前 pending action 表单是否可以提交。 */
function canSubmit(
  pending: PendingAction,
  selectedTarget: string,
  witchChoice: WitchChoice,
  speechDirection: SpeechDirection,
  sheriffRunChoice: SheriffRunChoice,
): boolean {
  if (pending.action_type === "speak") return true;
  if (pending.action_type === "sheriff_run") return Boolean(sheriffRunChoice);
  if (pending.action_type === "vote") return true;
  if (pending.action_type === "sheriff_vote") return true;
  if (pending.action_type === "sheriff_order") return Boolean(speechDirection);
  if (pending.action_type === "hunter_shot") return true;
  if (pending.action_type === "sheriff_handoff") return true;
  if (pending.action_type === "idiot_reveal") return true;
  if (pending.action_type === "witch_action") {
    if (witchChoice === "poison") return Boolean(selectedTarget);
    if (witchChoice === "save") return pending.can_save;
    return true;
  }
  return Boolean(selectedTarget);
}

/** 将前端表单状态转换为后端行动请求体。 */
function buildPayload(
  pending: PendingAction,
  selectedTarget: string,
  speech: string,
  witchChoice: WitchChoice,
  speechDirection: SpeechDirection,
  sheriffRunChoice: SheriffRunChoice,
  idiotRevealChoice: IdiotRevealChoice,
) {
  if (pending.action_type === "speak") {
    return { action_type: "speak", speech: speech.trim() || "我先听大家发言，继续观察。" };
  }
  if (pending.action_type === "witch_action") {
    return {
      action_type: "witch_action",
      save: witchChoice === "save",
      poison_target_id: witchChoice === "poison" ? selectedTarget || null : null,
    };
  }
  if (pending.action_type === "idiot_reveal") {
    return { action_type: "idiot_reveal", reveal: idiotRevealChoice === "reveal" };
  }
  if (pending.action_type === "vote" && !selectedTarget) {
    return { action_type: "abstain" };
  }
  if (pending.action_type === "sheriff_vote") {
    return { action_type: "sheriff_vote", target_id: selectedTarget || null };
  }
  if (pending.action_type === "sheriff_run") {
    return { action_type: sheriffRunChoice === "run" ? "sheriff_run" : "abstain" };
  }
  if (pending.action_type === "sheriff_order") {
    return { action_type: "sheriff_order", direction: speechDirection || "counterclockwise" };
  }
  if (pending.action_type === "hunter_shot") {
    return { action_type: "hunter_shot", target_id: selectedTarget || null };
  }
  if (pending.action_type === "sheriff_handoff") {
    return { action_type: "sheriff_handoff", target_id: selectedTarget || null };
  }
  return {
    action_type: pending.action_type,
    target_id: selectedTarget || null,
  };
}

/** 根据待行动类型和已选目标生成提交按钮文案。 */
function submitLabel(
  pending: PendingAction,
  selectedPlayer: PublicPlayer | null,
  witchChoice: WitchChoice,
  speechDirection: SpeechDirection,
  sheriffRunChoice: SheriffRunChoice,
  idiotRevealChoice: IdiotRevealChoice,
): string {
  if (pending.action_type === "speak") return "结束发言";
  if (pending.action_type === "sheriff_run") return sheriffRunChoice === "run" ? "确认上警" : "不上警";
  if (pending.action_type === "vote") {
    return selectedPlayer ? `投给 ${selectedPlayer.seat} 号` : "弃票";
  }
  if (pending.action_type === "sheriff_vote") {
    return selectedPlayer ? `支持 ${selectedPlayer.seat} 号` : "弃票";
  }
  if (pending.action_type === "hunter_shot") {
    return selectedPlayer ? `开枪带走 ${selectedPlayer.seat} 号` : "不开枪";
  }
  if (pending.action_type === "sheriff_handoff") {
    return selectedPlayer ? `移交给 ${selectedPlayer.seat} 号` : "撕毁警徽";
  }
  if (pending.action_type === "sheriff_order") {
    if (speechDirection === "counterclockwise") return "左边开始发言";
    if (speechDirection === "clockwise") return "右边开始发言";
    return "选择发言顺序";
  }
  if (pending.action_type === "idiot_reveal") return idiotRevealChoice === "reveal" ? "\u7ffb\u724c" : "\u4e0d\u7ffb\u724c";
  if (pending.action_type === "witch_action") {
    if (witchChoice === "save") return "使用解药";
    if (witchChoice === "poison") return selectedPlayer ? `毒杀 ${selectedPlayer.seat} 号` : "选择毒药目标";
    return "不用药";
  }
  if (pending.action_type === "werewolf_kill") return selectedPlayer ? `袭击 ${selectedPlayer.seat} 号` : "选择袭击目标";
  if (pending.action_type === "seer_check") return selectedPlayer ? `查验 ${selectedPlayer.seat} 号` : "选择查验目标";
  return "提交行动";
}

/** 将行动类型转换为中文标签。 */
function actionTypeLabel(type: string): string {
  if (type === "werewolf_kill") return "狼人行动";
  if (type === "seer_check") return "预言家查验";
  if (type === "witch_action") return "女巫行动";
  if (type === "hunter_shot") return "猎人开枪";
  if (type === "idiot_reveal") return "白痴翻牌";
  if (type === "sheriff_run") return "是否上警";
  if (type === "sheriff_vote") return "警长投票";
  if (type === "sheriff_order") return "警长发言顺序";
  if (type === "sheriff_handoff") return "警徽移交";
  if (type === "speak") return "白天发言";
  if (type === "vote") return "投票放逐";
  return "玩家行动";
}

/** 将领域事件转换为玩家可读的中文描述。 */
const GENERIC_EVENT_DESCRIPTION = "系统记录了一条游戏事件。";

function describeEvent(event: GameEvent, playersById: Map<string, PublicPlayer>): string {
  const payload = event.payload;
  if (event.type === "day.speech_recorded") {
    return String(payload.speech ?? "");
  }
  if (event.type === "day.vote_recorded") {
    return payload.target_id
      ? `投给 ${playerName(String(payload.target_id), playersById)}`
      : "选择弃票";
  }
  if (event.type === "day.vote_resolved") {
    return payload.exiled_player_id
      ? `${playerName(String(payload.exiled_player_id), playersById)} 被放逐`
      : "平票或无人出局";
  }
  if (event.type === "night.resolved") {
    const dead = payload.dead_player_ids;
    return Array.isArray(dead) && dead.length
      ? `昨夜死亡：${dead.map((id) => playerName(String(id), playersById)).join("、")}`
      : "昨夜平安夜";
  }
  if (event.type === "game.win_checked" && payload.winner) {
    return `胜者：${winnerLabel(String(payload.winner))}`;
  }
  if (event.type === "game.created") {
    return "创建 12 人标准局，系统已随机分配座位和身份。";
  }
  if (event.type === "role.assigned") {
    return "你的身份已发放。";
  }
  if (event.type === "night.started") {
    return "天黑请闭眼。";
  }
  if (event.type === "night.werewolf_kill_selected") {
    return "狼人已选择袭击目标。";
  }
  if (event.type === "night.werewolf_kill_intent_recorded") {
    return payload.target_id
      ? `狼人意向：${playerName(String(payload.target_id), playersById)}`
      : "狼人已提交刀人意向。";
  }
  if (event.type === "night.werewolf_consensus_required") {
    return "狼人刀人意向不一致，主持要求重新统一目标。";
  }
  if (event.type === "night.seer_checked") {
    return `查验结果：${playerName(String(payload.target_id ?? ""), playersById)} 是 ${alignmentLabel(String(payload.alignment ?? ""))}`;
  }
  if (event.type === "night.witch_acted") {
    return describeWitchEvent(payload, playersById);
  }
  if (event.type === "night.hunter_status_confirmed") {
    return "猎人已确认技能状态。";
  }
  if (event.type === "night.idiot_confirmed") {
    return "白痴已确认身份。";
  }
  if (event.type === "sheriff.election_started") {
    return "警长竞选开始。";
  }
  if (event.type === "sheriff.candidates_set") {
    const candidates = payload.candidate_ids;
    return Array.isArray(candidates) && candidates.length
      ? `警上玩家：${candidates.map((id) => playerName(String(id), playersById)).join("、")}`
      : "无人上警。";
  }
  if (event.type === "sheriff.vote_recorded") {
    return payload.target_id
      ? `支持 ${playerName(String(payload.target_id), playersById)}`
      : "选择弃票";
  }
  if (event.type === "sheriff.assigned") {
    return `${playerName(String(payload.sheriff_id ?? ""), playersById)} 当选警长`;
  }
  if (event.type === "sheriff.badge_lost") {
    return "警徽流失。";
  }
  if (event.type === "sheriff.handed_off") {
    return `警徽移交给 ${playerName(String(payload.target_id ?? ""), playersById)}`;
  }
  if (event.type === "death.hunter_shot") {
    return `猎人开枪带走 ${playerName(String(payload.target_id ?? ""), playersById)}`;
  }
  if (event.type === "death.idiot_revealed") {
    return "白痴翻牌，继续发言但失去投票权。";
  }
  if (event.type === "day.pk_started") {
    const tied = payload.tied_player_ids;
    return Array.isArray(tied) ? `进入 PK：${tied.map((id) => playerName(String(id), playersById)).join("、")}` : "进入 PK。";
  }
  if (event.type === "day.no_exile") {
    return "再次平票，今日无人出局。";
  }
  if (event.type === "day.werewolf_self_exploded") {
    return "狼人自爆，跳过白天进入黑夜。";
  }
  if (event.type === "game.next_round_started") {
    return "进入下一轮。";
  }
  if (event.type === "game.forced_finish") {
    return `系统结束对局，胜者：${winnerLabel(String(payload.winner ?? ""))}`;
  }
  return GENERIC_EVENT_DESCRIPTION;
}

/** 将事件类型转换为简短中文标签。 */
function eventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    "game.created": "创建对局",
    "role.assigned": "身份发放",
    "night.started": "夜晚开始",
    "night.werewolf_kill_intent_recorded": "狼人意向",
    "night.werewolf_consensus_required": "狼队统一",
    "night.werewolf_kill_selected": "狼人行动",
    "night.seer_checked": "预言家查验",
    "night.witch_acted": "女巫行动",
    "night.hunter_status_confirmed": "猎人确认",
    "night.idiot_confirmed": "白痴确认",
    "night.resolved": "夜晚结算",
    "sheriff.election_started": "警长竞选",
    "sheriff.candidates_set": "警上名单",
    "sheriff.vote_recorded": "警长投票",
    "sheriff.vote_resolved": "警长结算",
    "sheriff.assigned": "警长产生",
    "sheriff.badge_lost": "警徽流失",
    "sheriff.handed_off": "警徽移交",
    "death.reaction_resolved": "死亡结算",
    "death.hunter_shot": "猎人开枪",
    "death.idiot_revealed": "白痴翻牌",
    "day.speech_recorded": "玩家发言",
    "day.vote_recorded": "投票",
    "day.vote_resolved": "投票结算",
    "day.pk_started": "平票 PK",
    "day.no_exile": "无人出局",
    "day.werewolf_self_exploded": "狼人自爆",
    "game.win_checked": "胜负检查",
    "game.next_round_started": "新回合",
    "game.forced_finish": "系统结束",
  };
  return labels[type] ?? "游戏事件";
}

/** 描述女巫行动事件。 */
function describeWitchEvent(
  payload: Record<string, unknown>,
  playersById: Map<string, PublicPlayer>,
): string {
  const usedSave = Boolean(payload.save);
  const poisonTarget = typeof payload.poison_target_id === "string" ? payload.poison_target_id : "";
  if (usedSave && poisonTarget) {
    return `女巫使用了解药，并毒杀 ${playerName(poisonTarget, playersById)}`;
  }
  if (usedSave) {
    return "女巫使用了解药。";
  }
  if (poisonTarget) {
    return `女巫毒杀 ${playerName(poisonTarget, playersById)}`;
  }
  return "女巫没有使用药。";
}

/** 根据玩家 id 返回座位号和昵称。 */
function playerName(playerId: string, playersById: Map<string, PublicPlayer>): string {
  const player = playersById.get(playerId);
  return player ? `${player.seat} 号 ${player.name}` : playerId || "无";
}

/** 将阶段枚举值转换为中文标签。 */
function phaseLabel(phase?: string): string {
  if (phase === "night") return "夜晚";
  if (phase === "sheriff_election") return "警长竞选";
  if (phase === "day_speech") return "白天发言";
  if (phase === "day_vote") return "白天投票";
  if (phase === "exile_pk_speech") return "PK 发言";
  if (phase === "exile_pk_vote") return "PK 投票";
  if (phase === "game_over") return "游戏结束";
  return "未开始";
}

/** 将身份枚举值转换为中文标签。 */
function roleLabel(role: string): string {
  if (role === "werewolf") return "狼人";
  if (role === "seer") return "预言家";
  if (role === "witch") return "女巫";
  if (role === "hunter") return "猎人";
  if (role === "idiot") return "白痴";
  if (role === "villager") return "村民";
  return role || "未知";
}

/** 将阵营枚举值转换为中文标签。 */
function alignmentLabel(alignment: string): string {
  if (alignment === "werewolves") return "狼人阵营";
  if (alignment === "villagers") return "好人阵营";
  return "未知";
}

function deathReasonLabel(reason: string): string {
  if (reason === "werewolf_kill") return "狼人袭击";
  if (reason === "witch_poison") return "女巫毒药";
  if (reason === "exile") return "白天放逐";
  if (reason === "hunter_shot") return "猎人开枪";
  if (reason === "self_explode") return "狼人自爆";
  return reason || "未知原因";
}

/** 将胜者枚举值转换为中文标签。 */
function winnerLabel(winner?: string | null): string {
  if (winner === "werewolves") return "狼人阵营";
  if (winner === "villagers") return "好人阵营";
  return winner ? winner : "未决";
}

function audioTrackLabel(track?: string | null): string {
  if (track === "night") return "夜晚环境音";
  if (track === "vote") return "投票环境音";
  if (track === "day") return "白天讨论环境音";
  return "等待对局";
}

function audioTrackForSnapshot(snapshot: GameSnapshot | null): "day" | "night" | "vote" | null {
  if (!snapshot || snapshot.phase === "game_over") return null;
  if (snapshot.phase === "night") return "night";
  if (snapshot.phase === "day_vote" || snapshot.phase === "exile_pk_vote") return "vote";
  if (snapshot.phase === "sheriff_election") {
    const message = snapshot.host_cue?.message || snapshot.god_message || "";
    if (snapshot.pending_action?.action_type === "sheriff_vote" || message.includes("\u6295\u7968")) return "vote";
    return "day";
  }
  return "day";
}

function readStoredAudioSettings(): AudioSettings {
  const storedEnabled = window.localStorage.getItem(AUDIO_ENABLED_KEY);
  const enabled = storedEnabled === null ? true : storedEnabled === "true";
  const storedVolume = Number(window.localStorage.getItem(AUDIO_VOLUME_KEY));
  const volume = Number.isFinite(storedVolume) ? Math.max(0, Math.min(1, storedVolume)) : 0.35;
  const storedHostVoiceEnabled = window.localStorage.getItem(HOST_VOICE_ENABLED_KEY);
  const hostVoiceEnabled =
    storedHostVoiceEnabled === null ? true : storedHostVoiceEnabled === "true";
  const storedHostVoiceVolume = Number(window.localStorage.getItem(HOST_VOICE_VOLUME_KEY));
  const hostVoiceVolume = Number.isFinite(storedHostVoiceVolume)
    ? Math.max(0, Math.min(1, storedHostVoiceVolume))
    : 0.85;
  return { enabled, volume, hostVoiceEnabled, hostVoiceVolume };
}

function audioStatusNote(status: BackgroundAudioPlaybackStatus): string {
  if (status === "blocked") return "\u6d4f\u89c8\u5668\u5df2\u963b\u6b62\u81ea\u52a8\u64ad\u653e\uff0c\u8bf7\u5728\u672c\u7a97\u53e3\u5185\u70b9\u51fb\u4e00\u6b21\u4ee5\u542f\u52a8\u80cc\u666f\u97f3\u3002";
  if (status === "load_failed") return "\u80cc\u666f\u97f3\u8d44\u6e90\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u97f3\u9891\u63a5\u53e3\u6216 data \u76ee\u5f55\u3002";
  if (status === "waiting") return "\u6b63\u5728\u5c1d\u8bd5\u542f\u52a8\u80cc\u666f\u97f3\u3002";
  if (status === "playing") return "\u80cc\u666f\u97f3\u4f1a\u968f\u591c\u665a\u3001\u767d\u5929\u8ba8\u8bba\u548c\u6295\u7968\u9636\u6bb5\u81ea\u52a8\u5207\u6362\u3002";
  return "\u5f00\u5c40\u540e\u5c06\u9ed8\u8ba4\u64ad\u653e\u80cc\u666f\u97f3\u3002";
}

function hostVoiceStatusNote(status: HostVoiceStatus): string {
  if (status === "blocked") return "浏览器已阻止主持语音，请在本窗口内点击一次以启用。";
  if (status === "failed") return "主持语音加载失败时会自动降级为文字播报。";
  if (status === "playing") return "主持语音播放时，背景音会自动降低。";
  if (status === "pausing") return "主持语音正在按流程停顿。";
  return "主持语音会跟随中央主持台词顺序播放。";
}

function llmStatusLabel(config: LlmConfigStatus): string {
  return config.api_key_configured ? "online multi-agent" : "online agent not configured";
}

function isGameSnapshot(value: unknown): value is GameSnapshot {
  return isRecord(value) && typeof value.game_id === "string" && Array.isArray(value.players);
}

function isAgentReplyStreamMessage(value: unknown): value is AgentReplyStreamMessage {
  if (!isRecord(value)) return false;
  return (
    (value.type === "agent_reply_started" ||
      value.type === "agent_reply_delta" ||
      value.type === "agent_reply_completed" ||
      value.type === "agent_reply_failed") &&
    typeof value.game_id === "string" &&
    typeof value.player_id === "string" &&
    typeof value.stream_id === "string" &&
    typeof value.text === "string" &&
    typeof value.node === "string" &&
    typeof value.round_no === "number" &&
    typeof value.phase === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function defaultPlayerName(user: AuthUser): string {
  const name = user.display_name?.trim() || user.email.split("@")[0] || "玩家";
  return name.slice(0, 18);
}
