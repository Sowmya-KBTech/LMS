// ============================================================
// PageSearch — "search for a page" box (top bar + home page)
// Searches only the pages this user can open (from hubs.js).
// Keyboard: ↑ ↓ to move, Enter to open, Esc to close.
// ============================================================

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "./Icon";
import { searchIndex } from "./hubs";

export default function PageSearch({ hubs, size = "sm", placeholder, autoShortcut = false }) {
  const navigate = useNavigate();
  const wrapRef = useRef(null);
  const inputRef = useRef(null);

  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const index = searchIndex(hubs);

  const results = (() => {
    const term = q.trim().toLowerCase();
    if (!term) return index.slice(0, 8);
    const words = term.split(/\s+/);
    return index
      .map((it) => {
        const hay = `${it.label} ${it.hubTitle}`.toLowerCase();
        if (!words.every((w) => hay.includes(w))) return null;
        const starts = it.label.toLowerCase().startsWith(words[0]) ? 0 : 1;
        return { it, starts };
      })
      .filter(Boolean)
      .sort((a, b) => a.starts - b.starts)
      .map((r) => r.it)
      .slice(0, 10);
  })();

  // close when clicking elsewhere
  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // "/" or Ctrl+K focuses the top-bar search
  useEffect(() => {
    if (!autoShortcut) return undefined;
    const onKey = (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable;
      if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [autoShortcut]);

  const go = (item) => {
    if (!item) return;
    setOpen(false);
    setQ("");
    inputRef.current?.blur();
    navigate(item.path);
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  return (
    <div className={`kb-search kb-search--${size}`} ref={wrapRef}>
      <Icon name="search" />
      <label className="kb-sr" htmlFor={`kb-search-${size}`}>Search pages</label>
      <input
        id={`kb-search-${size}`}
        ref={inputRef}
        type="search"
        className="kb-input"
        placeholder={placeholder || "Search pages…"}
        autoComplete="off"
        value={q}
        role="combobox"
        aria-expanded={open}
        aria-controls={`kb-suggest-${size}`}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onKeyDown={onKeyDown}
      />
      {autoShortcut && <kbd className="kb-kbd" aria-hidden="true">Ctrl K</kbd>}

      {open && (
        <div className="kb-suggest" id={`kb-suggest-${size}`} role="listbox">
          {results.length === 0 ? (
            <div className="kb-suggest-empty">No page matches “{q}”. Try a shorter word.</div>
          ) : (
            results.map((it, i) => (
              <button
                type="button"
                key={it.path}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => go(it)}
              >
                <span className={`kb-hub-dot tone-${it.tone}`} />
                <span className="kb-suggest-label">{it.label}</span>
                <span className="kb-suggest-tag">{it.hubTitle}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
