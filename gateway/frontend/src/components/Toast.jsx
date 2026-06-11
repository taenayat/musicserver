// A stack of transient toasts rendered above the player bar. State lives in
// App.jsx; this is the presentational layer. `kind` ∈ info|success|error.

const KIND = {
  info: 'bg-card text-white border-border',
  success: 'bg-success/15 text-success border-success/30',
  error: 'bg-error/15 text-error border-error/30',
};

export default function ToastStack({ toasts, onDismiss }) {
  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-32 left-1/2 z-50 w-full max-w-app -translate-x-1/2 space-y-2 px-3">
      {toasts.map((t) => (
        <button
          key={t.id}
          onClick={() => onDismiss(t.id)}
          className={`block w-full animate-fade-in rounded-lg border px-4 py-3 text-left text-sm shadow-lg shadow-black/40 ${
            KIND[t.kind] || KIND.info
          }`}
        >
          {t.msg}
        </button>
      ))}
    </div>
  );
}
