import Cover from './Cover';
import { CloseIcon } from './Icons';
import { timeAgo } from '../util';

// The scrollable list of download items. Used by QueuePage. (Named "drawer"
// because it's the slide-in queue panel content.)
const STATUS = {
  pending:     { label: 'Pending',     cls: 'bg-gray-600 text-gray-100' },
  downloading: { label: 'Downloading', cls: 'bg-accent-start text-white animate-pulse' },
  done:        { label: 'Done',        cls: 'bg-green-600 text-white' },
  error:       { label: 'Error',       cls: 'bg-red-600 text-white' },
};

export default function QueueDrawer({ items, onDelete }) {
  if (!items || items.length === 0) {
    return <div className="text-center text-gray-500 py-24">Queue is empty</div>;
  }

  return (
    <ul className="divide-y divide-white/5">
      {items.map((it) => {
        const s = STATUS[it.status] || STATUS.pending;
        const canDelete = it.status !== 'downloading';
        return (
          <li key={it.id} className="flex items-start gap-3 py-3">
            <Cover url={it.cover_url} size="sm" className="w-12 h-12 mt-0.5" rounded="rounded-md" alt="" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">
                {it.title || `${it.type} ${it.deezer_id}`}
              </div>
              {it.artist ? <div className="text-xs text-gray-500 truncate">{it.artist}</div> : null}
              <div className="mt-1 flex items-center gap-2">
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${s.cls}`}>
                  {s.label}
                </span>
                <span className="text-[10px] text-gray-600">{timeAgo(it.queued_at)}</span>
              </div>
              {it.status === 'error' && it.error_msg ? (
                <div className="mt-1 text-[11px] text-red-400 line-clamp-2 break-words">
                  {it.error_msg}
                </div>
              ) : null}
            </div>
            {canDelete && (
              <button
                onClick={() => onDelete(it.id)}
                className="p-2 -mr-1 text-gray-500 active:text-white"
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
