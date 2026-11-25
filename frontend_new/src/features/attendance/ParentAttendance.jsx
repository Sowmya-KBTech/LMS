import { useEffect, useRef, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";
import "../../styles/ParentModule.css";

// Semester choice (lead's decision 20-11-2026): the current semester by
// default, earlier semesters on request, or every record.
const CURRENT = "current";
const ALL = "all";

const fmt = (iso) => (iso ? iso.split("-").reverse().join("-") : "");   // 2026-07-01 -> 01-07-2026

export default function ParentAttendance() {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState([]);
  const [activeChild, setActiveChild] = useState(null);
  const [semesters, setSemesters] = useState(null);     // null = not loaded yet
  const [semChoice, setSemChoice] = useState(CURRENT);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const firstLoad = useRef(true);

  useEffect(() => {
    API.get("/parent/dashboard/")
      .then((res) => setChildren(res.data?.children || []))
      .catch(() => setChildren([]));
    API.get("/semester/all/")
      .then((res) => setSemesters(res.data?.results || res.data || []))
      .catch(() => setSemesters([]));
  }, []);

  // the semester that is in use now; if none is set, show every record
  const currentSem = (semesters || []).find((s) => s.is_active) || null;
  const chosenSem =
    semChoice === ALL ? null
      : semChoice === CURRENT ? currentSem
      : (semesters || []).find((s) => String(s.id) === String(semChoice)) || null;

  const fetchData = async (showLoading) => {
    const params = new URLSearchParams();
    if (activeChild) params.set("child", activeChild);
    if (chosenSem) {
      params.set("from_date", chosenSem.start_date);
      params.set("to_date", chosenSem.end_date);
    }
    const q = params.toString();
    try {
      if (showLoading) setLoading(true);
      const res = await API.get(`/attendance/${q ? `?${q}` : ""}`);
      setRecords(res.data?.results || res.data || []);
    } catch {
      /* keep what is on screen; the next refresh tries again */
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    if (semesters === null) return;          // wait until we know the semesters
    fetchData(true);
    const t = setInterval(() => fetchData(false), 15000);   // quiet refresh, no flicker
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChild, semChoice, semesters]);

  useEffect(() => {
    // no semester has been set up at all -> "All records" is the only sensible view
    if (semesters !== null && firstLoad.current) {
      firstLoad.current = false;
      if (!currentSem) setSemChoice(ALL);
    }
  }, [semesters, currentSem]);

  // ── overall totals ──
  const total = records.length;
  const present = records.filter((r) => (r.status || "").toLowerCase() === "present").length;
  const absent = total - present;

  // ── subject-wise breakdown ──
  const bySubject = {};
  records.forEach((r) => {
    const key = `${r.student_name} • ${r.subject_name}`;
    if (!bySubject[key]) {
      bySubject[key] = { child: r.student_name, subject: r.subject_name, total: 0, present: 0 };
    }
    bySubject[key].total += 1;
    if ((r.status || "").toLowerCase() === "present") bySubject[key].present += 1;
  });
  const subjectRows = Object.values(bySubject).map((s) => {
    const pct = s.total ? Math.round((s.present / s.total) * 100) : 0;
    return { ...s, absent: s.total - s.present, pct };
  });

  const pctBadge = (pct) => {
    if (pct >= 90) return "pm-badge green";
    if (pct >= 75) return "pm-badge yellow";
    return "pm-badge red";
  };

  const periodText = chosenSem
    ? `${chosenSem.name} (${fmt(chosenSem.start_date)} to ${fmt(chosenSem.end_date)})`
    : "All records";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="pm-page">

              <div className="pm-header">
                <h1>Attendance</h1>
                <p>Attendance records for your children</p>
              </div>

              <div className="pm-tabs">
                <div
                  className={`pm-tab ${activeChild === null ? "active" : ""}`}
                  onClick={() => setActiveChild(null)}
                >
                  All Children
                </div>
                {children.map((c) => (
                  <div
                    key={c.id}
                    className={`pm-tab ${activeChild === c.id ? "active" : ""}`}
                    onClick={() => setActiveChild(c.id)}
                  >
                    {c.username}
                  </div>
                ))}
              </div>

              {/* ── semester choice ── */}
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", margin: "4px 0 14px" }}>
                <label htmlFor="pm-sem" style={{ fontSize: 14, fontWeight: 600 }}>Semester</label>
                <select
                  id="pm-sem"
                  value={semChoice}
                  onChange={(e) => setSemChoice(e.target.value)}
                  style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #D5D3DE", fontSize: 14, minWidth: 220 }}
                >
                  {currentSem && <option value={CURRENT}>Current semester ({currentSem.name})</option>}
                  {(semesters || [])
                    .filter((s) => !s.is_active)
                    .map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  <option value={ALL}>All records</option>
                </select>
                <span style={{ fontSize: 13, color: "#5D5A6B" }}>Showing: {periodText}</span>
              </div>

              {loading ? (
                <div className="pm-loading">Loading attendance…</div>
              ) : (
                <>
                  <div className="pm-stat-grid three">
                    <div className="pm-stat-card">
                      <div className="pm-stat-label">Total classes</div>
                      <div className="pm-stat-val">{total}</div>
                    </div>
                    <div className="pm-stat-card">
                      <div className="pm-stat-label">Present</div>
                      <div className="pm-stat-val green">{present}</div>
                    </div>
                    <div className="pm-stat-card">
                      <div className="pm-stat-label">Absent</div>
                      <div className="pm-stat-val red">{absent}</div>
                    </div>
                  </div>

                  <div className="pm-card">
                    <div className="pm-card-title">Subject-wise attendance</div>
                    {subjectRows.length === 0 ? (
                      <div className="pm-empty">No attendance recorded for this period</div>
                    ) : (
                      <table className="pm-table">
                        <thead>
                          <tr>
                            <th>Child</th><th>Subject</th><th>Total</th>
                            <th>Present</th><th>Absent</th><th>%</th><th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {subjectRows.map((s, i) => (
                            <tr key={i}>
                              <td>{s.child}</td>
                              <td>{s.subject}</td>
                              <td>{s.total}</td>
                              <td>{s.present}</td>
                              <td>{s.absent}</td>
                              <td>{s.pct}%</td>
                              <td><span className={pctBadge(s.pct)}>
                                {s.pct >= 90 ? "Good" : s.pct >= 75 ? "Average" : "Low"}
                              </span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}