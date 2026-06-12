import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { api } from '../api';

const PlayerContext = createContext(null);

export function usePlayer() {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error('usePlayer must be used within PlayerProvider');
  return ctx;
}

// One global <audio> element drives all 30s previews. Starting a new preview
// stops the current one.
export function PlayerProvider({ children }) {
  const audioRef = useRef(null);
  if (audioRef.current === null && typeof Audio !== 'undefined') {
    audioRef.current = new Audio();
  }
  const objectUrlRef = useRef(null);
  const currentTrackRef = useRef(null);
  const [player, setPlayer] = useState({ track: null, isPlaying: false, progress: 0 });

  useEffect(() => {
    currentTrackRef.current = player.track;
  }, [player.track]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;
    const onPlay = () => setPlayer((p) => ({ ...p, isPlaying: true }));
    const onPause = () => setPlayer((p) => ({ ...p, isPlaying: false }));
    const onTime = () => {
      const d = audio.duration || 30;
      setPlayer((p) => ({ ...p, progress: d ? Math.min(1, audio.currentTime / d) : 0 }));
    };
    const onEnded = () => setPlayer((p) => ({ ...p, isPlaying: false, progress: 1 }));
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('ended', onEnded);
    return () => {
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('timeupdate', onTime);
      audio.removeEventListener('ended', onEnded);
    };
  }, []);

  const play = useCallback(async (track) => {
    const audio = audioRef.current;
    if (!audio) return;
    if (currentTrackRef.current?.id === track.id) {
      audio.play().catch(() => {});
      return;
    }
    setPlayer({ track, isPlaying: false, progress: 0 });
    try {
      const blob = await api.previewBlob(track.id);
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      audio.src = url;
      await audio.play();
    } catch {
      /* preview unavailable — keep the bar, just don't play */
    }
  }, []);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !currentTrackRef.current) return;
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  }, []);

  const stopPlay = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPlayer({ track: null, isPlaying: false, progress: 0 });
  }, []);

  const value = { player, play, togglePlay, stopPlay };
  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}
