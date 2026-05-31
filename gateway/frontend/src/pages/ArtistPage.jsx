import { useEffect, useState } from 'react';
import Cover from '../components/Cover';
import AlbumCard from '../components/AlbumCard';
import TrackRow from '../components/TrackRow';
import { BackIcon } from '../components/Icons';
import { api } from '../api';

// Full-screen overlay that slides up. Shows an artist's top tracks + discography.
export default function ArtistPage({ id, onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(false);
    api
      .artist(id)
      .then((d) => active && setData(d))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [id]);

  return (
    <Overlay onBack={onBack}>
      {error && <div className="mt-24 text-center text-red-400">Couldn’t load this artist.</div>}
      {!error && !data && <div className="mt-24 text-center text-gray-500">Loading…</div>}

      {data && (
        <>
          {/* Header with a blurred blow-up of the artist image behind it. */}
          <div className="relative mb-4 h-56 overflow-hidden">
            <div className="absolute inset-0 scale-110 opacity-40 blur-2xl">
              <Cover url={data.artist.cover_url} size="lg" rounded="rounded-none" className="h-full w-full" />
            </div>
            <div className="absolute inset-0 bg-gradient-to-b from-transparent to-bg" />
            <div className="relative flex h-full flex-col items-center justify-end pb-4">
              <Cover
                url={data.artist.cover_url}
                size="lg"
                rounded="rounded-full"
                className="h-28 w-28 ring-4 ring-bg"
                alt={data.artist.name}
              />
              <h1 className="mt-3 px-6 text-center text-2xl font-bold">{data.artist.name}</h1>
              {data.artist.nb_album ? (
                <p className="text-sm text-gray-400">{data.artist.nb_album} albums</p>
              ) : null}
            </div>
          </div>

          <div className="space-y-7 px-3 pb-6">
            {data.top_tracks.length > 0 && (
              <section>
                <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  Top Tracks
                </h2>
                {data.top_tracks.map((t, i) => (
                  <TrackRow key={t.id} track={t} index={i + 1} />
                ))}
              </section>
            )}

            {data.albums.length > 0 && (
              <section>
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  Discography
                </h2>
                <div className="grid grid-cols-2 gap-4">
                  {data.albums.map((al) => (
                    <AlbumCard key={al.id} album={al} />
                  ))}
                </div>
              </section>
            )}
          </div>
        </>
      )}
    </Overlay>
  );
}

// Shared overlay chrome (slide-up panel + floating back button).
// The back button is absolute within the centered column so it tracks the
// panel edge on desktop, while the inner div scrolls beneath it.
export function Overlay({ onBack, children }) {
  return (
    <div className="fixed inset-0 z-40 bg-bg">
      <div className="relative mx-auto h-full max-w-app">
        <button
          onClick={onBack}
          className="absolute left-3 top-3 z-50 rounded-full bg-black/50 p-2 text-white backdrop-blur active:bg-black/70"
          aria-label="Back"
        >
          <BackIcon />
        </button>
        <div className="h-full animate-slide-up overflow-y-auto pb-24">{children}</div>
      </div>
    </div>
  );
}
