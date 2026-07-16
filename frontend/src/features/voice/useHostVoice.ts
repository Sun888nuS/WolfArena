import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";

import { hostVoiceUrl } from "../../services/game";
import type { GameSnapshot } from "../../types/game";

export type HostVoiceStatus =
  | "idle"
  | "playing"
  | "pausing"
  | "done"
  | "skipped"
  | "failed"
  | "blocked";

type UseHostVoiceParams = {
  snapshot: GameSnapshot | null;
  enabled: boolean;
  volume: number;
  mutedByStreaming?: boolean;
};

type HostVoiceState = {
  speaking: boolean;
  readyForAdvance: boolean;
  status: HostVoiceStatus;
  completedCueId: string | null;
  followUpCueId: string | null;
  unlock: () => void;
};

const DEFAULT_UNLOCK_VOICE_KEY = "night_close_eyes";
const ADVANCE_FALLBACK_MIN_MS = 250;

export function useHostVoice({
  snapshot,
  enabled,
  volume,
  mutedByStreaming = false,
}: UseHostVoiceParams): HostVoiceState {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const runIdRef = useRef(0);
  const handledCueIdsRef = useRef<Set<string>>(new Set());
  const [status, setStatus] = useState<HostVoiceStatus>("idle");
  const [completedCueId, setCompletedCueId] = useState<string | null>(null);
  const [followUpCueId, setFollowUpCueId] = useState<string | null>(null);

  const cue = snapshot?.host_cue ?? null;
  const cueId = cue?.cue_id ?? null;
  const blocksAutoAdvance = Boolean(cue?.blocks_auto_advance);
  const readyForAdvance = !blocksAutoAdvance || (cueId !== null && completedCueId === cueId);
  const speaking = status === "playing" || status === "pausing";

  const unlock = useCallback(() => {
    const audio = new Audio(hostVoiceUrl(cue?.voice_key ?? DEFAULT_UNLOCK_VOICE_KEY));
    audio.volume = 0;
    const playPromise = audio.play();
    if (playPromise) {
      playPromise
        .then(() => {
          audio.pause();
          audio.removeAttribute("src");
          audio.load();
        })
        .catch(() => {
          // A later real playback attempt will surface the blocked state.
        });
    }
  }, [cue?.voice_key]);

  useEffect(() => {
    const currentCue = snapshot?.host_cue ?? null;
    const currentCueId = currentCue?.cue_id ?? null;
    runIdRef.current += 1;
    const runId = runIdRef.current;
    stopAudio(audioRef);
    clearTimer(timerRef);
    setFollowUpCueId(null);

    if (!snapshot || !currentCue || !currentCueId) {
      setCompletedCueId(null);
      setStatus("idle");
      return;
    }
    if (handledCueIdsRef.current.has(currentCueId)) {
      setCompletedCueId(currentCueId);
      setStatus("done");
      return;
    }
    setCompletedCueId(null);

    const completeCue = (completedId: string) => {
      handledCueIdsRef.current.add(completedId);
      setCompletedCueId(completedId);
    };

    if (!currentCue.visible || !currentCue.blocks_auto_advance || mutedByStreaming) {
      setStatus("skipped");
      completeCue(currentCueId);
      return;
    }
    const voiceKey = currentCue.voice_key;
    const followUpVoiceKey = currentCue.follow_up_voice_key;
    const voicePauseMs = currentCue.voice_pause_ms;
    const holdMs = currentCue.hold_ms;
    if (!enabled || !voiceKey) {
      setStatus("skipped");
      waitThenComplete(holdMs, runId, currentCueId, timerRef, runIdRef, completeCue);
      return;
    }
    const activeCueId = currentCueId;
    const activeVoiceKey = voiceKey;

    let cancelled = false;

    async function playCueQueue() {
      try {
        setStatus("playing");
        await playVoice(activeVoiceKey, volume, audioRef, runId, runIdRef);
        if (cancelled || runIdRef.current !== runId) return;

        if (followUpVoiceKey) {
          const pauseMs = Math.max(0, voicePauseMs);
          if (pauseMs > 0) {
            setStatus("pausing");
            await wait(pauseMs, timerRef, runId, runIdRef);
          }
          if (cancelled || runIdRef.current !== runId) return;
          setFollowUpCueId(activeCueId);
          setStatus("playing");
          await playVoice(followUpVoiceKey, volume, audioRef, runId, runIdRef);
        }

        if (cancelled || runIdRef.current !== runId) return;
        setStatus("done");
        completeCue(activeCueId);
      } catch (error) {
        if (cancelled || runIdRef.current !== runId) return;
        setStatus(isAutoplayBlocked(error) ? "blocked" : "failed");
        waitThenComplete(holdMs, runId, activeCueId, timerRef, runIdRef, completeCue);
      }
    }

    void playCueQueue();
    return () => {
      cancelled = true;
      stopAudio(audioRef);
      clearTimer(timerRef);
    };
  }, [
    enabled,
    mutedByStreaming,
    snapshot?.host_cue?.blocks_auto_advance,
    snapshot?.host_cue?.cue_id,
    snapshot?.host_cue?.follow_up_voice_key,
    snapshot?.host_cue?.hold_ms,
    snapshot?.host_cue?.visible,
    snapshot?.host_cue?.voice_key,
    snapshot?.host_cue?.voice_pause_ms,
    volume,
  ]);

  return {
    speaking,
    readyForAdvance,
    status,
    completedCueId,
    followUpCueId,
    unlock,
  };
}

