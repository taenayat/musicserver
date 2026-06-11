import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import { BackIcon } from './Icons';

// Slide-up overlay showing a track's lyrics. Synced lyrics highlight the line
// matching the current preview position (previews are 30s, so the highlight
// tracks the first 30s of the song).
export default function LyricsOverlay({ track, onClose }) {
  const { player } = useApp();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const activeRef = useRef(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .lyrics({
        track_id: track.id,
        title: track.title,
        artist: track.artist_name || track.artist,
        album: track.album_title || '',
        duration: track.duration || 0,
      })
      .then((d) => active && setData(d))
      .catch(() => active && setData({ synced: null, plain: null, source: null }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [track]);

  const isCurrent = player.track?.id === track.id;
  const elapsedMs = isCurrent ? (player.progress || 0) * 30000 : 0;

  let activeIdx = -1;
  if (data?.synced) {
    for (let i = 0; i < data.synced.length; i += 1) {
      if (data.synced[i].time_ms <= elapsedMs) activeIdx = i;
      else break;
    }
  }

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [activeIdx]);

  return (
    <div className="fixed inset-0 z-[60] bg-bg">
      <div className="relative mx-auto h-full max-w-app">
        <button
          onClick={onClose}
          className="absolute left-3 top-3 z-10 rounded-full bg-black/50 p-2 text-white backdrop-blur"
          aria-label="Close lyrics"
        >
          <BackIcon />
        </button>
        <div className="h-full animate-slide-up overflow-y-auto px-6 pb-24 pt-16">
          <h1 className="text-center text-lg font-bold">{track.title}</h1>
          <p className="mb-6 text-center text-sm text-muted">{track.artist_name || track.artist}</p>

          {loading && <p className="mt-16 text-center text-muted">Loading lyrics…</p>}

          {!loading && data && !data.synced && !data.plain && (
            <p className="mt-16 text-center text-muted">No lyrics found.</p>
          )}

          {!loading && data?.synced && (
            <div className="space-y-3 text-center">
              {data.synced.map((line, i) => (
                <p
                  key={i}
                  ref={i === activeIdx ? activeRef : null}
                  className={`transition-colors ${
                    i === activeIdx ? 'text-lg font-semibold text-white' : 'text-muted'
                  }`}
                >
                  {line.text || '♪'}
                </p>
              ))}
            </div>
          )}

          {!loading && data && !data.synced && data.plain && (
            <pre className="whitespace-pre-wrap text-center font-sans text-sm leading-relaxed text-gray-300">
              {data.plain}
            </pre>
          )}

          {data?.source && (
            <p className="mt-8 text-center text-[11px] text-gray-600">source: {data.source}</p>
          )}
        </div>
      </div>
    </div>
  );
}
