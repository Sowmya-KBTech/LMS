import { useEffect, useMemo, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import ReadinessCard from "../placement/ReadinessCard";
import "../../App.css";
import StudentRequests from "../attendance/StudentRequests";   // student on duty + leave in one list
import AttendanceCorrection from "./AttendanceCorrection";
import { RegistrationReview } from "../electives/CourseRegistration";   // CBCS PART A

const initials = (name = "") =>
  name.replace(/[^A-Za-z. ]/g, "").split(/[ .]/).filter(Boolean)
    .map((p) => p[0]).slice(0, 2).join("").toUpperCase();

export default function MyClass() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isTutor, setIsTutor] = useState(false);
  const [classes, setClasses] = useState([]);
  const [active, setActive] = useState(0);
  const [onlyAtRisk, setOnlyAtRisk] = useState(false);
  // FIX #11: /my-class?tab=... (from a notification) opens that tab.
  // Old links ?tab=onduty and ?tab=leave open the combined Student requests tab.
  const [tab, setTab] = useState(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t === "onduty" || t === "leave") return "requests";
    return ["class", "attendance", "marksheet", "requests", "registration"].includes(t) ? t : "class";
  });   // "class" | "attendance" | "marksheet" | "requests" | "registration"

  // mark report modal (single student)
  const [reportFor, setReportFor] = useState(null);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);

  // class mark sheet (all students, by semester)
  const [msData, setMsData] = useState([]);
  const [msLoaded, setMsLoaded] = useState(false);
  const [semSel, setSemSel] = useState("");

  useEffect(() => {
    API.get("users/my-class/")
      .then((res) => {
        setIsTutor(res.data?.is_tutor || false);
        setClasses(res.data?.classes || []);
      })
      .catch(() => setIsTutor(false))
      .finally(() => setLoading(false));
  }, []);

  // load mark sheet data lazily when the tab opens
  useEffect(() => {
    if (tab === "marksheet" && !msLoaded) {
      API.get("users/my-class/marksheet/")
        .then((res) => setMsData(res.data?.classes || []))
        .catch(() => setMsData([]))
        .finally(() => setMsLoaded(true));
    }
  }, [tab, msLoaded]);

  const cls = classes[active];

  // open the single-student report modal
  const openReport = (student) => {
    setReportFor(student);
    setReport(null);
    setReportLoading(true);
    API.get(`users/my-class/student/${student.id}/report/`)
      .then((res) => setReport(res.data || null))
      .catch(() => setReport(null))
      .finally(() => setReportLoading(false));
  };
  const closeReport = () => {
    setReportFor(null);
    setReport(null);
    setReportLoading(false);
  };

  // sort: at-risk first (arrears, then low attendance), then the rest
  const sortedStudents = useMemo(() => {
    const list = cls?.students ? [...cls.students] : [];
    const risk = (s) => {
      if (s.result_status === "failed") return 0;
      if (s.attendance_percent != null && s.attendance_percent < 75) return 1;
      return 2;
    };
    return list.sort((a, b) => {
      const r = risk(a) - risk(b);
      if (r !== 0) return r;
      const aa = a.attendance_percent ?? 999;
      const bb = b.attendance_percent ?? 999;
      return aa - bb;
    });
  }, [cls]);

  const visibleStudents = useMemo(() => {
    if (!onlyAtRisk) return sortedStudents;
    return sortedStudents.filter(
      (s) => s.result_status === "failed" ||
        (s.attendance_percent != null && s.attendance_percent < 75)
    );
  }, [sortedStudents, onlyAtRisk]);

  const attColor = (p) => (p == null ? "#85839A" : p < 75 ? "#dc2626" : "#15803d");

  // ----- mark sheet: matching class + selected semester -----
  const msClass = useMemo(() => {
    if (!cls) return null;
    return msData.find(
      (c) => c.course_id === cls.course_id && c.year_number === cls.year_number
    ) || null;
  }, [msData, cls]);

  // default the semester dropdown to the latest semester that has data
  useEffect(() => {
    if (msClass?.semesters?.length) {
      setSemSel(String(msClass.semesters[msClass.semesters.length - 1]));
    } else {
      setSemSel("");
    }
  }, [msClass]);

  const sheet = msClass && semSel ? msClass.by_semester[semSel] : null;

  // mark cell helpers (on-screen)
  const cellText = (m) => {
    if (!m) return "—";
    if (m.obtained == null) return "AB";
    return `${m.obtained}/${m.max}${m.grade ? ` (${m.grade})` : ""}`;
  };
  const cellColor = (m) => {
    if (!m || m.obtained == null) return "#85839A";
    return m.is_pass ? "#15803d" : "#dc2626";
  };

  // ----- print the selected semester's sheet -----
  const printSheet = () => {
    if (!msClass || !sheet || sheet.students.length === 0) return;

    const esc = (v) =>
      String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const today = new Date().toLocaleDateString();

    const head = `
      <tr>
        <th>#</th>
        <th>Roll No</th>
        <th class="l">Student</th>
        ${sheet.subjects.map((s) => `<th>${esc(s)}</th>`).join("")}
        <th>Result</th>
      </tr>`;

    const rows = sheet.students
      .map((st, i) => {
        const cells = sheet.subjects
          .map((subj) => {
            const m = st.marks[subj];
            const txt = !m ? "—" : m.obtained == null ? "AB" : `${m.obtained}/${m.max}${m.grade ? ` (${m.grade})` : ""}`;
            const cl = !m || m.obtained == null ? "muted" : m.is_pass ? "pass" : "fail";
            return `<td class="${cl}">${esc(txt)}</td>`;
          })
          .join("");
        const res =
          st.result === "pass" ? `<td class="pass b">PASS</td>`
          : st.result === "fail" ? `<td class="fail b">FAIL</td>`
          : `<td class="muted">—</td>`;
        return `<tr>
          <td>${i + 1}</td>
          <td>${esc(st.roll_number || "-")}</td>
          <td class="l">${esc(st.name || st.username)}</td>
          ${cells}
          ${res}
        </tr>`;
      })
      .join("");

    const html = `<!doctype html>
<html><head><meta charset="utf-8" />
<title>Mark Sheet - ${esc(msClass.course_name)} Y${esc(msClass.year_number)} Sem ${esc(semSel)}</title>
<style>
  @page { size: A4 landscape; margin: 12mm; }
  * { box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #111; margin: 0; }
  .head { text-align: center; margin-bottom: 10px; }
  .head h1 { font-size: 18px; margin: 0 0 4px; }
  .head p { font-size: 13px; margin: 2px 0; color: #333; }
  .meta { display: flex; justify-content: space-between; font-size: 12px; color: #444; margin: 8px 2px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border: 1px solid #999; padding: 4px 6px; font-size: 11.5px; text-align: center; }
  th { background: #f0f0f0; }
  td.l, th.l { text-align: left; }
  td.pass { color: #15803d; }
  td.fail { color: #dc2626; }
  td.muted { color: #888; }
  td.b { font-weight: bold; }
</style></head>
<body>
  <div class="head">
    <h1>Internal Mark Sheet</h1>
    <p>${esc(msClass.course_name)} &middot; Year ${esc(msClass.year_number)} &middot; Semester ${esc(semSel)}</p>
  </div>
  <div class="meta">
    <span>Total students: ${sheet.students.length}</span>
    <span>Generated: ${esc(today)}</span>
  </div>
  <table><thead>${head}</thead><tbody>${rows}</tbody></table>
</body></html>`;

    const w = window.open("", "_blank");
    if (!w) {
      alert("Please allow pop-ups to print the mark sheet.");
      return;
    }
    w.document.open();
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

              <h1 className="sd-hello">My Class</h1>
              <p className="sd-sub">
                {isTutor && cls ? `Class in-charge — ${cls.course_name} · Year ${cls.year_number}` : "Class overview"}
              </p>

              {loading && <div className="sd-panel">Loading…</div>}

              {!loading && !isTutor && (
                <div className="sd-panel">You are not assigned as a class in-charge for any class.</div>
              )}

              {!loading && isTutor && (
                <>
                  {/* main tabs */}
                  <div className="sd-seg" style={{ marginBottom: 16 }}>
                    <button className={tab === "class" ? "on" : ""} onClick={() => setTab("class")}>Class</button>
                    <button className={tab === "attendance" ? "on" : ""} onClick={() => setTab("attendance")}>Attendance</button>
                    <button className={tab === "marksheet" ? "on" : ""} onClick={() => setTab("marksheet")}>Mark Sheet</button>
                    <button className={tab === "requests" ? "on" : ""} onClick={() => setTab("requests")}>Student requests</button>
                    <button className={tab === "registration" ? "on" : ""} onClick={() => setTab("registration")}>Course registration</button>
                  </div>

                  {/* class switcher (shared across tabs) if more than one class */}
                  {classes.length > 1 && tab !== "requests" && tab !== "registration" && (
                    <div className="sd-seg" style={{ marginBottom: 16 }}>
                      {classes.map((c, i) => (
                        <button key={i} className={i === active ? "on" : ""} onClick={() => { setActive(i); setOnlyAtRisk(false); }}>
                          {c.course_name} · Y{c.year_number}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* ════════ CLASS TAB ════════ */}
                  {tab === "class" && cls && (
                    <>
                      {/* summary cards */}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                        <div className="sd-card">
                          <div className="sd-label">Total Students</div>
                          <div className="sd-val">{cls.total_students}</div>
                        </div>
                        <div className="sd-card">
                          <div className="sd-label">Below 75% Attendance</div>
                          <div className="sd-val" style={{ color: cls.below_75 > 0 ? "#dc2626" : "#17151F" }}>{cls.below_75}</div>
                        </div>
                        <div className="sd-card">
                          <div className="sd-label">Failing (Arrears)</div>
                          <div className="sd-val" style={{ color: cls.failing > 0 ? "#dc2626" : "#17151F" }}>{cls.failing}</div>
                        </div>
                      </div>

                      {/* student table */}
                      <div className="sd-panel" style={{ marginTop: 16 }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
                          <div className="sd-pt" style={{ margin: 0 }}>
                            Students ({visibleStudents.length})
                          </div>
                          <button
                            onClick={() => setOnlyAtRisk((v) => !v)}
                            style={{
                              background: onlyAtRisk ? "#17151F" : "#fff",
                              color: onlyAtRisk ? "#fff" : "#5D5A6B",
                              border: "1px solid #d8dee9",
                              borderRadius: 8,
                              padding: "7px 14px",
                              fontSize: 14,
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            {onlyAtRisk ? "Showing at-risk only" : "Show at-risk only"}
                          </button>
                        </div>

                        <table className="sd-tbl">
                          <thead>
                            <tr>
                              <th>Student</th>
                              <th>Roll No</th>
                              <th style={{ textAlign: "center" }}>Attendance</th>
                              <th style={{ textAlign: "center" }}>Result</th>
                              <th style={{ textAlign: "right" }}>Report</th>
                            </tr>
                          </thead>
                          <tbody>
                            {visibleStudents.length > 0 ? (
                              visibleStudents.map((s) => {
                                const isArrear = s.result_status === "failed";
                                return (
                                  <tr key={s.id} onClick={() => openReport(s)} style={{ cursor: "pointer" }}>
                                    <td>
                                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                        <span style={{
                                          width: 28, height: 28, borderRadius: "50%",
                                          background: isArrear ? "#fef2f2" : "#eef4ff",
                                          color: isArrear ? "#dc2626" : "#4B32C3",
                                          fontSize: 12, fontWeight: 700,
                                          display: "flex", alignItems: "center", justifyContent: "center",
                                        }}>
                                          {initials(s.username)}
                                        </span>
                                        <span>{s.username}</span>
                                      </div>
                                    </td>
                                    <td className="sd-num">{s.roll_number || "-"}</td>
                                    <td className="sd-num" style={{ textAlign: "center", fontWeight: 600, color: attColor(s.attendance_percent) }}>
                                      {s.attendance_percent != null ? `${s.attendance_percent}%` : "—"}
                                    </td>
                                    <td style={{ textAlign: "center" }}>
                                      {isArrear && (
                                        <span style={{ fontSize: 13, fontWeight: 600, color: "#dc2626", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 999, padding: "3px 12px" }}>
                                          Arrear
                                        </span>
                                      )}
                                      {!isArrear && s.result_status === "passed" && (
                                        <span style={{ fontSize: 13, fontWeight: 600, color: "#15803d", background: "#f0faf4", border: "1px solid #c6ebd4", borderRadius: 999, padding: "3px 12px" }}>
                                          Pass
                                        </span>
                                      )}
                                      {s.result_status == null && (
                                        <span style={{ fontSize: 13, color: "#85839A" }}>—</span>
                                      )}
                                    </td>
                                    <td style={{ textAlign: "right" }}>
                                      <button
                                        onClick={(ev) => { ev.stopPropagation(); openReport(s); }}
                                        style={{
                                          background: "#fff", color: "#4B32C3", border: "1px solid #E3DCFA",
                                          borderRadius: 8, padding: "5px 12px", fontSize: 13.5, fontWeight: 600,
                                          cursor: "pointer", whiteSpace: "nowrap",
                                        }}
                                      >
                                        View report
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })
                            ) : (
                              <tr><td colSpan="5" className="sd-empty">
                                {onlyAtRisk ? "No at-risk students — class looks healthy." : "No students in this class."}
                              </td></tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {/* ════════ MARK SHEET TAB ════════ */}
                  {tab === "marksheet" && cls && (
                    <>
                      {!msLoaded && <div className="sd-panel">Loading mark sheet…</div>}

                      {msLoaded && (!msClass || !msClass.semesters?.length) && (
                        <div className="sd-panel">No published results yet for this class.</div>
                      )}

                      {msLoaded && msClass && msClass.semesters?.length > 0 && (
                        <div className="sd-panel">
                          {/* controls: semester + print */}
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                              <span className="sd-pt" style={{ margin: 0 }}>Semester</span>
                              <select value={semSel} onChange={(e) => setSemSel(e.target.value)}>
                                {msClass.semesters.map((sem) => (
                                  <option key={sem} value={String(sem)}>Semester {sem}</option>
                                ))}
                              </select>
                            </div>
                            <button
                              onClick={printSheet}
                              disabled={!sheet || sheet.students.length === 0}
                              style={{
                                background: "#17151F", color: "#fff", border: "none", borderRadius: 8,
                                padding: "9px 18px", fontSize: 14, fontWeight: 600,
                                cursor: (!sheet || sheet.students.length === 0) ? "default" : "pointer",
                                opacity: (!sheet || sheet.students.length === 0) ? 0.5 : 1,
                              }}
                            >
                              Print / Save as PDF
                            </button>
                          </div>

                          {sheet && sheet.students.length > 0 ? (
                            <>
                              <div style={{ overflowX: "auto" }}>
                                <table className="sd-tbl" style={{ minWidth: 640 }}>
                                  <thead>
                                    <tr>
                                      <th>#</th>
                                      <th>Roll No</th>
                                      <th>Student</th>
                                      {sheet.subjects.map((s) => (
                                        <th key={s} style={{ textAlign: "center", whiteSpace: "nowrap" }}>{s}</th>
                                      ))}
                                      <th style={{ textAlign: "center" }}>Result</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {sheet.students.map((st, i) => (
                                      <tr key={st.id}>
                                        <td className="sd-num">{i + 1}</td>
                                        <td className="sd-num">{st.roll_number || "-"}</td>
                                        <td>{st.name || st.username}</td>
                                        {sheet.subjects.map((subj) => {
                                          const m = st.marks[subj];
                                          return (
                                            <td key={subj} className="sd-num" style={{ textAlign: "center", whiteSpace: "nowrap", color: cellColor(m), fontWeight: m && m.obtained != null ? 600 : 400 }}>
                                              {cellText(m)}
                                            </td>
                                          );
                                        })}
                                        <td style={{ textAlign: "center" }}>
                                          {st.result === "pass" && (
                                            <span style={{ fontSize: 13, fontWeight: 600, color: "#15803d", background: "#f0faf4", border: "1px solid #c6ebd4", borderRadius: 999, padding: "3px 12px" }}>Pass</span>
                                          )}
                                          {st.result === "fail" && (
                                            <span style={{ fontSize: 13, fontWeight: 600, color: "#dc2626", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 999, padding: "3px 12px" }}>Fail</span>
                                          )}
                                          {st.result === "pending" && (
                                            <span style={{ fontSize: 13, color: "#85839A" }}>Not published</span>
                                          )}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                              <div style={{ fontSize: 13, color: "#5D5A6B", marginTop: 12 }}>
                                Cells show marks / max (grade). AB = absent. "—" = subject not applicable. Use Print / Save as PDF for the meeting copy.
                              </div>
                            </>
                          ) : (
                            <div className="sd-empty">No marks for the selected semester.</div>
                          )}
                        </div>
                      )}
                    </>
                  )}

                  {/* ════════ ATTENDANCE TAB (meeting point 6) ════════ */}
                  {/* only the class tutor gets here (isTutor); the server checks again */}
                  {tab === "attendance" && cls && (
                    <AttendanceCorrection courseId={cls.course_id} yearNumber={cls.year_number} />
                  )}

                  {/* ════════ ON DUTY TAB ════════ */}
                  {tab === "requests" && <StudentRequests who="tutor" />}
                  {tab === "registration" && <RegistrationReview />}
                </>
              )}

            </div>
          </div>
        </div>
      </div>

      {/* ════════ SINGLE-STUDENT MARK REPORT MODAL ════════ */}
      {reportFor && (
        <div
          onClick={closeReport}
          style={{
            position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 16, zIndex: 1000,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#fff", borderRadius: 16, width: "100%", maxWidth: 640,
              maxHeight: "85vh", overflowY: "auto", padding: 24,
              boxShadow: "0 20px 50px rgba(0,0,0,0.25)",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 18 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: "#17151F" }}>{reportFor.username}</div>
                <div style={{ fontSize: 14, color: "#5D5A6B", marginTop: 2 }}>
                  {reportFor.roll_number || "-"}
                  {report?.semester ? ` · Semester ${report.semester}` : ""}
                </div>
              </div>
              <button
                onClick={closeReport}
                style={{
                  background: "#fff", color: "#5D5A6B", border: "1px solid #d8dee9",
                  borderRadius: 8, width: 32, height: 32, fontSize: 16, fontWeight: 600,
                  cursor: "pointer", lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>

            <ReadinessCard studentId={reportFor.id} />

            {reportLoading ? (
              <div className="sd-empty">Loading report…</div>
            ) : !report ? (
              <div className="sd-empty">Could not load this student's report.</div>
            ) : !report.published || report.subjects.length === 0 ? (
              <div className="sd-panel" style={{ margin: 0 }}>
                Results not published yet for this student's current semester.
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
                  <div className="sd-card" style={{ flex: 1, minWidth: 120 }}>
                    <div className="sd-label">Passed</div>
                    <div className="sd-val" style={{ color: "#15803d" }}>{report.passed}</div>
                  </div>
                  <div className="sd-card" style={{ flex: 1, minWidth: 120 }}>
                    <div className="sd-label">Failed (arrears)</div>
                    <div className="sd-val" style={{ color: report.failed > 0 ? "#dc2626" : "#17151F" }}>{report.failed}</div>
                  </div>
                  <div className="sd-card" style={{ flex: 1, minWidth: 120 }}>
                    <div className="sd-label">Subjects</div>
                    <div className="sd-val">{report.subjects.length}</div>
                  </div>
                </div>

                <table className="sd-tbl">
                  <thead>
                    <tr>
                      <th>Subject</th>
                      <th style={{ textAlign: "center" }}>Marks</th>
                      <th style={{ textAlign: "center" }}>Grade</th>
                      <th style={{ textAlign: "center" }}>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.subjects.map((sub, idx) => (
                      <tr key={idx}>
                        <td>
                          {sub.subject}
                          {sub.code ? <span style={{ fontSize: 13, color: "#85839A" }}> · {sub.code}</span> : ""}
                        </td>
                        <td className="sd-num" style={{ textAlign: "center" }}>
                          {sub.marks_obtained != null ? `${sub.marks_obtained} / ${sub.max_marks}` : "AB"}
                        </td>
                        <td className="sd-num" style={{ textAlign: "center", fontWeight: 600 }}>
                          {sub.grade || "—"}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          {sub.is_pass ? (
                            <span style={{ fontSize: 13, fontWeight: 600, color: "#15803d", background: "#f0faf4", border: "1px solid #c6ebd4", borderRadius: 999, padding: "3px 12px" }}>
                              Pass
                            </span>
                          ) : (
                            <span style={{ fontSize: 13, fontWeight: 600, color: "#dc2626", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 999, padding: "3px 12px" }}>
                              Fail
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}