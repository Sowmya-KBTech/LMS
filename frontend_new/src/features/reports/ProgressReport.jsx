// WAVE 1 - one student's progress report (printable).
//   /progress-report/:studentId   staff (class in-charge, HOD, mentor, admin) and parents
//   /my-progress-report           the student
//   /parent/progress-report       a parent: pick a child
// Shows published semester results with class rank, declared IA marks and
// this semester's attendance, with signature lines for printing.
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import API from "../../api";
import { API_BASE_URL } from "../../apiBase";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { errorText, getCollege, getProgressReport, pctTone, roman } from "./reportsApi";
import "../../App.css";
import "../../styles/Reports.css";

// WAVE 3 PART 1B: where "Credits and CGPA" goes for whoever is looking
function creditsPath(studentId) {
  let role = "";
  try { role = JSON.parse(localStorage.getItem("user") || "{}").role || ""; } catch { role = ""; }
  if (role === "student") return "/my-credits";
  if (role === "parent") return "/parent/credits";
  return `/credits/${studentId}`;
}

const fmt = (n) => (n == null ? "—" : Number(n).toFixed(2).replace(/\.00$/, ""));

function Shell({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main"><div className="content">{children}</div></div>
      </div>
    </div>
  );
}

export function ReportSheet({ studentId }) {
  const [report, setReport] = useState(null);
  const [college, setCollege] = useState({});
  const [error, setError] = useState("");

  useEffect(() => { getCollege().then(setCollege); }, []);
  useEffect(() => {
    setReport(null);
    setError("");
    getProgressReport(studentId)
      .then(setReport)
      .catch((err) => setError(errorText(err, "Couldn't load the progress report.")));
  }, [studentId]);

  if (error) return <section className="kb-card"><p className="rp-bad">{error}</p></section>;
  if (!report) return <section className="kb-card"><p className="rp-muted">Loading…</p></section>;

  const s = report.student;
  const att = report.attendance;           // null when the college has attendance switched off
  const today = new Date().toLocaleDateString("en-GB").replace(/\//g, "-");

  return (
    <>
      <div className="rp-actions no-print" style={{ marginBottom: 12 }}>
        <button type="button" className="kb-btn kb-btn--primary" onClick={() => window.print()}>
          Print / save as PDF
        </button>
        {/* WAVE 3 PART 1B: credits earned, CGPA and arrears */}
        <Link className="kb-btn" to={creditsPath(s.id)}>Credits and CGPA</Link>
      </div>

      <article className="rp-sheet">
        <header className="rp-head">
          {college.logo_version && (
            <img src={`${API_BASE_URL}college/logo/?v=${college.logo_version}`} alt="" />
          )}
          <div>
            <h1>{college.name || "Progress report"}</h1>
            <p>Student progress report · issued {today}</p>
          </div>
        </header>

        <div className="rp-info">
          <div><b>Name</b> {s.name}</div>
          <div><b>Roll no.</b> {s.roll_number || "—"}</div>
          <div><b>Course</b> {s.course || "—"}</div>
          <div><b>Department</b> {s.department || "—"}</div>
          <div><b>Year</b> {s.year ? roman(s.year) : "—"}</div>
          <div><b>Semester</b> {s.semester || "—"}</div>
        </div>

        <div className="rp-stats">
          <div className="rp-stat"><span>Overall marks</span><b>{fmt(report.overall.percentage)}%</b></div>
          <div className="rp-stat"><span>Semesters published</span><b>{report.overall.semesters}</b></div>
          <div className="rp-stat"><span>Arrears</span><b className={report.overall.arrears ? "rp-bad" : ""}>{report.overall.arrears}</b></div>
          <div className="rp-stat"><span>Attendance (this sem)</span>
            {att?.total ? <b className={`rp-${pctTone(att.percentage)}`}>{fmt(att.percentage)}%</b> : <b>—</b>}
          </div>
        </div>

        <h2>Semester results</h2>
        {report.semester_results.length === 0 ? (
          <p className="rp-muted">No published results yet.</p>
        ) : report.semester_results.map((sem) => (
          <div className="rp-sem" key={sem.semester}>
            <div className="rp-sem-head">
              <span>Semester {sem.semester}</span>
              <span>
                {fmt(sem.total)} / {sem.max} · {fmt(sem.percentage)}% ·{" "}
                {sem.rank ? `Rank ${sem.rank} of ${sem.class_size}`
                  : sem.arrears ? <span className="rp-bad">{sem.arrears} arrear{sem.arrears > 1 ? "s" : ""} · not ranked</span>
                  : "Not ranked"}
              </span>
            </div>
            <table className="rp-table">
              <thead><tr><th>Code</th><th>Subject</th><th className="num">Marks</th><th className="c">Grade</th><th className="c">Result</th></tr></thead>
              <tbody>
                {sem.entries.map((e, i) => (
                  <tr key={i}>
                    <td>{e.code || "—"}</td><td>{e.subject}</td>
                    <td className="num">{fmt(e.obtained)} / {e.max}</td>
                    <td className="c">{e.grade || "—"}</td>
                    <td className="c">{e.is_pass ? <span className="rp-ok">Pass</span> : <span className="rp-bad">Arrear</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}

        <h2>Internal assessments</h2>
        {report.internal_assessments.length === 0 ? (
          <p className="rp-muted">No declared internal assessment marks.</p>
        ) : (
          <table className="rp-table">
            <thead><tr><th>Subject</th><th className="c">Sem</th><th>Tests</th></tr></thead>
            <tbody>
              {report.internal_assessments.map((r, i) => (
                <tr key={i}>
                  <td>{r.code ? `${r.code} · ` : ""}{r.subject}</td>
                  <td className="c">{r.semester || "—"}</td>
                  <td>
                    {r.tests.map((t) => (
                      <span key={t.number} style={{ marginRight: 14 }}>
                        IA {t.number}: {t.absent ? <span className="rp-bad">Absent</span> : <b>{fmt(t.obtained)}</b>}/{t.max}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {att && <>
        <h2>Attendance · current semester</h2>
        {att.subjects.length === 0 ? (
          <p className="rp-muted">No attendance marked yet this semester.</p>
        ) : (
          <table className="rp-table">
            <thead><tr><th>Subject</th><th className="num">Attended</th><th className="num">On duty</th><th className="num">%</th></tr></thead>
            <tbody>
              {att.subjects.map((a, i) => (
                <tr key={i}>
                  <td>{a.code ? `${a.code} · ` : ""}{a.subject}</td>
                  <td className="num">{a.attended} / {a.total}</td>
                  <td className="num">{a.on_duty}</td>
                  <td className={`num rp-${pctTone(a.percentage)}`}>{fmt(a.percentage)}</td>
                </tr>
              ))}
              <tr>
                <td><b>Total</b></td>
                <td className="num"><b>{att.attended} / {att.total}</b></td><td />
                <td className={`num rp-${pctTone(att.percentage)}`}>{fmt(att.percentage)}</td>
              </tr>
            </tbody>
          </table>
        )}
        <p className="rp-muted" style={{ marginTop: 6 }}>
          On duty counts as attended. Approved leave days so far: {att.approved_leave_days} (excused, not counted as present).
        </p>
        </>}

        <div className="rp-sign">
          <div>Class in-charge</div>
          <div>Head of department</div>
          <div>Parent / guardian</div>
        </div>
      </article>
    </>
  );
}

/** /progress-report/:studentId */
export default function ProgressReport() {
  const { studentId } = useParams();
  const navigate = useNavigate();
  return (
    <Shell>
      <div className="header-box no-print">
        <h1>Progress report</h1>
        <p><button type="button" className="kb-btn kb-btn--sm" onClick={() => navigate(-1)}>← Back</button></p>
      </div>
      <ReportSheet studentId={studentId} />
    </Shell>
  );
}

/** /my-progress-report */
export function MyProgressReport() {
  return (
    <Shell>
      <div className="header-box no-print">
        <h1>My progress report</h1>
        <p>Your published results, class rank, internal marks and attendance in one page.</p>
      </div>
      <ReportSheet />
    </Shell>
  );
}

/** /parent/progress-report */
export function ParentProgressReport() {
  const [kids, setKids] = useState(null);
  const [child, setChild] = useState(null);

  useEffect(() => {
    API.get("/parent/dashboard/")
      .then((res) => {
        const list = res.data?.children || [];
        setKids(list);
        if (list.length) setChild(list[0].id);
      })
      .catch(() => setKids([]));
  }, []);

  return (
    <Shell>
      <div className="header-box no-print">
        <h1>Progress report</h1>
        <p>Your child's published results, class rank, internal marks and attendance.</p>
      </div>
      {kids && kids.length > 1 && (
        <div className="rp-kids no-print">
          {kids.map((k) => (
            <button key={k.id} type="button"
              className={`kb-btn kb-btn--sm${child === k.id ? " kb-btn--primary" : ""}`}
              onClick={() => setChild(k.id)}>
              {k.username}
            </button>
          ))}
        </div>
      )}
      {kids && kids.length === 0 && (
        <section className="kb-card"><p className="rp-muted">No child is linked to your account yet.</p></section>
      )}
      {child && <ReportSheet studentId={child} />}
    </Shell>
  );
}
