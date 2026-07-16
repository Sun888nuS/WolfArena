import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";

import { backgroundAudioUrl, type BackgroundAudioTrack } from "../../services/game";
import type { GameSnapshot } from "../../types/game";

type AudioSettings = {
  enabled: boolean;
  volume: number;
};

export type BackgroundAudioPlaybackStatus =
  | "idle"
  | "waiting"
  | "playing"
  | "blocked"
  | "load_failed";

type BackgroundAudioStatus = {
  track: BackgroundAudioTrack | null;
  status: BackgroundAudioPlaybackStatus;
  blocked: boolean;
  loadFailed: boolean;
  waitingForGesture: boolean;
  unlock: (preferredTrack?: BackgroundAudioTrack | null, volumeOverride?: number) => void;
};

type UseBackgroundAudioParams = {
  snapshot: GameSnapshot | null;
  settings: AudioSettings;
  voiceDucking?: boolean;
};

const FADE_MS = 600;
const DUCKING_VOLUME_RATIO = 0.38;

export function useBackgroundAudio({
  snapshot,
  settings,
  voiceDucking = false,
}: UseBackgroundAudioParams): BackgroundAudioStatus {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fadeTimerRef = useRef<number | null>(null);
  const [status, setStatus] = useState<BackgroundAudioPlaybackStatus>("idle");
  const track = useMemo(() => backgroundTrackForSnapshot(snapshot), [snapshot]);
  const volumeRatio = voiceDucking ? DUCKING_VOLUME_RATIO : 1;
  const targetVolume = settings.enabled ? clampVolume(settings.volume) * volumeRatio : 0;

  useEffect(() => {
    return () => {
      stopFade(fadeTimerRef);
      stopCurrentAudio(audioRef, fadeTimerRef);
    };
  }, []);

  const unlock = useCallback(
    (preferredTrack: BackgroundAudioTrack | null = track, volumeOverride = settings.volume) => {
      if (preferredTrack === null) return;
      const onLoadError = () => {
        if (audioRef.current?.dataset.track === preferredTrack) {
          setStatus("load_failed");
        }
      };
      const audio = ensureAudio(preferredTrack, audioRef, fadeTimerRef, onLoadError);
      const volume = clampVolume(volumeOverride) * volumeRatio;
      setStatus("waiting");
      const playPromise = audio.play();
      if (playPromise) {
        playPromise
          .then(() => {
            if (audioRef.current !== audio) return;
            setStatus("playing");
            fadeTo(audio, volume, FADE_MS, fadeTimerRef);
          })
          .catch((error: unknown) => {
            if (audioRef.current !== audio) return;
            setStatus(isAutoplayBlocked(error) ? "blocked" : "load_failed");
          });
      } else {
        setStatus("playing");
        fadeTo(audio, volume, FADE_MS, fadeTimerRef);
      }
    },
    [settings.volume, track, volumeRatio],
  );

  useEffect(() => {
    if (!settings.enabled || track === null) {
      fadeOutAndPause(audioRef, fadeTimerRef);
      setStatus("idle");
      return;
    }

    unlock(track, settings.volume);
  }, [settings.enabled, settings.volume, targetVolume, track, unlock]);

  return {
    track: settings.enabled ? track : null,
    status,
    blocked: status === "blocked",
    loadFailed: status === "load_failed",
    waitingForGesture: status === "blocked",
    unlock,
  };
}

function backgroundTrackForSnapshot(snapshot: GameSnapshot | null): BackgroundAudioTrack | null {
  if (!snapshot || snapshot.phase === "game_over") return null;
  if (snapshot.phase === "night") return "night";
  if (snapshot.phase === "day_vote" || snapshot.phase === "exile_pk_vote") return "vote";
  if (snapshot.phase === "sheriff_election") {
    const pendingType = snapshot.pending_action?.action_type;
    const message = snapshot.host_cue?.message || snapshot.god_message || "";
    if (pendingType === "sheriff_vote" || message.includes("\u6295\u7968")) return "vote";
    return "day";
  }
  return "day";
}

function clampVolume(volume: number): number {
  return Math.max(0, Math.min(1, volume));
}

function ensureAudio(
  track: BackgroundAudioTrack,
  audioRef: MutableRefObject<HTMLAudioElement | null>,
  timerRef: MutableRefObject<number | null>,
  onLoadError: () => void,
): HTMLAudioElement {
  let audio = audioRef.current;
  if (audio && audio.dataset.track === track) return audio;

  stopCurrentAudio(audioRef, timerRef);
  audio = new Audio(backgroundAudioUrl(track));
  audio.autoplay = true;
  audio.loop = true;
  audio.preload = "auto";
  audio.volume = 0;
  audio.dataset.track = track;
  audio.addEventListener("error", onLoadError);
  audioRef.current = audio;
  return audio;
}

function fadeTo(
  audio: HTMLAudioElement,
  targetVolume: number,
  durationMs: number,
  timerRef: MutableRefObject<number | null>,
) {
  stopFade(timerRef);
  const startVolume = audio.volume;
  const startedAt = window.performance.now();
  const step = () => {
    const progress = Math.min(1, (window.performance.now() - startedAt) / durationMs);
    audio.volume = startVolume + (targetVolume - startVolume) * progress;
    if (progress < 1) {
      timerRef.current = window.setTimeout(step, 30);
    } else {
      timerRef.current = null;
    }
  };
  step();
}

function fadeOutAndPause(
  audioRef: MutableRefObject<HTMLAudioElement | null>,
  timerRef: MutableRefObject<number | null>,
) {
  const audio = audioRef.current;
  if (!audio) return;
  fadeTo(audio, 0, FADE_MS, timerRef);
  window.setTimeout(() => {
    if (audioRef.current === audio && audio.volume <= 0.02) {
      stopCurrentAudio(audioRef, timerRef);
    }
  }, FADE_MS + 50);
}

function stopCurrentAudio(
  audioRef: MutableRefObject<HTMLAudioElement | null>,
  timerRef: MutableRefObject<number | null>,
) {
  stopFade(timerRef);
  const audio = audioRef.current;
  if (!audio) return;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  audioRef.current = null;
}

function stopFade(timerRef: MutableRefObject<number | null>) {
  if (timerRef.current !== null) {
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }
}

function isAutoplayBlocked(error: unknown): boolean {
  return error instanceof DOMException && error.name === "NotAllowedError";
}
