import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../App.css";

const YEARS = [
  { value: "", label: "All years" },
  { value: "1", label: "1st Year" },
  { value: "2", label: "2nd Year" },
  { value: "3", label: "3rd Year" },
  { value: "4", label: "4th Year" },
];

function pct(v) {
  return v === null || v === undefined ? "—" : `${v}%`;
}

// colour a pass % : green >=75, amber 50-75, red <50
function passColor(v) {
  if (v === null || v === undefined) return "#85839A";
  if (v >= 75) return "#0f6e56";
  if (v >= 50) return "#8A4B0A";
  return "#B42318";
}

export default function AcademicQuality() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState("");

  const load = async (yr) => {
    setLoading(true);
    try {
      const q = yr ? `?year=${yr}` : "";
      const r = await API.get(`users/iqac/academic-quality/${q}`);
      setData(r.data || null);
    } catch (err) {
      console.error("Academic quality error:", err);
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  const college = data?.college;
  const departments = data?.departments || [];

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
                  <h1 className="sd-hello">IQAC — Academic Quality</h1>
                  <p className="sd-sub">College-wide results and arrears, by department and year (NAAC Criterion 2).</p>
                </div>
                <div style={{ marginTop: 6 }}>
                  <select value={year} onChange={(e) => setYear(e.target.value)} style={{ fontSize: 14, padding: "6px 10px" }}>
                    {YEARS.map((y) => <option key={y.value} value={y.value}>{y.label}</option>)}
                  </select>
                </div>
              </div>

              {/* ===== COLLEGE TOTALS ===== */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, margin: "8px 0 16px" }}>
                <div className="sd-card">
                  <div className="sd-label">Students</div>
                  <div className="sd-val">{college?.student_count ?? "—"}</div>
                </div>
                <div className="sd-card">
                  <div className="sd-label">Overall Pass %</div>
                  <div className="sd-val" style={{ color: passColor(college?.pass_percent) }}>{pct(college?.pass_percent)}</div>
                </div>
                <div className="sd-card">
                  <div className="sd-label">Total Arrears</div>
                  <div className="sd-val" style={{ color: college?.arrears ? "#B42318" : undefined }}>{college?.arrears ?? "—"}</div>
                </div>
                <div className="sd-card">
                  <div className="sd-label">Departments</div>
                  <div className="sd-val">{college?.departments ?? "—"}</div>
                </div>
              </div>

              {loading ? (
                <div className="sd-panel"><div className="sd-empty">Loading…</div></div>
              ) : departments.length === 0 ? (
                <div className="sd-panel"><div className="sd-empty">No published results yet.</div></div>
              ) : (
                departments.map((dept) => (
                  <div key={dept.id} className="sd-panel" style={{ marginBottom: 14 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
                      <div className="sd-pt" style={{ margin: 0 }}>{dept.name}</div>
                      <div style={{ display: "flex", gap: 16, fontSize: 13.5, color: "#475467" }}>
                        <span>{dept.student_count} students</span>
                        <span>Pass: <b style={{ color: passColor(dept.pass_percent) }}>{pct(dept.pass_percent)}</b></span>
                        <span>Arrears: <b style={{ color: dept.arrears ? "#B42318" : "#475467" }}>{dept.arrears}</b></span>
                      </div>
                    </div>

                    <table className="sd-tbl">
                      <thead>
                        <tr>
                          <th>Year</th>
                          <th style={{ textAlign: "right" }}>Students</th>
                          <th style={{ textAlign: "right" }}>Evaluated</th>
                          <th style={{ textAlign: "right" }}>Pass %</th>
                          <th style={{ textAlign: "right" }}>Arrears</th>
                          <th style={{ textAlign: "right" }}>Attendance %</th>
                          <th>Weak subjects</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dept.years.map((y) => (
                          <tr key={y.year}>
                            <td style={{ fontWeight: 600 }}>Year {y.year}</td>
                            <td className="sd-num" style={{ textAlign: "right" }}>{y.student_count}</td>
                            <td className="sd-num" style={{ textAlign: "right" }}>{y.evaluated}</td>
                            <td className="sd-num" style={{ textAlign: "right", fontWeight: 700, color: passColor(y.pass_percent) }}>{pct(y.pass_percent)}</td>
                            <td className="sd-num" style={{ textAlign: "right", color: y.arrears ? "#B42318" : undefined }}>{y.arrears}</td>
                            <td className="sd-num" style={{ textAlign: "right" }}>{pct(y.attendance_percent)}</td>
                            <td>
                              {y.weak_subjects && y.weak_subjects.length ? (
                                <span style={{ fontSize: 13.5, color: "#475467" }}>
                                  {y.weak_subjects.map((w) => `${w.subject} (${w.fails})`).join(", ")}
                                </span>
                              ) : (
                                <span style={{ color: "#85839A", fontSize: 13.5 }}>—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))
              )}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}