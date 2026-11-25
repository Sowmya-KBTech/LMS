// ============================================================
// KB Tech Campus — icon set (stroke icons taken from the Hub design)
// Usage: <Icon name="book" />   size defaults to 20px (see .kb-i in App.css)
// ============================================================

const PATHS = {
  grid: (<><rect x="4" y="4" width="7" height="7" rx="2" /><rect x="13" y="4" width="7" height="7" rx="2" /><rect x="4" y="13" width="7" height="7" rx="2" /><rect x="13" y="13" width="7" height="7" rx="2" /></>),
  megaphone: (<><path d="M4 10v4a1 1 0 0 0 1 1h3l6 4V5L8 9H5a1 1 0 0 0-1 1z" /><path d="M18 9a4 4 0 0 1 0 6" /></>),
  award: (<><circle cx="12" cy="9" r="5" /><path d="m9 13-1.5 8L12 19l4.5 2L15 13" /></>),
  layers: (<><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 13 9 5 9-5" /></>),
  clipboard: (<><rect x="6" y="4" width="12" height="17" rx="2" /><path d="M9 4h6v3H9z" /><path d="M9 12h6M9 16h4" /></>),
  userCheck: (<><circle cx="9" cy="8" r="3.5" /><path d="M2 20c0-3.5 3-6 7-6 1.5 0 2.8.3 3.9.9" /><path d="m15 18 2 2 4-4" /></>),
  table: (<><rect x="3" y="5" width="18" height="15" rx="2" /><path d="M3 10h18M9 10v10" /></>),
  settings: (<><circle cx="12" cy="12" r="3" /><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z" /></>),
  chevronDown: (<path d="m6 9 6 6 6-6" />),
  book: (<><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 21V5" /><path d="M9 7h6" /></>),
  exam: (<><path d="M9 4h6l1 2h3v15H5V6h3z" /><path d="m9 13 2 2 4-4" /></>),
  people: (<><circle cx="9" cy="8" r="3.5" /><path d="M2 20c0-3.5 3-6 7-6s7 2.5 7 6" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M22 20c0-2.8-1.8-5-4.5-5.7" /></>),
  rupee: (<path d="M7 4h11M7 9h11M7 4c6 0 7 5 1 8l7 8" />),
  briefcase: (<><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18" /></>),
  chat: (<><path d="M4 5h16v11H9l-5 4z" /><path d="M8 10h8M8 13h5" /></>),
  building: (<><path d="M3 21h18" /><path d="M5 21V9l7-5 7 5v12" /><path d="M9 21v-5h6v5" /><path d="M9 11h.01M15 11h.01" /></>),
  group: (<><circle cx="9" cy="8" r="3.2" /><path d="M3 20c.6-3.3 3-5 6-5s5.4 1.7 6 5" /><circle cx="17" cy="9" r="2.4" /><path d="M16 14.5c2.6 0 4.4 1.4 5 4" /></>),
  calendar: (<><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></>),
  shield: (<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" />),
  chart: (<path d="M6 20V12M12 20V5M18 20v-6" />),
  clock: (<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>),
  search: (<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>),
  home: (<><path d="m3 11 9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" /></>),
  bell: (<><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z" /><path d="M10 21h4" /></>),
  user: (<><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4-6 8-6s7 2 8 6" /></>),
  logout: (<><path d="M15 4h4v16h-4" /><path d="M10 8l-4 4 4 4" /><path d="M6 12h10" /></>),
  lock: (<><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>),
  eye: (<><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>),
  eyeOff: (<><path d="M3 3l18 18" /><path d="M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6C3.8 8.4 2 12 2 12s3.6 7 10 7c1.8 0 3.4-.5 4.8-1.3" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>),
  help: (<><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.3 2.4c-.5.2-.8.7-.8 1.2V14" /><path d="M12 17h.01" /></>),
  arrowRight: (<path d="M5 12h14M13 6l6 6-6 6" />),
  arrowLeft: (<path d="M19 12H5M11 6l-6 6 6 6" />),
  chevronRight: (<path d="m9 6 6 6-6 6" />),
  menu: (<path d="M4 7h16M4 12h16M4 17h16" />),
  close: (<path d="M6 6l12 12M18 6 6 18" />),
  check: (<path d="m5 12 5 5 9-10" />),
  cap: (<><path d="m2 9 10-5 10 5-10 5z" /><path d="M6 11v5c2 2 10 2 12 0v-5" /><path d="M22 9v5" /></>),
  faculty: (<><circle cx="10" cy="8" r="3.5" /><path d="M3 20c.8-4 3.6-6 7-6s6.2 2 7 6" /><path d="M17 4l1 2 2 .3-1.5 1.4.4 2.1-1.9-1-1.9 1 .4-2.1L14 6.3 16 6z" /></>),
  star: (<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z" />),
  plus: (<path d="M12 5v14M5 12h14" />),
  alert: (<><path d="M12 3 2 20h20z" /><path d="M12 10v4M12 17h.01" /></>),
};

export default function Icon({ name, className = "", size, title }) {
  const d = PATHS[name] || PATHS.book;
  const style = size ? { width: size, height: size } : undefined;
  return (
    <svg
      className={`kb-i ${className}`}
      viewBox="0 0 24 24"
      style={style}
      aria-hidden={title ? undefined : "true"}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {d}
    </svg>
  );
}
