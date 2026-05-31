import { useCallback, useEffect, useRef, useState } from 'react';
import { AppContext } from './context';
import {
  api,
  getKey,
  setKey as persistKey,
  clearKey as forgetKey,
  validateKey,
  onUnauthorized,
} from './api';
import SearchPage from './pages/SearchPage';
import QueuePage from './pages/QueuePage';
import ArtistPage from './pages/ArtistPage';
import AlbumPage from './pages/AlbumPage';
import PreviewPlayer from './components/PreviewPlayer';
import { SearchIcon, DownloadIcon } from './components/Icons';

export default function App() {
  const [apiKey, setApiKey] = useState(getKey());
  const [tab, setTab] = useState('search');
  const [overlays, setOverlays] = useState([]); // stack of { type, id }

  // ── Singleton audio player ──────────────────────────────────────────────────
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
    // Lazily fetch the 30s stream (with auth) only on tap, as a blob URL.
    setPlayer({ track, isPlaying: false, progress: 0 });
    try {
      const blob = await api.previewBlob(track.id);
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      audio.src = url;
      await audio.play();
    } catch {
      /* preview unavailable — leave the bar showing, just don't play */
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

  // ── Download queue ──────────────────────────────────────────────────────────
  const [queueItems, setQueueItems] = useState([]);
  const [queuedKeys, setQueuedKeys] = useState(() => new Set());

  const refreshQueue = useCallback(async () => {
    if (!getKey()) return;
    try {
      const { items } = await api.queue(100);
      setQueueItems(items);
    } catch {
      /* transient — next tick retries */
    }
  }, []);

  useEffect(() => {
    if (apiKey) refreshQueue();
  }, [apiKey, refreshQueue]);

  const hasActive = queueItems.some((i) => i.status === 'pending' || i.status === 'downloading');
  useEffect(() => {
    if (!apiKey) return undefined;
    if (tab !== 'queue' && !hasActive) return undefined;
    const id = setInterval(refreshQueue, 3000);
    return () => clearInterval(id);
  }, [apiKey, tab, hasActive, refreshQueue]);

  const download = useCallback(
    async (item) => {
      setQueuedKeys((prev) => new Set(prev).add(`${item.type}:${item.deezer_id}`));
      try {
        await api.download(item);
        await refreshQueue();
      } catch {
        /* keep the optimistic "queued" mark; the server is the source of truth */
      }
    },
    [refreshQueue],
  );

  const deleteItem = useCallback(async (id) => {
    try {
      await api.deleteQueueItem(id);
      setQueueItems((prev) => prev.filter((i) => i.id !== id));
    } catch {
      /* e.g. 409 while downloading — ignore, the row stays */
    }
  }, []);

  const isQueued = useCallback(
    (type, id) => {
      if (queuedKeys.has(`${type}:${id}`)) return true;
      return queueItems.some(
        (i) =>
          i.type === type &&
          i.deezer_id === id &&
          ['pending', 'downloading', 'done'].includes(i.status),
      );
    },
    [queuedKeys, queueItems],
  );

  // ── Navigation ──────────────────────────────────────────────────────────────
  const openArtist = useCallback((id) => setOverlays((s) => [...s, { type: 'artist', id }]), []);
  const openAlbum = useCallback((id) => setOverlays((s) => [...s, { type: 'album', id }]), []);
  const back = useCallback(() => setOverlays((s) => s.slice(0, -1)), []);

  // ── Auth ────────────────────────────────────────────────────────────────────
  useEffect(() => {
    onUnauthorized(() => {
      forgetKey();
      setApiKey('');
    });
  }, []);

  if (!apiKey) {
    return (
      <Login
        onSuccess={(k) => {
          persistKey(k);
          setApiKey(k);
        }}
      />
    );
  }

  const ctx = { player, play, togglePlay, stopPlay, download, isQueued, openArtist, openAlbum };
  const topOverlay = overlays[overlays.length - 1];
  const pendingCount = queueItems.filter(
    (i) => i.status === 'pending' || i.status === 'downloading',
  ).length;

  return (
    <AppContext.Provider value={ctx}>
      <div className="mx-auto min-h-screen max-w-app bg-bg">
        <main className="pb-28">
          {tab === 'search' ? (
            <SearchPage />
          ) : (
            <QueuePage items={queueItems} onDelete={deleteItem} />
          )}
        </main>
      </div>

      {topOverlay &&
        (topOverlay.type === 'artist' ? (
          <ArtistPage key={`a${topOverlay.id}`} id={topOverlay.id} onBack={back} />
        ) : (
          <AlbumPage key={`l${topOverlay.id}`} id={topOverlay.id} onBack={back} />
        ))}

      <PreviewPlayer />
      <TabBar tab={tab} setTab={setTab} pending={pendingCount} />
    </AppContext.Provider>
  );
}

function TabBar({ tab, setTab, pending }) {
  const item = (id, label, Icon, badge) => (
    <button
      onClick={() => setTab(id)}
      className={`relative flex flex-col items-center justify-center gap-0.5 ${
        tab === id ? 'text-white' : 'text-gray-500'
      }`}
    >
      <Icon className="h-6 w-6" />
      <span className="text-[11px]">{label}</span>
      {badge > 0 && (
        <span className="absolute right-6 top-1 min-w-[18px] rounded-full bg-accent px-1 text-center text-[10px] font-bold leading-[18px] text-white">
          {badge}
        </span>
      )}
    </button>
  );
  return (
    <nav className="fixed bottom-0 left-1/2 z-30 grid h-16 w-full max-w-app -translate-x-1/2 grid-cols-2 border-t border-white/5 bg-surface">
      {item('search', 'Search', SearchIcon, 0)}
      {item('queue', 'Queue', DownloadIcon, pending)}
    </nav>
  );
}

function Login({ onSuccess }) {
  const [val, setVal] = useState('');
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const key = val.trim();
    if (!key) return;
    setBusy(true);
    setErr(false);
    const ok = await validateKey(key);
    setBusy(false);
    if (ok) onSuccess(key);
    else setErr(true);
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-app flex-col items-center justify-center bg-bg px-8">
      <div className="mb-8 flex h-20 w-20 items-center justify-center rounded-2xl bg-accent">
        <svg viewBox="0 0 24 24" className="h-10 w-10 text-white" fill="currentColor">
          <path d="M12 3v10.55A4 4 0 1014 17V7h4V3h-6z" />
        </svg>
      </div>
      <h1 className="mb-1 text-xl font-bold">Music Gateway</h1>
      <p className="mb-6 text-sm text-gray-500">Enter your API key to continue</p>
      <form onSubmit={submit} className="w-full">
        <input
          type="password"
          value={val}
          onChange={(e) => {
            setVal(e.target.value);
            setErr(false);
          }}
          placeholder="API key"
          autoFocus
          className="w-full rounded-xl bg-card px-4 py-3 text-center outline-none focus:ring-2 focus:ring-accent-start"
        />
        {err && <p className="mt-2 text-center text-sm text-red-400">Invalid key</p>}
        <button
          type="submit"
          disabled={busy || !val.trim()}
          className="mt-4 w-full rounded-xl bg-accent py-3 font-semibold text-white disabled:opacity-50"
        >
          {busy ? 'Checking…' : 'Submit'}
        </button>
      </form>
    </div>
  );
}
