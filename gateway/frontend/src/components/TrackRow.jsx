import Cover from './Cover';
import { useApp } from '../context';
import { formatDuration } from '../util';
import { PlayIcon, PauseIcon, DownloadIcon, CheckIcon } from './Icons';

// A single track line: cover (or track number) + title + artist + duration,
// with a preview toggle and a download button.
// Pass `index` (1-based) to show a track number instead of a cover thumbnail.
export default function TrackRow({ track, index = null }) {
  const { player, play, togglePlay, download, isQueued } = useApp();

  const isCurrent = player.track?.id === track.id;
  const isPlaying = isCurrent && player.isPlaying;
  const queued = isQueued('track', track.id);

  const onPreview = () => (isCurrent ? togglePlay() : play(track));

  return (
    <div className="flex items-center gap-3 py-2">
      {index != null ? (
        <div className="w-7 text-center text-sm text-gray-500 tabular-nums">{index}</div>
      ) : (
        <Cover url={track.cover_url} size="sm" className="w-11 h-11" rounded="rounded-md" alt="" />
      )}

      <button onClick={onPreview} className="flex-1 min-w-0 text-left">
        <div className={`text-sm font-medium truncate ${isCurrent ? 'text-accent-start' : ''}`}>
          {track.title}
        </div>
        <div className="text-xs text-gray-500 truncate">{track.artist_name}</div>
      </button>

      <div className="text-xs text-gray-500 tabular-nums">{formatDuration(track.duration)}</div>

      <button onClick={onPreview} className="p-2 text-gray-300 active:text-white" aria-label="Preview">
        {isPlaying ? <PauseIcon /> : <PlayIcon />}
      </button>

      <button
        onClick={() =>
          download({
            type: 'track',
            deezer_id: track.id,
            title: track.title,
            artist: track.artist_name,
            cover_url: track.cover_url,
          })
        }
        disabled={queued}
        className={`p-2 ${queued ? 'text-green-400' : 'text-gray-300 active:text-white'}`}
        aria-label={queued ? 'Queued' : 'Download'}
      >
        {queued ? <CheckIcon /> : <DownloadIcon />}
      </button>
    </div>
  );
}
