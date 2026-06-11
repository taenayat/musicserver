import Cover from './Cover';
import { CloseIcon, CloudIcon, CheckIcon } from './Icons';
import { timeAgo } from '../util';

// The scrollable list of download items. Used by QueuePage.
const STATUS = {
  pending:        { label: 'Waiting',     cls: 'bg-gray-600 text-gray-100' },
  downloading:    { label: 'Downloading', cls: 'bg-accent-start text-white animate-pulse' },
  done:           { label: 'Done',        cls: 'bg-success text-white' },
  error:          { label: 'Error',       cls: 'bg-error text-white' },
  skipped_exists: { label: 'In Library',  cls: 'bg-accent-end text-white' },
};

function CloudState({ item }) {
  if (item.source === 'youtube' || item.status !== 'done') {
    if (item.status !== 'done') return null;
  }
  const t = item.telegram_status;
  if (t === 'uploaded') return <CloudIcon className="h-4 w-4 text-success" />;
  if (t === 'uploading') return <CloudIcon className="h-4 w-4 animate-pulse text-accent-start" />;
  if (t === 'not_applicable') return null;
  return <CloudIcon className="h-4 w-4 text-muted" />;
}

export default function QueueDrawer({ items, onDelete }) {
  if (!items || items.length === 0) {
    return <div className="py-24 text-center text-muted">Queue is empty</div>;
  }

  return (
    <ul className="divide-y divide-border">
      {items.map((it) => {
        const s = STATUS[it.status] || STATUS.pending;
        const canDelete = ['done', 'error', 'skipped_exists'].includes(it.status);
        return (
          <li key={it.id} className="flex items-start gap-3 py-3">
            <Cover url={it.cover_url} size="sm" className="mt-0.5 h-12 w-12" rounded="rounded-md" alt="" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">
                {it.title || `${it.type || it.source} ${it.deezer_id || ''}`}
              </div>
              {it.artist ? <div className="truncate text-xs text-muted">{it.artist}</div> : null}
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-border px-1.5 py-0.5 text-[9px] font-bold uppercase text-gray-300">
                  {it.source === 'youtube' ? 'YT' : 'Deezer'}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${s.cls}`}>
                  {s.label}
                  {it.status === 'done' && it.bitrate_actual ? ` · ${it.bitrate_actual} kbps` : ''}
                </span>
                <CloudState item={it} />
                <span className="text-[10px] text-gray-600">{timeAgo(it.queued_at)}</span>
              </div>
              {it.status === 'error' && it.error_msg ? (
                <details className="mt-1">
                  <summary className="cursor-pointer text-[11px] text-error">Show error</summary>
                  <div className="mt-1 break-words text-[11px] text-error/80">{it.error_msg}</div>
                </details>
              ) : null}
            </div>
            {canDelete && (
              <button
                onClick={() => onDelete(it.id)}
                className="-mr-1 p-2 text-muted active:text-white"
                aria-label="Remove from queue"
              >
                <CloseIcon />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
