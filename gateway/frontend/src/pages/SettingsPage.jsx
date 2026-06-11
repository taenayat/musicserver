import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useApp } from '../context';
import { api } from '../api';

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const { toast } = useApp();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);

  const changePw = async (e) => {
    e.preventDefault();
    if (next !== confirm) {
      toast('New passwords do not match', 'error');
      return;
    }
    setBusy(true);
    try {
      await api.changeMyPassword(current, next);
      toast('Password changed', 'success');
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (ex) {
      toast(ex.message || 'Could not change password', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-3 pt-4">
      <h1 className="mb-4 text-lg font-bold">Settings</h1>

      <div className="mb-5 rounded-xl bg-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-muted">Signed in as</div>
            <div className="text-base font-semibold">{user?.username}</div>
          </div>
          <span className="rounded-md bg-accent px-2 py-1 text-xs font-medium text-white">
            {user?.role}
          </span>
        </div>
      </div>

      <form onSubmit={changePw} className="space-y-3 rounded-xl bg-card p-4">
        <h2 className="text-sm font-semibold">Change password</h2>
        <input
          type="password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          placeholder="Current password"
          className="w-full rounded-lg bg-surface px-4 py-2.5 outline-none focus:ring-2 focus:ring-accent-start"
        />
        <input
          type="password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          placeholder="New password"
          className="w-full rounded-lg bg-surface px-4 py-2.5 outline-none focus:ring-2 focus:ring-accent-start"
        />
        <input
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Confirm new password"
          className="w-full rounded-lg bg-surface px-4 py-2.5 outline-none focus:ring-2 focus:ring-accent-start"
        />
        <button
          type="submit"
          disabled={busy || !current || !next}
          className="w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Update password'}
        </button>
      </form>

      <button
        onClick={logout}
        className="mt-5 w-full rounded-xl border border-border py-3 text-sm font-medium text-error active:bg-card"
      >
        Sign out
      </button>
    </div>
  );
}
