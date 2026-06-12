import { createContext, useContext } from 'react';

// One app-wide context carrying the singleton audio-player controls plus the
// navigation / download / toast actions, so components don't prop-drill them.
//
// Shape (provided by App.jsx):
//   player:   { track, isPlaying, progress }   // progress is 0..1
//   play(track)        start/resume a 30s preview
//   togglePlay()       pause/resume the current preview
//   stopPlay()         stop and hide the player bar
//   download(item)     queue a download ({source?, type, deezer_id|yt_id, ...})
//   isQueued(type,id)  has this item been queued this session?
//   openArtist(id)     push the ArtistPage overlay
//   openAlbum(id)      push the AlbumPage overlay
//   openLyrics(track)  push the lyrics overlay for a track
//   toast(msg, kind)   show a transient toast ('info'|'success'|'error')
export const AppContext = createContext(null);

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppContext.Provider');
  return ctx;
}
