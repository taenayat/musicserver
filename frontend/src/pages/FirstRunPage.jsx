import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function FirstRunPage() {
  const { createAdmin } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!username || !password) return;
    if (password !== confirm) {
      setErr('Passwords do not match');
      return;
    }
    setBusy(true);
    setErr('');
    try {
      await createAdmin(username, password);
    } catch (ex) {
      setErr(ex.message || 'Could not create admin');
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-app flex-col items-center justify-center bg-bg px-8">
      <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-accent">
        <svg viewBox="0 0 24 24" className="h-10 w-10 text-white" fill="currentColor">
          <path d="M12 3v10.55A4 4 0 1014 17V7h4V3h-6z" />
        </svg>
      </div>
      <h1 className="mb-1 text-xl font-bold">Welcome to Music Gateway</h1>
      <p className="mb-6 text-center text-sm text-muted">
        Create the first administrator account to get started.
      </p>
      <form onSubmit={submit} className="w-full space-y-3">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Username"
          autoCapitalize="none"
          autoFocus
          className="w-full rounded-xl bg-card px-4 py-3 outline-none focus:ring-2 focus:ring-accent-start"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full rounded-xl bg-card px-4 py-3 outline-none focus:ring-2 focus:ring-accent-start"
        />
        <input
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Confirm password"
          className="w-full rounded-xl bg-card px-4 py-3 outline-none focus:ring-2 focus:ring-accent-start"
        />
        {err && <p className="text-center text-sm text-error">{err}</p>}
        <button
          type="submit"
          disabled={busy || !username || !password || !confirm}
          className="w-full rounded-xl bg-accent py-3 font-semibold text-white disabled:opacity-50"
        >
          {busy ? 'Creating…' : 'Create Admin Account'}
        </button>
      </form>
    </div>
  );
}
