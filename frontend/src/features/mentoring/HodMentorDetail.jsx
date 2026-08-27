// frontend/src/features/mentoring/HodMentorDetail.jsx
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";

import { bandClass, errorText, getMentor, prettyYear, yearLabel } from "./mentoringApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

export default function HodMentorDetail() {
  const [open, setOpen] = useState(false);
  const { mentorId } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getMentor(mentorId));
    } catch (err) {
      setError(errorText(err, "Could not load this mentor."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [mentorId]);

  useEffect(() => {
    load();
  }, [load]);

  const cap = data?.capacity || {};
  const comp = data?.composition || {};
  const students = (data?.students || []).filter((s) => {
    if (!q) return true;
    const t = q.toLowerCase();
    return (
      (s.student_name || "").toLowerCase().includes(t) ||
      (s.student_roll || "").toLowerCase().includes(t)
    );
  });

  const pct = cap.capacity ? Math.min(100, (cap.assigned / cap.capacity) * 100) : 0;
  const capPill = cap.is_full ? "ma-red" : cap.available <= 3 ? "ma-amber" : "ma-green";
  const capWord = cap.is_full ? "Full" : cap.available <= 3 ? "Nearly full" : "Available";
  const balPill =
    comp.state === "ok" ? "ma-green" : comp.state === "warn" ? "ma-amber" : "ma-red";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2 style={{ margin: 0 }}>Mentor Details</h2>
              <p>
                {data?.mentor?.name
                  ? `${data.mentor.name} · ${cap.assigned} active mentees`
                  : "Loading…"}
              </p>
            </div>

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>
                {error}
              </div>
            )}

            {loading && (
              <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
            )}

            {!loading && data && (
              <>
                {/* ================= HEADER ================= */}
                <div className="ma-panel">
                  <div className="ma-panel-body">
                    <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                      <div className="ma-avatar" style={{ width: 56, height: 56, borderRadius: "50%", fontSize: 17 }}>
                        {(data.mentor.name || "?").slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
                          {data.mentor.name}
                        </h2>
                        <div style={{ fontSize: 12.5, color: "#6b7280" }}>
                          {data.mentor.designation || "Teacher"} · {data.mentor.department}
                        </div>
                      </div>
                      <div style={{ flex: 1 }} />
                      <span className={`ma-pill ${capPill}`}>
                        {cap.assigned} / {cap.capacity} · {capWord}
                      </span>
                      <span className={`ma-pill ${balPill}`}>{comp.message}</span>
                      <button className="ma-btn" onClick={() => navigate("/hod/mentor-allocation")}>
                        Back to allocations
                      </button>
                    </div>
                  </div>
                </div>

                {/* ================= DETAILS + CAPACITY ================= */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
                  <div className="ma-panel">
                    <div className="ma-panel-head"><div><h3>Mentor details</h3></div></div>
                    <div className="ma-panel-body">
                      <table className="ma-table">
                        <tbody>
                          <tr><td style={{ color: "#6b7280" }}>Mentor name</td><td><b>{data.mentor.name}</b></td></tr>
                          <tr><td style={{ color: "#6b7280" }}>Employee ID</td><td><b>{data.mentor.employee_id || "—"}</b></td></tr>
                          <tr><td style={{ color: "#6b7280" }}>Designation</td><td><b>{data.mentor.designation || "—"}</b></td></tr>
                          <tr><td style={{ color: "#6b7280" }}>Department</td><td><b>{data.mentor.department}</b></td></tr>
                          <tr><td style={{ color: "#6b7280" }}>Email</td><td><b>{data.mentor.email || "—"}</b></td></tr>
                          <tr><td style={{ color: "#6b7280" }}>Academic year</td><td><b>{prettyYear(data.academic_year)}</b></td></tr>
                          <tr><td style={{ color: "#6b7280" }}>Active mentees</td><td><b>{cap.assigned}</b></td></tr>
                          <tr>
                            <td style={{ color: "#6b7280" }}>Previous year</td>
                            <td>
                              <b>
                                {data.previous_year?.count
                                  ? `${data.previous_year.count} students in ${prettyYear(data.previous_year.academic_year)}`
                                  : "No allocation last year"}
                              </b>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div><h3>Capacity and composition</h3><p>{prettyYear(data.academic_year)}</p></div>
                    </div>
                    <div className="ma-panel-body">
                      <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 16 }}>
                        <div>
                          <div style={{ fontSize: 34, fontWeight: 700, lineHeight: 1 }}>
                            {cap.assigned}
                            <span style={{ fontSize: 17, color: "#6b7280", fontWeight: 600 }}>
                              {" "}/ {cap.capacity}
                            </span>
                          </div>
                          <div style={{ fontSize: 11.5, color: "#6b7280" }}>students assigned</div>
                        </div>
                        <div style={{ flex: 1 }}>
                          <div className="ma-bar" style={{ height: 11 }}>
                            <i
                              className={cap.is_full ? "red" : cap.available <= 3 ? "amber" : "green"}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <div style={{ fontSize: 11.5, color: "#6b7280", marginTop: 6 }}>
                            {cap.available} place{cap.available === 1 ? "" : "s"} left
                          </div>
                        </div>
                        <span className={`ma-pill ${capPill}`}>{capWord}</span>
                      </div>

                      {["a", "b", "c"].map((k) => {
                        const n = comp[`band_${k}`] || 0;
                        const p = cap.assigned ? Math.round((n / cap.assigned) * 100) : 0;
                        const colour = { a: "green", b: "", c: "amber" }[k];
                        return (
                          <div key={k} style={{ marginBottom: 10 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 5 }}>
                              <span>Grade {k.toUpperCase()}</span>
                              <b>{n} of {cap.assigned} · {p}%</b>
                            </div>
                            <div className="ma-bar">
                              <i className={colour} style={{ width: `${p}%` }} />
                            </div>
                          </div>
                        );
                      })}

                      <div className={`ma-note ${comp.state === "ok" ? "green" : "amber"}`} style={{ marginTop: 12 }}>
                        <b>{comp.message}</b>
                        {comp.state === "ok"
                          ? "All three grades present, so this group meets the composition rule."
                          : "Move a student across before the year starts."}
                      </div>
                    </div>
                  </div>
                </div>

                {/* ================= STUDENTS ================= */}
                <div className="ma-panel" style={{ marginTop: 16 }}>
                  <div className="ma-panel-head">
                    <div>
                      <h3>Assigned students</h3>
                      <p>Active allocations for {prettyYear(data.academic_year)}</p>
                    </div>
                    <div style={{ flex: 1 }} />
                    <input
                      placeholder="Search"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                      style={{
                        padding: "8px 11px",
                        border: "1px solid #e6e9ef",
                        borderRadius: 9,
                        fontSize: 13.5,
                      }}
                    />
                    <span className="ma-pill ma-blue">{students.length}</span>
                  </div>
                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead>
                        <tr>
                          <th>Student</th>
                          <th>Register No</th>
                          <th>Grade</th>
                          <th>CGPA</th>
                          <th>Year</th>
                          <th>Course</th>
                          <th>Academic Year</th>
                          <th>Assigned on</th>
                        </tr>
                      </thead>
                      <tbody>
                        {students.length === 0 && (
                          <tr>
                            <td colSpan={8} className="ma-empty">
                              {q ? "No student matches that search." : "No students assigned yet."}
                            </td>
                          </tr>
                        )}
                        {students.map((s) => (
                          <tr key={s.id}>
                            <td><b>{s.student_name}</b></td>
                            <td className="num">{s.student_roll}</td>
                            <td>
                              <span className={`ma-pill ${bandClass(s.grade_band)}`}>
                                {s.grade_band || "—"}
                              </span>
                            </td>
                            <td className="num">
                              {s.cgpa_at_allocation == null ? "—" : s.cgpa_at_allocation.toFixed(2)}
                            </td>
                            <td>{yearLabel(s.student_year)}</td>
                            <td>{s.course_name || "—"}</td>
                            <td className="num">{prettyYear(s.academic_year)}</td>
                            <td className="num">{s.start_date || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="ma-panel-foot">
                    To move any of these students, use Reassign on the Mentor Allocation page.
                  </div>
                </div>
              </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}