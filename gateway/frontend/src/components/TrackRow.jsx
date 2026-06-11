import Cover from './Cover';
import { useApp } from '../context';
import { formatDuration } from '../util';
import {
  PlayIcon,
  PauseIcon,
  DownloadIcon,
  CheckIcon,
  UpgradeIcon,
  LyricsIcon,
} from './Icons';

// A single track line: cover (or track number) + title + artist + duration,
// with a preview toggle, an "In Library" badge or download button, and an
// optional lyrics button. Pass `index` (1-based) to show a track number.
export default function TrackRow({ track, index = null }) {
  const { player, play, togglePlay, download, isQueued, openLyrics } = useApp();

  const isCurrent = player.track?.id === track.id;
  const isPlaying = isCurrent && player.isPlaying;
  const queued = isQueued('track', track.id);
  const isYoutube = track.source === 'youtube';

  const onPreview = () => (isCurrent ? togglePlay() : play(track));

  const doDownload = (force = false) =>
    download({
      source: isYoutube ? 'youtube' : 'deezer',
      type: isYoutube ? undefined : 'track',
      deezer_id: isYoutube ? undefined : track.id,
      yt_id: isYoutube ? track.yt_id : undefined,
      yt_query: isYoutube ? track.title : undefined,
      title: track.title,
      artist: track.artist_name || track.artist,
      cover_url: track.cover_url || track.thumbnail_url,
      force,
    });

  return (
    <div className="flex items-center gap-3 py-2">
      {index != null ? (
        <div className="w-7 text-center text-sm text-muted tabular-nums">{index}</div>
      ) : (
        <Cover url={track.cover_url} size="sm" className="w-11 h-11" rounded="rounded-md" alt="" />
      )}

      <button onClick={onPreview} className="flex-1 min-w-0 text-left">
        <div className="flex items-center gap-1.5">
          {isYoutube && (
            <span className="rounded bg-error px-1 py-0.5 text-[9px] font-bold leading-none text-white">
              YT
            </span>
          )}
          <span className={`truncate text-sm font-medium ${isCurrent ? 'text-accent-start' : ''}`}>
            {track.title}
          </span>
        </div>
        <div className="truncate text-xs text-muted">{track.artist_name || track.artist}</div>
      </button>

      <div className="text-xs text-muted tabular-nums">{formatDuration(track.duration)}</div>

      {!isYoutube && track.id && (
        <button
          onClick={() => openLyrics?.(track)}
          className="p-2 text-gray-400 active:text-white"
          aria-label="Lyrics"
        >
          <LyricsIcon className="h-4 w-4" />
        </button>
      )}

      <button onClick={onPreview} className="p-2 text-gray-300 active:text-white" aria-label="Preview">
        {isPlaying ? <PauseIcon /> : <PlayIcon />}
      </button>

      {track.in_library ? (
        <div className="flex items-center gap-1">
          <span className="flex items-center gap-1 rounded-md bg-success/15 px-2 py-1 text-[11px] font-medium text-success">
            <CheckIcon className="h-3.5 w-3.5" /> Library
          </span>
          <button
            onClick={() => {
              if (confirm('Re-download to upgrade quality? This overwrites the current file.'))
                doDownload(true);
            }}
            className="p-1 text-muted active:text-white"
            aria-label="Upgrade quality"
            title="Upgrade quality"
          >
            <UpgradeIcon />
          </button>
        </div>
      ) : (
        <button
          onClick={() => doDownload(false)}
          disabled={queued}
          className={`p-2 ${queued ? 'text-success' : 'text-gray-300 active:text-white'}`}
          aria-label={queued ? 'Queued' : 'Download'}
        >
          {queued ? <CheckIcon /> : <DownloadIcon />}
        </button>
      )}
    </div>
  );
}
