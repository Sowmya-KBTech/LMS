import { useEffect, useState, useRef } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";
import "../../styles/ParentModule.css";

export default function ParentMessages() {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [open, setOpen] = useState(false);

  const [contacts, setContacts] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const endRef = useRef(null);

  useEffect(() => {
    API.get("/messages/contacts/")
      .then((res) => {
        const list = res.data || [];
        setContacts(list);
        if (list.length) setActive(list[0]);
      })
      .catch((err) => console.log("contacts error:", err))
      .finally(() => setLoading(false));
  }, []);

  const fetchMessages = async (teacherId) => {
    try {
      const res = await API.get(`/messages/with/${teacherId}/`);
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

  const send = async () => {
    if (!text.trim() || !active) return;
    try {
      await API.post(`/messages/with/${active.id}/`, { text: text.trim() });
      setText("");
      fetchMessages(active.id);
    } catch (err) {
      console.log("send error:", err);
    }
  };

  const initials = (name = "") => name.slice(0, 2).toUpperCase();
  const fmt = (iso) =>
    iso ? new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="pm-page">

              <div className="pm-header">
                <h1>Messages</h1>
                <p>Communicate with your children's teachers</p>
              </div>

              {loading ? (
                <div className="pm-loading">Loading…</div>
              ) : contacts.length === 0 ? (
                <div className="pm-card">
                  <div className="pm-empty">
                    No teachers found. Teachers appear here once your child is enrolled in their subjects.
                  </div>
                </div>
              ) : (
                <div className="pm-two-col">
                  <div className="pm-card">
                    <div className="pm-card-title">Conversations</div>
                    {contacts.map((c) => (
                      <div
                        key={c.id}
                        onClick={() => setActive(c)}
                        style={{
                          display: "flex", alignItems: "center", gap: "10px",
                          padding: "10px 8px", borderRadius: "8px", cursor: "pointer",
                          background: active?.id === c.id ? "#eef4ff" : "transparent",
                        }}
                      >
                        <div style={{
                          width: 34, height: 34, borderRadius: "50%", flexShrink: 0,
                          background: "#4B32C3", color: "#fff", fontSize: 13, fontWeight: 600,
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                          {initials(c.username)}
                        </div>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: "#17151F" }}>{c.username}</div>
                          <div style={{ fontSize: 12, color: "#5D5A6B" }}>{c.subject}</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="pm-card">
                    <div className="pm-card-title">
                      {active ? `${active.username} — ${active.subject}` : "Select a conversation"}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "10px", minHeight: 220, maxHeight: 360, overflowY: "auto", paddingRight: 4 }}>
                      {messages.length === 0 ? (
                        <div className="pm-empty">No messages yet. Say hello!</div>
                      ) : (
                        messages.map((m) => {
                          const mine = (m.sender === user.id) || (m.sender_name === user.username);
                          return (
                            <div key={m.id} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "80%" }}>
                              <div style={{ fontSize: 12, color: "#85839A", marginBottom: 3, textAlign: mine ? "right" : "left" }}>
                                {mine ? "You" : m.sender_name} · {fmt(m.created_at)}
                              </div>
                              <div style={{
                                padding: "9px 13px", borderRadius: 10, fontSize: 14, lineHeight: 1.5,
                                background: mine ? "#4B32C3" : "#ECECF0",
                                color: mine ? "#fff" : "#1a1d2e",
                              }}>
                                {m.text}
                              </div>
                            </div>
                          );
                        })
                      )}
                      <div ref={endRef} />
                    </div>

                    {active && (
                      <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                        <input
                          type="text"
                          value={text}
                          placeholder="Type a message…"
                          onChange={(e) => setText(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && send()}
                          style={{ flex: 1, border: "1px solid #E7E7EC", borderRadius: 10, padding: "9px 14px", fontSize: 14, background: "#F6F6F8", outline: "none" }}
                        />
                        <button className="btn-primary" style={{ background: "#4B32C3", color: "#fff" }} onClick={send}>
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