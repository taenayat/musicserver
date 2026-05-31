import { useEffect, useState } from 'react';
import Cover from '../components/Cover';
import TrackRow from '../components/TrackRow';
import { Overlay } from './ArtistPage';
import { DownloadIcon, CheckIcon } from '../components/Icons';
import { useApp } from '../context';
import { api } from '../api';

// Full-screen overlay: album header + "Download All" + numbered track list.
export default function AlbumPage({ id, onBack }) {
  const { download, isQueued } = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(false);
    api
      .album(id)
      .then((d) => active && setData(d))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [id]);

  const album = data?.album;
  const queued = album ? isQueued('album', album.id) : false;

  return (
    <Overlay onBack={onBack}>
      {error && <div className="mt-24 text-center text-red-400">Couldn’t load this album.</div>}
      {!error && !data && <div className="mt-24 text-center text-gray-500">Loading…</div>}

      {album && (
        <>
          <div className="flex flex-col items-center px-6 pt-16 pb-5">
            <Cover url={album.cover_url} size="lg" className="h-48 w-48 shadow-xl shadow-black/50" alt={album.title} />
            <h1 className="mt-4 text-center text-xl font-bold">{album.title}</h1>
            <p className="text-sm text-gray-400">{album.artist_name}</p>
            <p className="mt-0.5 text-xs text-gray-500">
              {[album.release_year, data.tracks.length ? `${data.tracks.length} tracks` : null]
                .filter(Boolean)
                .join(' · ')}
            </p>

            <button
              onClick={() =>
                download({
                  type: 'album',
                  deezer_id: album.id,
                  title: album.title,
                  artist: album.artist_name,
                  cover_url: album.cover_url,
                })
              }
              disabled={queued}
              className={`mt-4 flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-semibold ${
                queued ? 'bg-green-600 text-white' : 'bg-accent text-white active:opacity-90'
              }`}
            >
              {queued ? <CheckIcon /> : <DownloadIcon />}
              {queued ? 'Queued' : 'Download All'}
            </button>
          </div>

          <div className="px-3 pb-6">
            {data.tracks.map((t) => (
              <TrackRow key={t.id} track={t} index={t.track_no} />
            ))}
          </div>
        </>
      )}
    </Overlay>
  );
}
