import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../App.css";

const CATEGORIES = [
  { value: "", label: "All types" },
  { value: "fdp", label: "FDP / Training Attended" },
  { value: "workshop_attended", label: "Workshop / Seminar Attended" },
  { value: "workshop_conducted", label: "Workshop / Seminar Conducted" },
  { value: "conference", label: "Conference Paper Presented" },
  { value: "journal", label: "Journal Publication" },
  { value: "certification", label: "Certification / MOOC" },
  { value: "guest_lecture", label: "Guest Lecture Delivered" },
  { value: "committee", label: "Committee / Cell Membership" },
  { value: "project", label: "Project / Grant / Consultancy" },
  { value: "other", label: "Other" },
];

export default function IqacDashboard() {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  // filters
  const [year, setYear] = useState("");
  const [category, setCategory] = useState("");
  const [teacher, setTeacher] = useState("");

  const loadSummary = async (yr) => {
    try {
      const q = yr ? `?year=${yr}` : "";
      const r = await API.get(`users/iqac/participation/summary/${q}`);
      setSummary(r.data || null);
    } catch (err) {
      console.error("Summary error:", err);
      setSummary(null);
    }
  };

  const loadList = async () => {
    setLoading(true);
    try {
      const params = [];
      if (year) params.push(`year=${year}`);
      if (category) params.push(`category=${category}`);
      if (teacher) params.push(`teacher=${teacher}`);
      const q = params.length ? `?${params.join("&")}` : "";
      const r = await API.get(`users/iqac/participation/${q}`);
      setRows(r.data || []);
    } catch (err) {
      console.error("List error:", err);
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary("");
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, category, teacher]);

  useEffect(() => {
    loadSummary(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  // ---------- PRINT REPORT ----------
  const printReport = () => {
    if (!summary) return;
    const yearLabel = year || "All Academic Years";
    const today = new Date().toLocaleDateString();

    const catRows = (summary.by_category || [])
      .map((c) => `<tr><td>${c.label}</td><td style="text-align:right">${c.count}</td></tr>`)
      .join("");

    const deptRows = (summary.by_department || [])
      .map((d) => `<tr><td>${d.department}</td><td style="text-align:right">${d.count}</td></tr>`)
      .join("");

    const teacherRows = (summary.by_teacher || [])
      .map(
        (t) =>
          `<tr><td>${t.name}</td><td>${t.employee_id || "—"}</td><td>${t.department}</td><td style="text-align:right">${t.count}</td></tr>`
      )
      .join("");

    const html = `
      <html>
      <head>
        <title>IQAC Faculty Participation Report</title>
        <style>
          body { font-family: Arial, sans-serif; color: #17151F; padding: 32px; }
          h1 { font-size: 22px; margin: 0 0 4px; }
          .sub { color: #5D5A6B; font-size: 14px; margin-bottom: 24px; }
          h2 { font-size: 15px; margin: 26px 0 8px; border-bottom: 2px solid #E7E7EC; padding-bottom: 4px; }
          table { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 14px; }
          th, td { border: 1px solid #E7E7EC; padding: 7px 10px; text-align: left; }
          th { background: #F6F6F8; }
          .stat { display: inline-block; margin-right: 28px; }
          .stat b { font-size: 22px; display: block; }
          .stat span { font-size: 13px; color: #5D5A6B; }
          @media print { button { display: none; } }
        </style>
      </head>
      <body>
        <h1>IQAC — Faculty Participation Report</h1>
        <div class="sub">Academic Year: ${yearLabel} &nbsp;•&nbsp; Generated: ${today}</div>

        <div>
          <div class="stat"><b>${summary.total ?? 0}</b><span>Total Activities</span></div>
          <div class="stat"><b>${summary.by_teacher?.length ?? 0}</b><span>Faculty Involved</span></div>
          <div class="stat"><b>${summary.by_department?.length ?? 0}</b><span>Departments</span></div>
        </div>

        <h2>By Department</h2>
        <table>
          <thead><tr><th>Department</th><th style="text-align:right">Activities</th></tr></thead>
          <tbody>${deptRows || '<tr><td colspan="2">No data</td></tr>'}</tbody>
        </table>

        <h2>By Category</h2>
        <table>
          <thead><tr><th>Category</th><th style="text-align:right">Activities</th></tr></thead>
          <tbody>${catRows || '<tr><td colspan="2">No data</td></tr>'}</tbody>
        </table>

        <h2>By Faculty</h2>
        <table>
          <thead><tr><th>Faculty</th><th>Employee ID</th><th>Department</th><th style="text-align:right">Activities</th></tr></thead>
          <tbody>${teacherRows || '<tr><td colspan="4">No data</td></tr>'}</tbody>
        </table>
      </body>
      </html>
    `;

    const w = window.open("", "_blank");
    if (!w) return;
    w.document.write(html);
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="sd-root">

              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <h1 className="sd-hello">IQAC — Faculty Participation</h1>
                  <p className="sd-sub">All faculty activities recorded for NAAC, with totals.</p>
                </div>
                <button
                  onClick={printReport}
                  disabled={!summary || summary.total === 0}
                  style={{
                    background: (!summary || summary.total === 0) ? "#cbd5e1" : "#4B32C3",
                    color: "#fff", border: "none", borderRadius: 8, padding: "10px 18px",
                    fontSize: 14, fontWeight: 600, cursor: (!summary || summary.total === 0) ? "default" : "pointer",
                    marginTop: 6, whiteSpace: "nowrap",
                  }}
                >
                  Print / Save Report
                </button>
              </div>

              {/* ===== TOP STATS ===== */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16, marginTop: 8 }}>
                <div className="sd-card">
                  <div className="sd-label">Total Activities</div>
                  <div className="sd-val">{summary?.total ?? "—"}</div>
                </div>
                <div className="sd-card">
                  <div className="sd-label">Faculty Involved</div>
                  <div className="sd-val">{summary?.by_teacher?.length ?? "—"}</div>
                </div>
                <div className="sd-card">
                  <div className="sd-label">Academic Year</div>
                  <div className="sd-val" style={{ fontSize: 20 }}>
                    <select value={year} onChange={(e) => setYear(e.target.value)} style={{ fontSize: 15, padding: "4px 6px" }}>
                      <option value="">All years</option>
                      {(summary?.years || []).map((y) => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                </div>
              </div>

              {/* ===== BY DEPARTMENT ===== */}
              <div className="sd-panel" style={{ marginBottom: 16 }}>
                <div className="sd-pt">By department</div>
                {summary?.by_department?.length ? (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
                    {summary.by_department.map((d) => (
                      <div key={d.department} style={{ border: "1px solid #eaecf0", borderRadius: 10, padding: "12px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: "#17151F" }}>{d.department}</span>
                        <span style={{ fontSize: 20, fontWeight: 700, color: "#0e9384" }}>{d.count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="sd-empty">No activities recorded yet.</div>
                )}
              </div>

              {/* ===== BY CATEGORY ===== */}
              <div className="sd-panel" style={{ marginBottom: 16 }}>
                <div className="sd-pt">By category</div>
                {summary?.by_category?.length ? (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
                    {summary.by_category.map((c) => (
                      <div key={c.category} style={{ border: "1px solid #eaecf0", borderRadius: 10, padding: "10px 12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 14, color: "#17151F" }}>{c.label}</span>
                        <span style={{ fontSize: 18, fontWeight: 700, color: "#4B32C3" }}>{c.count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="sd-empty">No activities recorded yet.</div>
                )}
              </div>

              {/* ===== PER TEACHER ===== */}
              <div className="sd-panel" style={{ marginBottom: 16 }}>
                <div className="sd-pt">By faculty</div>
                {summary?.by_teacher?.length ? (
                  <table className="sd-tbl">
                    <thead>
                      <tr>
                        <th>Faculty</th>
                        <th>Employee ID</th>
                        <th>Department</th>
                        <th style={{ textAlign: "right" }}>Activities</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.by_teacher.map((t) => (
                        <tr key={t.id} onClick={() => setTeacher(String(t.id))} style={{ cursor: "pointer" }}>
                          <td>{t.name}</td>
                          <td className="sd-num">{t.employee_id || "—"}</td>
                          <td>{t.department}</td>
                          <td className="sd-num" style={{ textAlign: "right", fontWeight: 700 }}>{t.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="sd-empty">No faculty activities yet.</div>
                )}
              </div>

              {/* ===== FULL LIST + FILTERS ===== */}
              <div className="sd-panel">
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
                  <div className="sd-pt" style={{ margin: 0 }}>All activities ({rows.length})</div>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <select value={category} onChange={(e) => setCategory(e.target.value)}>
                      {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                    {teacher && (
                      <button
                        onClick={() => setTeacher("")}
                        style={{ background: "#fff", color: "#5D5A6B", border: "1px solid #d8dee9", borderRadius: 8, padding: "6px 12px", fontSize: 14, cursor: "pointer" }}
                      >
                        Clear faculty filter
                      </button>
                    )}
                  </div>
                </div>

                {loading ? (
                  <div className="sd-empty">Loading…</div>
                ) : rows.length === 0 ? (
                  <div className="sd-empty">No activities match.</div>
                ) : (
                  <table className="sd-tbl">
                    <thead>
                      <tr>
                        <th>Faculty</th>
                        <th>Title</th>
                        <th>Type</th>
                        <th>Role</th>
                        <th>Date</th>
                        <th>Proof</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.id}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{r.faculty_name}</div>
                            <div style={{ fontSize: 13, color: "#5D5A6B" }}>{r.department_name || "—"}</div>
                          </td>
                          <td>
                            <div>{r.title}</div>
                            {r.organizer && <div style={{ fontSize: 13, color: "#5D5A6B" }}>{r.organizer}</div>}
                          </td>
                          <td>{r.category_label}</td>
                          <td>{r.role_label}</td>
                          <td className="sd-num">{r.date ? String(r.date).slice(0, 10).split("-").reverse().join("-") : ""}</td>
                          <td>
                            {r.proof_url ? (
                              <a href={r.proof_url} target="_blank" rel="noreferrer" style={{ color: "#4B32C3", fontSize: 14 }}>View</a>
                            ) : (
                              <span style={{ color: "#85839A", fontSize: 14 }}>—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}