// WAVE 3 PART 1B - one student's semester results under their regulation:
// SGPA with its working, internal / end-sem / total, grade, points and
// credits × points, and every attempt at an arrear subject.
// Fed by GET results/credits/me/ or results/credits/<id>/ (data prop).
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { num } from "./creditsUtil";
import "../../styles/Credits.css";

const outcomeTone = (e) => (e.is_pass ? "ok" : e.outcome === "excluded" ? "grey" : "bad");

export default function ResultSheet({ data, creditsLink }) {
  const sems = useMemo(() => [...(data?.semesters || [])].sort((a, b) => b.semester - a.semester), [data]);
  const [pick, setPick] = useState(null);
  const sem = sems.find((s) => s.semester === pick) || sems[0];

  if (!data) return null;
  if (!sems.length) {
    return <div className="kb-card"><p className="cr-muted">No results have been published yet. They will appear here once the college releases them.</p></div>;
  }
  const arrearRows = sem.entries.filter((e) => !e.is_pass && e.outcome !== "excluded");
  const sessions = [...new Set(sem.entries.map((e) => e.exam_session).filter(Boolean))];

  return (
    <div className="cr-wrap">
      <div className="cr-bar no-print">
        <label className="cr-field">Semester
          <select className="kb-input" value={sem.semester} onChange={(e) => setPick(Number(e.target.value))}>
            {sems.map((s) => <option key={s.semester} value={s.semester}>Semester {s.semester}{s.is_published ? "" : " (not published)"}</option>)}
          </select>
        </label>
        <span className="cr-actions">
          {creditsLink && <Link className="kb-btn" to={creditsLink}>Credits and CGPA</Link>}
          <button type="button" className="kb-btn" onClick={() => window.print()}>Print grade sheet</button>
        </span>
      </div>

      <div className="cr-print-head">
        <b>{data.student.name}</b> · {data.student.roll_number} · {data.student.course}
        {data.regulation ? ` · Regulation ${data.regulation.name}` : ""} — Semester {sem.semester}
      </div>

      <div className="cr-stats">
        <div><span>SGPA · Semester {sem.semester}</span><b>{num(sem.sgpa)}</b>
          <small>{sem.sgpa != null ? `${num(sem.grade_points)} grade points ÷ ${num(sem.gpa_credits)} credits` : "no graded credits yet"}</small></div>
        <div><span>Credits earned this semester</span><b>{num(sem.credits_earned)} <em>/ {num(sem.credits_total)}</em></b>
          <small>{sem.has_arrear ? "some credits are held by an arrear" : "every credit earned"}</small></div>
        <div><span>CGPA</span><b>{num(data.cgpa)}</b>
          <small>{data.cgpa_problem === "no_credits" ? "a subject has no credits set" : `all ${data.semesters.length} semester${data.semesters.length === 1 ? "" : "s"}`}</small></div>
        <div><span>Exam</span><b className="cr-b-small">{sessions.join(", ") || "—"}</b>
          <small>{sem.is_published ? "published" : "not published yet"}</small></div>
      </div>

      <section className="kb-card">
        <h2 className="cr-h2">Semester {sem.semester} subjects</h2>
        <div className="cr-table-wrap">
          <table className="cr-table">
            <thead>
              <tr><th>Subject</th><th>Credits</th><th>Internal</th><th>End-sem</th><th>Total</th><th>Grade</th><th>Points</th><th>Credits × points</th></tr>
            </thead>
            <tbody>
              {sem.entries.map((e) => (
                <tr key={e.id} className={e.is_pass ? "" : "cr-row-bad"}>
                  <td><b>{e.code}</b> {e.name}
                    {(!e.is_pass || !e.counts_for_credit || e.attempt > 1) && (
                      <small>{!e.counts_for_credit ? "No-credit course · pass needed, not in SGPA"
                        : e.outcome === "excluded" ? "Withdrawn · not counted"
                          : !e.is_pass ? `Arrear · write again${e.attempt > 1 ? ` · attempt ${e.attempt}` : ""}`
                            : `Passed in attempt ${e.attempt}${e.exam_session ? ` (${e.exam_session})` : ""}`}</small>
                    )}</td>
                  <td>{num(e.credits)}</td>
                  <td>{num(e.internal_marks)}</td>
                  <td>{num(e.end_marks)}</td>
                  <td>{e.marks_obtained == null ? "Absent" : `${num(e.marks_obtained)} / ${num(e.max_marks)}`}</td>
                  <td><span className={`cr-grade ${outcomeTone(e)}`}>{e.grade || "—"}</span></td>
                  <td>{num(e.points)}</td>
                  <td>{e.in_gpa ? num(e.credit_points) : <span className="cr-muted">{!e.counts_for_credit ? "no credit" : "left out"}</span>}</td>
                </tr>
              ))}
              <tr className="cr-total"><td><b>Counted in SGPA</b></td><td><b>{num(sem.gpa_credits)}</b></td><td colSpan={5} /><td><b>{num(sem.grade_points)}</b></td></tr>
            </tbody>
          </table>
        </div>
      </section>

      {arrearRows.length > 0 && (
        <section className="kb-card">
          <h2 className="cr-h2">Arrear attempts</h2>
          {arrearRows.map((e) => (
            <div key={e.id} className="cr-attempts">
              <b className="cr-att-title">{e.code} {e.name}</b>
              <div className="cr-cards">
                {[...e.attempts, { attempt: e.attempt, exam_session: e.exam_session, grade: e.grade,
                  internal_marks: e.internal_marks, end_marks: e.end_marks, marks_obtained: e.marks_obtained }].map((a) => (
                  <div key={a.attempt} className="cr-card bad">
                    <b>Attempt {a.attempt}{a.exam_session ? ` · ${a.exam_session}` : ""}</b>
                    <span>{a.internal_marks != null ? `Internal ${num(a.internal_marks)} · End-sem ${num(a.end_marks)}` : a.marks_obtained == null ? "Absent" : `Marks ${num(a.marks_obtained)}`} · <b>{a.grade}</b></span>
                  </div>
                ))}
                <div className="cr-card next">
                  <b>Attempt {e.attempt + 1}</b>
                  <span>Written in the next exam session. A pass updates this semester and the CGPA.</span>
                </div>
              </div>
            </div>
          ))}
        </section>
      )}
      <p className="cr-muted">
        {data.regulation
          ? `Graded under regulation ${data.regulation.name}. ${data.regulation.arrears_in_gpa === "zero"
            ? "Arrear subjects count with 0 points until passed."
            : "Arrear subjects are left out of the SGPA until passed."}`
          : "No regulation is set up yet, so grades use the college's standard scale."}
      </p>
    </div>
  );
}
