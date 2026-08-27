// frontend/src/features/classgroups/ClassPrivate.jsx
import { useCallback, useEffect, useRef, useState } from "react";

import {
  errorText,
  fileSize,
  getPrivateThread,
  getStudents,
  initials,
  sendPrivateMessage,
  when,
} from "./classGroupsApi";

const MAX_UPLOAD = 10 * 1024 * 1024; // 10 MB — matches the server

/**
 * Private 1-to-1 conversations, living inside the class group.
 *
 * Staff  (isOwner) — the students of the class they advise, one thread each.
 * Student          — their class advisor, a single thread.
 *
 * This is NOT the mentor conversation. The server tags every message written
 * here as context="advisor", and the mentor thread is read only by My Mentees
 * / My Mentor. A teacher who is both gets two separate histories on purpose.
 */
export default function ClassPrivate({ isOwner, groupId, advisor }) {
  const [contacts, setContacts] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [q, setQ] = useState("");

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const endRef = useRef(null);
  const fileRef = useRef(null);

  const me = JSON.parse(localStorage.getItem("user") || "{}");

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3000);
  };

  // ================= CONTACTS =================
  // Names come from the class group itself, not from chat/contacts/ — that
  // endpoint is the parent inbox and deliberately lists no students.
  useEffect(() => {
    let alive = true;

    // A student has exactly one contact: their class advisor, already in the
    // group payload. No lookup needed.
    if (!isOwner) {
      const one = advisor
        ? [{
            id: advisor.id,
            username: advisor.name,
            roll_number: "",
            subject: "Class advisor",
          }]
        : [];
      setContacts(one);
      if (one.length) setActive(one[0]);
      setLoading(false);
      return () => { alive = false; };
    }

    getStudents(groupId)
      .then((d) => {
        if (!alive) return;
        const rows = (d.results || d || []).map((s) => ({
          id: s.id,
          username: s.name,
          roll_number: s.roll_number || "",
          subject: s.semester ? `Semester ${s.semester}` : "",
          unread: 0,
        }));
        setContacts(rows);
        if (rows.length) setActive(rows[0]);
      })
      .catch((err) => {
        if (alive) setError(errorText(err, "Could not load the class list."));
      })
      .finally(() => alive && setLoading(false));

    return () => { alive = false; };
  }, [isOwner, groupId, advisor]);

  // ================= THREAD =================
  const fetchThread = useCallback(async (id) => {
    try {
      setMessages(await getPrivateThread(id));
    } catch (err) {
      flash(errorText(err, "Could not open that conversation."));
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    fetchThread(active.id);
    const t = setInterval(() => fetchThread(active.id), 8000);
    return () => clearInterval(t);
  }, [active, fetchThread]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // switching person clears a half-written message and any picked file
  useEffect(() => {
    setText("");
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  }, [active]);

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > MAX_UPLOAD) {
      flash("That file is over 10 MB.");
      e.target.value = "";
      return;
    }
    setFile(f);
  };

  const clearFile = () => {
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const send = async () => {
    const body = text.trim();
    if ((!body && !file) || !active) return;
    setBusy(true);
    try {
      await sendPrivateMessage(active.id, { text: body, file });
      setText("");
      clearFile();
      fetchThread(active.id);
    } catch (err) {
      flash(errorText(err, "Could not send."));
    } finally {
      setBusy(false);
    }
  };

  const shown = q
    ? contacts.filter(
        (c) =>
          c.username.toLowerCase().includes(q.toLowerCase()) ||
          (c.roll_number || "").toLowerCase().includes(q.toLowerCase())
      )
    : contacts;

  // nothing to send = the button is off. Kept as one value so the label,
  // the colour and the cursor can never disagree with each other.
  const nothingToSend = !text.trim() && !file;
  const sendOff = busy || nothingToSend;

  // ================= RENDER =================
  if (loading) {
    return <div className="cg-card"><div className="cg-aud">Loading…</div></div>;
  }
  if (error) {
    return <div className="cg-lock"><b>Could not load</b>{error}</div>;
  }

  if (!contacts.length) {
    return (
      <div className="cg-card">
        <div className="cg-aud">
          {isOwner
            ? "Nobody to message. This tab lists the students of the class you advise."
            : "Your class has no class advisor assigned yet, so there is nobody to message here."}
        </div>
      </div>
    );
  }

  return (
    <>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: isOwner ? "300px 1fr" : "1fr",
          gap: 18,
          alignItems: "start",
        }}
      >
        {/* -------- who -------- */}
        {isOwner && (
          <div className="cg-card" style={{ overflow: "hidden" }}>
            <div style={{ padding: 12, borderBottom: "1px solid #e6e9ef" }}>
              <input
                placeholder="Search name or register number"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                style={{
                  width: "100%", padding: "9px 11px", borderRadius: 8,
                  border: "1px solid #e6e9ef", font: "inherit", fontSize: 13,
                }}
              />
            </div>

            {shown.length === 0 && (
              <div className="cg-aud">No name matches.</div>
            )}

            {shown.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setActive(c)}
                style={{
                  display: "flex", alignItems: "center", gap: 11, width: "100%",
                  padding: "12px 14px", border: 0, textAlign: "left",
                  borderBottom: "1px solid #f3f5f9", cursor: "pointer",
                  background: active?.id === c.id ? "#eef4ff" : "transparent",
                }}
              >
                <span
                  style={{
                    width: 34, height: 34, borderRadius: "50%", flex: "none",
                    display: "grid", placeItems: "center", fontSize: 12,
                    fontWeight: 700, background: "#e8eefc", color: "#1d4ed8",
                  }}
                >
                  {initials(c.username)}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: "block", fontSize: 13.5, fontWeight: 600 }}>
                    {c.username}
                  </span>
                  <span style={{ display: "block", fontSize: 11.5, color: "#6b7280" }}>
                    {c.roll_number || "—"}
                  </span>
                </span>
                {c.unread > 0 && (
                  <span
                    style={{
                      marginLeft: "auto", background: "#dc2626", color: "#fff",
                      fontSize: 10, fontWeight: 700, borderRadius: 9, padding: "1px 6px",
                    }}
                  >
                    {c.unread}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* -------- thread -------- */}
        <div className="cg-card" style={{ display: "flex", flexDirection: "column", minHeight: 480 }}>
          {active && (
            <div
              style={{
                display: "flex", gap: 12, alignItems: "center",
                padding: "14px 17px", borderBottom: "1px solid #e6e9ef",
              }}
            >
              <span
                style={{
                  width: 38, height: 38, borderRadius: "50%", display: "grid",
                  placeItems: "center", fontSize: 13, fontWeight: 700,
                  background: "#e8eefc", color: "#1d4ed8",
                }}
              >
                {initials(active.username)}
              </span>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15.5 }}>{active.username}</div>
                <div style={{ fontSize: 12.5, color: "#6b7280" }}>
                  {active.roll_number ? `${active.roll_number} · ` : ""}
                  {active.subject}
                </div>
              </div>
            </div>
          )}

          <div
            className="cg-msgs"
            style={{
              flex: 1, padding: 18, display: "flex", flexDirection: "column",
              gap: 12, overflowY: "auto",
            }}
          >
            {messages.length === 0 && (
              <div style={{ textAlign: "center", color: "#6b7280", fontSize: 13, padding: 40 }}>
                <b style={{ display: "block", color: "#16233f", marginBottom: 6 }}>
                  No messages yet
                </b>
                {isOwner
                  ? `Write the first one below. ${active?.username} sees it under their class advisor, not in the class conversation.`
                  : "Write the first one below. Only your class advisor sees it."}
              </div>
            )}

            {messages.map((m) => {
              const mine = m.sender === me.id || m.sender_name === me.username;
              return (
                <div
                  key={m.id}
                  style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "72%" }}
                >
                  <div
                    style={{
                      fontSize: 11.5, color: "#9ca3af", marginBottom: 4,
                      textAlign: mine ? "right" : "left",
                    }}
                  >
                    {mine ? "You" : m.sender_name} · {when(m.created_at)}
                  </div>
                  <div
                    style={{
                      padding: "10px 13px", borderRadius: 12, fontSize: 13.5,
                      lineHeight: 1.5,
                      background: mine ? "#2563eb" : "#f1f5f9",
                      color: mine ? "#fff" : "#1a1d2e",
                    }}
                  >
                    {m.text}

                    {m.attachment_url && (
                      <a
                        href={m.attachment_url}
                        target="_blank"
                        rel="noreferrer"
                        download
                        style={{
                          display: "flex", alignItems: "center", gap: 8,
                          marginTop: m.text ? 8 : 0, padding: "8px 10px",
                          borderRadius: 8, textDecoration: "none",
                          background: mine ? "rgba(255,255,255,.18)" : "#fff",
                          border: mine ? "none" : "1px solid #e6e9ef",
                          color: mine ? "#fff" : "#1d4ed8",
                        }}
                      >
                        <span>📎</span>
                        <span style={{ minWidth: 0 }}>
                          <span
                            style={{
                              display: "block", fontSize: 13, fontWeight: 600,
                              overflow: "hidden", textOverflow: "ellipsis",
                              whiteSpace: "nowrap", maxWidth: 220,
                            }}
                          >
                            {m.attachment_name}
                          </span>
                          <span style={{ fontSize: 11, opacity: 0.8 }}>
                            {fileSize(m.attachment_size)}
                          </span>
                        </span>
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={endRef} />
          </div>

          {/* -------- composer -------- */}
          {active && (
            <div style={{ borderTop: "1px solid #e6e9ef", background: "#fff" }}>
              {file && (
                <div
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "10px 17px 0", fontSize: 12.5, color: "#374151",
                  }}
                >
                  <span>📎</span>
                  <span style={{ fontWeight: 600 }}>{file.name}</span>
                  <span style={{ color: "#6b7280" }}>{fileSize(file.size)}</span>
                  <button
                    type="button"
                    onClick={clearFile}
                    style={{
                      marginLeft: 4, border: 0, background: "none",
                      color: "#dc2626", cursor: "pointer", fontSize: 12.5,
                    }}
                  >
                    Remove
                  </button>
                </div>
              )}

              <div
                style={{
                  display: "flex", gap: 10, padding: "13px 17px",
                  alignItems: "flex-end",
                }}
              >
                <input ref={fileRef} type="file" hidden onChange={pickFile} />

                {/* attach — bordered square so it reads as a control, not an icon */}
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  title="Attach a file · 10 MB max"
                  style={{
                    height: 44,
                    width: 48,
                    flex: "none",
                    borderRadius: 9,
                    border: "1px solid #cbd5e1",
                    background: "#f8fafc",
                    color: "#334155",
                    fontSize: 18,
                    lineHeight: 1,
                    padding: 0,
                    cursor: "pointer",
                    textDecoration: "none",
                    display: "grid",
                    placeItems: "center",
                  }}
                >
                  📎
                </button>

                <textarea
                  value={text}
                  placeholder={
                    isOwner
                      ? `Write privately to ${active.username}…`
                      : "Write to your class advisor…"
                  }
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  style={{
                    flex: 1, border: "1px solid #cbd5e1", borderRadius: 9,
                    padding: "11px 12px", font: "inherit", fontSize: 13.5,
                    height: 44, minHeight: 44, maxHeight: 140, resize: "vertical",
                  }}
                />

                {/* send — solid blue when there is something to send, clearly
                    greyed when there is not. The disabled colour is grey rather
                    than pale blue: a washed-out blue reads as a broken button. */}
                <button
                  type="button"
                  onClick={send}
                  disabled={sendOff}
                  style={{
                    height: 44,
                    padding: "0 30px",
                    flex: "none",
                    borderRadius: 9,
                    border: "none",
                    outline: "none",
                    background: sendOff ? "#e2e8f0" : "#2563eb",
                    color: sendOff ? "#94a3b8" : "#ffffff",
                    fontSize: 15,
                    fontWeight: 700,
                    fontFamily: "inherit",
                    letterSpacing: ".2px",
                    lineHeight: 1,
                    textDecoration: "none",
                    textTransform: "none",
                    cursor: sendOff ? "not-allowed" : "pointer",
                    boxShadow: sendOff ? "none" : "0 1px 3px rgba(37,99,235,.35)",
                  }}
                >
                  {busy ? "Sending…" : "Send"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {toast && <div className="ma-toast">{toast}</div>}
    </>
  );
}