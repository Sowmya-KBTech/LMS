// frontend/src/features/mentoring/StaffMyMentees.jsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";

import StaffChangeRequests from "./StaffChangeRequests";

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
} from "./staffApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

const TABS = [
  { key: "dash", label: "Dashboard" },
  { key: "list", label: "All Mentees" },
  { key: "requests", label: "Change Requests" },
  { key: "profile", label: "Student Profile" },
  { key: "messages", label: "Messages" },
  { key: "groups", label: "Groups" },
];

export default function StaffMyMentees() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("dash");

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

  useEffect(() => { load(); }, [load]);

  const loadConvos = useCallback(async () => {
    try {
      const d = await getConversations();
      setConvos(d.results || []);
      setUnread(d.unread_total || 0);
    } catch { /* messages are optional; the page still works */ }
  }, []);

  useEffect(() => { loadConvos(); }, [loadConvos]);

  useEffect(() => {
    if (tab !== "groups") return;
    getGroups().then((d) => setGroups(d.groups || [])).catch(() => setGroups([]));
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
    try {
      setThread(await getThread(id));
      loadConvos();
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 60);
    } catch (err) {
      flash(errorText(err, "Could not open that conversation."));
    }
  };

  const doSend = async () => {
    const text = draft.trim();
    if (!text) { flash("Nothing to send."); return; }
    setBusy(true);
    try {
      const m = await sendMessage(openId, text);
      setThread((t) => ({ ...t, messages: [...t.messages, m] }));
      setDraft("");
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
    if (!text) { flash("Write a message first."); return; }
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
  const cards = data?.cards || {};
  const comp = data?.composition || {};
  const rows = data?.results || [];
  const watch = data?.watchlist || [];

  const listRows = useMemo(() => {
    if (!listQ) return rows;
    const t = listQ.toLowerCase();
    return rows.filter(
      (r) => r.student_name.toLowerCase().includes(t) ||
             (r.roll_number || "").toLowerCase().includes(t)
    );
  }, [rows, listQ]);

  const grouped = useMemo(() => {
    const out = {};
    listRows.forEach((r) => { (out[r.year] ||= []).push(r); });
    return Object.entries(out).sort((a, b) => a[0] - b[0]);
  }, [listRows]);

  const convoRows = useMemo(() => {
    if (!convQ) return convos;
    const t = convQ.toLowerCase();
    return convos.filter(
      (c) => c.student_name.toLowerCase().includes(t) ||
             (c.roll_number || "").toLowerCase().includes(t)
    );
  }, [convos, convQ]);

  const selectedGroup = groups.find((g) => g.key === groupKey);
  const balPill = comp.state === "ok" ? "ma-green" : comp.state === "warn" ? "ma-amber" : "ma-red";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2 style={{ margin: 0 }}>My Mentees</h2>
              <p>
                Students the HOD has assigned to you
                {data?.academic_year ? ` · ${data.academic_year.replace("-", "\u2013")}` : ""}
              </p>
            </div>

            {/* ================= TABS ================= */}
            <div className="ma-toggle" style={{ marginBottom: 16 }}>
              {TABS.map((t) => (
                <button key={t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>
                  {t.label}
                  {t.key === "messages" && unread > 0 ? ` (${unread})` : ""}
                </button>
              ))}
            </div>

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>{error}
              </div>
            )}

            {loading && <div className="ma-panel"><div className="ma-empty">Loading…</div></div>}

              {!loading && data && tab !== "requests" && rows.length === 0 && !q && fYear === "all" && fGrade === "all" && (
              <div className="ma-panel">
                <div className="ma-empty">
                  <b style={{ display: "block", marginBottom: 6 }}>You have no mentees yet</b>
                  The HOD allocates students to mentors. Once that happens they appear here.
                </div>
              </div>
            )}

            {/* ================= DASHBOARD ================= */}
            {!loading && data && tab === "dash" && (
              <>
                <div className="ma-cards">
                  <div className="ma-card">
                    <div className="l">Total Mentees</div>
                    <div className="n">{cards.total_mentees}</div>
                    <div className="d">Assigned by the HOD</div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Average Attendance</div>
                    <div className="n green">
                      {cards.average_attendance == null ? "—" : `${cards.average_attendance}%`}
                    </div>
                    <div className="d">Requirement 75%</div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Below 75%</div>
                    <div className="n red">{cards.below_75}</div>
                    <div className="d">{cards.below_75 ? "Need attention" : "Nobody below the line"}</div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Average CGPA</div>
                    <div className="n">{cards.average_cgpa == null ? "—" : cards.average_cgpa}</div>
                    <div className="d">out of 10</div>
                  </div>
                </div>

                <div className="ma-panel">
                  <div className="ma-panel-head">
                    <div>
                      <h3>Students to look at first</h3>
                      <p>Attendance at or near the 75% requirement</p>
                    </div>
                    <div style={{ flex: 1 }} />
                    <span className={`ma-pill ${watch.length ? "ma-amber" : "ma-green"}`}>
                      {watch.length} student{watch.length === 1 ? "" : "s"}
                    </span>
                    <button className="ma-btn" onClick={() => setTab("list")}>Open all mentees</button>
                  </div>
                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead>
                        <tr>
                          <th>Student</th><th>Register No</th><th>Year</th>
                          <th>Grade</th><th>Attendance</th><th>CGPA</th><th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {watch.length === 0 && (
                          <tr><td colSpan={7} className="ma-empty">
                            Nobody is below 80% attendance right now.
                          </td></tr>
                        )}
                        {watch.map((s) => (
                          <tr key={s.student_id}>
                            <td><b>{s.student_name}</b></td>
                            <td className="num">{s.roll_number}</td>
                            <td>{yearLabel(s.year)}</td>
                            <td><span className={`ma-pill ${gradeClass(s.grade_band)}`}>{s.grade_band || "—"}</span></td>
                            <td><span className={`ma-pill ${attClass(s.attendance)}`}>
                              {s.attendance == null ? "—" : `${s.attendance}%`}</span></td>
                            <td className="num">{s.cgpa == null ? "—" : s.cgpa.toFixed(2)}</td>
                            <td className="ma-right">
                              <div className="ma-actions">
                                <button className="ma-btn small violet" onClick={() => openStudent(s.student_id)}>View</button>
                                <button className="ma-btn small" onClick={() => openThread(s.student_id)}>Message</button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="ma-panel-foot">
                    Sorted by attendance, lowest first. Figures come from your existing
                    attendance and results modules.
                  </div>
                </div>

                <div className="ma-panel" style={{ marginTop: 16 }}>
                  <div className="ma-panel-head">
                    <div><h3>My mentees by year</h3><p>Click a year to open that group</p></div>
                    <div style={{ flex: 1 }} />
                    <span className={`ma-pill ${balPill}`}>{comp.message}</span>
                  </div>
                  <div className="ma-panel-body">
                    <div className="ma-capacity">
                      {(data.by_year || []).map((y) => (
                        <div
                          className="ma-cap"
                          key={y.year}
                          onClick={() => { setFYear(String(y.year)); setTab("list"); }}
                        >
                          <div className="name">{yearLabel(y.year)} Year</div>
                          <div className="big"><b>{y.count}</b><span>students</span></div>
                          <div className="ma-mix">
                            <i style={{ background: "#10b981", flex: y.A || 0.02 }} />
                            <i style={{ background: "#2563eb", flex: y.B || 0.02 }} />
                            <i style={{ background: "#f59e0b", flex: y.C || 0.02 }} />
                          </div>
                          <div className="ma-small">A {y.A} · B {y.B} · C {y.C}</div>
                        </div>
                      ))}
                    </div>
                    <div className="ma-note" style={{ marginTop: 14 }}>
                      <b>Your group: A {comp.band_a} · B {comp.band_b} · C {comp.band_c}</b>
                      The grade mix is set by the HOD when allocating. You can see it for
                      your own mentees only — students never see it.
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* ================= ALL MENTEES ================= */}
            {!loading && data && tab === "list" && (
              <>
                <div className="ma-panel">
                  <div className="ma-panel-body">
                    <div className="ma-filters" style={{ alignItems: "center" }}>
                      <span className="ma-label" style={{ margin: 0 }}>Year</span>
                      <div className="ma-toggle">
                        <button className={fYear === "all" ? "on" : ""} onClick={() => setFYear("all")}>All</button>
                        {(data.by_year || []).map((y) => (
                          <button key={y.year} className={fYear === String(y.year) ? "on" : ""}
                                  onClick={() => setFYear(String(y.year))}>
                            {yearLabel(y.year)}
                          </button>
                        ))}
                      </div>
                      <span className="ma-label" style={{ margin: "0 0 0 8px" }}>Grade</span>
                      <div className="ma-toggle">
                        {["all", "A", "B", "C"].map((g) => (
                          <button key={g} className={fGrade === g ? "on" : ""} onClick={() => setFGrade(g)}>
                            {g === "all" ? "All" : g}
                          </button>
                        ))}
                      </div>
                      <div style={{ flex: 1 }} />
                      <input
                        placeholder="Search name or register number"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: 240 }}
                      />
                      <button className="ma-btn" onClick={() => { setFYear("all"); setFGrade("all"); setSearch(""); }}>
                        Reset
                      </button>
                    </div>
                  </div>
                </div>

                <div className="ma-panel">
                  <div className="ma-panel-head">
                    <div><h3>All my mentees</h3><p>{rows.length} students · grouped by year</p></div>
                    <div style={{ flex: 1 }} />
                    <button className="ma-btn" onClick={() => window.print()}>Print</button>
                  </div>
                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead>
                        <tr>
                          <th>Register No</th><th>Student Name</th><th>Course</th>
                          <th>Grade</th><th>Attendance</th><th>CGPA</th><th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.length === 0 && (
                          <tr><td colSpan={7} className="ma-empty">
                            No student matches these filters.{" "}
                            <button className="ma-btn link" onClick={() => { setFYear("all"); setFGrade("all"); setSearch(""); }}>
                              Clear filters
                            </button>
                          </td></tr>
                        )}
                        {grouped.map(([year, list]) => (
                          <React.Fragment key={`g-${year}`}>
                            <tr>
                              <td colSpan={7} style={{
                                background: "#f8fafc", fontSize: 10.5, fontWeight: 700,
                                letterSpacing: ".7px", textTransform: "uppercase", color: "#6b7280",
                              }}>
                                {yearLabel(year)} Year · Semester {list[0].semester} · {list.length} student{list.length === 1 ? "" : "s"}
                              </td>
                            </tr>
                            {list.map((r) => (
                              <tr key={r.student_id}>
                                <td className="num">{r.roll_number}</td>
                                <td><b>{r.student_name}</b></td>
                                <td>{r.course_name || "—"}</td>
                                <td><span className={`ma-pill ${gradeClass(r.grade_band)}`}>{r.grade_band || "—"}</span></td>
                                <td><span className={`ma-pill ${attClass(r.attendance)}`}>
                                  {r.attendance == null ? "—" : `${r.attendance}%`}</span></td>
                                <td className="num">{r.cgpa == null ? "—" : r.cgpa.toFixed(2)}</td>
                                <td className="ma-right">
                                  <div className="ma-actions">
                                    <button className="ma-btn small violet" onClick={() => openStudent(r.student_id)}>View</button>
                                    <button className="ma-btn small" onClick={() => openThread(r.student_id)}>Message</button>
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

            {/* ================= CHANGE REQUESTS ================= */}
            {tab === "requests" && <StaffChangeRequests />}

            {/* ================= STUDENT PROFILE ================= */}
            {!loading && data && tab === "profile" && (
              <div className="md">
                <div className="ma-panel" style={{ flex: "0 0 300px", maxHeight: 640, overflowY: "auto" }}>
                  <div className="ma-panel-head" style={{ position: "sticky", top: 0, background: "#fff", zIndex: 3 }}>
                    <div><h3>My mentees</h3><p>{listRows.length} students</p></div>
                  </div>
                  <div className="ma-panel-body" style={{ padding: "10px 12px", borderBottom: "1px solid #f0f2f6" }}>
                    <input
                      placeholder="Search a name"
                      value={listQ}
                      onChange={(e) => setListQ(e.target.value)}
                      style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: "100%" }}
                    />
                  </div>
                  {grouped.map(([year, list]) => (
                    <div key={year}>
                      <div className="ylabel">{yearLabel(year)} Year<span className="n">{list.length}</span></div>
                      {list.map((s) => (
                        <button
                          key={s.student_id}
                          className={`srow${current === s.student_id ? " on" : ""}`}
                          onClick={() => openStudent(s.student_id)}
                        >
                          <span className="av">
                            {s.student_name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase()}
                          </span>
                          <span>
                            <b>{s.student_name}</b>
                            <span className="m">{s.roll_number}</span>
                          </span>
                          <span className="g">
                            <span className={`ma-pill ${gradeClass(s.grade_band)}`}>{s.grade_band || "—"}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  ))}
                  {listRows.length === 0 && <div className="ma-empty">No name matches.</div>}
                </div>

                <div className="detail" style={{ flex: 1, minWidth: 0 }}>
                  {!current && (
                    <div className="ma-panel"><div className="ma-empty">
                      Pick a student on the left to see their details.
                    </div></div>
                  )}
                  {current && !detail && (
                    <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
                  )}
                  {detail && (
                    <>
                      <div className="ma-panel">
                        <div className="ma-panel-body">
                          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                            <div className="ma-avatar" style={{ width: 56, height: 56, borderRadius: "50%", fontSize: 17 }}>
                              {detail.student.name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase()}
                            </div>
                            <div>
                              <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>{detail.student.name}</h2>
                              <div style={{ fontSize: 12.5, color: "#6b7280" }}>
                                {detail.student.roll_number} · {yearLabel(detail.student.year)} Year ·
                                Semester {detail.student.semester} · {detail.student.course_name}
                              </div>
                            </div>
                            <div style={{ flex: 1 }} />
                            <span className={`ma-pill ${gradeClass(detail.allocation.grade_band)}`}>
                              {detail.allocation.grade_band || "—"}
                            </span>
                            <button className="ma-btn" onClick={() => openThread(detail.student.id)}>Message</button>
                          </div>
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
                        <div className="ma-panel">
                          <div className="ma-panel-head"><div><h3>Student details</h3><p>Read-only</p></div></div>
                          <div className="ma-panel-body">
                            <table className="ma-table"><tbody>
                              <tr><td style={{ color: "#6b7280" }}>Name</td><td><b>{detail.student.name}</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Register number</td><td><b>{detail.student.roll_number}</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Department</td><td><b>{detail.student.department}</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Course</td><td><b>{detail.student.course_name || "—"}</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Year</td><td><b>{yearLabel(detail.student.year)} Year</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Semester</td><td><b>{detail.student.semester}</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Email</td><td><b>{detail.student.email || "—"}</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Your mentee since</td><td><b>{detail.allocation.assigned_on}</b></td></tr>
                            </tbody></table>
                          </div>
                          <div className="ma-panel-foot">
                            Contact the office if a detail is wrong — it comes from the student record.
                          </div>
                        </div>

                        <div className="ma-panel">
                          <div className="ma-panel-head">
                            <div><h3>Academic summary</h3><p>From the attendance and results modules</p></div>
                          </div>
                          <div className="ma-panel-body">
                            <div style={{ display: "flex", gap: 20, marginBottom: 14 }}>
                              <div style={{ flex: 1 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 5 }}>
                                  <span>Attendance</span>
                                  <b>{detail.academics.attendance == null ? "—" : `${detail.academics.attendance}%`}</b>
                                </div>
                                <div className="ma-bar">
                                  <i className={detail.academics.attendance >= 80 ? "green" :
                                                detail.academics.attendance >= 75 ? "amber" : "red"}
                                     style={{ width: `${detail.academics.attendance || 0}%` }} />
                                </div>
                              </div>
                              <div style={{ flex: 1 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 5 }}>
                                  <span>CGPA</span>
                                  <b>{detail.academics.cgpa == null ? "—" : detail.academics.cgpa}</b>
                                </div>
                                <div className="ma-bar">
                                  <i style={{ width: `${(detail.academics.cgpa || 0) * 10}%` }} />
                                </div>
                              </div>
                            </div>

                            <table className="ma-table"><tbody>
                              <tr><td style={{ color: "#6b7280" }}>Backlogs</td>
                                  <td><b>{detail.academics.backlogs}</b></td></tr>
                              <tr><td style={{ color: "#6b7280" }}>Grade</td>
                                  <td><b>{detail.allocation.grade_band || "—"}</b>
                                  <span style={{ fontSize: 11.5, color: "#6b7280" }}> — frozen at allocation</span></td></tr>
                            </tbody></table>

                            {detail.academics.attendance != null && detail.academics.attendance < 75 && (
                              <div className="ma-note red" style={{ marginTop: 12 }}>
                                <b>Below the 75% requirement</b>
                                This is the first thing to raise when you meet.
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="ma-panel" style={{ marginTop: 16 }}>
                        <div className="ma-panel-head">
                          <div><h3>Published semester results</h3><p>Newest first</p></div>
                        </div>
                        <div className="ma-scroll">
                          <table className="ma-table">
                            <thead>
                              <tr><th>Semester</th><th>Percentage</th><th>Subjects</th><th>Backlogs</th></tr>
                            </thead>
                            <tbody>
                              {detail.academics.semesters.length === 0 && (
                                <tr><td colSpan={4} className="ma-empty">
                                  No published result yet.
                                </td></tr>
                              )}
                              {detail.academics.semesters.map((s) => (
                                <tr key={s.semester}>
                                  <td><b>Semester {s.semester}</b></td>
                                  <td className="num">{s.percentage}%</td>
                                  <td className="num">{s.subjects}</td>
                                  <td>
                                    {s.backlogs
                                      ? <span className="ma-pill ma-amber">{s.backlogs}</span>
                                      : <span className="num">0</span>}
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
            )}

            {/* ================= MESSAGES ================= */}
            {!loading && data && tab === "messages" && (
              <>
                <div className="ma-note blue" style={{ marginBottom: 16 }}>
                  <b>This is your existing LMS messaging, filtered to your mentees</b>
                  Not a second inbox. You can only message students currently allocated to you.
                </div>

                <div className="md">
                  <div className="ma-panel" style={{ flex: "0 0 300px", maxHeight: 660, overflowY: "auto" }}>
                    <div className="ma-panel-head" style={{ position: "sticky", top: 0, background: "#fff", zIndex: 3 }}>
                      <div>
                        <h3>Conversations</h3>
                        <p>{convoRows.length} · {unread} unread</p>
                      </div>
                    </div>
                    <div className="ma-panel-body" style={{ padding: "10px 12px", borderBottom: "1px solid #f0f2f6" }}>
                      <input
                        placeholder="Search a name"
                        value={convQ}
                        onChange={(e) => setConvQ(e.target.value)}
                        style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: "100%" }}
                      />
                    </div>
                    {convoRows.length === 0 && <div className="ma-empty">No conversation matches.</div>}
                    {convoRows.map((c) => (
                      <button
                        key={c.student_id}
                        className={`conv${openId === c.student_id ? " on" : ""}`}
                        onClick={() => openThread(c.student_id)}
                      >
                        <span className="av">
                          {c.student_name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase()}
                        </span>
                        <span className="bd">
                          <span className="tp">
                            <b>{c.student_name}</b>
                            {c.unread > 0 && <span className="un">{c.unread}</span>}
                            <span className="t">{when(c.last_at)}</span>
                          </span>
                          <span className="pv">
                            {c.last_message ? `${c.last_from_me ? "You: " : ""}${c.last_message}` : "No messages yet"}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>

                  <div className="thread" style={{ flex: 1, minWidth: 0 }}>
                    {!openId && (
                      <div className="ma-panel"><div className="ma-empty">
                        Pick a mentee on the left to open the conversation.
                      </div></div>
                    )}
                    {openId && !thread && (
                      <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
                    )}
                    {thread && (
                      <div className="ma-panel">
                        <div className="ma-panel-head">
                          <div className="ma-avatar" style={{ width: 38, height: 38, borderRadius: "50%", fontSize: 12 }}>
                            {thread.student.name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase()}
                          </div>
                          <div>
                            <h3 style={{ margin: 0 }}>{thread.student.name}</h3>
                            <p>{thread.student.roll_number} · {yearLabel(thread.student.year)} Year</p>
                          </div>
                          <div style={{ flex: 1 }} />
                          <button className="ma-btn small" onClick={() => openStudent(thread.student.id)}>
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
                                <span className="tm">{when(m.created_at)}</span>
                              </div>
                            </div>
                          ))}
                          <div ref={bottomRef} />
                        </div>

                        <div className="composer">
                          <textarea
                            value={draft}
                            placeholder="Write a reply…"
                            onChange={(e) => setDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
                            }}
                          />
                          <button className="ma-btn primary" onClick={doSend} disabled={busy}>Send</button>
                        </div>
                        <div className="ma-panel-foot">
                          Messages are kept on record and cannot be permanently deleted by either side.
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* ================= GROUPS ================= */}
            {!loading && data && tab === "groups" && (
              <>
                <div className="ma-note blue" style={{ marginBottom: 16 }}>
                  <b>Groups are generated from your allocation, not created by hand</b>
                  They update on their own when the HOD adds or moves a student.
                  There is nothing to maintain.
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1.25fr 1fr", gap: 16 }}>
                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div><h3>Send to a group</h3><p>One message, everyone in the group</p></div>
                    </div>
                    <div className="ma-panel-body">
                      <div style={{ marginBottom: 15 }}>
                        <span className="ma-label">Group</span>
                        <select
                          value={groupKey}
                          onChange={(e) => setGroupKey(e.target.value)}
                          style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: "100%" }}
                        >
                          {groups.map((g) => (
                            <option key={g.key} value={g.key}>{g.name} · {g.count} students</option>
                          ))}
                        </select>
                        {selectedGroup && (
                          <div style={{ fontSize: 11.5, color: "#6b7280", marginTop: 5 }}>
                            {selectedGroup.why} · {selectedGroup.count} students will receive this.
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
                            padding: "10px 12px", border: "1px solid #e6e9ef", borderRadius: 9,
                            width: "100%", minHeight: 90, fontFamily: "inherit", fontSize: 13.5,
                          }}
                        />
                      </div>

                      {selectedGroup && !selectedGroup.visible_to_student && (
                        <div className="ma-note amber" style={{ marginBottom: 15 }}>
                          <b>The group name is not shown to students</b>
                          They receive this as a normal message from you. A student should
                          never read a performance label attached to themselves.
                        </div>
                      )}

                      <button className="ma-btn primary" onClick={doBroadcast} disabled={busy}>
                        Send to group
                      </button>
                      <button className="ma-btn" style={{ marginLeft: 8 }} onClick={() => setGroupText("")}>
                        Clear
                      </button>
                    </div>
                    <div className="ma-panel-foot">
                      Group messages are one-to-many. Students never see each other's replies.
                    </div>
                  </div>

                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div><h3>My groups</h3><p>Built from your allocation</p></div>
                    </div>
                    <div className="ma-scroll">
                      <table className="ma-table">
                        <thead>
                          <tr><th>Group</th><th>Students</th><th>Student sees name</th><th></th></tr>
                        </thead>
                        <tbody>
                          {groups.length === 0 && (
                            <tr><td colSpan={4} className="ma-empty">No groups yet.</td></tr>
                          )}
                          {groups.map((g) => (
                            <tr key={g.key}>
                              <td><b>{g.name}</b><div style={{ fontSize: 11.5, color: "#6b7280" }}>{g.why}</div></td>
                              <td className="num">{g.count}</td>
                              <td>
                                <span className={`ma-pill ${g.visible_to_student ? "ma-green" : "ma-red"}`}>
                                  {g.visible_to_student ? "Yes" : "Hidden"}
                                </span>
                              </td>
                              <td className="ma-right">
                                <button className="ma-btn small" onClick={() => setGroupKey(g.key)}>Message</button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="ma-panel-foot">
                      A group is a saved query, not a member list, so it cannot drift out of date.
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