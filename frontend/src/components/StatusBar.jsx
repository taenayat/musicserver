import { useEffect, useState } from 'react';
import { api } from '../api';

// Thin status strip at the top of the screen for regular (non-admin) users.
// Polls GET /api/status every 10s: server health, queue activity, storage.
export default function StatusBar() {
  const [s, setS] = useState(null);

  useEffect(() => {
    let active = true;
    const poll = () =>
      api
        .status()
        .then((d) => active && setS(d))
        .catch(() => active && setS(null));
    poll();
    const id = setInterval(poll, 10000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const ok = s?.server_ok;
  const pending = s?.queue_pending || 0;
  const downloading = s?.queue_downloading || 0;
  const center =
    pending || downloading
      ? `${downloading} downloading · ${pending} pending`
      : 'Queue empty';
  const storage =
    s != null ? `${(s.storage_gb_used ?? 0).toFixed(1)} / ${s.storage_gb_limit} GB` : '—';

  return (
    <div className="flex h-10 items-center justify-between border-b border-border bg-surface px-3 text-xs text-muted">
      <div className="flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${ok ? 'bg-success' : 'bg-error'}`} />
        <span>{ok ? 'OK' : 'Server issue'}</span>
      </div>
      <div className="truncate">{center}</div>
      <div className="tabular-nums">{storage}</div>
    </div>
  );
}
