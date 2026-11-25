// frontend/src/features/mentoring/StaffMyMentees.jsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";

import StaffChangeRequests from "./StaffChangeRequests";
import AdvisorTeamsTab from "./AdvisorTeamsTab";
import AdvisorMentorsTab from "./AdvisorMentorsTab";
import "../../styles/TeamAllocation.css";

import {
  attClass,
  broadcast,
  errorText,
  getConversations,
  getGroups,
  getMenteeDetail,
  getMyMentees,
  getThread,
  gradeClass,
  sendMessage,
  when,
  yearLabel,
  fileSize,
} from "./staffApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";
import ReadinessCard from "../placement/ReadinessCard";
import MentoringRecords from "./MentoringRecords";       // WAVE 1: mentoring & guidance records

// ================= SECTIONS =================
// Each section is opened from the sidebar (components/hubs.js) as
// /my-mentees?tab=<key>; the address decides what is showing, so Refresh,
// Back and shared links all work. "list" is the default (the old Overview
// tab was removed on request). "profile" is the detail view reached by
// clicking a student — it stays under "My mentees" in the sidebar.
const SECTIONS = {
  list: { title: "My mentees", sub: "Students the HOD has assigned to you" },
  requests: { title: "Change requests", sub: "Requests to change a student's mentor" },
  messages: { title: "Messages", sub: "Conversations with your mentees" },
  groups: { title: "Group message", sub: "Send one message to a group of your mentees" },
  teams: { title: "Team formation", sub: "Form mentoring teams for your class" },
  mentors: { title: "Pick mentors", sub: "Choose a mentor for each team in your class" },
  profile: { title: "Mentee profile", sub: "Attendance, results and notes for one student" },
};

// only a class tutor may open these
const TUTOR_ONLY = ["teams", "mentors"];

const onDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
};

