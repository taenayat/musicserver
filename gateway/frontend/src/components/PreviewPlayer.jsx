import Cover from './Cover';
import { useApp } from '../context';
import { PlayIcon, PauseIcon, CloseIcon } from './Icons';

// Bottom mini-player on the accent gradient. Sits just above the tab bar.
// Visible whenever a preview track is loaded; the progress bar is display-only.
export default function PreviewPlayer() {
  const { player, togglePlay, stopPlay } = useApp();
  const track = player.track;
  if (!track) return null;

  return (
    <div className="fixed bottom-16 left-1/2 -translate-x-1/2 w-full max-w-app px-2 z-30">
      <div className="bg-accent rounded-xl shadow-lg shadow-black/40 overflow-hidden">
        <div className="flex items-center gap-3 px-3 py-2">
          <Cover url={track.cover_url} size="sm" className="w-10 h-10" rounded="rounded-md" alt="" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold truncate text-white">{track.title}</div>
            <div className="text-xs text-white/70 truncate">{track.artist_name}</div>
          </div>
          <button onClick={togglePlay} className="p-2 text-white" aria-label="Play or pause">
            {player.isPlaying ? <PauseIcon className="w-7 h-7" /> : <PlayIcon className="w-7 h-7" />}
          </button>
          <button onClick={stopPlay} className="p-1 text-white/80 active:text-white" aria-label="Dismiss">
            <CloseIcon />
          </button>
        </div>
        <div className="h-1 bg-white/20">
          <div
            className="h-full bg-white transition-[width] duration-150 ease-linear"
            style={{ width: `${Math.round((player.progress || 0) * 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}
