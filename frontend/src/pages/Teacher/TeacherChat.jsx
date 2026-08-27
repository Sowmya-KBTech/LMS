// frontend/src/pages/Teacher/TeacherChat.jsx
import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";

export default function TeacherChat() {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [open, setOpen] = useState(false);
  const [contacts, setContacts] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const endRef = useRef(null);

  // ?to=<user id> — set by a Message button elsewhere in the app
  const [params] = useSearchParams();
  const wantedId = params.get("to");

  useEffect(() => {
    API.get("/chat/contacts/")
      .then((res) => {
        const list = res.data || [];
        setContacts(list);
        if (!list.length) return;
        const wanted = wantedId
          ? list.find((c) => String(c.id) === String(wantedId))
          : null;
        setActive(wanted || list[0]);
      })
      .catch((err) => console.log("contacts error:", err))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedId]);

  const fetchMessages = async (id) => {
    try {
      const res = await API.get(`/chat/with/${id}/`);
      setMessages(res.data || []);
    } catch (err) {
      console.log("messages error:", err);
    }
  };

  useEffect(() => {
    if (!active) return;
    fetchMessages(active.id);
    const t = setInterval(() => fetchMessages(active.id), 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // a fresh person means a fresh reply box
  useEffect(() => { setText(""); }, [active]);

  const send = async () => {
    if (!text.trim() || !active) return;
    try {
      await API.post(`/chat/with/${active.id}/`, { text: text.trim() });
      setText("");
      fetchMessages(active.id);
    } catch (err) {
      console.log("send error:", err);
    }
  };

  const initials = (n = "") => n.slice(0, 2).toUpperCase();

  const fmt = (iso) =>
    iso
      ? new Date(iso).toLocaleString("en-IN", {
          day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
        })
      : "";

  // "Today" / "Yesterday" / "14 Aug" — a date bar between days, so a long
  // thread reads as a history instead of one unbroken run of bubbles
  const dayOf = (iso) => (iso ? new Date(iso).toDateString() : "");
  const dayLabel = (iso) => {
    const d = new Date(iso);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) return "Today";
    const y = new Date(today);
    y.setDate(y.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return "Yesterday";
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "long" });
  };

  const canSend = !!text.trim();

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div style={{ width: "100%", margin: "0 auto", padding: "0" }}>

              {/* ================= HEADER ================= */}
              <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 32, fontWeight: 800, margin: 0, color: "#0f172a" }}>
                  Messages
                </h1>
                <p style={{ color: "#64748b", fontSize: 15, marginTop: 4 }}>
                  Reply to parents of your students
                </p>
              </div>

              {loading ? (
                <div style={{ padding: 60, textAlign: "center", color: "#64748b" }}>
                  Loading…
                </div>
              ) : contacts.length === 0 ? (
                <div
                  style={{
                    background: "#fff", border: "1px solid #e2e8f0",
                    borderRadius: 16, padding: 60, textAlign: "center",
                    color: "#64748b",
                  }}
                >
                  No parents yet. Parents appear once their children are linked
                  to a parent account.
                </div>
              ) : (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(0, 380px) minmax(0, 1fr)",
                    gap: 20,
                    height: "calc(100vh - 220px)",
                    alignItems: "stretch",
                  }}
                >

                  {/* ================= PARENTS ================= */}
                  <div
                    style={{
                      background: "#fff", border: "1px solid #e2e8f0",
                      borderRadius: 16, padding: 24, height: "100%",
                      overflowY: "auto",
                    }}
                  >
                    <h3 style={{ fontSize: 17, fontWeight: 700, marginBottom: 18, color: "#0f172a" }}>
                      Parents
                    </h3>

                    {contacts.map((c) => (
                      <div
                        key={c.id}
                        onClick={() => setActive(c)}
                        style={{
                          display: "flex", alignItems: "center", gap: 12,
                          padding: "12px 12px", borderRadius: 12,
                          cursor: "pointer", marginBottom: 4,
                          background: active?.id === c.id ? "#eef4ff" : "transparent",
                          transition: "background 0.15s",
                        }}
                      >
                        <div
                          style={{
                            width: 42, height: 42, borderRadius: "50%",
                            flexShrink: 0, background: "#2563eb", color: "#fff",
                            fontSize: 14, fontWeight: 700, display: "flex",
                            alignItems: "center", justifyContent: "center",
                          }}
                        >
                          {initials(c.username)}
                        </div>

                        {/* name on top, "Parent of <student> · <roll>" below —
                            a teacher recognises the child, not the parent */}
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: 15, fontWeight: 600, color: "#0f172a" }}>
                            {c.username}
                          </div>
                          <div
                            style={{
                              fontSize: 13, color: "#64748b", marginTop: 1,
                              overflow: "hidden", textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {c.subject || "Parent"}
                          </div>
                        </div>

                        {c.unread > 0 && (
                          <span
                            style={{
                              flexShrink: 0, background: "#dc2626", color: "#fff",
                              fontSize: 10, fontWeight: 700, borderRadius: 9,
                              padding: "2px 7px",
                            }}
                          >
                            {c.unread}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* ================= CONVERSATION ================= */}
                  <div
                    style={{
                      background: "#fff", border: "1px solid #e2e8f0",
                      borderRadius: 16, padding: 24, height: "100%",
                      display: "flex", flexDirection: "column",
                    }}
                  >
                    {/* header — name, and who the child is */}
                    <div
                      style={{
                        borderBottom: "1px solid #f1f5f9",
                        paddingBottom: 16, marginBottom: 18,
                      }}
                    >
                      <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: "#0f172a" }}>
                        {active ? active.username : "Select a parent"}
                      </h3>
                      {active?.subject && (
                        <div style={{ fontSize: 13, color: "#64748b", marginTop: 3 }}>
                          {active.subject}
                        </div>
                      )}
                    </div>

                    <div
                      style={{
                        flex: 1, display: "flex", flexDirection: "column",
                        gap: 14, overflowY: "auto", paddingRight: 6,
                        marginBottom: 16,
                      }}
                    >
                      {messages.length === 0 ? (
                        <div
                          style={{
                            color: "#94a3b8", fontSize: 14, textAlign: "center",
                            marginTop: "auto", marginBottom: "auto",
                          }}
                        >
                          No messages yet.
                        </div>
                      ) : (
                        messages.map((m, i) => {
                          const mine =
                            m.sender === user.id || m.sender_name === user.username;
                          const newDay =
                            i === 0 ||
                            dayOf(m.created_at) !== dayOf(messages[i - 1].created_at);

                          return (
                            <div key={m.id}>
                              {newDay && (
                                <div
                                  style={{
                                    textAlign: "center", fontSize: 11.5,
                                    color: "#94a3b8", margin: "4px 0 14px",
                                  }}
                                >
                                  {dayLabel(m.created_at)}
                                </div>
                              )}

                              <div
                                style={{
                                  display: "flex",
                                  justifyContent: mine ? "flex-end" : "flex-start",
                                }}
                              >
                                <div style={{ maxWidth: "75%" }}>
                                  <div
                                    style={{
                                      fontSize: 12, color: "#9ca3af",
                                      marginBottom: 5,
                                      textAlign: mine ? "right" : "left",
                                    }}
                                  >
                                    {mine ? "You" : m.sender_name} · {fmt(m.created_at)}
                                  </div>
                                  <div
                                    style={{
                                      padding: "12px 16px", borderRadius: 14,
                                      fontSize: 14, lineHeight: 1.55,
                                      background: mine ? "#2563eb" : "#f1f5f9",
                                      color: mine ? "#fff" : "#1a1d2e",
                                      borderBottomRightRadius: mine ? 4 : 14,
                                      borderBottomLeftRadius: mine ? 14 : 4,
                                      wordBreak: "break-word",
                                    }}
                                  >
                                    {m.text}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })
                      )}
                      <div ref={endRef} />
                    </div>

                    {active && (
                      <div style={{ display: "flex", gap: 10 }}>
                        <input
                          type="text"
                          value={text}
                          placeholder="Type a reply…"
                          onChange={(e) => setText(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && send()}
                          style={{
                            flex: 1, border: "1px solid #e2e8f0", borderRadius: 12,
                            padding: "13px 16px", fontSize: 14,
                            background: "#f8fafc", outline: "none",
                          }}
                        />
                        <button
                          type="button"
                          onClick={send}
                          disabled={!canSend}
                          style={{
                            background: canSend ? "#2563eb" : "#e2e8f0",
                            color: canSend ? "#fff" : "#94a3b8",
                            border: "none", borderRadius: 12, padding: "0 28px",
                            fontSize: 15, fontWeight: 600,
                            fontFamily: "inherit", textDecoration: "none",
                            cursor: canSend ? "pointer" : "not-allowed",
                          }}
                        >
                          Send
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}