function playVoice(
  voiceKey: string,
  volume: number,
  audioRef: MutableRefObject<HTMLAudioElement | null>,
  runId: number,
  runIdRef: MutableRefObject<number>,
): Promise<void> {
  stopAudio(audioRef);
  const audio = new Audio(hostVoiceUrl(voiceKey));
  audio.preload = "auto";
  audio.volume = clampVolume(volume);
  audioRef.current = audio;
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("error", onError);
    };
    const onEnded = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("host voice failed to load"));
    };
    audio.addEventListener("ended", onEnded, { once: true });
    audio.addEventListener("error", onError, { once: true });
    const playPromise = audio.play();
    if (playPromise) {
      playPromise.catch((error: unknown) => {
        cleanup();
        reject(error);
      });
    }
    if (runIdRef.current !== runId) {
      cleanup();
      resolve();
    }
  });
}

function wait(
  ms: number,
  timerRef: MutableRefObject<number | null>,
  runId: number,
  runIdRef: MutableRefObject<number>,
): Promise<void> {
  clearTimer(timerRef);
  return new Promise((resolve) => {
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      if (runIdRef.current === runId) resolve();
    }, ms);
  });
}

function waitThenComplete(
  holdMs: number,
  runId: number,
  cueId: string,
  timerRef: MutableRefObject<number | null>,
  runIdRef: MutableRefObject<number>,
  setCompletedCueId: (cueId: string) => void,
) {
  const delay = Math.max(ADVANCE_FALLBACK_MIN_MS, holdMs);
  clearTimer(timerRef);
  timerRef.current = window.setTimeout(() => {
    timerRef.current = null;
    if (runIdRef.current === runId) {
      setCompletedCueId(cueId);
    }
  }, delay);
}

function stopAudio(audioRef: MutableRefObject<HTMLAudioElement | null>) {
  const audio = audioRef.current;
  if (!audio) return;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  audioRef.current = null;
}

function clearTimer(timerRef: MutableRefObject<number | null>) {
  if (timerRef.current !== null) {
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }
}

function clampVolume(volume: number): number {
  return Math.max(0, Math.min(1, volume));
}

function isAutoplayBlocked(error: unknown): boolean {
  return error instanceof DOMException && error.name === "NotAllowedError";
}
