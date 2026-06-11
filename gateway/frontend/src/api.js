// api.js — single source of every network call.
//
// The session token lives in localStorage and is attached as
// `Authorization: Bearer` to every request. A global 401 handler lets the auth
// layer bounce the user back to the login screen if the session is rejected.

const TOKEN_STORAGE = 'gateway_token';

export function getToken() {
  return localStorage.getItem(TOKEN_STORAGE) || '';
}
export function setToken(t) {
  localStorage.setItem(TOKEN_STORAGE, t);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_STORAGE);
}

let unauthorizedHandler = () => {};
export function onUnauthorized(fn) {
  unauthorizedHandler = fn;
}

function authHeaders(extra = {}) {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}`, ...extra } : { ...extra };
}

async function request(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: authHeaders(opts.headers) });
  if (res.status === 401) {
    unauthorizedHandler();
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res;
}

function jget(path) {
  return request(path).then((r) => r.json());
}
function jpost(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then((r) => (r.status === 204 ? null : r.json()));
}
function jpatch(path, body) {
  return request(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json());
}
function jdelete(path) {
  return request(path, { method: 'DELETE' });
}

export async function getHealth() {
  const res = await fetch('/health');
  return res.json();
}

export const api = {
  // auth
  login: (username, password) =>
    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => jpost('/api/auth/logout'),
  me: () => jget('/api/auth/me'),
  changeMyPassword: (current_password, new_password) =>
    jpatch('/api/auth/me/password', { current_password, new_password }),
  createFirstAdmin: (username, password) =>
    fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, role: 'admin' }),
    }),

  // status
  status: () => jget('/api/status'),

  // search + browse
  search: (q, limit = 20) =>
    jget(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  searchYoutube: (q, limit = 10) =>
    jget(`/api/search/youtube?q=${encodeURIComponent(q)}&limit=${limit}`),
  artist: (id) => jget(`/api/artist/${id}`),
  album: (id) => jget(`/api/album/${id}`),

  // downloads
  download: (item) => jpost('/api/download', item),
  queue: (limit = 50, offset = 0) => jget(`/api/queue?limit=${limit}&offset=${offset}`),
  deleteQueueItem: (id) => jdelete(`/api/queue/${id}`),

  // library
  libraryStats: () => jget('/api/library/stats'),
  syncLibrary: () => jpost('/api/admin/library/scan'),
  deleteTrack: (id) => jdelete(`/api/library/tracks/${id}`),
  deleteAlbum: (id) => jdelete(`/api/library/albums/${id}`),

  // radio
  radioList: () => jget('/api/radio'),
  radioStart: (seed) => jpost('/api/radio', seed),
  radioLike: (sessionId, deezer_track_id) =>
    jpost(`/api/radio/${sessionId}/like`, { deezer_track_id }),
  radioDismiss: (sessionId) => jpost(`/api/radio/${sessionId}/dismiss`),

  // lyrics
  lyrics: ({ track_id, title, artist, album, duration }) =>
    jget(
      `/api/lyrics?track_id=${track_id || 0}&title=${encodeURIComponent(title || '')}` +
        `&artist=${encodeURIComponent(artist || '')}&album=${encodeURIComponent(album || '')}` +
        `&duration=${duration || 0}`,
    ),

  // cache
  cacheStatus: () => jget('/api/cache/status'),
  cacheRecall: (file_path) => jpost('/api/cache/recall', { file_path }),
  cacheEvict: () => jpost('/api/admin/cache/evict'),
  cacheRecallAll: () => jpost('/api/admin/cache/recall-all'),

  // admin
  adminStatus: () => jget('/api/admin/status'),
  adminLogs: (lines = 100) => jget(`/api/admin/logs?lines=${lines}`),
  adminUsers: () => jget('/api/admin/users'),
  createUser: (username, password, role) =>
    jpost('/api/admin/users', { username, password, role }),
  patchUser: (id, patch) => jpatch(`/api/admin/users/${id}`, patch),
  deleteUser: (id) => jdelete(`/api/admin/users/${id}`),
  navScan: () => jpost('/api/admin/scan'),
  clearQueue: () => jpost('/api/admin/clear-queue'),
  telegramBackfill: () => jpost('/api/admin/telegram/backfill'),
  artBackfill: () => jpost('/api/admin/art/backfill'),
  lyricsBackfill: () => jpost('/api/admin/lyrics/backfill'),
  artMissing: () => jget('/api/admin/art/missing'),
  artApply: (track_ids) => jpost('/api/admin/art/apply', { track_ids }),
  metrics: (hours = 24) => jget(`/api/admin/metrics?hours=${hours}`),

  // binary helpers — fetched with auth, returned as object URLs.
  coverBlob: (url, size = 'md') =>
    request(`/api/cover?url=${encodeURIComponent(url)}&size=${size}`).then((r) => r.blob()),
  previewBlob: (id) => request(`/api/preview/${id}`).then((r) => r.blob()),
};
