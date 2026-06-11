import { useEffect, useRef } from 'react';
import { SearchIcon, CloseIcon } from './Icons';

// Controlled search input. Autofocuses on mount and debounces nothing itself —
// the parent decides when to fire the query (on submit / debounced value).
export default function SearchBar({ value, onChange, onSubmit, placeholder = 'Search Deezer…' }) {
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        inputRef.current?.blur();
        onSubmit?.(value);
      }}
      className="relative"
    >
      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
        <SearchIcon />
      </span>
      <input
        ref={inputRef}
        type="search"
        inputMode="search"
        enterKeyHint="search"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-full bg-card pl-10 pr-10 py-3 text-base text-gray-100
                   placeholder-gray-500 outline-none focus:ring-2 focus:ring-accent-start"
      />
      {value && (
        <button
          type="button"
          onClick={() => {
            onChange('');
            inputRef.current?.focus();
          }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 active:text-gray-200"
          aria-label="Clear"
        >
          <CloseIcon />
        </button>
      )}
    </form>
  );
}
