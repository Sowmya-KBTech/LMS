// frontend/src/features/mentoring/StudentMyMentor.jsx
import { useCallback, useEffect, useRef, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import StudentChangeRequest from "./StudentChangeRequest";

import {
  errorText,
  getAnnouncements,
  getMyMentor,
  getThread,
  prettyYear,
  sendMessage,
  when,
  yearLabel,
} from "./studentApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

const TABS = [
  { key: "mentor", label: "My Mentor" },
  { key: "change", label: "Request a Change" },
  { key: "messages", label: "Messages" },
  { key: "announcements", label: "Announcements" },
  { key: "help", label: "Help" },
];

export default function StudentMyMentor() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("mentor");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  const [thread, setThread] = useState(null);
  const [draft, setDraft] = useState("");
  const [anns, setAnns] = useState(null);
  const bottomRef = useRef(null);

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3000);
  };

  // ================= LOAD =================
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getMyMentor());
    } catch (err) {
      setError(errorText(err, "Could not load your mentor."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (tab !== "messages" || !data?.has_mentor) return;
    getThread()
      .then((t) => {
        setThread(t);
        setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 60);
      })
      .catch((err) => flash(errorText(err, "Could not open the conversation.")));
  }, [tab, data]);

  useEffect(() => {
    if (tab !== "announcements" || !data?.has_mentor) return;
    getAnnouncements().then(setAnns).catch(() => setAnns({ count: 0, results: [] }));
  }, [tab, data]);

  const doSend = async () => {
    const text = draft.trim();
    if (!text) { flash("Nothing to send."); return; }
    setBusy(true);
    try {
      const m = await sendMessage(text);
      setThread((t) => ({ ...t, messages: [...t.messages, m] }));
      setDraft("");
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 60);
    } catch (err) {
      flash(errorText(err, "Could not send."));
    } finally {
      setBusy(false);
    }
  };

  const p = data?.progress || {};
  const mentor = data?.mentor;
  const advisor = data?.class_advisor;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2 style={{ margin: 0 }}>My Mentor</h2>
              <p>
                Who your mentor is and how to reach them
                {data?.academic_year ? ` · ${prettyYear(data.academic_year)}` : ""}
              </p>
            </div>

            {data?.has_mentor && (
              <div className="ma-toggle" style={{ marginBottom: 16 }}>
                {TABS.map((t) => (
                  <button key={t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>
                    {t.label}
                    {t.key === "announcements" && anns?.unread ? ` (${anns.unread})` : ""}
                  </button>
                ))}
              </div>
            )}

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>{error}
              </div>
            )}

            {loading && <div className="ma-panel"><div className="ma-empty">Loading…</div></div>}

            {/* ================= NO MENTOR ================= */}
            {!loading && data && !data.has_mentor && (
              <>
                <div className="ma-panel" style={{ maxWidth: 620 }}>
                  <div className="ma-panel-body" style={{ textAlign: "center", padding: "44px 28px" }}>
                    <div style={{ fontSize: 30, opacity: 0.3, marginBottom: 12 }}>◉</div>
                    <b style={{ fontSize: 16, display: "block", marginBottom: 8 }}>
                      No mentor has been assigned yet
                    </b>
                    <p style={{ fontSize: 13, color: "#6b7280", maxWidth: 420, margin: "0 auto 16px" }}>
                      {data.message}
                    </p>
                    {advisor?.email && (
                      <button
                        className="ma-btn primary"
                        onClick={() => { window.location.href = `mailto:${advisor.email}`; }}
                      >
                        Email {advisor.name}
                      </button>
                    )}
                  </div>
                </div>

                <div className="ma-panel" style={{ marginTop: 16, maxWidth: 620 }}>
                  <div className="ma-panel-head"><div><h3>My progress</h3><p>Read-only</p></div></div>
                  <div className="ma-panel-body">
                    <ProgressGrid p={p} />
                  </div>
                </div>
              </>
            )}

            {/* ================= MY MENTOR ================= */}
            {!loading && data?.has_mentor && tab === "mentor" && (
              <>
                <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
                  <div className="ma-panel" style={{ flex: "1 1 340px" }}>
                    <div className="ma-panel-body">
                      <div style={{ display: "flex", alignItems: "center", gap: 15 }}>
                        <div className="ma-avatar" style={{ width: 62, height: 62, borderRadius: "50%", fontSize: 19 }}>
                          {mentor.name.split(" ").map((x) => x[0]).join("").slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <h2 style={{ margin: 0, fontSize: 21, fontWeight: 700 }}>{mentor.name}</h2>
                          <div style={{ fontSize: 12.5, color: "#6b7280" }}>
                            {mentor.designation || "Teacher"} · {mentor.department}
                          </div>
                        </div>
                      </div>

                      <table className="ma-table" style={{ marginTop: 14 }}><tbody>
                        <tr><td style={{ color: "#6b7280" }}>Mentor name</td><td><b>{mentor.name}</b></td></tr>
                        <tr><td style={{ color: "#6b7280" }}>Employee ID</td><td><b>{mentor.employee_id || "—"}</b></td></tr>
                        <tr><td style={{ color: "#6b7280" }}>Designation</td><td><b>{mentor.designation || "—"}</b></td></tr>
                        <tr><td style={{ color: "#6b7280" }}>Department</td><td><b>{mentor.department}</b></td></tr>
                        <tr><td style={{ color: "#6b7280" }}>Email</td><td><b>{mentor.email || "—"}</b></td></tr>
                        <tr><td style={{ color: "#6b7280" }}>Academic year</td><td><b>{prettyYear(data.academic_year)}</b></td></tr>
                        <tr><td style={{ color: "#6b7280" }}>Assigned since</td><td><b>{data.assigned_on}</b></td></tr>
                      </tbody></table>
                    </div>
                    <div className="ma-panel-foot">
                      Assigned by the HOD. If any of this is wrong, tell your class advisor.
                    </div>
                  </div>

                  <div style={{ flex: "1 1 300px" }}>
                    <div className="ma-panel">
                      <div className="ma-panel-head"><div><h3>Quick actions</h3></div></div>
                      <div className="ma-panel-body">
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                          <button className="ma-cap" style={{ textAlign: "left" }} onClick={() => setTab("messages")}>
                            <div style={{ fontSize: 17, marginBottom: 6 }}>💬</div>
                            <b style={{ fontSize: 13.5 }}>Message my mentor</b>
                            <div className="ma-small">Private conversation</div>
                          </button>
                          <button className="ma-cap" style={{ textAlign: "left" }} onClick={() => setTab("announcements")}>
                            <div style={{ fontSize: 17, marginBottom: 6 }}>📢</div>
                            <b style={{ fontSize: 13.5 }}>Announcements</b>
                            <div className="ma-small">
                              {anns?.unread ? `${anns.unread} unread` : "Messages to your group"}
                            </div>
                          </button>
                          <button
                            className="ma-cap" style={{ textAlign: "left" }}
                            onClick={() => {
                              if (!mentor.email) { flash("No email on record."); return; }
                              // mailto: only works when the OS has a default mail app.
                              // Copy the address too, so the button always does something.
                              navigator.clipboard?.writeText(mentor.email);
                              flash(`Copied ${mentor.email}`);
                              window.location.href = `mailto:${mentor.email}`;
                            }}
                          >
                            <div style={{ fontSize: 17, marginBottom: 6 }}>✉</div>
                            <b style={{ fontSize: 13.5 }}>Email address</b>
                            <div className="ma-small">
                              {mentor.email ? "Tap to copy" : "Not on record"}
                            </div>
                          </button>
                          <button className="ma-cap" style={{ textAlign: "left" }} onClick={() => setTab("help")}>
                            <div style={{ fontSize: 17, marginBottom: 6 }}>?</div>
                            <b style={{ fontSize: 13.5 }}>Help</b>
                            <div className="ma-small">How this works</div>
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="ma-panel" style={{ marginTop: 16 }}>
                      <div className="ma-panel-head"><div><h3>How to reach your mentor</h3></div></div>
                      <div className="ma-panel-body">
                        <div className="ma-note blue">
                          <b>Messages are the fastest route</b>
                          Your mentor may not reply immediately.
                        </div>
                        <div className="ma-note" style={{ marginTop: 10 }}>
                          <b>For attendance or leave</b>
                          Go to your class advisor
                          {advisor?.name ? `, ${advisor.name}` : ""} — not your mentor.
                          On-duty and leave letters are handled there.
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="ma-panel" style={{ marginTop: 16 }}>
                  <div className="ma-panel-head">
                    <div><h3>My progress</h3><p>The same figures your mentor sees</p></div>
                    <div style={{ flex: 1 }} />
                    <span className="ma-pill ma-grey">Read-only</span>
                  </div>
                  <div className="ma-panel-body">
                    <ProgressGrid p={p} />
                    <div className="ma-note" style={{ marginTop: 14 }}>
                      These come from the attendance and results modules. Nothing here is
                      set by your mentor.
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* ================= MESSAGES ================= */}
            {!loading && data?.has_mentor && tab === "messages" && (
              <>
                <div className="ma-note blue" style={{ marginBottom: 16 }}>
                  <b>This is a private conversation with your mentor</b>
                  Only you and your mentor can see it. Messages are kept on record by the
                  college and cannot be permanently deleted by either of you.
                </div>

                <div className="ma-panel" style={{ maxWidth: 840 }}>
                  {!thread && <div className="ma-empty">Loading…</div>}
                  {thread && (
                    <>
                      <div className="ma-panel-head">
                        <div className="ma-avatar" style={{ width: 38, height: 38, borderRadius: "50%", fontSize: 12 }}>
                          {thread.mentor.name.split(" ").map((x) => x[0]).join("").slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <h3 style={{ margin: 0 }}>{thread.mentor.name}</h3>
                          <p>{thread.mentor.designation || "Your mentor"}</p>
                        </div>
                        <div style={{ flex: 1 }} />
                        <button className="ma-btn small" onClick={() => setTab("mentor")}>
                          Mentor details
                        </button>
                      </div>

                      <div className="msgs">
                        {thread.messages.length === 0 && (
                          <div className="ma-empty">No messages yet. Say hello.</div>
                        )}
                        {thread.messages.map((m) => (
                          <div key={m.id} className={`msg ${m.from_me ? "me" : "them"}`}>
                            <div className="bub">
                              {m.text}
                              <span className="tm">{when(m.created_at)}</span>
                            </div>
                          </div>
                        ))}
                        <div ref={bottomRef} />
                      </div>

                      <div className="composer">
                        <textarea
                          value={draft}
                          placeholder="Write a message…"
                          onChange={(e) => setDraft(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
                          }}
                        />
                        <button className="ma-btn primary" onClick={doSend} disabled={busy}>Send</button>
                      </div>
                      <div className="ma-panel-foot">
                        For anything urgent, speak to your class advisor.
                      </div>
                    </>
                  )}
                </div>
              </>
            )}

            {/* ================= ANNOUNCEMENTS ================= */}
            {!loading && data?.has_mentor && tab === "announcements" && (
              <>
                <div className="ma-note blue" style={{ marginBottom: 16 }}>
                  <b>Read-only</b>
                  Your mentor sends these to several students at once. You cannot reply
                  here and other students cannot see that you read it. To say something,
                  send a private message instead.
                </div>

                <div className="ma-panel" style={{ maxWidth: 840 }}>
                  <div className="ma-panel-head">
                    <div>
                      <h3>Announcements from {anns?.mentor_name || "your mentor"}</h3>
                      <p>{anns ? `${anns.count} announcement${anns.count === 1 ? "" : "s"}` : "Loading…"}</p>
                    </div>
                  </div>
                  <div className="ma-panel-body">
                    {!anns && <div className="ma-empty">Loading…</div>}
                    {anns?.results.length === 0 && (
                      <div className="ma-empty">
                        Your mentor has not sent any group announcements yet.
                      </div>
                    )}
                    {anns?.results.map((a) => (
                      <div
                        key={a.id}
                        style={{
                          border: "1px solid #e6e9ef",
                          borderLeft: a.is_read ? "1px solid #e6e9ef" : "3px solid #2563eb",
                          borderRadius: 11,
                          padding: "15px 17px",
                          marginBottom: 12,
                          background: a.is_read ? "#fff" : "#fbfdff",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8 }}>
                          {!a.is_read && <span className="ma-pill ma-red">New</span>}
                          <div style={{ flex: 1 }} />
                          <span style={{ fontSize: 11.5, color: "#9ca3af" }}>{when(a.created_at)}</span>
                        </div>
                        <p style={{ margin: 0, fontSize: 13.6, lineHeight: 1.6 }}>{a.text}</p>
                        <div style={{
                          marginTop: 10, paddingTop: 9, borderTop: "1px solid #f0f2f6",
                          fontSize: 11.5, color: "#9ca3af",
                        }}>
                          From {anns.mentor_name} · sent to {a.recipients} students ·
                          you cannot reply to a group message
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* ================= REQUEST A CHANGE ================= */}
            {!loading && data?.has_mentor && tab === "change" && (
              <StudentChangeRequest />
            )}

            {/* ================= HELP ================= */}
            {!loading && data?.has_mentor && tab === "help" && (
              <>
                <div className="ma-panel" style={{ maxWidth: 840 }}>
                  <div className="ma-panel-head">
                    <div>
                      <h3>What your mentor can see about you</h3>
                      <p>Nothing more than this</p>
                    </div>
                  </div>
                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead><tr><th>Item</th><th>Your mentor</th></tr></thead>
                      <tbody>
                        <tr><td>Name, register number, year</td><td><span className="ma-pill ma-green">Yes</span></td></tr>
                        <tr><td>Email</td><td><span className="ma-pill ma-green">Yes</span></td></tr>
                        <tr><td>Attendance percentage</td><td><span className="ma-pill ma-green">Yes</span></td></tr>
                        <tr><td>CGPA and published results</td><td><span className="ma-pill ma-green">Yes</span></td></tr>
                        <tr><td>Your messages to other staff</td><td><span className="ma-pill ma-red">No</span></td></tr>
                        <tr><td>Your fee or family details</td><td><span className="ma-pill ma-red">No</span></td></tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="ma-panel-foot">
                    Your mentor sees the same figures you see on this page. Nothing extra.
                  </div>
                </div>

                <div className="ma-panel" style={{ marginTop: 16, maxWidth: 840 }}>
                  <div className="ma-panel-head"><div><h3>Common questions</h3></div></div>
                  <div className="ma-panel-body">
                    <div className="ma-note">
                      <b>Who assigned my mentor?</b>
                      The HOD, at the start of the academic year. Mentors are reassigned each year.
                    </div>
                    <div className="ma-note" style={{ marginTop: 10 }}>
                      <b>Can I message any teacher here?</b>
                      No. This page connects you to your mentor only. Use the normal
                      Messages module for other staff.
                    </div>
                    <div className="ma-note" style={{ marginTop: 10 }}>
                      <b>Can I reply to an announcement?</b>
                      No. Group announcements are one-way. Send a private message instead.
                    </div>
                    <div className="ma-note" style={{ marginTop: 10 }}>
                      <b>Who handles attendance and leave?</b>
                      Your class advisor{advisor?.name ? `, ${advisor.name}` : ""} — not
                      your mentor. On-duty and leave letters go there.
                    </div>
                    <div className="ma-note" style={{ marginTop: 10 }}>
                      <b>My mentor is not replying. What do I do?</b>
                      Wait two working days, then speak to your class advisor.
                    </div>
                    <div className="ma-note amber" style={{ marginTop: 10 }}>
                      <b>⚠ If something is urgent or serious</b>
                      For anything to do with your safety or wellbeing, contact your class
                      advisor or the HOD directly. Do not wait for a message reply.
                    </div>
                  </div>
                </div>
              </>
            )}

          </div>
        </div>
      </div>
      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );
}

// ================= PROGRESS CARDS =================
function ProgressGrid({ p }) {
  return (
    <div className="ma-cards">
      <div className="ma-card">
        <div className="l">Attendance</div>
        <div className={`n ${p.attendance == null ? "" : p.attendance >= 75 ? "green" : "red"}`}>
          {p.attendance == null ? "—" : `${p.attendance}%`}
        </div>
        <div className="d">Requirement 75%</div>
      </div>
      <div className="ma-card">
        <div className="l">CGPA</div>
        <div className="n">{p.cgpa == null ? "—" : p.cgpa}</div>
        <div className="d">out of 10</div>
      </div>
      <div className="ma-card">
        <div className="l">Backlogs</div>
        <div className={`n ${p.backlogs ? "amber" : "green"}`}>{p.backlogs ?? "—"}</div>
        <div className="d">{p.backlogs ? "Arrears to clear" : "None"}</div>
      </div>
      <div className="ma-card">
        <div className="l">Published Semesters</div>
        <div className="n">{p.semesters_published ?? "—"}</div>
        <div className="d">Results released so far</div>
      </div>
    </div>
  );
}