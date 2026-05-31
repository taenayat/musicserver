import { useEffect, useState } from 'react';
import { api } from '../api';

// Covers are served by the authed /api/cover proxy, so a plain <img src> can't
// load them (no Authorization header). We fetch the bytes and hand the <img> an
// object URL instead. Results are memoised per url+size for the session so the
// same cover isn't refetched on every render/scroll.
const cache = new Map();

export default function Cover({ url, size = 'md', className = '', rounded = 'rounded-lg', alt = '' }) {
  const cacheKey = url ? `${url}|${size}` : null;
  const [src, setSrc] = useState(() => (cacheKey ? cache.get(cacheKey) || null : null));

  useEffect(() => {
    if (!cacheKey) {
      setSrc(null);
      return;
    }
    if (cache.has(cacheKey)) {
      setSrc(cache.get(cacheKey));
      return;
    }
    let active = true;
    api
      .coverBlob(url, size)
      .then((blob) => {
        const obj = URL.createObjectURL(blob);
        cache.set(cacheKey, obj);
        if (active) setSrc(obj);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [cacheKey, url, size]);

  const base = `bg-card overflow-hidden flex items-center justify-center ${rounded} ${className}`;

  if (!src) {
    // Placeholder: a muted music glyph while loading or when no cover exists.
    return (
      <div className={base}>
        <svg viewBox="0 0 24 24" className="w-1/3 h-1/3 text-gray-600" fill="currentColor">
          <path d="M12 3v10.55A4 4 0 1014 17V7h4V3h-6z" />
        </svg>
      </div>
    );
  }
  return <img src={src} alt={alt} loading="lazy" className={`${base} object-cover`} />;
}
