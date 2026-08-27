import React, {
  useEffect,
  useState
} from "react";

import {
  useNavigate
} from "react-router-dom";

import API from "../api";

function Navbar({ setOpen }) {

  const user = JSON.parse(
    localStorage.getItem("user") || "{}"
  );

  const navigate = useNavigate();

  // ================= NOTIFICATIONS =================
  const [notifications, setNotifications] =
    useState([]);

  const [showNotifications, setShowNotifications] =
    useState(false);

  // ================= FETCH =================
  const fetchNotifications = async () => {

    try {

      const res = await API.get(
        "/notifications/?unread=true"
      );

      setNotifications(
        res.data?.results ||
        res.data ||
        []
      );

    } catch (err) {

      console.log(
        "Notification fetch error:",
        err
      );
    }
  };

  useEffect(() => {

    fetchNotifications();

    // AUTO REFRESH
    const interval =
      setInterval(() => {

        fetchNotifications();

      }, 10000);

    return () =>
      clearInterval(interval);

  }, []);

  // ================= MARK READ =================
  const markAsRead = async (
    id
  ) => {

    try {

      await API.post(
        `/notifications/${id}/mark_read/`
      );

      fetchNotifications();

    } catch (err) {

      console.log(err);
    }
  };

  // ================= NOTIFICATION DISPLAY =================
  /** "2m", "3h", "yesterday", "12 Jun" — short enough for a dropdown row. */
  const timeAgo = (iso) => {
    if (!iso) return "";
    const then = new Date(iso);
    const mins = Math.floor((Date.now() - then.getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    if (hrs < 48) return "yesterday";
    return then.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  };

  /**
   * Everything lands in one Notification table, so the source is worked out
   * from the wording the sending module used. Not elegant, but it beats a
   * schema change on a table three other modules already write to.
   */
  const iconFor = (n) => {
    const t = (n.title || "").toLowerCase();
    if (t.startsWith("\u{1F4E2}") || t.includes("announcement")) return "\u{1F4E2}";
    if (t.startsWith("event")) return "\u{1F4C5}";
    if (t.startsWith("message from")) return "\u{1F4AC}";
    // a class or subject group message: either "Group \u2014 Sender" from a
    // student, or the bare group name when the teacher posted it
    if (t.includes("\u2014") || /\b(b\.e|b\.tech|m\.e|year)\b/.test(t)) return "\u{1F465}";
    return "\u{1F4CC}";
  };

  /**
   * Where a notification should take you.
   *
   * The Notification table has no link column and four modules already write
   * to it, so the target is worked out from the wording each module used.
   * Fragile if that wording changes — the proper fix is a `link` field on the
   * model, which is a migration touching every writer.
   */
  const linkFor = (n) => {
    const t = (n.title || "").toLowerCase();
    const role = (user?.role || "").toLowerCase();

    if (t.startsWith("event")) return "/calendar";
    if (t.startsWith("announcement:")) return "/announcements";

    // mentoring: "Message from X" / "Announcement from X"
    if (t.startsWith("message from") || t.startsWith("announcement from"))
      return role === "student" ? "/my-mentor" : "/my-mentees";

    // class or subject group: "Group \u2014 Sender", or the bare group name
    if (t.includes("\u2014") || /\b(b\.e|b\.tech|m\.e|year)\b/.test(t))
      return "/my-groups";

    return "/notifications";
  };

  /**
   * Group messages arrive titled "II B.E Mechanical \u2014 Aarthi.R", which is
   * two facts in one line and always truncates. Split them: the group name gets
   * the title, the sender goes in front of the preview, the way a chat list does.
   */
  const splitTitle = (n) => {
    const raw = n.title || "";
    const i = raw.indexOf("\u2014");
    if (i === -1) return { head: raw, who: "" };
    return {
      head: raw.slice(0, i).trim(),
      who: raw.slice(i + 1).trim(),
    };
  };

  /** Row click opens the page. It does NOT mark the notification read \u2014
   *  that is what the tick is for. */
  const openNotification = (n) => {
    setShowNotifications(false);
    navigate(linkFor(n));
  };

  // ================= USER =================
  const initials = user?.username
    ? user.username
        .slice(0, 2)
        .toUpperCase()
    : "??";

  const roleColors = {

    admin: {
      bg: "#dbeafe",
      color: "#1d4ed8"
    },

    teacher: {
      bg: "#ede9fe",
      color: "#5b21b6"
    },

    student: {
      bg: "#dcfce7",
      color: "#166534"
    },
  };

  const rc =
    roleColors[user?.role] || {

      bg: "#f1f5f9",
      color: "#475569"
    };

  // ================= LOGOUT =================
  const handleLogout = () => {

    localStorage.removeItem(
      "user"
    );

    navigate("/");
  };

  return (
    <div style={styles.navbar}>

      {/* ================= LEFT ================= */}
      <div style={styles.left}>

        {/* MENU */}
        <button style={styles.menuBtn} onClick={() => setOpen(true)}>
          ☰
        </button>

        {/* BRAND */}
        <div
          style={styles.brand} onClick={() => navigate("/dashboard")} >

          <div
            style={ styles.brandIcon } > 🎓 </div>

          <span style={styles.brandText}>
            Learning Management System
          </span>

        </div>

      </div>

      {/* ================= RIGHT ================= */}
      <div style={styles.right}>

        {/* ================= NOTIFICATION ================= */}
        <div style={{ position: "relative",}} >

          {/* BELL */}
          <button
            style={ styles.notificationBtn }
            onClick={() =>
              setShowNotifications(  !showNotifications )} >🔔

            {/* COUNT */}
            {notifications.length >
              0 && (
              <span
                style={ styles.notificationBadge}>
                { notifications.length }
              </span>)}
          </button>

          {/* ================= DROPDOWN ================= */}
          {showNotifications && (

            <div
              style={styles.notificationDropdown}>

              <h4 style={{ marginBottom:"10px",}}> Notifications </h4>

              {notifications.length ===
              0 ? (

                <p
                  style={{
                    fontSize:
                      "13px",
                  }}
                >
                  No new
                  notifications
                </p>

              ) : (

                notifications.map(
                  (n) => (

                    <div
                      key={n.id}
                      style={styles.notificationItem}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.background = "#f8fafc")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.background = "transparent")
                      }
                    >

                      <div
                        onClick={() => openNotification(n)}
                        title="Open"
                        style={{
                          display: "flex",
                          gap: "10px",
                          alignItems: "flex-start",
                          flex: 1,
                          minWidth: 0,
                          cursor: "pointer",
                        }}
                      >

                        <span
                          style={{
                            fontSize: "15px",
                            lineHeight: "1.4",
                            flex: "0 0 auto",
                          }}
                        >
                          {iconFor(n)}
                        </span>

                        <div style={{ flex: 1, minWidth: 0 }}>

                          <div
                            style={{
                              display: "flex",
                              alignItems: "baseline",
                              gap: "8px",
                            }}
                          >

                            <strong
                              style={{
                                fontSize: "13.5px",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {splitTitle(n).head}
                            </strong>

                            <span
                              style={{
                                marginLeft: "auto",
                                fontSize: "11px",
                                color: "#9ca3af",
                                whiteSpace: "nowrap",
                                flex: "0 0 auto",
                              }}
                            >
                              {timeAgo(n.created_at)}
                            </span>

                          </div>

                          <p
                            style={{
                              margin: "2px 0 0",
                              fontSize: "12px",
                              color: "#6b7280",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {splitTitle(n).who && (
                              <span style={{ fontWeight: 600, color: "#374151" }}>
                                {splitTitle(n).who}:{" "}
                              </span>
                            )}
                            {n.message}
                          </p>

                        </div>

                      </div>

                      <button
                        style={
                          styles.readBtn
                        }
                        title="Mark as seen"
                        onClick={(e) => {
                          e.stopPropagation();   // ticking must not open the page
                          markAsRead(n.id);
                        }}
                      >
                        ✓
                      </button>

                    </div>

                  )
                )

              )}

            </div>

          )}

        </div>

        {/* ================= USER ================= */}
        <div style={styles.userPill}>

          <div
            style={{
              ...styles.avatar,
              background:
                rc.bg,
              color:
                rc.color
            }}
          >
            {initials}
          </div>

          <div
            style={
              styles.userInfo
            }
          >

            <span
              style={
                styles.username
              }
            >
              {
                user?.username
              }
            </span>

            <span
              style={{
                ...styles.roleBadge,
                background:
                  rc.bg,
                color:
                  rc.color
              }}
            >
              {user?.role}
            </span>

          </div>

        </div>

        {/* DIVIDER */}
        <div style={styles.divider} />

        {/* LOGOUT */}
        <button
          style={
            styles.logoutBtn
          }
          onClick={
            handleLogout
          }
        >
          Log out
        </button>

      </div>

    </div>
  );
}

/* ================= CSS ================= */
const styles = {

  navbar: {
    width: "100%",
    height: 65,
    padding: "0 24px",
    background:   "linear-gradient(180deg, #faffff, #f8fafc)",
    borderBottom: "1px solid #e5e7eb",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    position: "sticky",
    top: 0,
    zIndex: 1000,
    boxShadow: "0 2px 10px rgba(0,0,0,0.05)"
  },

  left: {
    display: "flex",
    alignItems: "center",
    gap: 16
  },

  menuBtn: {
    fontSize: 20,
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: 6,
    borderRadius: 6
  },

  brand: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    cursor: "pointer"
  },

  brandIcon: {
    width: "26",
    height: "26",
    borderRadius: "6",
    background: "#3b82f6",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: "bold",
    fontSize: 14
  },

  brandText: {

    fontSize: 15,

    fontWeight: 600,

    color: "#0f172a"
  },

  right: {

    display: "flex",

    alignItems: "center",

    gap: 18
  },

  notificationBtn: {

    position: "relative",

    border: "none",

    background: "#fff",

    cursor: "pointer",

    fontSize: 20,

    padding: "6px 10px",

    borderRadius: 8
  },

  notificationBadge: {

    position: "absolute",

    top: -4,

    right: -4,

    background: "red",

    color: "white",

    borderRadius: "50%",

    width: 18,

    height: 18,

    fontSize: 11,

    display: "flex",

    alignItems: "center",

    justifyContent: "center"
  },

  notificationDropdown: {

    position: "absolute",

    right: 0,

    top: 45,

    width: 380,

    maxHeight: 440,

    overflowY: "auto",

    background: "#fff",

    border:
      "1px solid #e5e7eb",

    borderRadius: 10,

    padding: 15,

    boxShadow:
      "0 4px 14px rgba(0,0,0,0.1)",

    zIndex: 2000
  },

  notificationItem: {

    display: "flex",

    justifyContent:
      "space-between",

    gap: 10,

    padding: 10,

    borderBottom:
      "1px solid #f1f5f9",

    borderRadius: 8,

    transition: "background .12s"
  },

  readBtn: {

    border: "none",

    background: "#22c55e",

    color: "white",

    borderRadius: 6,

    padding: "4px 8px",

    cursor: "pointer"
  },

  userPill: {

    display: "flex",

    alignItems: "center",

    gap: 10,

    padding: "4px 8px",

    borderRadius: 10
  },

  avatar: {

    width: 34,

    height: 34,

    borderRadius: "50%",

    display: "flex",

    alignItems: "center",

    justifyContent: "center",

    fontSize: 12,

    fontWeight: 700
  },

  userInfo: {

    display: "flex",

    flexDirection: "column",

    lineHeight: 1.2
  },

  username: {

    fontSize: 13,

    fontWeight: 600,

    color: "#0f172a"
  },

  roleBadge: {

    fontSize: 10,

    padding: "2px 6px",

    borderRadius: 999,

    textTransform:
      "capitalize"
  },

  divider: {

    width: 1,

    height: 28,

    background: "#e5e7eb"
  },

  logoutBtn: {

    padding: "7px 14px",

    borderRadius: 8,

    border:
      "1px solid #e5e7eb",

    background: "#fff",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 500
  }
};

export default Navbar;