export default function StaffMyMentees() {
  const [open, setOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab = SECTIONS[tabParam] ? tabParam : "list";
  // moving between sections updates the address (so Back works)
  const setTab = (key) => setSearchParams(key === "list" ? {} : { tab: key });

  // only a tutor gets the team tabs — same check the sidebar uses
  const [isTutor, setIsTutor] = useState(false);
  // The class this teacher tutors, shown under the Team formation / Pick
  // mentors headings.
  // "As tutor of your class" named the role, which the teacher already knows;
  // what they actually need to see is WHICH class those two tabs act on.
  const [tutorClass, setTutorClass] = useState("");
  const [tutorChecked, setTutorChecked] = useState(false);
  useEffect(() => {
    API.get("users/my-class/")
      .then((r) => {
        setIsTutor(r.data?.is_tutor || false);
        const c = (r.data?.classes || [])[0];
        setTutorClass(
          c ? `${c.course_name} · ${yearLabel(c.year_number)} Year` : ""
        );
      })
      .catch(() => {
        setIsTutor(false);
        setTutorClass("");
      })
      .finally(() => setTutorChecked(true));
  }, []);

  // ================= DATA =================
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  // ================= FILTERS =================
  const [fYear, setFYear] = useState("all");
  const [fGrade, setFGrade] = useState("all");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");

  // ================= PROFILE =================
  const [current, setCurrent] = useState(null);
  const [detail, setDetail] = useState(null);
  const [listQ, setListQ] = useState("");

  // ================= MESSAGES =================
  const [convos, setConvos] = useState([]);
  const [unread, setUnread] = useState(0);
  const [openId, setOpenId] = useState(null);
  const [thread, setThread] = useState(null);
  const [draft, setDraft] = useState("");
  const [convQ, setConvQ] = useState("");
  const bottomRef = useRef(null);

  // ---- attachment on the private thread ----
  const [file, setFile] = useState(null);
  const fileRef = useRef(null);

  // ================= GROUPS =================
  const [groups, setGroups] = useState([]);
  const [groupKey, setGroupKey] = useState("all");
  const [groupText, setGroupText] = useState("");

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3000);
  };

  // debounce the search box
  useEffect(() => {
    const t = setTimeout(() => setQ(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  // ================= LOADERS =================
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getMyMentees({ year: fYear, band: fGrade, q }));
    } catch (err) {
      setError(errorText(err, "Could not load your mentees."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fYear, fGrade, q]);

  useEffect(() => {
    load();
  }, [load]);

  const loadConvos = useCallback(async () => {
    try {
      const d = await getConversations();
      setConvos(d.results || []);
      setUnread(d.unread_total || 0);
    } catch {
      /* messages are optional; the page still works */
    }
  }, []);

  useEffect(() => {
    loadConvos();
  }, [loadConvos]);

  // FIX #23b: /my-mentees?tab=messages&student=7 (from a notification)
  // opens that mentee's conversation directly
  useEffect(() => {
    const sid = searchParams.get("student");
    if (tab === "messages" && sid && String(openId) !== sid) openThread(Number(sid));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, searchParams]);

  useEffect(() => {
    if (tab !== "groups") return;
    getGroups()
      .then((d) => setGroups(d.groups || []))
      .catch(() => setGroups([]));
  }, [tab]);

  const openStudent = async (id) => {
    setCurrent(id);
    setTab("profile");
    setDetail(null);
    try {
      setDetail(await getMenteeDetail(id));
    } catch (err) {
      flash(errorText(err, "Could not open that student."));
    }
  };

  const openThread = async (id) => {
    setOpenId(id);
    setTab("messages");
    setThread(null);
    // a file picked for one mentee must not follow you to the next
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
    try {
      setThread(await getThread(id));
      loadConvos();
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 60);
    } catch (err) {
      flash(errorText(err, "Could not open that conversation."));
    }
  };

  const clearFile = () => {
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const doSend = async () => {
    const text = draft.trim();
    if (!text && !file) {
      flash("Write something or attach a file.");
      return;
    }
    setBusy(true);
    try {
      const m = await sendMessage(openId, text, file);
      setThread((t) => ({ ...t, messages: [...t.messages, m] }));
      setDraft("");
      clearFile();
      loadConvos();
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 60);
    } catch (err) {
      flash(errorText(err, "Could not send."));
    } finally {
      setBusy(false);
    }
  };

  const doBroadcast = async () => {
    const text = groupText.trim();
    if (!text) {
      flash("Write a message first.");
      return;
    }
    setBusy(true);
    try {
      const r = await broadcast(groupKey, text);
      setGroupText("");
      loadConvos();
      flash(`Sent to ${r.sent} student(s)`);
    } catch (err) {
      flash(errorText(err, "Could not send."));
    } finally {
      setBusy(false);
    }
  };

  // ================= DERIVED =================
  const rows = data?.results || [];

  const filtersOn = q !== "" || fYear !== "all" || fGrade !== "all";
  const noMenteesAtAll = !!data && rows.length === 0 && !filtersOn;

  const listRows = useMemo(() => {
    if (!listQ) return rows;
    const t = listQ.toLowerCase();
    return rows.filter(
      (r) =>
        r.student_name.toLowerCase().includes(t) ||
        (r.roll_number || "").toLowerCase().includes(t)
    );
  }, [rows, listQ]);

  const grouped = useMemo(() => {
    const out = {};
    listRows.forEach((r) => {
      (out[r.year] ||= []).push(r);
    });
    return Object.entries(out).sort((a, b) => a[0] - b[0]);
  }, [listRows]);

  const convoRows = useMemo(() => {
    if (!convQ) return convos;
    const t = convQ.toLowerCase();
    return convos.filter(
      (c) =>
        c.student_name.toLowerCase().includes(t) ||
        (c.roll_number || "").toLowerCase().includes(t)
    );
  }, [convos, convQ]);

  const selectedGroup = groups.find((g) => g.key === groupKey);

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2 style={{ margin: 0 }}>{SECTIONS[tab].title}</h2>
              <p>
                {SECTIONS[tab].sub}
                {tab === "list" && data?.academic_year
                  ? ` · ${data.academic_year.replace("-", "\u2013")}`
                  : ""}
                {TUTOR_ONLY.includes(tab) && tutorClass ? ` · ${tutorClass}` : ""}
              </p>
            </div>

            {/* sections are chosen from the sidebar — see SECTIONS above */}
            {TUTOR_ONLY.includes(tab) && tutorChecked && !isTutor && (
              <div className="ma-panel">
                <div className="ma-empty">
                  <b style={{ display: "block", marginBottom: 6 }}>Only for class in-charges</b>
                  This section is available to a class in-charge.
                </div>
              </div>
            )}

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>
                {error}
              </div>
            )}

            {loading && (
              <div className="ma-panel">
                <div className="ma-empty">Loading…</div>
              </div>
            )}

            {/* ================= NO MENTEES =================
                This used to render ABOVE the tab content rather than instead
                of it, so a teacher with no mentees saw the empty state and a
                row of zero cards together. */}
            {!loading &&
              noMenteesAtAll &&
              !TUTOR_ONLY.includes(tab) &&
              tab !== "requests" && (
                <div className="ma-panel">
                  <div className="ma-empty">
                    <b style={{ display: "block", marginBottom: 6 }}>
                      No students are assigned to you yet
                    </b>
                    The HOD allocates students to mentors. Once that happens they
                    appear here with their attendance and results.
                    {isTutor && (
                      <>
                        <br />
                        <br />
                        You are also the class in-charge of {tutorClass || "a class"}, so you
                        can still use <b>Team formation</b> in the sidebar.
                      </>
                    )}
                  </div>
                </div>
              )}

            {!loading && data && tab === "list" && !noMenteesAtAll && (
              <>
                <div className="ma-panel">
                  <div className="ma-panel-body">
                    <div className="ma-filters" style={{ alignItems: "center" }}>
                      <span className="ma-label" style={{ margin: 0 }}>
                        Year
                      </span>
                      <div className="ma-toggle">
                        <button
                          className={fYear === "all" ? "on" : ""}
                          onClick={() => setFYear("all")}
                        >
                          All
                        </button>
                        {(data.by_year || []).map((y) => (
                          <button
                            key={y.year}
                            className={fYear === String(y.year) ? "on" : ""}
                            onClick={() => setFYear(String(y.year))}
                          >
                            {yearLabel(y.year)}
                          </button>
                        ))}
                      </div>
                      <span className="ma-label" style={{ margin: "0 0 0 8px" }}>
                        Grade
                      </span>
                      <div className="ma-toggle">
                        {["all", "A", "B", "C"].map((g) => (
                          <button
                            key={g}
                            className={fGrade === g ? "on" : ""}
                            onClick={() => setFGrade(g)}
                          >
                            {g === "all" ? "All" : g}
                          </button>
                        ))}
                      </div>
                      <div style={{ flex: 1 }} />
                      <input
                        placeholder="Search name or register number"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        style={{
                          padding: "9px 11px",
                          border: "1px solid #E7E7EC",
                          borderRadius: 9,
                          width: 240,
                        }}
                      />
                      <button
                        className="ma-btn"
                        onClick={() => {
                          setFYear("all");
                          setFGrade("all");
                          setSearch("");
                        }}
                      >
                        Reset
                      </button>
                    </div>
                  </div>
                </div>

                <div className="ma-panel">
                  <div className="ma-panel-head">
                    <div>
                      <h3>All your mentees</h3>
                      <p>
                        {rows.length} student{rows.length === 1 ? "" : "s"} · grouped by
                        year
                      </p>
                    </div>
                    <div style={{ flex: 1 }} />
                    <button className="ma-btn" onClick={() => window.print()}>
                      Print
                    </button>
                  </div>
                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead>
                        <tr>
                          <th>Register No</th>
                          <th>Student Name</th>
                          <th>Course</th>
                          <th>Grade</th>
                          <th>Attendance</th>
                          <th>CGPA</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.length === 0 && (
                          <tr>
                            <td colSpan={7} className="ma-empty">
                              No student matches these filters.{" "}
                              <button
                                className="ma-btn link"
                                onClick={() => {
                                  setFYear("all");
                                  setFGrade("all");
                                  setSearch("");
                                }}
                              >
                                Clear filters
                              </button>
                            </td>
                          </tr>
                        )}
                        {grouped.map(([year, list]) => (
                          <React.Fragment key={`g-${year}`}>
                            <tr>
                              <td
                                colSpan={7}
                                style={{
                                  background: "#F6F6F8",
                                  fontSize: 11.5,
                                  fontWeight: 700,
                                  letterSpacing: ".7px",
                                  textTransform: "uppercase",
                                  color: "#5D5A6B",
                                }}
                              >
                                {yearLabel(year)} Year · Semester {list[0].semester} ·{" "}
                                {list.length} student{list.length === 1 ? "" : "s"}
                              </td>
                            </tr>
                            {list.map((r) => (
                              <tr key={r.student_id}>
                                <td className="num">{r.roll_number}</td>
                                <td>
                                  <b>{r.student_name}</b>
                                </td>
                                <td>{r.course_name || "—"}</td>
                                <td>
                                  <span className={`ma-pill ${gradeClass(r.grade_band)}`}>
                                    {r.grade_band || "—"}
                                  </span>
                                </td>
                                <td>
                                  <span className={`ma-pill ${attClass(r.attendance)}`}>
                                    {r.attendance == null ? "—" : `${r.attendance}%`}
                                  </span>
                                </td>
                                <td className="num">
                                  {r.cgpa == null ? "—" : r.cgpa.toFixed(2)}
                                </td>
                                <td className="ma-right">
                                  <div className="ma-actions">
                                    <button
                                      className="ma-btn small violet"
                                      onClick={() => openStudent(r.student_id)}
                                    >
                                      View
                                    </button>
                                    <button
                                      className="ma-btn small"
                                      onClick={() => openThread(r.student_id)}
                                    >
                                      Message
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </React.Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="ma-panel-foot">
                    Semester appears in the year heading, not as a column — it never
                    varies within a year.
                  </div>
                </div>
              </>
            )}

            {/* ================= TUTOR TABS ================= */}
            {tab === "teams" && isTutor && <AdvisorTeamsTab />}
            {tab === "mentors" && isTutor && <AdvisorMentorsTab />}

            {/* ================= CHANGE REQUESTS ================= */}
            {tab === "requests" && <StaffChangeRequests />}

            {/* ================= STUDENT PROFILE ================= */}
            {!loading && data && tab === "profile" && (
              <>
                <div style={{ marginBottom: 12 }}>
                  <button className="ma-btn" onClick={() => setTab("list")}>
                    ← Back to all mentees
                  </button>
                </div>

                <div className="md">
                  <div
                    className="ma-panel"
                    style={{ flex: "0 0 300px", maxHeight: 640, overflowY: "auto" }}
                  >
                    <div
                      className="ma-panel-head"
                      style={{ position: "sticky", top: 0, background: "#fff", zIndex: 3 }}
                    >
                      <div>
                        <h3>Your mentees</h3>
                        <p>{listRows.length} students</p>
                      </div>
                    </div>
                    <div
                      className="ma-panel-body"
                      style={{ padding: "10px 12px", borderBottom: "1px solid #ECECF0" }}
                    >
                      <input
                        placeholder="Search a name"
                        value={listQ}
                        onChange={(e) => setListQ(e.target.value)}
                        style={{
                          padding: "9px 11px",
                          border: "1px solid #E7E7EC",
                          borderRadius: 9,
                          width: "100%",
                        }}
                      />
                    </div>
                    {grouped.map(([year, list]) => (
                      <div key={year}>
                        <div className="ylabel">
                          {yearLabel(year)} Year<span className="n">{list.length}</span>
                        </div>
                        {list.map((s) => (
                          <button
                            key={s.student_id}
                            className={`srow${current === s.student_id ? " on" : ""}`}
                            onClick={() => openStudent(s.student_id)}
                          >
                            <span className="av">
                              {s.student_name
                                .split(" ")
                                .map((p) => p[0])
                                .join("")
                                .slice(0, 2)
                                .toUpperCase()}
                            </span>
                            <span>
                              <b>{s.student_name}</b>
                              <span className="m">{s.roll_number}</span>
                            </span>
                            <span className="g">
                              <span className={`ma-pill ${gradeClass(s.grade_band)}`}>
                                {s.grade_band || "—"}
                              </span>
                            </span>
                          </button>
                        ))}
                      </div>
                    ))}
                    {listRows.length === 0 && (
                      <div className="ma-empty">No name matches.</div>
                    )}
                  </div>

                  <div className="detail" style={{ flex: 1, minWidth: 0 }}>
                    {!current && (
                      <div className="ma-panel">
                        <div className="ma-empty">
                          Pick a student on the left to see their details.
                        </div>
                      </div>
                    )}
                    {current && !detail && (
                      <div className="ma-panel">
                        <div className="ma-empty">Loading…</div>
                      </div>
                    )}
                    {detail && (
                      <>
                        <div className="ma-panel">
                          <div className="ma-panel-body">
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 16,
                                flexWrap: "wrap",
                              }}
                            >
                              <div
                                className="ma-avatar"
                                style={{
                                  width: 56,
                                  height: 56,
                                  borderRadius: "50%",
                                  fontSize: 17,
                                }}
                              >
                                {detail.student.name
                                  .split(" ")
                                  .map((p) => p[0])
                                  .join("")
                                  .slice(0, 2)
                                  .toUpperCase()}
                              </div>
                              <div>
                                <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
                                  {detail.student.name}
                                </h2>
                                <div style={{ fontSize: 13.5, color: "#5D5A6B" }}>
                                  {detail.student.roll_number} ·{" "}
                                  {yearLabel(detail.student.year)} Year · Semester{" "}
                                  {detail.student.semester} · {detail.student.course_name}
                                </div>
                              </div>
                              <div style={{ flex: 1 }} />
                              <span
                                className={`ma-pill ${gradeClass(
                                  detail.allocation.grade_band
                                )}`}
                              >
                                Grade {detail.allocation.grade_band || "—"}
                              </span>
                              <button
                                className="ma-btn"
                                onClick={() => openThread(detail.student.id)}
                              >
                                Message
                              </button>
                            </div>
                          </div>
                        </div>

                        <div style={{ marginTop: 16 }}>
                          <ReadinessCard studentId={detail.student.id} />
                        </div>

                        {/* WAVE 1: sessions by category (academic, personal, competitive exams ...) */}
                        <MentoringRecords studentId={detail.student.id} />

                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))",
                            gap: 16,
                            marginTop: 16,
                          }}
                        >
                          <div className="ma-panel">
                            <div className="ma-panel-head">
                              <div>
                                <h3>Student details</h3>
                                <p>Read-only</p>
                              </div>
                            </div>
                            <div className="ma-panel-body">
                              <table className="ma-table">
                                <tbody>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Name</td>
                                    <td>
                                      <b>{detail.student.name}</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Register number</td>
                                    <td>
                                      <b>{detail.student.roll_number}</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Department</td>
                                    <td>
                                      <b>{detail.student.department}</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Course</td>
                                    <td>
                                      <b>{detail.student.course_name || "—"}</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Year</td>
                                    <td>
                                      <b>{yearLabel(detail.student.year)} Year</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Semester</td>
                                    <td>
                                      <b>{detail.student.semester}</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Email</td>
                                    <td>
                                      <b>{detail.student.email || "—"}</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Your mentee since</td>
                                    <td>
                                      <b>{onDate(detail.allocation.assigned_on)}</b>
                                    </td>
                                  </tr>
                                </tbody>
                              </table>
                            </div>
                            <div className="ma-panel-foot">
                              Contact the office if a detail is wrong — it comes from the
                              student record.
                            </div>
                          </div>

                          <div className="ma-panel">
                            <div className="ma-panel-head">
                              <div>
                                <h3>How they are doing</h3>
                                <p>From the attendance and results modules</p>
                              </div>
                            </div>
                            <div className="ma-panel-body">
                              <div style={{ display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap" }}>
                                <div style={{ flex: 1, minWidth: 130 }}>
                                  <div
                                    style={{
                                      display: "flex",
                                      justifyContent: "space-between",
                                      fontSize: 14,
                                      marginBottom: 5,
                                    }}
                                  >
                                    <span>Attendance</span>
                                    <b>
                                      {detail.academics.attendance == null
                                        ? "—"
                                        : `${detail.academics.attendance}%`}
                                    </b>
                                  </div>
                                  <div className="ma-bar">
                                    <i
                                      className={
                                        detail.academics.attendance >= 80
                                          ? "green"
                                          : detail.academics.attendance >= 75
                                          ? "amber"
                                          : "red"
                                      }
                                      style={{ width: `${detail.academics.attendance || 0}%` }}
                                    />
                                  </div>
                                </div>
                                <div style={{ flex: 1, minWidth: 130 }}>
                                  <div
                                    style={{
                                      display: "flex",
                                      justifyContent: "space-between",
                                      fontSize: 14,
                                      marginBottom: 5,
                                    }}
                                  >
                                    <span>CGPA</span>
                                    <b>
                                      {detail.academics.cgpa == null
                                        ? "—"
                                        : detail.academics.cgpa}
                                    </b>
                                  </div>
                                  <div className="ma-bar">
                                    <i style={{ width: `${(detail.academics.cgpa || 0) * 10}%` }} />
                                  </div>
                                </div>
                              </div>

                              <table className="ma-table">
                                <tbody>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Backlogs</td>
                                    <td>
                                      <b>{detail.academics.backlogs}</b>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td style={{ color: "#5D5A6B" }}>Grade band</td>
                                    <td>
                                      <b>{detail.allocation.grade_band || "—"}</b>
                                      <span style={{ fontSize: 12.5, color: "#5D5A6B" }}>
                                        {" "}
                                        — fixed at allocation, so later results do not
                                        rewrite it
                                      </span>
                                    </td>
                                  </tr>
                                </tbody>
                              </table>

                              {detail.academics.attendance != null &&
                                detail.academics.attendance < 75 && (
                                  <div className="ma-note red" style={{ marginTop: 12 }}>
                                    <b>Below the 75% requirement</b>
                                    Worth raising the next time you meet.
                                  </div>
                                )}
                            </div>
                          </div>
                        </div>

                        <div className="ma-panel" style={{ marginTop: 16 }}>
                          <div className="ma-panel-head">
                            <div>
                              <h3>Published semester results</h3>
                              <p>Newest first</p>
                            </div>
                          </div>
                          <div className="ma-scroll">
                            <table className="ma-table">
                              <thead>
                                <tr>
                                  <th>Semester</th>
                                  <th>Percentage</th>
                                  <th>Subjects</th>
                                  <th>Backlogs</th>
                                </tr>
                              </thead>
                              <tbody>
                                {detail.academics.semesters.length === 0 && (
                                  <tr>
                                    <td colSpan={4} className="ma-empty">
                                      No published result yet.
                                    </td>
                                  </tr>
                                )}
                                {detail.academics.semesters.map((s) => (
                                  <tr key={s.semester}>
                                    <td>
                                      <b>Semester {s.semester}</b>
                                    </td>
                                    <td className="num">{s.percentage}%</td>
                                    <td className="num">{s.subjects}</td>
                                    <td>
                                      {s.backlogs ? (
                                        <span className="ma-pill ma-amber">{s.backlogs}</span>
                                      ) : (
                                        <span className="num">0</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <div className="ma-panel-foot">{detail.note}</div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* ================= MESSAGES ================= */}
            {!loading && data && tab === "messages" && (
              <>
                <div className="ma-note blue" style={{ marginBottom: 16 }}>
                  <b>Your normal LMS messaging, filtered to your mentees</b>
                  Not a second inbox. You can only message students currently allocated
                  to you.
                </div>

                <div className="md">
                  <div
                    className="ma-panel"
                    style={{ flex: "0 0 300px", maxHeight: 660, overflowY: "auto" }}
                  >
                    <div
                      className="ma-panel-head"
                      style={{ position: "sticky", top: 0, background: "#fff", zIndex: 3 }}
                    >
                      <div>
                        <h3>Conversations</h3>
                        <p>
                          {convoRows.length} · {unread} unread
                        </p>
                      </div>
                    </div>
                    <div
                      className="ma-panel-body"
                      style={{ padding: "10px 12px", borderBottom: "1px solid #ECECF0" }}
                    >
                      <input
                        placeholder="Search a name"
                        value={convQ}
                        onChange={(e) => setConvQ(e.target.value)}
                        style={{
                          padding: "9px 11px",
                          border: "1px solid #E7E7EC",
                          borderRadius: 9,
                          width: "100%",
                        }}
                      />
                    </div>
                    {convoRows.length === 0 && (
                      <div className="ma-empty">No conversation matches.</div>
                    )}
                    {convoRows.map((c) => (
                      <button
                        key={c.student_id}
                        className={`conv${openId === c.student_id ? " on" : ""}`}
                        onClick={() => openThread(c.student_id)}
                      >
                        <span className="av">
                          {c.student_name
                            .split(" ")
                            .map((p) => p[0])
                            .join("")
                            .slice(0, 2)
                            .toUpperCase()}
                        </span>
                        <span className="bd">
                          <span className="tp">
                            <b>{c.student_name}</b>
                            {c.unread > 0 && <span className="un">{c.unread}</span>}
                            <span className="t">{when(c.last_at)}</span>
                          </span>
                          <span className="pv">
                            {c.last_message
                              ? `${c.last_from_me ? "You: " : ""}${c.last_message}`
                              : "No messages yet"}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>

                  <div className="thread" style={{ flex: 1, minWidth: 0 }}>
                    {!openId && (
                      <div className="ma-panel">
                        <div className="ma-empty">
                          Pick a mentee on the left to open the conversation.
                        </div>
                      </div>
                    )}
                    {openId && !thread && (
                      <div className="ma-panel">
                        <div className="ma-empty">Loading…</div>
                      </div>
                    )}
                    {thread && (
                      <div className="ma-panel">
                        <div className="ma-panel-head">
                          <div
                            className="ma-avatar"
                            style={{ width: 38, height: 38, borderRadius: "50%", fontSize: 13 }}
                          >
                            {thread.student.name
                              .split(" ")
                              .map((p) => p[0])
                              .join("")
                              .slice(0, 2)
                              .toUpperCase()}
                          </div>
                          <div>
                            <h3 style={{ margin: 0 }}>{thread.student.name}</h3>
                            <p>
                              {thread.student.roll_number} ·{" "}
                              {yearLabel(thread.student.year)} Year
                            </p>
                          </div>
                          <div style={{ flex: 1 }} />
                          <button
                            className="ma-btn small"
                            onClick={() => openStudent(thread.student.id)}
                          >
                            Open profile
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
                                {m.attachment_url && (
                                  <a
                                    className="msg-att"
                                    href={m.attachment_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    📎 {m.attachment_name}
                                    <span className="sz">{fileSize(m.attachment_size)}</span>
                                  </a>
                                )}
                                <span className="tm">{when(m.created_at)}</span>
                              </div>
                            </div>
                          ))}
                          <div ref={bottomRef} />
                        </div>

                        {file && (
                          <div className="msg-bar">
                            <span className="ma-pill ma-purple">📎 {file.name}</span>
                            <div style={{ flex: 1 }} />
                            <button className="ma-btn small" onClick={clearFile}>
                              Remove
                            </button>
                          </div>
                        )}

                        <div className="composer">
                          <input
                            type="file"
                            ref={fileRef}
                            style={{ display: "none" }}
                            onChange={(e) => setFile(e.target.files[0] || null)}
                          />
                          <button
                            className="ma-btn"
                            title="Attach a file"
                            onClick={() => fileRef.current?.click()}
                          >
                            📎
                          </button>
                          <textarea
                            value={draft}
                            placeholder="Write a reply…"
                            onChange={(e) => setDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                doSend();
                              }
                            }}
                          />
                          <button className="ma-btn primary" onClick={doSend} disabled={busy}>
                            Send
                          </button>
                        </div>
                        <div className="ma-panel-foot">
                          Messages are kept on record and cannot be permanently deleted by
                          either side.
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* ================= GROUP MESSAGE ================= */}
            {!loading && data && tab === "groups" && !noMenteesAtAll && (
              <>
                <div className="ma-note blue" style={{ marginBottom: 16 }}>
                  <b>Groups build themselves from your allocation</b>
                  There is no member list to maintain. When the HOD adds or moves a
                  student, the groups update on their own.
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
                    gap: 16,
                  }}
                >
                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>Send to a group</h3>
                        <p>One message, everyone in the group</p>
                      </div>
                    </div>
                    <div className="ma-panel-body">
                      <div style={{ marginBottom: 15 }}>
                        <span className="ma-label">Who gets it</span>
                        <select
                          value={groupKey}
                          onChange={(e) => setGroupKey(e.target.value)}
                          style={{
                            padding: "9px 11px",
                            border: "1px solid #E7E7EC",
                            borderRadius: 9,
                            width: "100%",
                          }}
                        >
                          {groups.map((g) => (
                            <option key={g.key} value={g.key}>
                              {g.name} · {g.count} students
                            </option>
                          ))}
                        </select>
                        {selectedGroup && (
                          <div style={{ fontSize: 12.5, color: "#5D5A6B", marginTop: 5 }}>
                            {selectedGroup.why} · {selectedGroup.count} students will
                            receive this.
                          </div>
                        )}
                      </div>

                      <div style={{ marginBottom: 15 }}>
                        <span className="ma-label">Message</span>
                        <textarea
                          value={groupText}
                          placeholder="Keep it short. Students see this as a message from you."
                          onChange={(e) => setGroupText(e.target.value)}
                          style={{
                            padding: "10px 12px",
                            border: "1px solid #E7E7EC",
                            borderRadius: 9,
                            width: "100%",
                            minHeight: 90,
                            fontFamily: "inherit",
                            fontSize: 14.5,
                          }}
                        />
                      </div>

                      {selectedGroup && !selectedGroup.visible_to_student && (
                        <div className="ma-note amber" style={{ marginBottom: 15 }}>
                          <b>Students do not see this group's name</b>
                          They receive it as a normal message from you. Nobody should read
                          a performance label attached to themselves.
                        </div>
                      )}

                      <button
                        className="ma-btn primary"
                        onClick={doBroadcast}
                        disabled={busy || !groupText.trim()}
                      >
                        Send to {selectedGroup ? `${selectedGroup.count} students` : "group"}
                      </button>
                      <button
                        className="ma-btn"
                        style={{ marginLeft: 8 }}
                        onClick={() => setGroupText("")}
                      >
                        Clear
                      </button>
                    </div>
                    <div className="ma-panel-foot">
                      One-to-many. Students never see each other's replies.
                    </div>
                  </div>

                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>Your groups</h3>
                        <p>Built from your allocation</p>
                      </div>
                    </div>
                    <div className="ma-scroll">
                      <table className="ma-table">
                        <thead>
                          <tr>
                            <th>Group</th>
                            <th>Students</th>
                            <th>Name shown to them</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {groups.length === 0 && (
                            <tr>
                              <td colSpan={4} className="ma-empty">
                                No groups yet.
                              </td>
                            </tr>
                          )}
                          {groups.map((g) => (
                            <tr key={g.key}>
                              <td>
                                <b>{g.name}</b>
                                <div style={{ fontSize: 12.5, color: "#5D5A6B" }}>
                                  {g.why}
                                </div>
                              </td>
                              <td className="num">{g.count}</td>
                              <td>
                                <span
                                  className={`ma-pill ${
                                    g.visible_to_student ? "ma-green" : "ma-red"
                                  }`}
                                >
                                  {g.visible_to_student ? "Yes" : "Hidden"}
                                </span>
                              </td>
                              <td className="ma-right">
                                <button
                                  className="ma-btn small"
                                  onClick={() => setGroupKey(g.key)}
                                >
                                  Use this
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="ma-panel-foot">
                      A group is a saved query, not a fixed list, so it cannot drift out
                      of date.
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