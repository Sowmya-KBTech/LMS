// ============================================================
// Navbar — top row of the main panel (Option C template)
// ============================================================
// Breadcrumb · "search pages" pill (Ctrl K) · notifications.
// The logo and the account card live in the Sidebar.
// Same props as before: pages pass setOpen so the menu button can open
// the sidebar drawer on small screens.
// ============================================================

import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import Icon from "./Icon";
import PageSearch from "./PageSearch";
import useRoleFlags from "./useRoleFlags";
import useModules from "./useModules";
import useNotifications, { markNotificationRead } from "./useNotifications";
import { buildHubs, isMainAdmin, locate, readUser } from "./hubs";

const crumbRoot = (user) => {
  if (isMainAdmin(user) || user?.role === "admin") return "Admin";
  if (user?.role === "teacher") return "Faculty";
  if (user?.role === "student") return "Student";
  if (user?.role === "parent") return "Parent";
  return "Campus";
};

function Navbar({ setOpen }) {
  const navigate = useNavigate();
  const location = useLocation();
  const user = readUser();
  const flags = useRoleFlags();
  const modules = useModules();
  const hubs = buildHubs(user, flags, modules);
  const { link, parent } = locate(hubs, location.pathname, location.search);

  const notifications = useNotifications();
  const unread = notifications.length;
  const [showNotifications, setShowNotifications] = useState(false);
  const bellRef = useRef(null);

  useEffect(() => {
    const onDoc = (e) => {
      if (bellRef.current && !bellRef.current.contains(e.target)) setShowNotifications(false);
    };
    const onKey = (e) => e.key === "Escape" && setShowNotifications(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const fmtTime = (iso) =>
    iso ? new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <header className="kb-top">
      {setOpen && (
        <button type="button" className="kb-icon-btn kb-menu-btn" aria-label="Open menu" onClick={() => setOpen(true)}>
          <Icon name="menu" />
        </button>
      )}

      <div className="kb-crumbs">
        {crumbRoot(user)}
        {parent && parent !== link && <> / <span>{parent.label}</span></>}
        {link && <> / <strong>{link.label}</strong></>}
      </div>

      <div className="kb-top-search">
        <PageSearch hubs={hubs} size="sm" placeholder="Search pages…" autoShortcut />
      </div>

      <div className="kb-pop-wrap" ref={bellRef}>
        <button
          type="button"
          className="kb-bell"
          aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
          aria-haspopup="true"
          aria-expanded={showNotifications}
          onClick={() => setShowNotifications((s) => !s)}
        >
          <Icon name="bell" />
          {unread > 0 && <span className="kb-dot">{unread > 99 ? "99+" : unread}</span>}
        </button>

        {showNotifications && (
          <div className="kb-pop kb-notif-pop" role="dialog" aria-label="Notifications">
            <div className="kb-pop-head">
              <b>Notifications</b>
              <span className="kb-muted">{unread ? `${unread} unread` : "All caught up"}</span>
            </div>
            <div className="kb-notif-list">
              {unread === 0 ? (
                <div className="kb-pop-empty">No new notifications.</div>
              ) : (
                notifications.map((n) => (
                  <div key={n.id} className="kb-notif-item">
                    <span className="kb-notif-dot" />
                    <div className="kb-grow">
                      <div className="kb-notif-title">{n.title}</div>
                      {n.message && <div className="kb-notif-msg">{n.message}</div>}
                      {n.created_at && <div className="kb-notif-time">{fmtTime(n.created_at)}</div>}
                    </div>
                    <button
                      type="button"
                      className="kb-icon-btn kb-icon-btn--sm"
                      title="Mark as read"
                      aria-label="Mark as read"
                      onClick={() => markNotificationRead(n.id)}
                    >
                      <Icon name="check" />
                    </button>
                  </div>
                ))
              )}
            </div>
            <button
              type="button"
              className="kb-pop-foot"
              onClick={() => {
                setShowNotifications(false);
                navigate("/notifications");
              }}
            >
              See all notifications
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

export default Navbar;
