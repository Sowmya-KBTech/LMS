// ============================================================
// AttendanceCorrection — the CLASS TUTOR's attendance tools (meeting point 6)
// ============================================================
// Lives as the "Attendance" tab of My Class. Uses the existing APIs:
//   GET  /attendance-corrections/day/?course=&year=&date=   that day's periods
//   POST /attendance-corrections/                           correct one record
//   POST /attendance-corrections/late-entry/                enter a missed period
//   GET  /attendance-corrections/?course=&year=             the correction log
//
// Every change needs a reason (10+ characters) and is logged. Approved
// on-duty records can't be changed here. The server enforces all of it;
// this screen only makes it easy to do.
// ============================================================

import { useEffect, useState } from "react";
import API from "../../api";
import Icon from "../../components/Icon";

const MIN_REASON = 10;
const LABEL = { present: "Present", absent: "Absent", duty_leave: "On duty", not_marked: "Not marked" };
const PILL = { present: "ok", absent: "bad", duty_leave: "info", not_marked: "warn" };

const toKey = (d) => {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().split("T")[0];
};
const todayKey = () => toKey(new Date());
const shift = (key, n) => {
  const d = new Date(`${key}T00:00:00`);
  d.setDate(d.getDate() + n);
  return toKey(d);
};
const dayLabel = (key) =>
  new Date(`${key}T00:00:00`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
const fmtWhen = (iso) =>
  iso ? new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit" }) : "";
const fmtDate = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("-") : "");
const errText = (err, fallback) => err?.response?.data?.detail || err?.response?.data?.error || fallback;

