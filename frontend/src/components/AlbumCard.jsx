import Cover from './Cover';
import { useApp } from '../context';

// Square cover + title + artist + year. Fills its container width, so the
// parent controls sizing (fixed-width in the search scroller, grid cell in the
// artist discography). Tapping opens the AlbumPage.
export default function AlbumCard({ album }) {
  const { openAlbum } = useApp();
  return (
    <button onClick={() => openAlbum(album.id)} className="w-full text-left">
      <Cover url={album.cover_url} size="md" className="w-full aspect-square" alt={album.title} />
      <div className="mt-2 text-sm font-medium truncate">{album.title}</div>
      <div className="text-xs text-gray-500 truncate">
        {album.artist_name}
        {album.release_year ? ` · ${album.release_year}` : ''}
      </div>
    </button>
  );
}
