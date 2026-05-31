import QueueDrawer from '../components/QueueDrawer';

// The Queue tab. Items + polling live in App (so the tab badge and this list
// share one source of truth); this page just renders them.
export default function QueuePage({ items, onDelete }) {
  return (
    <div className="px-3 pt-4">
      <h1 className="mb-3 text-lg font-bold">Downloads</h1>
      <QueueDrawer items={items} onDelete={onDelete} />
    </div>
  );
}