export default function AttendanceCorrection({ courseId, yearNumber }) {
  const [day, setDay] = useState(todayKey());
  const [periods, setPeriods] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // correcting one record: { attendance, newStatus }
  const [edit, setEdit] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  // entering a never-marked period: { key, statuses: {studentId: status}, reason }
  const [late, setLate] = useState(null);

  const [log, setLog] = useState([]);
  const [showLog, setShowLog] = useState(false);

  const loadDay = () => {
    if (!courseId || !yearNumber) return;
    setLoading(true);
    setError("");
    API.get("/attendance-corrections/day/", { params: { course: courseId, year: yearNumber, date: day } })
      .then((res) => setPeriods(res.data?.periods || []))
      .catch((err) => { setPeriods([]); setError(errText(err, "Couldn't load this day.")); })
      .finally(() => setLoading(false));
  };

  const loadLog = () =>
    API.get("/attendance-corrections/", { params: { course: courseId, year: yearNumber } })
      .then((res) => setLog(res.data || []))
      .catch(() => setLog([]));

  useEffect(() => { setEdit(null); setLate(null); setNotice(""); loadDay(); }, [day, courseId, yearNumber]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (showLog) loadLog(); }, [showLog, courseId, yearNumber]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- correct one record ----------
  const startEdit = (rec) => {
    setLate(null);
    setReason("");
    setEdit({ attendance: rec.attendance, newStatus: rec.status === "present" ? "absent" : "present", name: rec.student_name });
  };

  const saveEdit = async () => {
    if (reason.trim().length < MIN_REASON) return;
    setBusy(true);
    try {
      await API.post("/attendance-corrections/", {
        attendance: edit.attendance, new_status: edit.newStatus, reason: reason.trim(),
      });
      setNotice(`${edit.name}: changed to ${LABEL[edit.newStatus]}.`);
      setEdit(null);
      loadDay();
      if (showLog) loadLog();
    } catch (err) {
      alert(errText(err, "Couldn't save the correction."));
    } finally {
      setBusy(false);
    }
  };

  // ---------- enter a missed period ----------
  const startLate = (p) => {
    setEdit(null);
    const statuses = {};
    (p.students || []).forEach((s) => { statuses[s.student] = s.od_locked ? "duty_leave" : "present"; });
    setLate({ key: `${p.teaching_assignment}|${p.hour}`, statuses, reason: "" });
  };

  const saveLate = async (p) => {
    if (late.reason.trim().length < MIN_REASON) return;
    setBusy(true);
    try {
      const res = await API.post("/attendance-corrections/late-entry/", {
        teaching_assignment: p.teaching_assignment,
        date: day,
        hour: p.hour,
        reason: late.reason.trim(),
        records: (p.students || []).map((s) => ({ student: s.student, status: late.statuses[s.student] })),
      });
      setNotice(res.data?.message || "Attendance entered.");
      setLate(null);
      loadDay();
      if (showLog) loadLog();
    } catch (err) {
      alert(errText(err, "Couldn't enter the attendance."));
    } finally {
      setBusy(false);
    }
  };

  const isToday = day === todayKey();

  return (
    <div className="kb-tc">
      {/* ---------- day picker ---------- */}
      <section className="kb-card kb-tc-head">
        <div className="kb-grow">
          <h2>Correct attendance</h2>
          <p>Pick a day. Change a student's status, or enter a period nobody marked. Every change needs a reason and is logged.</p>
        </div>
        <div className="kb-tc-day">
          <button type="button" className="kb-btn kb-btn--sm" onClick={() => setDay(shift(day, -1))} aria-label="Previous day">‹</button>
          <input type="date" value={day} max={todayKey()} onChange={(e) => e.target.value && setDay(e.target.value)} />
          <button type="button" className="kb-btn kb-btn--sm" onClick={() => setDay(shift(day, 1))} disabled={isToday} aria-label="Next day">›</button>
        </div>
      </section>

      <p className="kb-tc-dayname">{dayLabel(day)}{isToday ? " · today" : ""}</p>
      {notice && <div className="kb-tc-notice" role="status"><Icon name="check" /> {notice}</div>}
      {error && <div className="kb-at-error" role="alert">{error}</div>}

      {loading ? (
        <div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading…</b></div>
      ) : !error && periods.length === 0 ? (
        <div className="kb-at-empty">
          <b>Nothing to show for this day</b>
          <span>No attendance was marked, and there are no timetable periods (weekend, holiday or no approved timetable).</span>
        </div>
      ) : (
        periods.map((p) => {
          const key = `${p.teaching_assignment}|${p.hour}`;
          const absent = (p.records || []).filter((r) => r.status === "absent").length;
          return (
            <section key={key} className="kb-card kb-tc-period">
              <div className="kb-tc-phead">
                <div className="kb-grow">
                  <b>Period {p.hour} · {p.subject}</b>
                  <span>{p.subject_code ? `${p.subject_code} · ` : ""}{p.teacher}</span>
                </div>
                {p.marked ? (
                  <span className="kb-pill ok">Marked · {absent} absent</span>
                ) : (
                  <span className="kb-pill warn">Not marked</span>
                )}
              </div>

              {/* ----- marked: correct individual students ----- */}
              {p.marked && (
                <ul className="kb-tc-list">
                  {p.records.map((r) => {
                    const editing = edit?.attendance === r.attendance;
                    return (
                      <li key={r.attendance} className={editing ? "is-editing" : ""}>
                        <div className="kb-tc-row">
                          <span className="kb-tc-who">
                            <b>{r.student_name}</b>
                            <span>{r.student_roll_no || ""}</span>
                          </span>
                          <span className={`kb-pill ${PILL[r.status] || ""}`}>{LABEL[r.status] || r.status}</span>
                          {r.od_locked ? (
                            <span className="kb-tc-lock" title="Approved on-duty - can't be changed here"><Icon name="lock" /> Approved OD</span>
                          ) : !editing ? (
                            <button type="button" className="kb-btn kb-btn--sm" onClick={() => startEdit(r)}>
                              Mark {r.status === "present" ? "absent" : "present"}
                            </button>
                          ) : null}
                        </div>
                        {editing && (
                          <div className="kb-tc-edit">
                            <span>Change <b>{LABEL[r.status]}</b> → <b>{LABEL[edit.newStatus]}</b></span>
                            <textarea
                              rows={2}
                              autoFocus
                              placeholder="Reason, e.g. 'Was present, teacher marked by mistake'"
                              value={reason}
                              onChange={(e) => setReason(e.target.value)}
                            />
                            <div className="kb-tc-actions">
                              <small>{reason.trim().length < MIN_REASON ? `At least ${MIN_REASON} characters` : "Ready"}</small>
                              <button type="button" className="kb-btn kb-btn--sm" onClick={() => setEdit(null)} disabled={busy}>Cancel</button>
                              <button type="button" className="kb-btn kb-btn--sm kb-btn--primary" onClick={saveEdit}
                                disabled={busy || reason.trim().length < MIN_REASON}>
                                {busy ? "Saving…" : "Save change"}
                              </button>
                            </div>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}

              {/* ----- not marked: enter it late ----- */}
              {!p.marked && late?.key !== key && (
                <div className="kb-tc-actions kb-tc-actions--start">
                  <span>{(p.students || []).length} students · the subject teacher can no longer mark this period</span>
                  <button type="button" className="kb-btn kb-btn--sm kb-btn--primary" onClick={() => startLate(p)}>
                    Enter attendance
                  </button>
                </div>
              )}
              {!p.marked && late?.key === key && (
                <>
                  <p className="kb-tc-help">Everyone starts as <b>Present</b>. Tap a student to mark <b>Absent</b>.</p>
                  <ul className="kb-tc-list">
                    {(p.students || []).map((s) => {
                      const st = late.statuses[s.student];
                      return (
                        <li key={s.student}>
                          <button
                            type="button"
                            className={`kb-tc-row kb-tc-tap s-${st}`}
                            disabled={s.od_locked}
                            onClick={() => setLate({ ...late, statuses: { ...late.statuses, [s.student]: st === "present" ? "absent" : "present" } })}
                          >
                            <span className="kb-tc-who">
                              <b>{s.student_name}</b>
                              <span>{s.student_roll_no || ""}</span>
                            </span>
                            <span className={`kb-pill ${PILL[st]}`}>{s.od_locked ? "On duty · approved" : LABEL[st]}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  <div className="kb-tc-edit">
                    <textarea
                      rows={2}
                      placeholder="Reason, e.g. 'Teacher was on leave, register given to class in-charge'"
                      value={late.reason}
                      onChange={(e) => setLate({ ...late, reason: e.target.value })}
                    />
                    <div className="kb-tc-actions">
                      <small>
                        {Object.values(late.statuses).filter((v) => v === "absent").length} absent ·{" "}
                        {late.reason.trim().length < MIN_REASON ? `reason: at least ${MIN_REASON} characters` : "ready"}
                      </small>
                      <button type="button" className="kb-btn kb-btn--sm" onClick={() => setLate(null)} disabled={busy}>Cancel</button>
                      <button type="button" className="kb-btn kb-btn--sm kb-btn--primary" onClick={() => saveLate(p)}
                        disabled={busy || late.reason.trim().length < MIN_REASON}>
                        {busy ? "Saving…" : "Save attendance"}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </section>
          );
        })
      )}

      {/* ---------- correction log ---------- */}
      <section className="kb-card kb-tc-period">
        <div className="kb-tc-phead">
          <div className="kb-grow">
            <b>Correction log</b>
            <span>Every change made by you, the admin, or a subject teacher after the first day.</span>
          </div>
          <button type="button" className="kb-btn kb-btn--sm" onClick={() => setShowLog(!showLog)}>
            {showLog ? "Hide" : "Show"}
          </button>
        </div>
        {showLog && (
          log.length === 0 ? (
            <p className="kb-tc-help">No corrections yet.</p>
          ) : (
            <div className="table-container">
              <table className="sd-tbl kb-tc-log">
                <thead>
                  <tr><th>Date</th><th>Student</th><th>Subject</th><th>Change</th><th>Reason</th><th>By</th></tr>
                </thead>
                <tbody>
                  {log.map((c) => (
                    <tr key={c.id}>
                      <td>{fmtDate(c.date)}<br /><small>Period {c.hour}</small></td>
                      <td>{c.student_name}<br /><small>{c.student_roll_no}</small></td>
                      <td>{c.subject}</td>
                      <td>{LABEL[c.old_status] || c.old_status} → <b>{LABEL[c.new_status] || c.new_status}</b></td>
                      <td className="kb-tc-reason">{c.reason}</td>
                      <td>{c.corrected_by}<br /><small>{fmtWhen(c.corrected_at)}</small></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </section>
    </div>
  );
}
