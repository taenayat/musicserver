import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import { useAuth } from '../context/AuthContext';
import { timeAgo } from '../util';
import { SpinnerIcon, TrashIcon, CloudIcon } from '../components/Icons';
import Cover from '../components/Cover';

function Card({ title, action, children }) {
  return (
    <div className="rounded-xl bg-card p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex justify-between py-0.5 text-sm">
      <span className="text-muted">{k}</span>
      <span className="font-medium">{v}</span>
    </div>
  );
}

// Tiny inline sparkline from a numeric series.
function Sparkline({ points, accessor }) {
  const vals = points.map(accessor).filter((n) => n != null);
  if (vals.length < 2) return <div className="h-10 text-xs text-gray-600">no data</div>;
  const max = Math.max(...vals, 1);
  const min = Math.min(...vals, 0);
  const range = max - min || 1;
  const w = 120;
  const h = 40;
  const step = w / (vals.length - 1);
  const d = vals
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`)
    .join(' ');
  return (
    <svg width={w} height={h} className="text-accent-start">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function OverviewTab() {
  const { toast } = useApp();
  const [s, setS] = useState(null);
  const [metrics, setMetrics] = useState(null);

  const load = useCallback(() => {
    api.adminStatus().then(setS).catch(() => {});
    api.metrics(24).then(setMetrics).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  if (!s) return <div className="py-12 text-center text-muted">Loading…</div>;
  const pts = metrics?.points || [];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Card title="Gateway">
        <Row k="Version" v={s.gateway.version} />
        <Row k="Uptime" v={`${Math.floor(s.gateway.uptime_seconds / 3600)}h`} />
        <Row k="CPU" v={`${s.gateway.cpu_percent?.toFixed(0)}%`} />
        <Row k="RAM" v={`${s.gateway.ram_mb_used?.toFixed(0)} MB`} />
        <Row k="Errors (1h)" v={s.gateway.log_errors_last_hour} />
        {pts.length > 1 && (
          <div className="mt-2 space-y-2">
            <div>
              <div className="text-[10px] text-muted">CPU</div>
              <Sparkline points={pts} accessor={(p) => p.cpu_percent} />
            </div>
            <div>
              <div className="text-[10px] text-muted">RAM</div>
              <Sparkline points={pts} accessor={(p) => p.ram_mb} />
            </div>
          </div>
        )}
      </Card>

      <Card
        title="Navidrome"
        action={
          <button
            onClick={() =>
              api
                .navScan()
                .then(() => toast('Scan triggered on Navidrome', 'success'))
                .catch((ex) => toast(ex.message || 'Scan could not be triggered', 'error'))
            }
            className="text-xs text-accent-start"
          >
            Trigger Scan
          </button>
        }
      >
        <Row k="Reachable" v={s.navidrome.reachable ? 'Yes' : 'No'} />
        <Row k="Songs" v={s.navidrome.song_count} />
        <Row k="Scanning" v={s.navidrome.scanning ? 'Yes' : 'No'} />
        <Row k="Last scan" v={s.navidrome.last_scan ? timeAgo(s.navidrome.last_scan) : '—'} />
        <p className="mt-2 text-[11px] text-muted">
          This updates Navidrome. Symfonium shows new music on its own sync schedule — enable its
          background library sync to have it appear automatically.
        </p>
      </Card>

      <Card title="Deezer">
        <Row k="ARL valid" v={s.deezer.arl_valid ? 'Yes' : 'No'} />
        <Row k="Cache entries" v={s.deezer.cache_entries} />
      </Card>

      <Card title="Queue">
        <Row k="Pending" v={s.queue.pending} />
        <Row k="Downloading" v={s.queue.downloading} />
        <Row k="Done today" v={s.queue.done_today} />
        <Row k="Errors today" v={s.queue.errors_today} />
        {pts.length > 1 && <Sparkline points={pts} accessor={(p) => p.queue_depth} />}
      </Card>

      <Card title="Telegram">
        <Row k="Connected" v={s.telegram.connected ? 'Yes' : 'No'} />
        <Row k="Backed up" v={s.telegram.backed_up_files} />
        <Row k="Pending uploads" v={s.telegram.pending_uploads} />
        <Row k="Total" v={`${s.telegram.total_backed_gb} GB`} />
      </Card>

      <Card title="Library">
        <Row k="Tracks" v={s.library.total_tracks} />
        <Row k="Last scan" v={s.library.last_scan ? timeAgo(s.library.last_scan) : '—'} />
        <Row k="Scanning" v={s.library.scan_in_progress ? 'Yes' : 'No'} />
      </Card>
    </div>
  );
}

function UsersTab() {
  const { toast } = useApp();
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', role: 'user' });

  const load = useCallback(() => api.adminUsers().then(setUsers).catch(() => {}), []);
  useEffect(() => {
    load();
  }, [load]);

  const create = async () => {
    try {
      await api.createUser(form.username, form.password, form.role);
      toast('User created', 'success');
      setAdding(false);
      setForm({ username: '', password: '', role: 'user' });
      load();
    } catch (ex) {
      toast(ex.message || 'Create failed', 'error');
    }
  };

  const del = async (u) => {
    if (!confirm(`Delete ${u.username}? This also deletes their Navidrome account.`)) return;
    try {
      await api.deleteUser(u.id);
      toast('User deleted', 'success');
      load();
    } catch (ex) {
      toast(ex.message || 'Delete failed', 'error');
    }
  };

  return (
    <div>
      <div className="mb-3 rounded-lg border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
        Manage all accounts here. Do not change passwords directly in Navidrome.
      </div>
      <button
        onClick={() => setAdding((a) => !a)}
        className="mb-3 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white"
      >
        {adding ? 'Cancel' : 'Add User'}
      </button>

      {adding && (
        <div className="mb-4 space-y-2 rounded-xl bg-card p-3">
          <input
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            placeholder="Username"
            className="w-full rounded-lg bg-surface px-3 py-2 outline-none"
          />
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            placeholder="Password"
            className="w-full rounded-lg bg-surface px-3 py-2 outline-none"
          />
          <div className="flex items-center gap-2">
            <label className="text-sm text-muted">Role</label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="rounded-lg bg-surface px-3 py-2 text-sm"
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <button
            onClick={create}
            disabled={!form.username || !form.password}
            className="w-full rounded-lg bg-accent py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Create
          </button>
        </div>
      )}

      <ul className="divide-y divide-border">
        {users.map((u) => (
          <li key={u.id} className="flex items-center gap-3 py-3">
            <span className={`h-2 w-2 rounded-full ${u.active ? 'bg-success' : 'bg-gray-600'}`} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">
                {u.username}{' '}
                <span className="ml-1 text-xs text-muted">({u.role})</span>
              </div>
              <div className="text-xs text-muted">
                {u.last_seen ? `seen ${timeAgo(u.last_seen)}` : 'never seen'}
              </div>
            </div>
            {u.id !== me?.id && (
              <button onClick={() => del(u)} className="p-2 text-error active:opacity-70" aria-label="Delete">
                <TrashIcon />
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LibraryTab() {
  const { toast } = useApp();
  const [stats, setStats] = useState(null);
  const [help, setHelp] = useState(false);

  const load = useCallback(() => api.libraryStats().then(setStats).catch(() => {}), []);
  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);

  const [busy, setBusy] = useState('');

  const sync = async () => {
    await api.syncLibrary();
    toast('Library sync started', 'success');
  };

  const runBackfill = async (kind) => {
    setBusy(kind);
    try {
      if (kind === 'art') {
        const r = await api.artBackfill();
        toast(`Cover art: ${r.updated} of ${r.scanned} updated`, 'success');
      } else {
        const r = await api.lyricsBackfill();
        toast(`Lyrics: ${r.written} sidecars written`, 'success');
      }
    } catch (ex) {
      toast(ex.message || 'Backfill failed', 'error');
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="space-y-4">
      <button
        onClick={sync}
        className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white"
      >
        {stats?.scan_in_progress && <SpinnerIcon className="h-4 w-4" />}
        Sync Library Index
      </button>

      <div className="rounded-xl bg-card p-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
          Maintenance
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => runBackfill('art')}
            disabled={!!busy}
            className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50"
          >
            {busy === 'art' && <SpinnerIcon className="h-4 w-4" />}
            Backfill cover art
          </button>
          <button
            onClick={() => runBackfill('lyrics')}
            disabled={!!busy}
            className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50"
          >
            {busy === 'lyrics' && <SpinnerIcon className="h-4 w-4" />}
            Backfill lyrics (.lrc)
          </button>
        </div>
        <p className="mt-2 text-[11px] text-muted">
          Adds missing embedded art and writes synced .lrc sidecars for existing tracks, then
          triggers a Navidrome scan.
        </p>
      </div>

      {stats && (
        <div className="rounded-xl bg-card p-4">
          <Row k="Total tracks" v={stats.total_tracks} />
          <Row k="Artists" v={stats.total_artists} />
          <Row k="Albums" v={stats.total_albums} />
          {stats.formats &&
            Object.entries(stats.formats).map(([f, c]) => (
              <Row key={f} k={`${f.toUpperCase()} files`} v={c} />
            ))}
        </div>
      )}

      <div className="rounded-xl bg-card p-4">
        <button onClick={() => setHelp((h) => !h)} className="text-sm font-semibold text-accent-start">
          {help ? 'Hide' : 'Show'} manual import instructions
        </button>
        {help && (
          <div className="mt-3 space-y-2 text-xs text-muted">
            <p>Required structure: <code>/music/&lt;Artist&gt;/&lt;Album&gt;/&lt;NN_Title.ext&gt;</code></p>
            <p>Accepted: mp3, flac, aac, m4a, ogg, opus</p>
            <p>Standardize locally with beets or MusicBrainz Picard before uploading:</p>
            <pre className="rounded bg-surface p-2">beet import /your/music</pre>
            <pre className="rounded bg-surface p-2">scp -r "Artist Name/" user@vps:/opt/music/music/</pre>
            <p>After upload: click “Sync Library Index” above.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function TelegramTab() {
  const { toast } = useApp();
  const [s, setS] = useState(null);

  const load = useCallback(() => api.adminStatus().then((d) => setS(d.telegram)).catch(() => {}), []);
  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);

  const backfill = async () => {
    try {
      const r = await api.telegramBackfill();
      toast(`${r.queued} tracks queued for upload`, 'success');
    } catch (ex) {
      toast(ex.message || 'Backfill failed', 'error');
    }
  };

  if (!s) return <div className="py-12 text-center text-muted">Loading…</div>;
  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-card p-4">
        <Row k="Connected" v={s.connected ? 'Yes' : 'No'} />
        <Row k="Backed up" v={s.backed_up_files} />
        <Row k="Pending uploads" v={s.pending_uploads} />
        <Row k="Total" v={`${s.total_backed_gb} GB`} />
      </div>
      <button
        onClick={backfill}
        disabled={!s.connected}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        Upload Existing Library
      </button>
    </div>
  );
}

function CacheTab() {
  const { toast } = useApp();
  const [s, setS] = useState(null);
  const [cold, setCold] = useState([]);

  const load = useCallback(() => api.cacheStatus().then(setS).catch(() => {}), []);
  useEffect(() => {
    load();
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, [load]);

  if (!s) return <div className="py-12 text-center text-muted">Loading…</div>;
  const pct = Math.min(100, (s.local_gb / s.limit_gb) * 100);

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-card p-4">
        <Row k="Local" v={`${s.local_gb} / ${s.limit_gb} GB`} />
        <div className="my-2 h-2 overflow-hidden rounded-full bg-surface">
          <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
        </div>
        <Row k="Policy" v={s.policy} />
        <Row k="Pinned" v={s.pinned_count} />
        <Row k="Evictable" v={s.evictable_count} />
        <Row k="Cold (Telegram only)" v={s.telegram_only_count} />
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => api.cacheEvict().then((r) => toast(`Evicted ${r.evicted} files`, 'success'))}
          className="flex-1 rounded-lg bg-accent py-2 text-sm font-semibold text-white"
        >
          Trigger Eviction
        </button>
        <button
          onClick={() => {
            if (confirm('Recall all cold files from Telegram?'))
              api.cacheRecallAll().then(() => toast('Recall started', 'info'));
          }}
          className="flex-1 rounded-lg border border-border py-2 text-sm font-medium"
        >
          Recall All
        </button>
      </div>
    </div>
  );
}

function LogsTab() {
  const [lines, setLines] = useState([]);
  const [auto, setAuto] = useState(false);

  const load = useCallback(() => api.adminLogs(100).then((d) => setLines(d.lines || [])).catch(() => {}), []);
  useEffect(() => {
    load();
    if (!auto) return undefined;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load, auto]);

  const color = (ln) =>
    ln.includes('ERROR') ? 'text-error' : ln.includes('WARNING') ? 'text-warning' : 'text-gray-300';

  return (
    <div>
      <label className="mb-2 flex items-center gap-2 text-sm text-muted">
        <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
        Auto-refresh (5s)
      </label>
      <div className="h-[60vh] overflow-auto rounded-xl bg-black/50 p-3 font-mono text-[11px] leading-relaxed">
        {lines.map((ln, i) => (
          <div key={i} className={color(ln)}>
            {ln}
          </div>
        ))}
      </div>
    </div>
  );
}

function AlbumArtTab() {
  const { toast } = useApp();
  const [tracks, setTracks] = useState(null);
  const [sel, setSel] = useState(() => new Set());
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const scan = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.artMissing();
      setTracks(d.tracks || []);
      setSel(new Set());
    } catch (ex) {
      toast(ex.message || 'Scan failed', 'error');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    scan();
  }, [scan]);

  const fixable = (tracks || []).filter((t) => t.fixable);
  const toggle = (id) =>
    setSel((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const allSelected = fixable.length > 0 && fixable.every((t) => sel.has(t.track_id));
  const selectAll = () =>
    setSel(allSelected ? new Set() : new Set(fixable.map((t) => t.track_id)));

  const apply = async () => {
    if (sel.size === 0) return;
    setApplying(true);
    try {
      const r = await api.artApply([...sel]);
      toast(`Applied art to ${r.updated} track(s)`, 'success');
      await scan();
    } catch (ex) {
      toast(ex.message || 'Apply failed', 'error');
    } finally {
      setApplying(false);
    }
  };

  if (loading && !tracks) return <div className="py-12 text-center text-muted">Scanning…</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted">
          {tracks ? `${tracks.length} track(s) missing art` : ''}
        </div>
        <div className="flex gap-2">
          <button onClick={scan} disabled={loading} className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-50">
            {loading ? 'Scanning…' : 'Rescan'}
          </button>
          {fixable.length > 0 && (
            <button onClick={selectAll} className="rounded-lg border border-border px-3 py-1.5 text-sm">
              {allSelected ? 'Clear all' : 'Select all'}
            </button>
          )}
          <button
            onClick={apply}
            disabled={applying || sel.size === 0}
            className="flex items-center gap-2 rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {applying && <SpinnerIcon className="h-4 w-4" />}
            Apply ({sel.size})
          </button>
        </div>
      </div>

      {tracks && tracks.length === 0 && (
        <div className="py-12 text-center text-muted">Every track has cover art. 🎉</div>
      )}

      <div className="space-y-1">
        {(tracks || []).map((t) => (
          <label
            key={t.track_id}
            className={`flex items-center gap-3 rounded-lg p-2 ${
              t.fixable ? 'bg-card active:opacity-80' : 'bg-card/50 opacity-60'
            }`}
          >
            <input
              type="checkbox"
              disabled={!t.fixable}
              checked={sel.has(t.track_id)}
              onChange={() => toggle(t.track_id)}
            />
            <Cover url={t.proposed_cover_url} size="sm" className="h-10 w-10" rounded="rounded-md" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{t.title}</div>
              <div className="truncate text-xs text-muted">
                {t.artist}
                {t.album ? ` · ${t.album}` : ''}
              </div>
            </div>
            {!t.fixable && <span className="text-[10px] text-muted">no source</span>}
          </label>
        ))}
      </div>
    </div>
  );
}

const TABS = ['Overview', 'Users', 'Library', 'Album Art', 'Telegram', 'Cache', 'Logs'];

export default function AdminPage() {
  const { health } = useAuth();
  const [tab, setTab] = useState('Overview');
  const tabs = TABS.filter((t) => t !== 'Cache' || health?.cache_enabled);

  return (
    <div className="px-3 pt-4">
      <h1 className="mb-3 text-lg font-bold">Admin</h1>
      <div className="no-scrollbar -mx-3 mb-4 flex gap-2 overflow-x-auto px-3">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm ${
              tab === t ? 'bg-accent text-white' : 'bg-card text-muted'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="pb-6">
        {tab === 'Overview' && <OverviewTab />}
        {tab === 'Users' && <UsersTab />}
        {tab === 'Library' && <LibraryTab />}
        {tab === 'Album Art' && <AlbumArtTab />}
        {tab === 'Telegram' && <TelegramTab />}
        {tab === 'Cache' && <CacheTab />}
        {tab === 'Logs' && <LogsTab />}
      </div>
    </div>
  );
}
