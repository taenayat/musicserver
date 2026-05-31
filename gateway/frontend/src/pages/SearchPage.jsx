import { useEffect, useRef, useState } from 'react';
import SearchBar from '../components/SearchBar';
import ArtistCard from '../components/ArtistCard';
import AlbumCard from '../components/AlbumCard';
import TrackRow from '../components/TrackRow';
import { SearchIcon } from '../components/Icons';
import { api } from '../api';

const INITIAL = 5;

function Section({ title, action, children }) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

// A section that initially shows INITIAL items and expands inline on "Show more".
function ExpandableSection({ title, items, children }) {
  const [expanded, setExpanded] = useState(false);
  const limit = expanded ? items.length : INITIAL;
  const action =
    items.length > INITIAL ? (
      <button onClick={() => setExpanded((e) => !e)} className="text-xs text-accent-start active:opacity-70">
        {expanded ? 'Show less' : 'Show more'}
      </button>
    ) : null;
  return (
    <Section title={title} action={action}>
      {children(limit)}
    </Section>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const reqId = useRef(0);

  // Debounced search: fire 350ms after the user stops typing. A monotonically
  // increasing request id guards against out-of-order responses.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      setLoading(false);
      setError(false);
      return;
    }
    setLoading(true);
    setError(false);
    const myId = ++reqId.current;
    const t = setTimeout(() => {
      api
        .search(q, 20)
        .then((data) => {
          if (myId === reqId.current) {
            setResults(data);
            setLoading(false);
          }
        })
        .catch(() => {
          if (myId === reqId.current) {
            setError(true);
            setLoading(false);
          }
        });
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  const hasResults =
    results && (results.artists.length || results.albums.length || results.tracks.length);

  return (
    <div className="px-3 pt-3">
      <SearchBar value={query} onChange={setQuery} onSubmit={setQuery} />

      {!query.trim() && (
        <div className="mt-32 flex flex-col items-center px-10 text-center text-gray-500">
          <SearchIcon className="mb-3 h-10 w-10" />
          <p>Search Deezer to discover and download music</p>
        </div>
      )}

      {query.trim() && loading && <div className="mt-16 text-center text-gray-500">Searching…</div>}
      {query.trim() && error && (
        <div className="mt-16 text-center text-red-400">Search failed. Pull to retry.</div>
      )}
      {query.trim() && !loading && !error && results && !hasResults && (
        <div className="mt-16 text-center text-gray-500">No results for “{query.trim()}”.</div>
      )}

      {results && hasResults && (
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
    </div>
  );
}
