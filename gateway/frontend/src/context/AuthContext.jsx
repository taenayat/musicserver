import { createContext, useContext, useCallback, useEffect, useState } from 'react';
import {
  api,
  getToken,
  setToken as persistToken,
  clearToken,
  onUnauthorized,
  getHealth,
} from '../api';

const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function AuthProvider({ children }) {
  const [token, setTok] = useState(getToken());
  const [user, setUser] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
    } catch {
      setHealth(null);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      if (getToken()) await api.logout();
    } catch {
      /* ignore */
    }
    clearToken();
    setTok('');
    setUser(null);
  }, []);

  useEffect(() => {
    onUnauthorized(() => {
      clearToken();
      setTok('');
      setUser(null);
    });
  }, []);

  useEffect(() => {
    (async () => {
      await refreshHealth();
      if (getToken()) {
        try {
          setUser(await api.me());
        } catch {
          clearToken();
          setTok('');
        }
      }
      setLoading(false);
    })();
  }, [refreshHealth]);

  const login = useCallback(async (username, password) => {
    const res = await api.login(username, password);
    if (!res.ok) {
      const e = new Error(res.status === 401 ? 'Invalid credentials' : 'Login failed');
      throw e;
    }
    const data = await res.json();
    persistToken(data.token);
    setTok(data.token);
    setUser(await api.me());
    await refreshHealth();
  }, [refreshHealth]);

  const createAdmin = useCallback(async (username, password) => {
    const res = await api.createFirstAdmin(username, password);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || 'Could not create admin');
    }
    // Auto-login after creating the admin.
    await login(username, password);
  }, [login]);

  const value = {
    token,
    user,
    health,
    loading,
    isAdmin: user?.role === 'admin',
    login,
    logout,
    createAdmin,
    refreshHealth,
    setUser,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
