// WAVE 3 PART 2 - registration progress for one exam session, by class,
// with each class's student list one click away.
import { Fragment, useEffect, useState } from "react";
import API from "../../api";
import { errorText, rupees } from "./examSessionUtil";

function ClassList({ sessionId, row }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    API.get(`exam-sessions/${sessionId}/registrations/`, { params: { course: row.course_id, year: row.year, semester: row.semester } })
      .then((r) => setList(r.data))
      .catch((err) => setError(errorText(err, "Couldn't load the students.")));
  }, [sessionId, row]);
  if (error) return <p className="xs-muted xs-bad">{error}</p>;
  if (!list) return <p className="xs-muted">Loading…</p>;
  if (!list.length) return <p className="xs-muted">No students.</p>;
  return (
    <div className="xs-table-wrap">
      <table className="xs-table">
        <thead><tr><th>Student</th><th>Registration</th><th>Papers</th><th>Arrears</th><th>Fee</th><th>Can write regular papers?</th></tr></thead>
        <tbody>
          {list.map((s) => (
            <tr key={s.student}>
              <td><b>{s.roll_number}</b> {s.name}</td>
              <td>{s.status === "submitted"
                ? <span className={`xs-chip ${s.complete ? "ok" : "warn"}`}>{s.complete ? "Complete" : "Fee not paid"}{s.is_late ? " · late" : ""}</span>
                : <span className="xs-chip grey">{s.status === "draft" ? "Saved, not submitted" : "Not yet"}</span>}</td>
              <td>{s.regular_papers + s.arrears.length || "—"}</td>
              <td>{s.arrears.length ? s.arrears.join(", ") : "—"}</td>
              <td>{s.fee ? `${rupees(s.fee.amount)} · ${s.fee.status}` : "—"}</td>
              <td>{s.eligible
                ? <span className="xs-chip ok">Yes{s.reason === "override" ? " (approved)" : ""}</span>
                : <span className="xs-chip bad">No · {s.reason === "exam_fee_unpaid" ? "exam fee" : `attendance ${s.attendance_percent ?? "—"}%`}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RegistrationProgress({ session }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [openRow, setOpenRow] = useState(null);

  useEffect(() => {
    API.get(`exam-sessions/${session.id}/progress/`)
      .then((r) => { setData(r.data); setError(""); })
      .catch((err) => setError(errorText(err, "Couldn't load registration progress.")));
  }, [session.id]);

  if (error) return <p className="xs-note bad">{error}</p>;
  if (!data) return <p className="xs-muted">Loading…</p>;
  const t = data.totals;
  const key = (c) => `${c.course_id}-${c.year}-${c.semester}`;

  return (
    <div className="xs-stack">
      {!session.registration_required && (
        <p className="xs-note vio">This session doesn't use registration. Hall tickets list each student's class subjects.</p>
      )}
      <div className="xs-stats">
        <div><span>Registered</span><b>{t.registered} <em>/ {t.students} students</em></b></div>
        <div><span>Arrear papers registered</span><b>{t.arrear_papers}</b></div>
        <div><span>Fee not paid</span><b className={t.fee_pending ? "xs-bad" : ""}>{t.fee_pending}</b></div>
        <div><span>Can't write regular papers</span><b className={t.not_eligible ? "xs-bad" : ""}>{t.not_eligible}</b></div>
      </div>
      {data.classes.length === 0 ? <p className="xs-muted">No students write in this session yet.</p> : (
        <div className="xs-table-wrap">
          <table className="xs-table">
            <thead><tr><th>Class</th><th>Students</th><th>Registered</th><th>Not yet</th><th>Arrear papers</th><th>Fee pending</th><th>Can't write</th><th><span className="sr-only">Students</span></th></tr></thead>
            <tbody>
              {data.classes.map((c) => (
                <Fragment key={key(c)}>
                  <tr>
                    <td><b>{c.course || "—"}</b><small>Year {c.year} · Semester {c.semester}</small></td>
                    <td>{c.students}</td><td>{c.registered}</td><td>{c.not_yet}</td>
                    <td>{c.arrear_papers}</td><td>{c.fee_pending}</td><td>{c.not_eligible}</td>
                    <td><button type="button" className="xs-link" aria-expanded={openRow === key(c)}
                      onClick={() => setOpenRow(openRow === key(c) ? null : key(c))}>{openRow === key(c) ? "Hide list" : "Open list"}</button></td>
                  </tr>
                  {openRow === key(c) && (
                    <tr className="xs-sub"><td colSpan={8}><ClassList sessionId={session.id} row={c} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="xs-muted xs-small">"Can't write" uses the hall-ticket eligibility rules (attendance, fines, the semester exam fee). Arrear papers skip the attendance check.</p>
    </div>
  );
}
