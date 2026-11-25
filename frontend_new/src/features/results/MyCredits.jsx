// WAVE 3 PART 1B - "My credits": credits earned against required (by
// category), CGPA, SGPA by semester, arrears with every attempt, degree class.
//   /my-credits            the signed-in student
//   /parent/credits        a parent, one child at a time
//   /credits/:studentId    class in-charge, mentor, HOD, Principal, admins
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import API from "../../api";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { errorText, num } from "./creditsUtil";
import "../../App.css";
import "../../styles/Credits.css";

function Shell({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main"><div className="content cr-page">{children}</div></div>
      </div>
    </div>
  );
}

export function CreditsView({ url, title = "My credits" }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!url) return;
    API.get(url).then((r) => { setData(r.data); setError(""); })
      .catch((err) => { setData(null); setError(errorText(err, "Couldn't load the credits.")); });
  }, [url]);

  if (error) return <section className="kb-card"><p className="cr-bad">{error}</p></section>;
  if (!data) return <section className="kb-card"><p className="cr-muted">Loading…</p></section>;
  const s = data.student;
  const sems = [...data.semesters].sort((a, b) => a.semester - b.semester);
  const pct = (a, b) => (b ? Math.min(100, Math.round((a * 100) / b)) : 0);
  const arrearCredits = data.arrears.reduce((t, a) => t + a.credits, 0);

  return (
    <>
      <div className="header-box cr-header">
        <div>
          <h1>{title}</h1>
          <p>{s.name} · {s.roll_number}{s.course ? ` · ${s.course}` : ""}{data.regulation ? ` · Regulation ${data.regulation.name}` : ""}{s.semester ? ` · now in Semester ${s.semester}` : ""}</p>
        </div>
      </div>

      <div className="cr-stats">
        <div><span>Credits earned</span>
          <b>{num(data.credits_earned)}{data.credits_required ? <em> / {num(data.credits_required)}</em> : ""}</b>
          {data.credits_required > 0 && <span className="cr-bar-track"><span style={{ width: `${pct(data.credits_earned, data.credits_required)}%` }} /></span>}
        </div>
        <div><span>CGPA</span><b>{num(data.cgpa)}</b>
          <small>{sems.length ? `after Semester ${sems[sems.length - 1].semester}` : "no published results yet"}</small></div>
        <div><span>Arrears</span><b className={data.arrears.length ? "cr-bad" : ""}>{data.arrears.length}</b>
          <small>{data.arrears.length ? `${num(arrearCredits)} credits waiting` : "none"}</small></div>
        <div><span>Degree class so far</span><b className="cr-b-small">{data.degree_class || "—"}</b>
          <small>{data.degree_class ? (data.ever_failed ? "an arrear rules out a first-attempt class" : "if things stay as they are") : "shown once a CGPA exists"}</small></div>
      </div>

      <div className="cr-two">
        <section className="kb-card">
          <div className="cr-head"><h2 className="cr-h2">Credits by category</h2><span className="cr-muted">earned / required</span></div>
          {data.categories.length === 0 ? <p className="cr-muted">No credit requirements are set for this course yet.</p> : (
            data.categories.map((c) => (
              <div className="cr-prog" key={c.code}>
                <b title={c.name}>{c.code}</b>
                <span className="cr-bar-track"><span className={c.required && c.earned >= c.required ? "done" : ""} style={{ width: `${c.required ? pct(c.earned, c.required) : 100}%` }} /></span>
                <span className="cr-nowrap">{num(c.earned)} / {num(c.required)}</span>
              </div>
            ))
          )}
        </section>

        <section className="kb-card">
          <div className="cr-head"><h2 className="cr-h2">SGPA by semester</h2><span className="cr-muted">out of 10</span></div>
          {sems.length === 0 ? <p className="cr-muted">No published results yet.</p> : (
            <>
              <div className="cr-chart" role="img" aria-label={`SGPA: ${sems.map((x) => `Semester ${x.semester} ${num(x.sgpa)}`).join(", ")}`}>
                {sems.map((x) => (
                  <div key={x.semester} className="cr-col">
                    <b>{num(x.sgpa)}</b>
                    <span className={x.has_arrear ? "warn" : ""} style={{ height: `${x.sgpa ? x.sgpa * 16 : 2}px` }} />
                    <small>Sem {x.semester}</small>
                  </div>
                ))}
              </div>
              {sems.some((x) => x.has_arrear) && <p className="cr-muted">Orange = a semester with an arrear.</p>}
            </>
          )}
        </section>
      </div>

      <section className="kb-card">
        <h2 className="cr-h2">Arrears</h2>
        {data.arrears.length === 0 ? <p className="cr-muted">No arrears.</p> : (
          <div className="cr-table-wrap">
            <table className="cr-table">
              <thead><tr><th>Subject</th><th>Semester</th><th>Credits</th><th>Attempts</th></tr></thead>
              <tbody>
                {data.arrears.map((a) => (
                  <tr key={`${a.semester}-${a.subject_id}`}>
                    <td><b>{a.code}</b> {a.name}</td>
                    <td>{a.semester}</td>
                    <td>{num(a.credits)}</td>
                    <td>{a.attempts.map((t) => `${t.exam_session || `Attempt ${t.attempt}`} ${t.grade}`).join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="cr-muted">Parents, the mentor, the class in-charge and the HOD see this same page.</p>
      </section>
    </>
  );
}

export default function MyCredits() {
  const { studentId } = useParams();
  return (
    <Shell>
      <CreditsView url={studentId ? `results/credits/${studentId}/` : "results/credits/me/"}
        title={studentId ? "Credits and CGPA" : "My credits"} />
    </Shell>
  );
}

export function ParentCredits() {
  const [kids, setKids] = useState(null);
  const [child, setChild] = useState(null);
  useEffect(() => {
    API.get("/parent/dashboard/").then((r) => {
      const list = r.data?.children || [];
      setKids(list);
      if (list.length) setChild(list[0].id);
    }).catch(() => setKids([]));
  }, []);
  return (
    <Shell>
      {kids && kids.length > 1 && (
        <div className="cr-kids">
          {kids.map((k) => (
            <button key={k.id} type="button" className={`kb-btn kb-btn--sm${child === k.id ? " kb-btn--primary" : ""}`}
              onClick={() => setChild(k.id)}>{k.username}</button>
          ))}
        </div>
      )}
      {kids && kids.length === 0 && <section className="kb-card"><p className="cr-muted">No child is linked to your account yet.</p></section>}
      {child && <CreditsView url={`results/credits/${child}/`} title="Credits and CGPA" />}
    </Shell>
  );
}
