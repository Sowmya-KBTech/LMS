// WAVE 3 PART 2 - the whole session's exam timetable, checked against every
// student who writes in it (arrears included): clashes, papers with no date,
// one-click moves to free slots, then publish and release hall tickets.
// Class-by-class dates are still set in Results > Hall Ticket > Exam Schedule.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import API from "../../api";
import { dayLabel, errorText, plural } from "./examSessionUtil";

function Paper({ p }) {
  const cls = `xs-paper${p.arrear_students ? " arrear" : ""}${p.clash_students ? " clash" : ""}`;
  return (
    <span className={cls}>
      <b>{p.code || p.name}{p.arrear_students ? " · has arrears" : ""}</b>
      <small>{p.clash_students ? `${plural(p.clash_students, "student")} clash` : `Sem ${p.semester} · ${p.students}`}</small>
    </span>
  );
}

export default function TimetableCheck({ session, onSessionChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    return API.get(`exam-sessions/${session.id}/timetable-check/`)
      .then((r) => { setData(r.data); setError(""); })
      .catch((err) => setError(errorText(err, "Couldn't check the timetable.")));
  }, [session.id]);

  useEffect(() => { load(); }, [load]);

  const run = async (fn, okText) => {
    setBusy(true);
    setNotice(null);
    try {
      const r = await fn();
      if (r?.data?.id && onSessionChange) onSessionChange(r.data);
      setNotice({ tone: "ok", text: okText });
      await load();
    } catch (err) {
      setNotice({ tone: "bad", text: errorText(err, "That didn't work. Please try again.") });
    } finally {
      setBusy(false);
    }
  };

  const moveTo = (subject, slot) => run(
    () => (subject.schedule_id
      ? API.patch(`exam-schedules/${subject.schedule_id}/`, { exam_date: slot.exam_date, session: slot.session })
      : API.post("exam-schedules/", { subject: subject.id, semester: subject.semester, exam_date: slot.exam_date,
        session: slot.session, exam_session: session.id })),
    `${subject.code || subject.name} is now on ${dayLabel(slot.exam_date)} ${slot.session}.`,
  );

  if (error) return <p className="xs-note bad">{error}</p>;
  if (!data) return <p className="xs-muted">Checking the timetable…</p>;
  const ch = data.checks;
  const published = session.timetable_published;
  const canPublish = data.days.length > 0 && !data.clashes.length && !data.unscheduled.length;

  return (
    <div className="xs-stack">
      {notice && <p className={`xs-note ${notice.tone}`} role="status">{notice.text}</p>}
      <div className="xs-note vio">
        <span>{published
          ? (session.hall_tickets_released ? "Timetable published and hall tickets released." : "Timetable published. Release hall tickets when you're ready.")
          : "Draft timetable. Set each class's dates in Results › Hall Ticket, then fix anything flagged here."}</span>
        <span className="xs-row">
          {!published && <Link className="kb-btn" to="/results?tab=ht">Class exam dates</Link>}
          {!published && <button type="button" className="kb-btn kb-btn--primary" disabled={busy || !canPublish}
            onClick={() => run(() => API.post(`exam-sessions/${session.id}/publish-timetable/`), "Timetable published. Dates are now locked.")}>Publish timetable</button>}
          {published && !session.hall_tickets_released && <button type="button" className="kb-btn kb-btn--primary" disabled={busy}
            onClick={() => run(() => API.post(`exam-sessions/${session.id}/release-hall-tickets/`), "Hall tickets released. Students can download them now.")}>Release hall tickets</button>}
          {published && session.hall_tickets_released && <button type="button" className="kb-btn" disabled={busy}
            onClick={() => run(() => API.post(`exam-sessions/${session.id}/withdraw-hall-tickets/`), "Hall tickets withdrawn.")}>Withdraw hall tickets</button>}
          {published && <button type="button" className="kb-btn" disabled={busy}
            onClick={() => { if (window.confirm("Unpublish the timetable? Hall tickets are withdrawn until you publish again.")) run(() => API.post(`exam-sessions/${session.id}/unpublish-timetable/`), "Timetable unpublished. You can change dates again."); }}>Unpublish</button>}
        </span>
      </div>

      <div className="xs-two">
        <section className="kb-card xs-main">
          <div className="xs-head"><h2 className="xs-h2">Timetable</h2><span className="xs-muted">FN = forenoon · AN = afternoon</span></div>
          {data.days.length === 0 ? <p className="xs-muted">No exam dates in this session yet.</p> : (
            <div className="xs-table-wrap">
              <table className="xs-table">
                <thead><tr><th style={{ width: 120 }}>Date</th><th>FN</th><th>AN</th></tr></thead>
                <tbody>
                  {data.days.map((d) => (
                    <tr key={d.date}>
                      <td><b>{dayLabel(d.date)}</b></td>
                      {["FN", "AN"].map((ss) => (
                        <td key={ss}>{d[ss].length ? d[ss].map((p) => <Paper key={p.id} p={p} />) : <span className="xs-muted">free</span>}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="xs-key">
            <span>Number = students writing</span><span>Dashed = some students write it as an arrear</span>
            <span className="xs-bad"><b>Red = students would have two papers at once</b></span>
          </div>
        </section>

        <aside className="xs-side xs-stack">
          <section className="kb-card xs-stack">
            <div className="xs-head" style={{ marginBottom: 0 }}>
              <h2 className="xs-h2">{data.clashes.length || data.unscheduled.length ? "To fix" : "No clashes"}</h2>
              {data.clashes.length > 0 && <span className="xs-chip bad">Can't publish yet</span>}
            </div>
            {data.clashes.length === 0 && data.unscheduled.length === 0 && (
              <p className="xs-muted">No student has two papers in the same session, and every paper has a date.</p>
            )}
            {data.clashes.map((c) => {
              const move = c.subjects.find((s) => s.id === c.move_subject);
              const other = c.subjects.filter((s) => s.id !== c.move_subject);
              return (
                <div key={`${c.exam_date}-${c.session}-${c.subjects.map((s) => s.id).join("-")}`} className="xs-issue">
                  <b>{dayLabel(c.exam_date)} {c.session} · {c.subjects.map((s) => s.code || s.name).join(" and ")}</b>
                  <span className="xs-muted">{plural(c.count, "student")} {c.count === 1 ? "writes" : "write"} both: {c.students.slice(0, 6).map((s) => s.roll_number || s.name).join(", ")}{c.count > 6 ? "…" : ""}</span>
                  {published ? <span className="xs-muted">Unpublish to move a paper.</span> : c.suggestions.length ? (
                    <>
                      <span>Move <b>{move?.code || move?.name}</b> ({plural(move?.students || 0, "student")}) to a slot free for all of them:</span>
                      <div className="xs-row">
                        {c.suggestions.map((sl) => (
                          <button key={`${sl.exam_date}${sl.session}`} type="button" className="kb-btn kb-btn--sm" disabled={busy}
                            onClick={() => moveTo(move, sl)}>{dayLabel(sl.exam_date)} {sl.session}</button>
                        ))}
                      </div>
                    </>
                  ) : <span className="xs-muted">No free slot inside the session dates. Move {other.map((s) => s.code).join(", ")} or widen the exam dates.</span>}
                </div>
              );
            })}
            {data.unscheduled.map((u) => (
              <div key={u.id} className="xs-issue">
                <b>{u.code || u.name} has no date</b>
                <span className="xs-muted">Semester {u.semester} paper · {plural(u.students, "student")} registered{u.arrear_students ? ` (${u.arrear_students} as arrears)` : ""}</span>
                {published ? null : u.suggestions.length ? (
                  <div className="xs-row">
                    {u.suggestions.map((sl) => (
                      <button key={`${sl.exam_date}${sl.session}`} type="button" className="kb-btn kb-btn--sm" disabled={busy}
                        onClick={() => moveTo(u, sl)}>Put on {dayLabel(sl.exam_date)} {sl.session}</button>
                    ))}
                  </div>
                ) : <span className="xs-muted">Set the session's exam dates to get free slots.</span>}
              </div>
            ))}
          </section>

          <section className="kb-card xs-stack">
            <h2 className="xs-h2">Checks</h2>
            <div className="xs-check-row"><span>Every paper has a date</span>
              <span className={`xs-chip ${ch.scheduled === ch.papers ? "ok" : "bad"}`}>{ch.scheduled} / {ch.papers}</span></div>
            <div className="xs-check-row"><span>No student has two papers at once</span>
              <span className={`xs-chip ${ch.clashes ? "bad" : "ok"}`}>{ch.clashes ? plural(ch.clashes, "clash", "clashes") : "OK"}</span></div>
            <div className="xs-check-row"><span>Most students in one sitting</span>
              <span className="xs-chip grey">{ch.max_students_in_a_session}</span></div>
            <p className="xs-muted xs-small">Students who haven't registered yet are counted with their class's subjects. The check updates as registrations come in.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
