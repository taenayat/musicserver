import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import { useAuth } from '../context/AuthContext';
import Cover from '../components/Cover';
import SearchBar from '../components/SearchBar';
import { WandIcon, HeartIcon, CloseIcon, CheckIcon, SpinnerIcon } from '../components/Icons';

const DOT = {
  pending: 'bg-gray-600',
  downloading: 'bg-accent-start animate-pulse',
  ready: 'bg-success',
  liked: 'bg-accent-end',
  deleted: 'bg-error',
};

function timeRemaining(expires) {
  if (!expires) return '';
  const ms = new Date(expires).getTime() - Date.now();
  if (ms <= 0) return 'expiring';
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return h > 0 ? `${h}h ${m}m left` : `${m}m left`;
}

function SessionCard({ session, onLike, onDismiss }) {
  const [open, setOpen] = useState(false);
  const tracks = session.tracks || [];
  return (
    <div className="rounded-xl bg-card p-3">
      <div className="flex items-center gap-3">
        <Cover url={session.seed_cover_url} size="sm" className="h-12 w-12" rounded="rounded-md" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">Radio: {session.seed_title}</div>
          <div className="text-xs text-muted">{timeRemaining(session.expires_at)}</div>
        </div>
        <button
          onClick={() => {
            if (confirm(`Delete all ${session.track_count} non-liked tracks?`)) onDismiss(session.id);
          }}
          className="rounded-lg border border-error/40 px-3 py-1.5 text-xs font-medium text-error active:bg-error/10"
        >
          Dismiss
        </button>
      </div>

      <div className="mt-3 text-xs text-muted">
        {session.tracks_ready}/{session.track_count} tracks ready
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {tracks.map((t) => (
          <span key={t.id} className={`h-2.5 w-2.5 rounded-full ${DOT[t.status] || 'bg-gray-600'}`} />
        ))}
      </div>

      <button onClick={() => setOpen((o) => !o)} className="mt-3 text-xs text-accent-start">
        {open ? 'Hide tracks' : 'Show tracks'}
      </button>

      {open && (
        <ul className="mt-2 divide-y divide-border">
          {tracks.map((t) => (
            <li key={t.id} className="flex items-center gap-2 py-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[t.status] || 'bg-gray-600'}`} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm">{t.title}</div>
                <div className="truncate text-xs text-muted">{t.artist}</div>
              </div>
              {t.status === 'ready' && (
                <button
                  onClick={() => onLike(session.id, t.deezer_track_id)}
                  className="flex items-center gap-1 rounded-md bg-surface px-2 py-1 text-xs text-accent-end active:opacity-70"
                >
                  <HeartIcon className="h-4 w-4" /> Like
                </button>
              )}
              {t.status === 'liked' && (
                <span className="flex items-center gap-1 text-xs text-accent-end">
                  <CheckIcon className="h-4 w-4" /> In Library
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-[11px] text-gray-600">
        Listen in Symfonium — open the “{session.navidrome_playlist_name}” playlist.
      </p>
    </div>
  );
}

function SeedModal({ trackCount, onClose, onStart }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [seed, setSeed] = useState(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      return undefined;
    }
    const t = setTimeout(() => {
      api.search(q, 10).then(setResults).catch(() => setResults(null));
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  const pick = (type, item) =>
    setSeed({
      seed_type: type,
      seed_deezer_id: item.id,
      seed_title: item.title || item.name,
      seed_cover_url: item.cover_url,
    });

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div
        className="flex max-h-[85vh] w-full animate-slide-up flex-col rounded-t-2xl bg-surface"
        onClick={(e) => e.stopPropagation()}
      >
        {!seed ? (
          <>
            {/* Pinned header — stays put while results scroll below, like the Search tab. */}
            <div className="shrink-0 p-4 pb-2">
              <h2 className="mb-3 text-base font-bold">Start Radio — pick a seed</h2>
              <SearchBar value={query} onChange={setQuery} onSubmit={setQuery} />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
              {results && (
                <div className="space-y-4">
                  {['artists', 'albums', 'tracks'].map((kind) =>
                    results[kind]?.length ? (
                      <div key={kind}>
                        <h3 className="mb-1 text-xs uppercase tracking-wide text-muted">{kind}</h3>
                        {results[kind].slice(0, 5).map((it) => (
                          <button
                            key={it.id}
                            onClick={() => pick(kind.slice(0, -1), it)}
                            className="flex w-full items-center gap-3 py-2 text-left active:opacity-70"
                          >
                            <Cover
                              url={it.cover_url}
                              size="sm"
                              className="h-10 w-10"
                              rounded={kind === 'artists' ? 'rounded-full' : 'rounded-md'}
                            />
                            <span className="truncate text-sm">{it.title || it.name}</span>
                          </button>
                        ))}
                      </div>
                    ) : null,
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="p-4 text-center">
            <h2 className="mb-2 text-base font-bold">Start radio?</h2>
            <p className="mb-4 text-sm text-muted">
              Start radio with {trackCount} tracks from “{seed.seed_title}”? Files will be
              downloaded now.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setSeed(null)}
                className="flex-1 rounded-lg border border-border py-2.5 text-sm"
              >
                Cancel
              </button>
              <button
                onClick={() => onStart(seed)}
                className="flex-1 rounded-lg bg-accent py-2.5 text-sm font-semibold text-white"
              >
                Start Radio
              </button>
            </div>
          </div>
        )}
        <button onClick={onClose} className="absolute right-4 top-4 text-muted" aria-label="Close">
          <CloseIcon />
        </button>
      </div>
    </div>
  );
}

export default function RadioPage() {
  const { health } = useAuth();
  const { toast } = useApp();
  const [sessions, setSessions] = useState([]);
  const [modal, setModal] = useState(false);
  const [starting, setStarting] = useState(false);
  const trackCount = health?.radio_track_count || 20;

  const refresh = useCallback(() => {
    api
      .radioList()
      .then((d) => setSessions(d.sessions || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  const start = async (seed) => {
    setStarting(true);
    try {
      await api.radioStart(seed);
      toast('Radio started — downloading tracks', 'success');
      setModal(false);
      refresh();
    } catch (ex) {
      toast(ex.message || 'Could not start radio', 'error');
    } finally {
      setStarting(false);
    }
  };

  const like = async (sid, tid) => {
    try {
      await api.radioLike(sid, tid);
      toast('Saved to library', 'success');
      refresh();
    } catch (ex) {
      toast(ex.message || 'Like failed', 'error');
    }
  };

  const dismiss = async (sid) => {
    try {
      await api.radioDismiss(sid);
      toast('Radio dismissed', 'info');
      setTimeout(refresh, 1000);
    } catch (ex) {
      toast(ex.message || 'Dismiss failed', 'error');
    }
  };

  return (
    <div className="px-3 pt-4">
      <h1 className="mb-3 text-lg font-bold">Radio</h1>
      <button
        onClick={() => setModal(true)}
        disabled={starting}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-3 font-semibold text-white disabled:opacity-50"
      >
        {starting ? <SpinnerIcon /> : <WandIcon />} Start Radio
      </button>

      <div className="mt-4 space-y-3 pb-4">
        {sessions.length === 0 ? (
          <p className="mt-16 text-center text-muted">No active radio sessions.</p>
        ) : (
          sessions.map((s) => (
            <SessionCard key={s.id} session={s} onLike={like} onDismiss={dismiss} />
          ))
        )}
      </div>

      {modal && <SeedModal trackCount={trackCount} onClose={() => setModal(false)} onStart={start} />}
    </div>
  );
}
