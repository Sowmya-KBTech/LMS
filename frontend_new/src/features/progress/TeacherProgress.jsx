import React, { useEffect, useState } from "react";
import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import "../../styles/Progress.css";

// ── helpers ───────────────────────────────────────────────────────────────────
function valCls(v) {
  const n = Number(v) || 0;
  return n >= 75 ? "good" : n >= 50 ? "warn" : "low";
}

function Bar({ value, color }) {
  const pct = Math.min(Math.max(Number(value) || 0, 0), 100);
  return (
    <div className="prg-bar-track">
      <div className="prg-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

// ── student row in the table ──────────────────────────────────────────────────
function StudentRow({ student, index, expanded, onToggle }) {
  const metrics = [
    { label: "Attendance",   key: "attendance_percent",  color: "#4B32C3" },
    { label: "Assignments",  key: "assignment_percent",  color: "#16a34a" },
    { label: "Quiz Average", key: "quiz_average",        color: "#d97706" },
  ];

  const overall = Math.min(Math.max(Number(student.overall_progress) || 0, 0), 100);
  const hasPending = student.pending_activities?.length > 0;

  return (
    <>
      {/* ── Main row ── */}
      <tr
        className={`tp-row${expanded ? " expanded" : ""}`}
        onClick={onToggle}
      >
        <td className="tp-td-num">{index + 1}</td>

        {/* Name + avatar */}
        <td className="tp-td-name">
          <div className="tp-name-cell">
            <div className="tp-avatar">
              {(student.student_name || "?").charAt(0).toUpperCase()}
            </div>
            <div>
              <span className="tp-student-name">{student.student_name}</span>
              {student.roll_no && (
                <span className="tp-roll">{student.roll_no}</span>
              )}
            </div>
          </div>
        </td>

        {/* Attendance */}
        <td className="tp-td-metric">
          <span className={`tp-pct ${valCls(student.attendance_percent)}`}>
            {Number(student.attendance_percent) || 0}%
          </span>
          <Bar value={student.attendance_percent} color="#4B32C3" />
        </td>

        {/* Assignments */}
        <td className="tp-td-metric">
          <span className={`tp-pct ${valCls(student.assignment_percent)}`}>
            {Number(student.assignment_percent) || 0}%
          </span>
          <Bar value={student.assignment_percent} color="#16a34a" />
        </td>

        {/* Quiz */}
        <td className="tp-td-metric">
          <span className={`tp-pct ${valCls(student.quiz_average)}`}>
            {Number(student.quiz_average) || 0}%
          </span>
          <Bar value={student.quiz_average} color="#d97706" />
        </td>

        {/* Overall badge */}
        <td className="tp-td-overall">
          <span className={`tp-overall-pill ${valCls(overall)}`}>
            {overall}%
          </span>
        </td>

        {/* Pending count */}
        <td className="tp-td-pending">
          {hasPending ? (
            <span className="tp-pending-pill">
              {student.pending_activities.length} pending
            </span>
          ) : (
            <span className="tp-no-pending">—</span>
          )}
        </td>

        {/* Expand toggle */}
        <td className="tp-td-toggle">
          <button className={`tp-toggle-btn${expanded ? " open" : ""}`}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
              width="14" height="14">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </td>
      </tr>

      {/* ── Expanded pending activities ── */}
      {expanded && (
        <tr className="tp-expand-row">
          <td colSpan={8}>
            <div className="tp-expand-wrap">
              <div className="tp-expand-inner">
                <h4 className="tp-expand-title">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2" width="14" height="14">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12 6 12 12 16 14"/>
                  </svg>
                  Pending Activities
                  {hasPending && (
                    <span className="tp-expand-count">
                      {student.pending_activities.length}
                    </span>
                  )}
                </h4>

                {!hasPending ? (
                  <p className="tp-expand-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="2" width="14" height="14">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                    No pending activities — all caught up!
                  </p>
                ) : (
                  <table className="tp-pending-table">
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Title</th>
                        <th>Due Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {student.pending_activities.map((a, i) => (
                        <tr key={i}>
                          <td>
                            <span className={`prg-type-badge ${(a.type || "").toLowerCase()}`}>
                              {a.type}
                            </span>
                          </td>
                          <td className="prg-td-title">{a.title}</td>
                          <td className="prg-td-date">
                            {a.due_date
                              ? new Date(a.due_date).toLocaleDateString()
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── main component ────────────────────────────────────────────────────────────
export default function TeacherProgress() {
  const [open, setOpen]               = useState(false);
  const [classes, setClasses]         = useState([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [students, setStudents]       = useState([]);
  const [loading, setLoading]         = useState(false);
  const [search, setSearch]           = useState("");
  const [expandedRow, setExpandedRow] = useState(null);

  useEffect(() => { loadClasses(); }, []);

  const loadClasses = async () => {
    try {
      const res = await API.get("/teaching-assignments/?my=true");
      setClasses(res.data?.results || res.data || []);
    } catch (err) { console.log(err); }
  };

  const loadProgress = async (taId) => {
    if (!taId) { setStudents([]); return; }
    setLoading(true);
    setExpandedRow(null);
    try {
      const res = await API.get(`/class-progress/?teaching_assignment=${taId}`);
      setStudents(res.data || []);
    } catch (err) { console.log(err); setStudents([]); }
    finally { setLoading(false); }
  };

  const filtered = students.filter((s) =>
    (s.student_name || "").toLowerCase().includes(search.toLowerCase())
  );

  const avg = (key) =>
    students.length
      ? (students.reduce((s, r) => s + Number(r[key] || 0), 0) / students.length).toFixed(1)
      : "—";

  const totalPending = students.reduce(
    (sum, s) => sum + (s.pending_activities?.length || 0), 0
  );

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="prg-page">

              {/* ── Page Header ── */}
              <div className="prg-header">
                <div>
                  <h1 className="prg-title">Student Progress</h1>
                  <p className="prg-subtitle">
                    View student performance, attendance, assignments and quizzes
                  </p>
                </div>
              </div>

              {/* ── Filter card ── */}
              <div className="prg-filter-card">
                <div className="prg-field">
                  <label className="prg-label">Select Class</label>
                  <select
                    className="prg-select"
                    value={selectedClass}
                    onChange={(e) => {
                      setSelectedClass(e.target.value);
                      loadProgress(e.target.value);
                      setSearch("");
                    }}
                  >
                    <option value="">— Choose a class —</option>
                    {classes.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.subject_name} | {c.course_name}
                      </option>
                    ))}
                  </select>
                </div>

                {students.length > 0 && (
                  <div className="prg-field">
                    <label className="prg-label">Search Student</label>
                    <div className="prg-search-wrap">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                        strokeWidth="2" width="15" height="15">
                        <circle cx="11" cy="11" r="8"/>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                      </svg>
                      <input
                        className="prg-search"
                        type="text"
                        placeholder="Search by name…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* ── Summary stat cards ── */}
              {!loading && students.length > 0 && (
                <div className="prg-summary-row">
                  <div className="prg-summary-card">
                    <span className="prg-summary-num">{students.length}</span>
                    <span className="prg-summary-label">Students</span>
                  </div>
                  <div className="prg-summary-card">
                    <span className={`prg-summary-num ${valCls(avg("attendance_percent"))}`}>
                      {avg("attendance_percent")}%
                    </span>
                    <span className="prg-summary-label">Avg Attendance</span>
                  </div>
                  <div className="prg-summary-card">
                    <span className={`prg-summary-num ${valCls(avg("assignment_percent"))}`}>
                      {avg("assignment_percent")}%
                    </span>
                    <span className="prg-summary-label">Avg Assignments</span>
                  </div>
                  <div className="prg-summary-card">
                    <span className={`prg-summary-num ${valCls(avg("quiz_average"))}`}>
                      {avg("quiz_average")}%
                    </span>
                    <span className="prg-summary-label">Avg Quiz</span>
                  </div>
                  <div className="prg-summary-card">
                    <span className={`prg-summary-num${totalPending > 0 ? " low" : " good"}`}>
                      {totalPending}
                    </span>
                    <span className="prg-summary-label">Pending Tasks</span>
                  </div>
                </div>
              )}

              {/* ── States ── */}
              {loading && (
                <div className="prg-state">
                  <div className="prg-spinner" />
                  <p>Loading progress data…</p>
                </div>
              )}

              {!loading && !selectedClass && (
                <div className="prg-state">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="1.5" width="44" height="44" style={{ color: "#cbd5e1" }}>
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                  <p>Select a class above to view student progress.</p>
                </div>
              )}

              {!loading && selectedClass && students.length === 0 && (
                <div className="prg-state">
                  <p>No students found for this class.</p>
                </div>
              )}

              {/* ── Student table ── */}
              {!loading && filtered.length > 0 && (
                <div className="tp-table-card">
                  <div className="tp-table-header">
                    <span className="tp-table-title">
                      Class Overview
                    </span>
                    <span className="tp-table-hint">
                      Click a row to view pending activities
                    </span>
                  </div>

                  <div className="tp-table-wrap">
                    <table className="tp-table">
                      {/* colgroup pins every column's width for BOTH header
                          and body. Widths sum to exactly 100% so table-layout:
                          fixed has no leftover space to distribute — headers
                          sit directly above their data with zero drift.
                          Order: #, Student, Attendance, Assignments, Quiz,
                          Overall, Pending, toggle. */}
                      <colgroup>
                        <col style={{ width: "5%" }} />
                        <col style={{ width: "33%" }} />
                        <col style={{ width: "52%" }} />
                        <col style={{ width: "25%" }} />
                        <col style={{ width: "25%" }} />
                        <col style={{ width: "25%" }} />
                        <col style={{ width: "10%" }} />
                        <col style={{ width: "5%" }} />
                      </colgroup>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Student</th>
                          <th>Attendance</th>
                          <th>Assignments</th>
                          <th>Quiz Avg</th>
                          <th>Overall</th>
                          <th>Pending</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((student, idx) => (
                          <StudentRow
                            key={idx}
                            student={student}
                            index={idx}
                            expanded={expandedRow === idx}
                            onToggle={() =>
                              setExpandedRow(expandedRow === idx ? null : idx)
                            }
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {!loading && search && filtered.length === 0 && students.length > 0 && (
                <div className="prg-state">
                  <p>No students match "{search}".</p>
                </div>
              )}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}