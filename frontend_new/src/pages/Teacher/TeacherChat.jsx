import { useEffect, useState, useRef } from "react";
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

  useEffect(() => {
    API.get("/chat/contacts/")
      .then((res) => {
        const list = res.data || [];
        setContacts(list);
        if (list.length) setActive(list[0]);
      })
      .catch((err) => console.log("contacts error:", err))
      .finally(() => setLoading(false));
  }, []);

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
    iso ? new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div style={{ width: "100%", margin: "0 auto", padding: "0" }}>

              {/* Header */}
              <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 32, fontWeight: 800, margin: 0, color: "#17151F" }}>Messages</h1>
                <p style={{ color: "#5D5A6B", fontSize: 15, marginTop: 4 }}>Reply to parents of your students</p>
              </div>

              {loading ? (
                <div style={{ padding: 60, textAlign: "center", color: "#5D5A6B" }}>Loading…</div>
              ) : contacts.length === 0 ? (
                <div style={{ background: "#fff", border: "1px solid #E7E7EC", borderRadius: 16, padding: 60, textAlign: "center", color: "#5D5A6B" }}>
                  No parents yet. Parents appear once their children are linked to a parent account.
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 380px) minmax(0, 1fr)", gap: 20, height: "calc(100vh - 220px)", alignItems: "stretch" }}>

                  {/* Contacts */}
                  <div style={{ background: "#fff", border: "1px solid #E7E7EC", borderRadius: 16, padding: 24, height: "100%", overflowY: "auto" }}>
                    <h3 style={{ fontSize: 17, fontWeight: 700, marginBottom: 18, color: "#17151F" }}>Parents</h3>
                    {contacts.map((c) => (
                      <div
                        key={c.id}
                        onClick={() => setActive(c)}
                        style={{
                          display: "flex", alignItems: "center", gap: 12,
                          padding: "12px 12px", borderRadius: 12, cursor: "pointer",
                          marginBottom: 4,
                          background: active?.id === c.id ? "#eef4ff" : "transparent",
                          transition: "background 0.15s",
                        }}
                      >
                        <div style={{
                          width: 42, height: 42, borderRadius: "50%", flexShrink: 0,
                          background: "#4B32C3", color: "#fff", fontSize: 15, fontWeight: 700,
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                          {initials(c.username)}
                        </div>
                        <div>
                          <div style={{ fontSize: 15, fontWeight: 600, color: "#17151F" }}>{c.username}</div>
                          <div style={{ fontSize: 14, color: "#5D5A6B", marginTop: 1 }}>{c.subject}</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Chat */}
                  <div style={{ background: "#fff", border: "1px solid #E7E7EC", borderRadius: 16, padding: 24, height: "100%", display: "flex", flexDirection: "column" }}>
                    <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 18, color: "#17151F", borderBottom: "1px solid #ECECF0", paddingBottom: 16 }}>
                      {active ? active.username : "Select a parent"}
                    </h3>

                    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 14, overflowY: "auto", paddingRight: 6, marginBottom: 16 }}>
                      {messages.length === 0 ? (
                        <div style={{ color: "#85839A", fontSize: 15, textAlign: "center", marginTop: "auto", marginBottom: "auto" }}>No messages yet.</div>
                      ) : (
                        messages.map((m) => {
                          const mine = m.sender === user.id || m.sender_name === user.username;
                          return (
                            <div key={m.id} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "75%" }}>
                              <div style={{ fontSize: 13, color: "#85839A", marginBottom: 5, textAlign: mine ? "right" : "left" }}>
                                {mine ? "You" : m.sender_name} · {fmt(m.created_at)}
                              </div>
                              <div style={{
                                padding: "12px 16px", borderRadius: 14, fontSize: 15, lineHeight: 1.55,
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
                      <div style={{ display: "flex", gap: 10 }}>
                        <input
                          type="text"
                          value={text}
                          placeholder="Type a reply…"
                          onChange={(e) => setText(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && send()}
                          style={{ flex: 1, border: "1px solid #E7E7EC", borderRadius: 12, padding: "13px 16px", fontSize: 15, background: "#F6F6F8", outline: "none" }}
                        />
                        <button
                          onClick={send}
                          style={{ background: "#4B32C3", color: "#fff", border: "none", borderRadius: 12, padding: "0 28px", fontSize: 15, fontWeight: 600, cursor: "pointer" }}
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