// frontend/src/features/mentoring/HodAllocationHistory.jsx
import { useCallback, useEffect, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";

import { errorText, getHistory, getOptions, prettyYear } from "./mentoringApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

const onDate = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
  });
};

export default function HodAllocationHistory() {
  const [open, setOpen] = useState(false);

  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [years, setYears] = useState([]);

  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [changedBy, setChangedBy] = useState("all");
  const [academicYear, setAcademicYear] = useState("all");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getOptions()
      .then((d) => setYears(d.academic_years || []))
      .catch(() => setYears([]));
  }, []);

  // debounce the search box — one request per pause, not per keystroke
  useEffect(() => {
    const t = setTimeout(() => setQ(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await getHistory({
        q,
        changed_by: changedBy,
        academic_year: academicYear,
      });
      setRows(d.results || []);
      setCount(d.count || 0);
    } catch (err) {
      setError(errorText(err, "Could not load the history."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [q, changedBy, academicYear]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    const head = [
      "Date", "Student", "Register No", "Old Mentor", "New Mentor",
      "Reason", "Recommended By", "Academic Year", "Status",
    ];
    const body = rows.map((r) => [
      onDate(r.updated_at), r.student_name, r.student_roll || "",
      r.previous_mentor_name || "", r.mentor_name,
      `"${(r.reason || "").replace(/"/g, "'")}"`,
      r.recommended_by || "", r.academic_year, r.status,
    ]);
    const csv = [head, ...body].map((x) => x.join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "allocation-history.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2 style={{ margin: 0 }}>Allocation History</h2>
              <p>Every change, who made it and why</p>
            </div>

            <MentoringTabs />

            <div className="ma-note blue" style={{ marginBottom: 16 }}>
              <b>Nothing is ever deleted</b>
              Remove closes an allocation and Reassign opens a new one, so every
              change leaves a row here. This is the audit trail if an allocation is
              ever questioned.
            </div>

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>{error}
              </div>
            )}

            <div className="ma-panel">
              <div className="ma-panel-body">
                <div className="ma-filters">
                  <div className="ma-grow">
                    <span className="ma-label">Search</span>
                    <input
                      value={search}
                      placeholder="Student, mentor or reason"
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <div>
                    <span className="ma-label">Changed by</span>
                    <select value={changedBy} onChange={(e) => setChangedBy(e.target.value)}>
                      <option value="all">Anyone</option>
                      <option value="hod">HOD</option>
                      <option value="advisor">Class advisor</option>
                      <option value="auto">Auto-distributed</option>
                    </select>
                  </div>
                  <div>
                    <span className="ma-label">Academic Year</span>
                    <select value={academicYear} onChange={(e) => setAcademicYear(e.target.value)}>
                      <option value="all">All years</option>
                      {years.map((y) => (
                        <option key={y} value={y}>{prettyYear(y)}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    className="ma-btn"
                    onClick={() => {
                      setSearch(""); setQ(""); setChangedBy("all"); setAcademicYear("all");
                    }}
                  >
                    Reset
                  </button>
                  <button className="ma-btn" onClick={exportCsv} disabled={!rows.length}>
                    Export CSV
                  </button>
                </div>
              </div>
            </div>

            <div className="ma-panel">
              <div className="ma-panel-head">
                <div><h3>Allocation history</h3><p>{count} entries</p></div>
              </div>
              <div className="ma-scroll">
                <table className="ma-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Student</th>
                      <th>Old mentor</th>
                      <th></th>
                      <th>New mentor</th>
                      <th>Reason</th>
                      <th>Recommended by</th>
                      <th>Academic Year</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr><td colSpan={8} className="ma-empty">Loading…</td></tr>
                    )}
                    {!loading && rows.length === 0 && (
                      <tr><td colSpan={8} className="ma-empty">No entry matches.</td></tr>
                    )}
                    {!loading && rows.map((r) => (
                      <tr key={r.id}>
                        <td style={{ whiteSpace: "nowrap", fontSize: 12 }}>
                          {onDate(r.updated_at)}
                        </td>
                        <td>
                          <b>{r.student_name}</b>
                          <div style={{ fontSize: 11.5, color: "#6b7280" }}>
                            {r.student_roll}
                          </div>
                        </td>
                        <td style={{ fontSize: 12, color: "#6b7280" }}>
                          {r.previous_mentor_name || "—"}
                        </td>
                        <td style={{ color: "#9ca3af" }}>→</td>
                        <td style={{ fontSize: 12 }}><b>{r.mentor_name}</b></td>
                        <td style={{ fontSize: 12, color: "#6b7280", maxWidth: 280 }}>
                          {r.reason || "—"}
                        </td>
                        <td style={{ fontSize: 12, color: "#6b7280" }}>
                          {r.recommended_by || "—"}
                        </td>
                        <td className="num" style={{ whiteSpace: "nowrap" }}>
                          {prettyYear(r.academic_year)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="ma-panel-foot">
                Kept indefinitely. A closed allocation stays readable after the
                student graduates.
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}