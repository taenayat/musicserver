// api.js — the single source of every network call.
//
// The API key lives in localStorage and is attached as `Authorization: Bearer`
// to every request. A global 401 handler lets App.jsx bounce the user back to
// the login screen if the key is ever rejected.

const KEY_STORAGE = 'gateway_api_key';

export function getKey() {
  return localStorage.getItem(KEY_STORAGE) || '';
}
export function setKey(key) {
  localStorage.setItem(KEY_STORAGE, key);
}
export function clearKey() {
  localStorage.removeItem(KEY_STORAGE);
}

let unauthorizedHandler = () => {};
export function onUnauthorized(fn) {
  unauthorizedHandler = fn;
}

function authHeaders(extra = {}) {
  return { Authorization: `Bearer ${getKey()}`, ...extra };
}

async function request(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: authHeaders(opts.headers) });
  if (res.status === 401) {
    unauthorizedHandler();
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res;
}

// Validate a key against /health (used only by the login screen). Returns true
// if the key is accepted. Does not persist anything.
export async function validateKey(key) {
  const res = await fetch('/health', { headers: { Authorization: `Bearer ${key}` } });
  return res.ok;
}

export const api = {
  search: (q, limit = 20) =>
    request(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`).then((r) => r.json()),

  artist: (id) => request(`/api/artist/${id}`).then((r) => r.json()),

  album: (id) => request(`/api/album/${id}`).then((r) => r.json()),

  queue: (limit = 50) =>
    request(`/api/queue?limit=${limit}`).then((r) => r.json()),

  download: (item) =>
    request('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    }).then((r) => r.json()),

  deleteQueueItem: (id) => request(`/api/queue/${id}`, { method: 'DELETE' }),

  // Binary helpers — fetched with the auth header, returned as object URLs so
  // <img>/<audio> (which can't send headers) can use them.
  coverBlob: (url, size = 'md') =>
    request(`/api/cover?url=${encodeURIComponent(url)}&size=${size}`).then((r) => r.blob()),

  previewBlob: (id) => request(`/api/preview/${id}`).then((r) => r.blob()),
};
