import { createContext, useContext } from 'react';

// One app-wide context carrying the singleton audio player controls and the
// navigation/download actions, so components don't have to prop-drill them.
//
// Shape (provided by App.jsx):
//   player:   { track, isPlaying, progress }   // progress is 0..1
//   play(track)        start/resume a 30s preview (track has id, title, etc.)
//   togglePlay()       pause/resume the current preview
//   stopPlay()         stop and hide the player bar
//   download(item)     queue a track/album download ({type, deezer_id, ...})
//   isQueued(type,id)  has this exact item been queued this session?
//   openArtist(id)     push the ArtistPage overlay
//   openAlbum(id)      push the AlbumPage overlay
export const AppContext = createContext(null);

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppContext.Provider');
  return ctx;
}
