
// ============================================================

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import Icon from "./Icon";
import kbLogo from "../assets/kb-logo.png";
import useRoleFlags, { clearRoleFlags } from "./useRoleFlags";
import API from "../api";
import useModules, { clearModules } from "./useModules";
import useNotifications from "./useNotifications";
import { buildHubs, homePath, initialsOf, locate, readUser, roleLabel } from "./hubs";

// Every page renders its own <Sidebar>, so a click on a link mounts a NEW
// sidebar that would start scrolled to the top. Its scroll position is kept
// here (for this browser tab only) and put back when the next page opens.
const SCROLL_KEY = "kb-side-scroll";

export default function Sidebar({ open, setOpen }) {
  const navigate = useNavigate();
  const location = useLocation();
  const user = readUser();
  const flags = useRoleFlags();
  const modules = useModules(); // hides links for modules this college switched off
  const hubs = buildHubs(user, flags, modules);
  const { link: activeLink, parent: activeParent } = locate(hubs, location.pathname, location.search);
  const unread = useNotifications().length;

  const [menu, setMenu] = useState(false);
  const cardRef = useRef(null);
  const sideRef = useRef(null);
  const userScrolled = useRef(false);
  const lastSet = useRef(null);       // the position WE set (its scroll event is not the user)

  // ---- keep the sidebar where it was ----
  // Restore before the browser paints (no jump). Links can arrive a moment
  // later (role flags / modules), which changes the height - so restore again
  // when the number of links changes, unless the user already scrolled here.
  const linkCount = hubs.reduce((n, g) => n + g.links.length, 0);
  useLayoutEffect(() => {
    const el = sideRef.current;
    if (!el || userScrolled.current) return;
    let saved = 0;
    try { saved = Number(sessionStorage.getItem(SCROLL_KEY)) || 0; } catch { /* storage off */ }
    el.scrollTop = saved;
    // the open page's link must be visible (e.g. reached from search or a bookmark).
    // Moved by hand, not scrollIntoView, so only the sidebar scrolls - never the page.
    const current = el.querySelector('[aria-current="page"]') || el.querySelector(".kb-side-link.is-active");
    if (current) {
      const box = el.getBoundingClientRect();
      const r = current.getBoundingClientRect();
      if (r.top < box.top || r.bottom > box.bottom) {
        el.scrollTop += r.top - box.top - (box.height - r.height) / 2;
      }
    }
    lastSet.current = el.scrollTop;
  }, [linkCount]);

  const onSideScroll = (e) => {
    const top = e.currentTarget.scrollTop;
    if (lastSet.current === null || Math.abs(top - lastSet.current) > 1) userScrolled.current = true;
    try { sessionStorage.setItem(SCROLL_KEY, String(top)); } catch { /* storage off */ }
  };

  // Esc closes the drawer / menu
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      setMenu(false);
      setOpen?.(false);
    };
    const onDoc = (e) => {
      if (cardRef.current && !cardRef.current.contains(e.target)) setMenu(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [setOpen]);

  const go = (path) => {
    navigate(path);
    setOpen?.(false);
    setMenu(false);
  };

  const logout = async () => {
    // PHASE 5 PART 4: tell the server first, so this token stops working now
    // (not in 24 hours). Signing out here still happens if the server is down.
    try { await API.post("users/logout/"); } catch { /* already signed out */ }
    localStorage.removeItem("user");
    localStorage.removeItem("token");
    clearRoleFlags();
    clearModules();
    try { sessionStorage.removeItem(SCROLL_KEY); } catch { /* storage off */ }   // next user starts at the top
    navigate("/");
  };

  const linkProps = (l) => ({
    href: l.path,
    onClick: (e) => {
      e.preventDefault();
      go(l.path);
    },
  });

  return (
    <>
      {open && <div className="kb-side-overlay" onClick={() => setOpen?.(false)} />}

      <aside ref={sideRef} onScroll={onSideScroll} className={`kb-side ${open ? "open" : ""}`} aria-label="Main navigation">
        <div className="kb-side-brand">
          <a {...linkProps({ path: homePath(user) })} className="kb-side-logo" aria-label="Go to dashboard">
            <img src={kbLogo} alt="" />
            <span>KB Tech Campus</span>
          </a>
          <button type="button" className="kb-side-close kb-icon-btn" aria-label="Close menu" onClick={() => setOpen?.(false)}>
            <Icon name="close" />
          </button>
        </div>

        <nav className="kb-side-groups">
          {hubs.map((g) => (
            <div key={g.id} className="kb-side-group">
              <div className="kb-side-gtitle">{g.title}</div>
              {g.links.map((l) => {
                const isParent = activeParent?.path === l.path;
                const isExact = activeLink?.path === l.path;
                const kids = l.children || [];
                const showKids = kids.length > 0 && isParent;
                return (
                  <div key={l.path}>
                    <a
                      {...linkProps(l)}
                      className={`kb-side-link${isParent ? " is-active" : ""}`}
                      aria-current={isExact ? "page" : undefined}
                    >
                      <span className="kb-side-ico"><Icon name={l.icon || "book"} /></span>
                      <span className="kb-grow">{l.label}</span>
                      {l.path === "/notifications" && unread > 0 && (
                        <span className="kb-side-badge">{unread > 99 ? "99+" : unread}</span>
                      )}
                      {kids.length > 0 && <Icon name="chevronDown" className={`kb-side-chev${showKids ? " is-open" : ""}`} />}
                    </a>
                    {showKids && (
                      <div className="kb-side-kids">
                        {kids.map((k) => (
                          <a
                            key={k.path}
                            {...linkProps(k)}
                            className="kb-side-kid"
                            aria-current={activeLink?.path === k.path ? "page" : undefined}
                          >
                            {k.label}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="kb-side-user" ref={cardRef}>
          <button
            type="button"
            className="kb-side-me"
            aria-haspopup="menu"
            aria-expanded={menu}
            onClick={() => setMenu((m) => !m)}
          >
            <span className="kb-side-avatar">{initialsOf(user?.username)}</span>
            <span className="kb-grow">
              <b>{user?.username}</b>
              <small>{roleLabel(user, flags)}</small>
            </span>
          </button>
          <button type="button" className="kb-side-out" aria-label="Log out" title="Log out" onClick={logout}>
            <Icon name="logout" />
          </button>

          {menu && (
            <div className="kb-pop kb-side-menu" role="menu">
              <button type="button" role="menuitem" onClick={() => go("/profile")}><Icon name="user" /> Profile</button>
              <button type="button" role="menuitem" onClick={() => go("/change-password")}><Icon name="lock" /> Change password</button>
              <hr />
              <button type="button" role="menuitem" onClick={logout}><Icon name="logout" /> Log out</button>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}