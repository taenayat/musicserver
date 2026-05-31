import Cover from './Cover';
import { useApp } from '../context';

// Square (circular) artist thumbnail + name. Tapping opens the ArtistPage.
export default function ArtistCard({ artist }) {
  const { openArtist } = useApp();
  return (
    <button onClick={() => openArtist(artist.id)} className="w-28 shrink-0 text-left">
      <Cover url={artist.cover_url} size="md" rounded="rounded-full" className="w-28 h-28" alt={artist.name} />
      <div className="mt-2 text-sm font-medium truncate">{artist.name}</div>
      {artist.nb_album ? (
        <div className="text-xs text-gray-500">{artist.nb_album} albums</div>
      ) : null}
    </button>
  );
}
