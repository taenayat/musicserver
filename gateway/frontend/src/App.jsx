import { useCallback, useEffect, useState } from 'react';
import { AppContext } from './context';
import { AuthProvider, useAuth } from './context/AuthContext';
import { PlayerProvider, usePlayer } from './context/PlayerContext';
import { api, getToken } from './api';

import SearchPage from './pages/SearchPage';
import QueuePage from './pages/QueuePage';
import RadioPage from './pages/RadioPage';
import SettingsPage from './pages/SettingsPage';
import AdminPage from './pages/AdminPage';
import ArtistPage from './pages/ArtistPage';
import AlbumPage from './pages/AlbumPage';
import LoginPage from './pages/LoginPage';
import FirstRunPage from './pages/FirstRunPage';
import PreviewPlayer from './components/PreviewPlayer';
import StatusBar from './components/StatusBar';
import ToastStack from './components/Toast';
import LyricsOverlay from './components/LyricsOverlay';
import {
  SearchIcon,
  DownloadIcon,
  RadioIcon,
  SettingsIcon,
  AdminIcon,
} from './components/Icons';

export default function App() {
  return (
    <AuthProvider>
      <PlayerProvider>
        <Root />
      </PlayerProvider>
    </AuthProvider>
  );
}

function Root() {
  const { loading, health, user } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg text-muted">Loading…</div>
    );
  }
  if (health?.first_run && !getToken()) return <FirstRunPage />;
  if (!user) return <LoginPage />;
  return <Shell />;
}

function Shell() {
  const { health, isAdmin } = useAuth();
  const playerCtx = usePlayer();

  const [tab, setTab] = useState('search');
  const [overlays, setOverlays] = useState([]); // stack of { type, id }
  const [lyricsTrack, setLyricsTrack] = useState(null);
  const [toasts, setToasts] = useState([]);

  // ── toasts ──────────────────────────────────────────────────────────────
  const toast = useCallback((msg, kind = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  const dismissToast = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  // ── download queue ────────────────────────────────────────────────────────
  const [queueItems, setQueueItems] = useState([]);
  const [queuedKeys, setQueuedKeys] = useState(() => new Set());

  const refreshQueue = useCallback(async () => {
    if (!getToken()) return;
    try {
      const { items } = await api.queue(100);
      setQueueItems(items);
    } catch {
      /* transient */
    }
  }, []);

  useEffect(() => {
    refreshQueue();
  }, [refreshQueue]);

  const hasActive = queueItems.some((i) => i.status === 'pending' || i.status === 'downloading');
  useEffect(() => {
    if (tab !== 'queue' && !hasActive) return undefined;
    const id = setInterval(refreshQueue, 3000);
    return () => clearInterval(id);
  }, [tab, hasActive, refreshQueue]);

  const keyFor = (item) =>
    item.source === 'youtube'
      ? `youtube:${item.yt_id}`
      : `${item.type}:${item.deezer_id}`;

  const download = useCallback(
    async (item) => {
      setQueuedKeys((prev) => new Set(prev).add(keyFor(item)));
      try {
        const res = await api.download(item);
        if (res?.status === 'already_in_library') {
          const fmt = (res.format || '').toUpperCase();
          toast(`Already in library${res.bitrate_kbps ? ` (${res.bitrate_kbps} kbps ${fmt})` : ''}`, 'info');
        } else {
          toast('Added to download queue', 'success');
        }
        await refreshQueue();
      } catch (ex) {
        toast(ex.message || 'Download failed', 'error');
      }
    },
    [refreshQueue, toast],
  );

  const deleteItem = useCallback(async (id) => {
    try {
      await api.deleteQueueItem(id);
      setQueueItems((prev) => prev.filter((i) => i.id !== id));
    } catch {
      /* e.g. 409 while downloading */
    }
  }, []);

  const clearHistory = useCallback(async () => {
    try {
      await api.clearQueue();
      await refreshQueue();
    } catch (ex) {
      toast(ex.message || 'Could not clear history', 'error');
    }
  }, [refreshQueue, toast]);

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

  // ── navigation ──────────────────────────────────────────────────────────
  const openArtist = useCallback((id) => setOverlays((s) => [...s, { type: 'artist', id }]), []);
  const openAlbum = useCallback((id) => setOverlays((s) => [...s, { type: 'album', id }]), []);
  const back = useCallback(() => setOverlays((s) => s.slice(0, -1)), []);
  const openLyrics = useCallback((track) => setLyricsTrack(track), []);

  const ctx = {
    ...playerCtx,
    download,
    isQueued,
    openArtist,
    openAlbum,
    openLyrics,
    toast,
  };

  const topOverlay = overlays[overlays.length - 1];
  const pendingCount = queueItems.filter(
    (i) => i.status === 'pending' || i.status === 'downloading',
  ).length;
  const radioEnabled = health?.radio_enabled;

  return (
    <AppContext.Provider value={ctx}>
      <div className="mx-auto min-h-screen max-w-app bg-bg">
        {!isAdmin && <StatusBar />}
        <main className="pb-40">
          {tab === 'search' && <SearchPage />}
          {tab === 'radio' && radioEnabled && <RadioPage />}
          {tab === 'queue' && (
            <QueuePage items={queueItems} onDelete={deleteItem} onClear={clearHistory} />
          )}
          {tab === 'settings' && <SettingsPage />}
          {tab === 'admin' && isAdmin && <AdminPage />}
        </main>
      </div>

      {topOverlay &&
        (topOverlay.type === 'artist' ? (
          <ArtistPage key={`a${topOverlay.id}`} id={topOverlay.id} onBack={back} />
        ) : (
          <AlbumPage key={`l${topOverlay.id}`} id={topOverlay.id} onBack={back} />
        ))}

      {lyricsTrack && (
        <LyricsOverlay track={lyricsTrack} onClose={() => setLyricsTrack(null)} />
      )}

      <PreviewPlayer />
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
      <TabBar
        tab={tab}
        setTab={setTab}
        pending={pendingCount}
        radioEnabled={radioEnabled}
        isAdmin={isAdmin}
      />
    </AppContext.Provider>
  );
}

function TabBar({ tab, setTab, pending, radioEnabled, isAdmin }) {
  const items = [
    ['search', 'Search', SearchIcon, 0],
    radioEnabled ? ['radio', 'Radio', RadioIcon, 0] : null,
    ['queue', 'Queue', DownloadIcon, pending],
    ['settings', 'Settings', SettingsIcon, 0],
    isAdmin ? ['admin', 'Admin', AdminIcon, 0] : null,
  ].filter(Boolean);

  return (
    <nav
      className="fixed bottom-0 left-1/2 z-30 flex h-14 w-full max-w-app -translate-x-1/2 border-t border-border bg-surface"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {items.map(([id, label, Icon, badge]) => (
        <button
          key={id}
          onClick={() => setTab(id)}
          className={`relative flex flex-1 flex-col items-center justify-center gap-0.5 ${
            tab === id ? 'text-white' : 'text-gray-500'
          }`}
        >
          <Icon className="h-5 w-5" />
          <span className="text-[10px]">{label}</span>
          {badge > 0 && (
            <span className="absolute right-1/4 top-1 min-w-[16px] rounded-full bg-accent px-1 text-center text-[9px] font-bold leading-4 text-white">
              {badge}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}
