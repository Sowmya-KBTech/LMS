// frontend/src/features/classgroups/ClassGroups.jsx
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import ClassPrivate from "./ClassPrivate";

import {
  dayLabel,
  deleteMessage,
  errorText,
  getFiles,
  getGroup,
  getMessages,
  getMyGroups,
  getSettings,
  getStudents,
  initials,
  saveSettings,
  sendMessage,
  togglePin,
  when,
} from "./classGroupsApi";

import "../../App.css";
import "../../styles/ClassGroups.css";

/**
 * One component for both roles. The API returns my_role per group, so the
 * teacher and student views differ by what the server says, not by a prop.
 */
export default function ClassGroups() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  // ================= ROUTING INSIDE THE PAGE =================
  // "groups" | "overview" | "conv" | "students" | "files" | "settings"
  const [view, setView] = useState("groups");
  const [groupId, setGroupId] = useState(null);

  // ================= DATA =================
  const [groups, setGroups] = useState({ class_groups: [], subject_groups: [] });
  const [group, setGroup] = useState(null);
  const [messages, setMessages] = useState([]);
  const [convMeta, setConvMeta] = useState({ can_post: true, blocked_reason: null });
  const [students, setStudents] = useState([]);
  const [files, setFiles] = useState([]);
  const [settings, setSettings] = useState(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  // ================= COMPOSER =================
  const [draft, setDraft] = useState("");
  const [annMode, setAnnMode] = useState(false);
  const [annTitle, setAnnTitle] = useState("");
  const [annPin, setAnnPin] = useState(false);
  const [file, setFile] = useState(null);
  const fileRef = useRef(null);
  const bottomRef = useRef(null);

  // ================= VOICE NOTE =================
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [micError, setMicError] = useState("");
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  // a voice note is capped so one long recording cannot fill the 10 MB limit
  const MAX_SECONDS = 300;

  // ================= FILTERS =================
  const [fileKind, setFileKind] = useState("all");
  const [studentQ, setStudentQ] = useState("");
  const [annOnly, setAnnOnly] = useState(false);

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3000);
  };

  // stop the microphone track, or the browser keeps the recording indicator on
  const releaseMic = () => {
    clearInterval(timerRef.current);
    const r = recorderRef.current;
    if (r?.stream) r.stream.getTracks().forEach((t) => t.stop());
    recorderRef.current = null;
  };

  const startRecording = async () => {
    setMicError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setMicError("This browser cannot record audio. Attach a file instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        const ext = (rec.mimeType || "audio/webm").includes("mp4") ? "m4a" : "webm";
        const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
        setFile(new File([blob], `voice-note-${stamp}.${ext}`, { type: blob.type }));
        releaseMic();
      };
      recorderRef.current = rec;
      rec.start();
      setRecording(true);
      setSeconds(0);
      timerRef.current = setInterval(
        () => setSeconds((n) => {
          if (n + 1 >= MAX_SECONDS) stopRecording();
          return n + 1;
        }),
        1000
      );
    } catch {
      // permission denied, or no microphone on the machine
      setMicError(
        "Could not use the microphone. Allow access in your browser, then try again."
      );
    }
  };

  const stopRecording = () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setRecording(false);
    clearInterval(timerRef.current);
  };

  const cancelRecording = () => {
    const r = recorderRef.current;
    if (r) r.onstop = releaseMic;      // drop the blob instead of attaching it
    if (r?.state === "recording") r.stop();
    setRecording(false);
    setSeconds(0);
  };

  // never leave the mic open if the page unmounts mid-recording
  useEffect(() => () => releaseMic(), []);

  const clock = (n) =>
    `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;

  const isAudio = (name) => /\.(webm|m4a|mp3|ogg|wav)$/i.test(name || "");

  // ================= LOAD: MY GROUPS =================
  const loadGroups = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setGroups(await getMyGroups());
    } catch (err) {
      setError(errorText(err, "Could not load your groups."));
      setGroups({ class_groups: [], subject_groups: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === "groups") loadGroups();
  }, [view, loadGroups]);

  // ================= LOAD: ONE GROUP =================
  const openGroup = async (id, target = "overview") => {
    setGroupId(id);
    setView(target);
    setGroup(null);
    try {
      setGroup(await getGroup(id));
    } catch (err) {
      flash(errorText(err, "Could not open that group."));
      setView("groups");
    }
  };

  useEffect(() => {
    if (!groupId || view !== "conv") return;
    setMessages([]);
    getMessages(groupId, annOnly ? { type: "announcement" } : {})
      .then((d) => {
        setMessages(d.results || []);
        setConvMeta({ can_post: d.can_post, blocked_reason: d.blocked_reason });
        setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 80);
      })
      .catch((err) => flash(errorText(err, "Could not load the conversation.")));
  }, [groupId, view, annOnly]);

  useEffect(() => {
    if (!groupId || view !== "students") return;
    getStudents(groupId, { q: studentQ })
      .then((d) => setStudents(d.results || []))
      .catch(() => setStudents([]));
  }, [groupId, view, studentQ]);

  useEffect(() => {
    if (view !== "files") return;
    getFiles({ kind: fileKind })
      .then((d) => setFiles(d.results || []))
      .catch(() => setFiles([]));
  }, [view, fileKind]);

  useEffect(() => {
    if (!groupId || view !== "settings") return;
    getSettings(groupId).then(setSettings).catch(() => setSettings(null));
  }, [groupId, view]);

  // ================= ACTIONS =================
  const doSend = async () => {
    const text = draft.trim();
    if (!text && !file) {
      flash("Write something or attach a file.");
      return;
    }
    if (annMode && !annTitle.trim()) {
      flash("An announcement needs a title.");
      return;
    }
    setBusy(true);
    try {
      const m = await sendMessage(groupId, {
        text,
        title: annMode ? annTitle.trim() : "",
        file,
        isAnnouncement: annMode,
        isPinned: annPin,
      });
      setMessages((prev) => [...prev, m]);
      setDraft("");
      setFile(null);
      setAnnMode(false);
      setAnnTitle("");
      setAnnPin(false);
      if (fileRef.current) fileRef.current.value = "";
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (err) {
      // 409 means the group has no enrolled students — a real state, not a crash
      flash(errorText(err, "Could not send."));
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (m) => {
    const mine = m.from_me;
    if (!window.confirm(mine ? "Delete your message?" : "Remove this message from the class?"))
      return;
    try {
      await deleteMessage(groupId, m.id);
      setMessages((prev) => prev.filter((x) => x.id !== m.id));
      flash("Message removed. The record is kept.");
    } catch (err) {
      flash(errorText(err, "Could not remove."));
    }
  };

  const doPin = async (m) => {
    try {
      const r = await togglePin(groupId, m.id);
      setMessages((prev) =>
        prev.map((x) => (x.id === m.id ? { ...x, is_pinned: r.is_pinned } : x))
      );
    } catch (err) {
      flash(errorText(err, "Could not pin."));
    }
  };

  const doSaveSettings = async () => {
    setBusy(true);
    try {
      setSettings(await saveSettings(groupId, settings));
      flash("Settings saved");
      setGroup(await getGroup(groupId));
    } catch (err) {
      flash(errorText(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  // ================= DERIVED =================
  const isOwner = group?.my_role === "owner";
  const isSubject = group?.kind === "subject";

  /**
   * The teacher can always attach. A student can only when the teacher has
   * allowed it for this group.
   *
   * `can_attach` is computed by the server. The `?? true` fallback keeps the
   * attach button working if the frontend is updated before the backend, when
   * the field would be undefined — attachments are on by default now, and the
   * server rejects the upload anyway if a teacher has switched it off.
   */
  const canAttach = group ? (group.can_attach ?? true) : false;

  const tabs = isSubject
    ? [["conv", "Conversation"], ["files", "Shared files"]]
    : isOwner
    ? [["overview", "Overview"], ["conv", "Conversation"],
       ["private", "Class students"], ["students", "Class list"],
       ["files", "Shared files"], ["settings", "Settings"]]
    : [["overview", "Overview"], ["conv", "Conversation"],
       ["private", "My class advisor"], ["students", "Classmates"],
       ["files", "Shared files"]];

  // ================= SHARED CHROME =================
  const GroupNav = () => (
    <div className="cg-nav">
      <button className="back" onClick={() => setView("groups")}>← All groups</button>
      <div className="cg-tabs">
        {tabs.map(([k, label]) => (
          <button key={k} className={view === k ? "on" : ""} onClick={() => setView(k)}>
            {label}
          </button>
        ))}
      </div>
      <span className="who">
        {group?.name} · {isSubject ? "Subject group" : "Class group"}
      </span>
    </div>
  );

  const Audience = () => (
    <div className={`cg-aud ${isSubject ? "subj" : "cls"}`}>
      <span className="ic">{isSubject ? "📚" : "👥"}</span>
      <div>
        <b>{group.name} · {isSubject ? "Subject group" : "Class group"}</b>
        <span>
          {isSubject
            ? `Audience: ${group.student_count} student${group.student_count === 1 ? "" : "s"} enrolled in this subject.`
            : `Audience: all ${group.student_count} student${group.student_count === 1 ? "" : "s"} in ${group.course_name} Year ${group.year_number}.`}
          {isOwner && isSubject
            ? " Your other classes for this subject do not receive it."
            : ""}
        </span>
      </div>
    </div>
  );

  const GroupCard = ({ g, kind }) => (
    <div
      className={`cg-card ${kind}${g.has_audience ? "" : " warn"}`}
      onClick={() => g.has_audience && openGroup(g.id, kind === "subj" ? "conv" : "overview")}
    >
      <div className="top">
        <div className="av">{g.year_label}</div>
        <div>
          <h4>{g.name}</h4>
          <div className="s">
            {kind === "subj" && g.subject_name && (
              <span className="ma-pill ma-purple">{g.subject_name}</span>
            )}
            {/* only the advisor sees this label; a student's own card should not
                say "Class Advisor" about them */}
            {kind === "cls" && g.my_role === "owner" && (
              <span className="ma-pill ma-blue">Class Advisor</span>
            )}{" "}
            Year {g.year_number} · {g.academic_year.replace("-", "–")}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {g.unread > 0 && <span className="ma-pill ma-red">{g.unread} new</span>}
        {!g.has_audience ? (
          <span className="ma-pill ma-red">No audience</span>
        ) : g.settings.announcement_only ? (
          <span className="ma-pill ma-amber">Announcement only</span>
        ) : (
          <span className="ma-pill ma-green">Active</span>
        )}
      </div>
      <div className="stats">
        <div className="stat">
          <b className={g.has_audience ? "" : "red"}>{g.student_count}</b>
          <span>{kind === "subj" ? "Enrolled" : "Students"}</span>
        </div>
        <div className="stat"><b>{g.message_count}</b><span>Messages</span></div>
        <div className="stat"><b>{g.announcement_count}</b><span>Announcements</span></div>
        <div className="stat"><b>{g.file_count}</b><span>Files</span></div>
      </div>
      <div className={`src${g.has_audience ? "" : " red"}`}>
        {g.has_audience
          ? kind === "subj"
            ? `Audience: ${g.student_count} students enrolled in this subject`
            : `Audience: every student in ${g.course_name} Year ${g.year_number}`
          : "⚠ No enrolment records for this subject. Nothing can be sent until the office enrols students — a message is never sent to the whole year instead."}
      </div>
    </div>
  );

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2 style={{ margin: 0 }}>
                {view === "groups" ? "My Groups" : group?.name || "Loading…"}
              </h2>
              <p>
                {view === "groups"
                  ? "Your class group and your subject groups"
                  : group
                  ? `Year ${group.year_number} · ${group.course_name} · ${group.academic_year.replace("-", "–")}`
                  : ""}
              </p>
            </div>

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>{error}
              </div>
            )}

            {/* ================= MY GROUPS ================= */}
            {view === "groups" && (
              <>
                {loading && <div className="ma-panel"><div className="ma-empty">Loading your groups…</div></div>}

                {!loading && groups.class_groups.length === 0 && groups.subject_groups.length === 0 && (
                  <div className="ma-panel">
                    <div className="ma-empty">
                      <b style={{ display: "block", marginBottom: 6 }}>No groups yet</b>
                      Class groups appear once you are made a class advisor, and subject
                      groups once a subject is allocated to you.
                    </div>
                  </div>
                )}

                {!loading && groups.class_groups.length > 0 && (
                  <>
                    {/* quick tiles belong to the class group, so only show with one */}
                    <div className={`cg-tiles ${groups.class_groups[0].my_role === "owner" ? "" : "three"}`}>
                      <button className="cg-tile" onClick={() => openGroup(groups.class_groups[0].id, "overview")}>
                        <span className="ic i-blue">◉</span>
                        <span><b>Class details</b><span className="d">Course, year, advisor</span></span>
                      </button>
                      <button className="cg-tile" onClick={() => openGroup(groups.class_groups[0].id, "students")}>
                        <span className="ic i-grn">👥</span>
                        <span>
                          <b>{groups.class_groups[0].my_role === "owner" ? "Class list" : "My classmates"}</b>
                          <span className="d">{groups.class_groups[0].student_count} students</span>
                        </span>
                      </button>
                      <button className="cg-tile" onClick={() => { setGroupId(groups.class_groups[0].id); setView("files"); }}>
                        <span className="ic i-pur">📎</span>
                        <span><b>Shared files</b><span className="d">From all your groups</span></span>
                      </button>
                      {groups.class_groups[0].my_role === "owner" && (
                        <button className="cg-tile" onClick={() => openGroup(groups.class_groups[0].id, "settings")}>
                          <span className="ic i-amb">⚙</span>
                          <span><b>Settings</b><span className="d">Who can post</span></span>
                        </button>
                      )}
                    </div>

                    <div className="cg-sec">
                      <span className="ic i-blue">👥</span>
                      <div>
                        <b>{groups.class_groups[0].my_role === "owner" ? "Class groups" : "My class"}</b>
                        <span>
                          {groups.class_groups[0].my_role === "owner"
                            ? "You are the class advisor · everyone in the year"
                            : "General class information from your class advisor"}
                        </span>
                      </div>
                    </div>

                    <div className="grid g2" style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 16 }}>
                      {groups.class_groups.map((g) => <GroupCard key={g.id} g={g} kind="cls" />)}
                    </div>
                  </>
                )}

                {!loading && groups.subject_groups.length > 0 && (
                  <>
                    <div className="cg-sec">
                      <span className="ic i-pur">📚</span>
                      <div>
                        <b>{groups.subject_groups[0].my_role === "owner" ? "Subject groups" : "My subjects"}</b>
                        <span>
                          {groups.subject_groups[0].my_role === "owner"
                            ? "One per class you teach · only the students enrolled"
                            : "One group per subject you are enrolled in"}
                        </span>
                      </div>
                      <div style={{ flex: 1 }} />
                      <span className="ma-pill ma-purple">{groups.subject_groups.length}</span>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 16 }}>
                      {groups.subject_groups.map((g) => <GroupCard key={g.id} g={g} kind="subj" />)}
                    </div>
                  </>
                )}
              </>
            )}

            {/* ================= INSIDE A GROUP ================= */}
            {view !== "groups" && !group && (
              <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
            )}

            {view !== "groups" && group && (
              <>
                <GroupNav />

                {/* ---------- OVERVIEW ---------- */}
                {view === "overview" && (
                  <>
                   <div className="ma-panel cg-ov-head">
                      <div className="ma-panel-body">
                        <div className={`cg-ov-hero ${isSubject ? "subj" : ""}`}>
                          <div className="cg-ov-badge">{group.year_label}</div>
                          <div className="cg-ov-title">
                            <h2>{group.name}</h2>
                            <div className="sub">
                              Year {group.year_number} · {group.course_name} · {group.academic_year.replace("-", "–")}
                            </div>
                          </div>
                          <div className="cg-ov-spacer" />
                          <div className="cg-ov-meta">
                            <div>
                              <span className="k">{isSubject ? "Subject teacher" : "Class advisor"}</span>
                              <span className="v">{group.owner?.name || "—"}</span>
                            </div>
                            <div>
                              <span className="k">Students</span>
                              <span className="v">{group.student_count}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="ma-cards cg-ov-cards">
                      <div className="ma-card">
                        <div className="l">Students</div>
                        <div className="n">{group.student_count}</div>
                        <div className="d">{group.department}</div>
                      </div>
                      <div className="ma-card">
                        <div className="l">Announcements</div>
                        <div className="n amber">{group.announcement_count}</div>
                        <div className="d">In the conversation</div>
                      </div>
                      <div className="ma-card">
                        <div className="l">Attachments</div>
                        <div className="n">{group.file_count}</div>
                        <div className="d">Shared in the conversation</div>
                      </div>
                    </div>

                    <div className="cg-ov-grid">
                      <div className="ma-panel">
                        <div className="ma-panel-head"><div><h3>Class details</h3></div></div>
                        <div className="ma-panel-body">
                          <table className="ma-table"><tbody>
                            <tr><td style={{ color: "#6b7280" }}>Group name</td><td><b>{group.name}</b></td></tr>
                            <tr><td style={{ color: "#6b7280" }}>Course</td><td><b>{group.course_name}</b></td></tr>
                            <tr><td style={{ color: "#6b7280" }}>Year</td><td><b>Year {group.year_number}</b></td></tr>
                            <tr><td style={{ color: "#6b7280" }}>Academic year</td><td><b>{group.academic_year.replace("-", "–")}</b></td></tr>
                            <tr><td style={{ color: "#6b7280" }}>Department</td><td><b>{group.department}</b></td></tr>
                            <tr>
                              <td style={{ color: "#6b7280" }}>{isSubject ? "Subject teacher" : "Class advisor"}</td>
                              <td><b>{group.owner?.name || "—"}</b>{isOwner && <span style={{ fontSize: 11.5, color: "#6b7280" }}> — you</span>}</td>
                            </tr>
                          </tbody></table>
                          <div className="ma-note" style={{ marginTop: 12 }}>
                            Every field here is read from the student records and the
                            allocation. Nothing is typed in twice.
                          </div>
                        </div>
                      </div>

                      <div className="ma-panel">
                        <div className="ma-panel-head">
                          <div><h3>Recent activity</h3></div>
                          <div style={{ flex: 1 }} />
                          <button className="ma-btn" onClick={() => setView("conv")}>Open conversation</button>
                        </div>
                        <div className="ma-panel-body">
                          {(group.recent_activity || []).length === 0 && (
                            <div className="ma-empty">No messages yet.</div>
                          )}
                          {(group.recent_activity || []).map((m) => (
                            <div className="cg-act-row" key={m.id} onClick={() => setView("conv")}>
                              <span className={`ic ${m.message_type === "announcement" ? "i-amb" : m.attachment_url ? "i-pur" : "i-blue"}`}>
                                {m.message_type === "announcement" ? "📢" : m.attachment_url ? "📎" : "💬"}
                              </span>
                              <div>
                                <b>{m.title || m.text || m.attachment_name}</b>
                                <div className="m">
                                  {m.from_me ? "You" : m.sender_name}
                                  {m.attachment_url ? " · with attachment" : ""} · {when(m.created_at)}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {/* ---------- CONVERSATION ---------- */}
                {view === "conv" && (
                  <>
                    <Audience />

                    <div className="ma-panel" style={{ maxWidth: 900 }}>
                      <div className="ma-panel-head">
                        <div className="cg-card" style={{ padding: 0, border: 0 }}>
                          <div className="av" style={{ width: 38, height: 38, fontSize: 12 }}>
                            {initials(group.name)}
                          </div>
                        </div>
                        <div>
                          <h3 style={{ margin: 0 }}>{group.name}</h3>
                          <p>{group.student_count} students · {group.owner?.name}</p>
                        </div>
                        <div style={{ flex: 1 }} />
                        <div className="cg-filt">
                          <button className={annOnly ? "" : "on"} onClick={() => setAnnOnly(false)}>All</button>
                          <button className={annOnly ? "on" : ""} onClick={() => setAnnOnly(true)}>Announcements</button>
                        </div>
                      </div>

                      <div className="cg-msgs">
                        {messages.length === 0 && (
                          <div className="ma-empty">
                            No messages yet.{isOwner ? " Start the conversation with your class." : ""}
                          </div>
                        )}
                        {messages.map((m, i) => {
                          const prev = messages[i - 1];
                          const newDay =
                            !prev ||
                            new Date(prev.created_at).toDateString() !==
                              new Date(m.created_at).toDateString();
                          return (
                            <div key={m.id}>
                              {newDay && <div className="cg-day">{dayLabel(m.created_at)}</div>}
                              <div className={`cg-msg ${m.from_me ? "me" : "them"}`}>
                                <div className={`bub${m.message_type === "announcement" ? " ann" : ""}`}>
                                  {m.message_type === "announcement" && (
                                    <span className="cg-tag">📢 Announcement</span>
                                  )}
                                  {!m.from_me && m.message_type !== "announcement" && (
                                    <b className="who">{m.sender_name}</b>
                                  )}
                                  {m.title && <b className="ttl">{m.title}</b>}
                                  {m.text}
                                  {m.attachment_url && isAudio(m.attachment_name) && (
                                    <div className="cg-voice">
                                      <span className="ic">🎤</span>
                                      <audio controls preload="metadata" src={m.attachment_url} />
                                      <a href={m.attachment_url} download title="Download">⤓</a>
                                    </div>
                                  )}
                                  {m.attachment_url && !isAudio(m.attachment_name) && (
                                    <a className="cg-att" href={m.attachment_url} target="_blank" rel="noreferrer">
                                      📎 {m.attachment_name} <span>{m.attachment_size_label}</span>
                                    </a>
                                  )}
                                  <span className="tm">
                                    {!m.from_me && m.message_type === "announcement" ? `${m.sender_name} · ` : ""}
                                    {when(m.created_at)}
                                    {m.is_pinned ? " · pinned" : ""}
                                  </span>
                                  {(m.can_delete || m.can_pin) && (
                                    <span className="cg-acts">
                                      {m.can_pin && (
                                        <button className="cg-act" onClick={() => doPin(m)}>
                                          {m.is_pinned ? "Unpin" : "Pin"}
                                        </button>
                                      )}
                                      {m.can_delete && (
                                        <button className="cg-act" onClick={() => doDelete(m)}>
                                          {m.from_me ? "Delete" : "Remove"}
                                        </button>
                                      )}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                        <div ref={bottomRef} />
                      </div>

                      {convMeta.can_post ? (
                        <>
                          {annMode && (
                            <div className="cg-annbar">
                              <span className="ma-pill ma-amber">📢 Announcement</span>
                              <input
                                value={annTitle}
                                placeholder="Title — e.g. Internal Assessment 1"
                                onChange={(e) => setAnnTitle(e.target.value)}
                              />
                              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
                                <input type="checkbox" checked={annPin} onChange={(e) => setAnnPin(e.target.checked)} />
                                Pin
                              </label>
                              <button className="ma-btn small" onClick={() => { setAnnMode(false); setAnnTitle(""); setAnnPin(false); }}>
                                Cancel
                              </button>
                            </div>
                          )}

                          {micError && (
                            <div className="ma-note red" style={{ margin: "0 16px 12px" }}>
                              <b>Microphone unavailable</b>{micError}
                            </div>
                          )}

                          {recording && (
                            <div className="cg-rec">
                              <span className="dot" />
                              <b>Recording</b>
                              <span className="t">{clock(seconds)}</span>
                              <span className="mini">
                                {seconds >= MAX_SECONDS - 30
                                  ? `stops at ${clock(MAX_SECONDS)}`
                                  : "speak, then stop to attach it"}
                              </span>
                              <div style={{ flex: 1 }} />
                              <button className="ma-btn small" onClick={cancelRecording}>Cancel</button>
                              <button className="ma-btn small primary" onClick={stopRecording}>Stop</button>
                            </div>
                          )}

                          {file && !recording && (
                            <div className="cg-annbar" style={{ background: "#f3efff", borderTopColor: "#e0d5ff" }}>
                              <span className="ma-pill ma-purple">
                                {isAudio(file.name) ? "🎤" : "📎"} {file.name}
                              </span>
                              {isAudio(file.name) && (
                                <audio controls src={URL.createObjectURL(file)} style={{ height: 32 }} />
                              )}
                              <div style={{ flex: 1 }} />
                              <button className="ma-btn small" onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ""; }}>
                                Remove
                              </button>
                            </div>
                          )}

                          <div className="cg-comp">
                            {/* can_attach comes from the server: always true for the
                                teacher, true for students only when the teacher has
                                allowed attachments in this group */}
                            {canAttach && (
                              <>
                                <input
                                  type="file" ref={fileRef} style={{ display: "none" }}
                                  onChange={(e) => setFile(e.target.files[0] || null)}
                                />
                                <button className="ma-btn" title="Attach a file" onClick={() => fileRef.current?.click()}>📎</button>
                              </>
                            )}
                            {/* voice notes are staff only: a student can attach a file
                                but cannot record into the class conversation */}
                            {isOwner && (
                              <button
                                className="ma-btn" title="Record a voice note"
                                onClick={startRecording} disabled={!!file}
                              >
                                🎤
                              </button>
                            )}
                            {isOwner && (
                              <button className="ma-btn" title="Send as an announcement" onClick={() => setAnnMode(true)}>📢</button>
                            )}
                            <textarea
                              value={draft}
                              placeholder={isOwner ? "Write to the class…" : "Write a message…"}
                              onChange={(e) => setDraft(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
                              }}
                            />
                            <button className="ma-btn primary" onClick={doSend} disabled={busy}>Send</button>
                          </div>
                        </>
                      ) : (
                        <div className="cg-lock">
                          <div className="ic">🔒</div>
                          <div>
                            <b>{group.has_audience ? "Messaging is currently disabled" : "This group has no students yet"}</b>
                            <div className="d">{convMeta.blocked_reason}</div>
                          </div>
                        </div>
                      )}

                      <div className="ma-panel-foot">
                        {isOwner
                          ? "One conversation. A file is an attachment on a message; an announcement is a message you marked as important. Everyone gets a notification either way."
                          : canAttach
                          ? "You can share files here with the whole class. Assignment submissions still go through the Assignments module."
                          : "Your teacher has turned off attachments in this group. You can still download anything shared here."}
                      </div>
                    </div>
                  </>
                )}

                {/* ---------- PRIVATE ---------- */}
                {view === "private" && (
                  <ClassPrivate
                    isOwner={isOwner}
                    groupId={groupId}
                    advisor={group?.owner}
                  />
                )}

                {/* ---------- STUDENTS ---------- */}
                {view === "students" && (
                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>{isOwner ? "Class list" : "My classmates"}</h3>
                        <p>{students.length} students in {group.name}</p>
                      </div>
                      <div style={{ flex: 1 }} />
                      <input
                        className="ma-input"
                        placeholder="Search name or register number"
                        value={studentQ}
                        onChange={(e) => setStudentQ(e.target.value)}
                        style={{ padding: "8px 11px", border: "1px solid #e6e9ef", borderRadius: 9, fontSize: 13.5 }}
                      />
                    </div>
                    <div className="ma-scroll">
                      <table className="ma-table">
                        <thead>
                          <tr>
                            <th>Register No</th><th>Name</th><th>Semester</th>
                            {isOwner && <><th>Batch</th><th>Attendance</th><th>Status</th><th></th></>}
                          </tr>
                        </thead>
                        <tbody>
                          {students.length === 0 && (
                            <tr><td colSpan={isOwner ? 7 : 3} className="ma-empty">No student matches.</td></tr>
                          )}
                          {students.map((s) => (
                            <tr key={s.id}>
                              <td className="num">{s.roll_number}</td>
                              <td><b>{s.name}</b></td>
                              <td className="num">{s.semester}</td>
                              {isOwner && (
                                <>
                                  <td className="num">{s.batch_year}</td>
                                  <td className="num">
                                    {s.attendance == null ? "—" : (
                                      <span className={`ma-pill ${s.attendance < 75 ? "ma-red" : "ma-green"}`}>
                                        {s.attendance}%
                                      </span>
                                    )}
                                  </td>
                                  <td>
                                    <span className={`ma-pill ${s.status === "Warning" ? "ma-amber" : "ma-green"}`}>
                                      {s.status}
                                    </span>
                                  </td>
                                  <td className="ma-right">
                                    <button
                                      className="ma-btn small"
                                      onClick={() => navigate(`/teacher/messages?kind=students&to=${s.id}`)}
                                      title={`Message ${s.name} privately`}
                                    >
                                      Message
                                    </button>
                                  </td>
                                </>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="ma-panel-foot">
                      {isOwner
                        ? "Students join by course and year. There is nothing to add or remove here. Message opens a private thread — the class conversation goes to everyone."
                        : "Names and register numbers only. Attendance and marks are never shown to classmates."}
                    </div>
                  </div>
                )}

                {/* ---------- SHARED FILES ---------- */}
                {view === "files" && (
                  <>
                    <div className="ma-note blue" style={{ marginBottom: 16 }}>
                      <b>This is not a separate file store</b>
                      It is every attachment sent in your groups, gathered in one list.
                    </div>

                    <div className="ma-panel" style={{ maxWidth: 940, marginBottom: 16 }}>
                      <div className="ma-panel-body" style={{ padding: "13px 18px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: "uppercase", color: "#6b7280" }}>
                            Group
                          </span>
                          <div className="cg-filt">
                            <button className={fileKind === "all" ? "on" : ""} onClick={() => setFileKind("all")}>All groups</button>
                            <button className={fileKind === "class" ? "on" : ""} onClick={() => setFileKind("class")}>
                              {isOwner ? "Class group" : "My class"}
                            </button>
                            <button className={fileKind === "subject" ? "on" : ""} onClick={() => setFileKind("subject")}>
                              {isOwner ? "Subject groups" : "My subjects"}
                            </button>
                          </div>
                          <div style={{ flex: 1 }} />
                          <span className={`ma-pill ${canAttach && !isOwner ? "ma-green" : "ma-grey"}`}>
                            {isOwner
                              ? (group.settings?.students_can_upload
                                  ? "🔓 Students can attach"
                                  : "🔒 Staff uploads only")
                              : (canAttach
                                  ? "🔓 You can attach files"
                                  : "🔒 You cannot upload")}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="ma-panel" style={{ maxWidth: 940 }}>
                      <div className="ma-panel-head">
                        <div><h3>Shared files</h3><p>{files.length} attachments</p></div>
                      </div>
                      {files.length === 0 && (
                        <div className="ma-empty">No files have been shared yet.</div>
                      )}
                      {files.map((f) => (
                        <div className="cg-file" key={f.id}>
                          <div className="ic">{isAudio(f.name) ? "🎤" : "📄"}</div>
                          <div>
                            <b>{f.name}</b>
                            <div className="m">
                              {f.size_label} · {f.uploaded_by} · {when(f.created_at)} ·{" "}
                              <span className={`ma-pill ${f.group_kind === "class" ? "ma-blue" : "ma-purple"}`}>
                                {f.group_name}
                              </span>
                              {f.is_announcement && <> · <span className="ma-pill ma-amber">📢 Announcement</span></>}
                            </div>
                          </div>
                          <div style={{ flex: 1 }} />
                          <button className="ma-btn small" onClick={() => openGroup(f.group_id, "conv")}>
                            Open in chat
                          </button>
                          <a className="ma-btn small primary" href={f.url} target="_blank" rel="noreferrer">
                            Download
                          </a>
                        </div>
                      ))}
                      <div className="ma-panel-foot">
                        <b>Open in chat</b> jumps to the group the file was sent in. Whether
                        students can attach is set per group, under Settings.
                      </div>
                    </div>
                  </>
                )}

                {/* ---------- SETTINGS ---------- */}
                {view === "settings" && settings && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                    <div className="ma-panel">
                      <div className="ma-panel-head">
                        <div><h3>Who can post</h3><p>These apply to this group only</p></div>
                      </div>
                      <div className="ma-panel-body">
                        <div className="cg-sw">
                          <div
                            className={`box${settings.announcement_only ? " on" : ""}`}
                            onClick={() => setSettings({ ...settings, announcement_only: !settings.announcement_only })}
                          />
                          <div>
                            <b>Announcement only</b>
                            <div className="d">
                              Students read the conversation and download attachments, but
                              cannot write. The composer is replaced by an explanation, not a
                              Send button that fails.
                            </div>
                          </div>
                        </div>
                        <div className="cg-sw">
                          <div
                            className={`box${settings.students_can_message ? " on" : ""}`}
                            onClick={() => setSettings({ ...settings, students_can_message: !settings.students_can_message })}
                          />
                          <div>
                            <b>Students can message</b>
                            <div className="d">
                              Two-way conversation. You can always post, whichever way these
                              are set.
                            </div>
                          </div>
                        </div>

                        <div className="cg-sw">
                          <div
                            className={`box${settings.students_can_upload ? " on" : ""}`}
                            onClick={() => setSettings({ ...settings, students_can_upload: !settings.students_can_upload })}
                          />
                          <div>
                            <b>Students can attach files</b>
                            <div className="d">
                              On by default, so the class can share notes and photos.
                              Switch it off if this group starts collecting assignment
                              submissions — those belong in the Assignments module,
                              where they can be collected and graded.
                            </div>
                          </div>
                        </div>

                        <button className="ma-btn primary" style={{ marginTop: 14 }} onClick={doSaveSettings} disabled={busy}>
                          {busy ? "Saving…" : "Save settings"}
                        </button>
                      </div>
                    </div>

                    <div className="ma-panel">
                      <div className="ma-panel-head"><div><h3>What you cannot change here</h3></div></div>
                      <div className="ma-scroll">
                        <table className="ma-table">
                          <thead><tr><th>Item</th><th>Who controls it</th></tr></thead>
                          <tbody>
                            <tr><td><b>Who is in this group</b></td><td style={{ fontSize: 12, color: "#6b7280" }}>The office — students join by course, year and enrolment</td></tr>
                            <tr><td><b>Who the teacher is</b></td><td style={{ fontSize: 12, color: "#6b7280" }}>The HOD, through Faculty Allocation</td></tr>
                            <tr><td><b>The group name</b></td><td style={{ fontSize: 12, color: "#6b7280" }}>Built from the course, year and subject</td></tr>
                            <tr><td><b>Deleting the group</b></td><td style={{ fontSize: 12, color: "#6b7280" }}>Not possible — it archives at year end</td></tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}

          </div>
        </div>
      </div>
      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );
}