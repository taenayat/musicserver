import { useEffect, useRef, useState } from 'react';
import SearchBar from '../components/SearchBar';
import ArtistCard from '../components/ArtistCard';
import AlbumCard from '../components/AlbumCard';
import TrackRow from '../components/TrackRow';
import { SearchIcon } from '../components/Icons';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

const INITIAL = 5;

function Section({ title, action, children }) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function ExpandableSection({ title, items, children }) {
  const [expanded, setExpanded] = useState(false);
  const limit = expanded ? items.length : INITIAL;
  const action =
    items.length > INITIAL ? (
      <button onClick={() => setExpanded((e) => !e)} className="text-xs text-accent-start active:opacity-70">
        {expanded ? 'Show less' : 'Show more'}
      </button>
    ) : null;
  return <Section title={title} action={action}>{children(limit)}</Section>;
}

export default function SearchPage() {
  const { health } = useAuth();
  const ytEnabled = health?.ytdlp_enabled;
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('deezer'); // 'deezer' | 'youtube'
  const [results, setResults] = useState(null); // Deezer shape { artists, albums, tracks }
  const [yt, setYt] = useState(null); // array of YouTube tracks
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const reqId = useRef(0);

  // If YouTube support is toggled off in health, fall back to Deezer.
  useEffect(() => {
    if (!ytEnabled && source === 'youtube') setSource('deezer');
  }, [ytEnabled, source]);

  // Debounced search against the active source. Switching source re-runs the
  // query and the inactive source's results are cleared so they never mix.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      setYt(null);
      setLoading(false);
      setError(false);
      return;
    }
    setLoading(true);
    setError(false);
    const myId = ++reqId.current;
    const t = setTimeout(() => {
      const req = source === 'youtube' ? api.searchYoutube(q, 10) : api.search(q, 20);
      req
        .then((data) => {
          if (myId !== reqId.current) return;
          if (source === 'youtube') {
            setYt(data.tracks || []);
            setResults(null);
          } else {
            setResults(data);
            setYt(null);
          }
          setLoading(false);
        })
        .catch(() => {
          if (myId !== reqId.current) return;
          setError(true);
          setLoading(false);
        });
    }, 350);
    return () => clearTimeout(t);
  }, [query, source]);

  const hasDeezer =
    results && (results.artists.length || results.albums.length || results.tracks.length);
  const q = query.trim();

  const Toggle = ({ value: v, label }) => (
    <button
      onClick={() => setSource(v)}
      className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
        source === v ? 'bg-accent text-white' : 'text-muted active:text-white'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="px-3 pt-3">
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={setQuery}
        placeholder={source === 'youtube' ? 'Search YouTube Music…' : 'Search Deezer…'}
      />

      {ytEnabled && (
        <div className="mt-2 flex w-max gap-1 rounded-full bg-card p-1">
          <Toggle value="deezer" label="Deezer" />
          <Toggle value="youtube" label="YouTube" />
        </div>
      )}

      {!q && (
        <div className="mt-32 flex flex-col items-center px-10 text-center text-muted">
          <SearchIcon className="mb-3 h-10 w-10" />
          <p>{source === 'youtube' ? 'Search YouTube Music' : 'Search Deezer to discover music'}</p>
        </div>
      )}

      {q && loading && <div className="mt-16 text-center text-muted">Searching…</div>}
      {q && error && (
        <div className="mt-16 text-center text-error">Search failed. Try again.</div>
      )}

      {/* Deezer results */}
      {source === 'deezer' && q && !loading && !error && results && !hasDeezer && (
        <div className="mt-16 text-center text-muted">No results for “{q}”.</div>
      )}
      {source === 'deezer' && results && hasDeezer && (
        <div className="mt-4 space-y-7 pb-4">
          {results.artists.length > 0 && (
            <ExpandableSection title="Artists" items={results.artists}>
              {(limit) => (
                <div className="no-scrollbar -mx-1 flex gap-3 overflow-x-auto px-1">
                  {results.artists.slice(0, limit).map((a) => (
                    <ArtistCard key={a.id} artist={a} />
                  ))}
                </div>
              )}
            </ExpandableSection>
          )}

          {results.albums.length > 0 && (
            <ExpandableSection title="Albums" items={results.albums}>
              {(limit) => (
                <div className="no-scrollbar -mx-1 flex gap-3 overflow-x-auto px-1">
                  {results.albums.slice(0, limit).map((al) => (
                    <div key={al.id} className="w-36 shrink-0">
                      <AlbumCard album={al} />
                    </div>
                  ))}
                </div>
              )}
            </ExpandableSection>
          )}

          {results.tracks.length > 0 && (
            <ExpandableSection title="Tracks" items={results.tracks}>
              {(limit) => (
                <div>
                  {results.tracks.slice(0, limit).map((t) => (
                    <TrackRow key={t.id} track={t} />
                  ))}
                </div>
              )}
            </ExpandableSection>
          )}
        </div>
      )}

      {/* YouTube results */}
      {source === 'youtube' && q && !loading && !error && yt && (
        <div className="mt-7 pb-4">
          <Section title="YouTube Music">
            {yt.length === 0 ? (
              <div className="py-6 text-center text-muted">No YouTube results.</div>
            ) : (
              yt.map((t) => <TrackRow key={t.yt_id} track={{ ...t, source: 'youtube' }} />)
            )}
          </Section>
        </div>
      )}
    </div>
  );
}
