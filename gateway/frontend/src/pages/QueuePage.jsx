import QueueDrawer from '../components/QueueDrawer';

// The Queue tab. Items + polling live in App (so the tab badge and this list
// share one source of truth); this page just renders them.
export default function QueuePage({ items, onDelete, onClear }) {
  const hasFinished = items.some((i) =>
    ['done', 'error', 'skipped_exists'].includes(i.status),
  );
  return (
    <div className="px-3 pt-4">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-lg font-bold">Downloads</h1>
        {hasFinished && (
          <button onClick={onClear} className="text-xs text-accent-start active:opacity-70">
            Clear history
          </button>
        )}
      </div>
      <QueueDrawer items={items} onDelete={onDelete} />
    </div>
  );
}
