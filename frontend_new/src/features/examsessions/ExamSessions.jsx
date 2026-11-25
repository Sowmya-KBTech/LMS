// WAVE 3 PART 2 - Exam sessions (exam admin): one session per exam season.
// Registration, the session timetable check, publishing and hall-ticket release.
import { useEffect, useState } from "react";
import API from "../../api";
import Shell from "../regulations/CbcsShell";
import SessionForm from "./SessionForm";
import RegistrationProgress from "./RegistrationProgress";
import TimetableCheck from "./TimetableCheck";
import { DutiesTab, SeatingTab } from "./ExamSeating";      // WAVE 3 PART 2b
import { WINDOW_LABEL, errorText, longDate, rupees } from "./examSessionUtil";
import "../../styles/ExamSessions.css";

function Steps({ s }) {
  const regDone = !s.registration_required || ["late", "closed"].includes(s.window) || s.timetable_published;
  const steps = [
    { name: "Set up", note: "done", done: true },
    { name: "Registration", note: s.registration_required ? WINDOW_LABEL[s.window]?.text : "not used", done: regDone || s.window === "open" },
    { name: "Timetable", note: s.timetable_published ? "published" : "draft", done: s.timetable_published },
    { name: "Hall tickets", note: s.hall_tickets_released ? "released" : "not released", done: s.hall_tickets_released },
    { name: "Seating + duties", note: "per exam day", done: false },
    { name: "Results", note: "marks entry", done: false },
  ];
  return (
    <ol className="xs-steps" aria-label="Session progress">
      {steps.map((st, i) => (
        <li key={st.name} className={st.done ? "done" : ""}><b>{i + 1} {st.name}</b>{st.note}</li>
      ))}
    </ol>
  );
}

export default function ExamSessions() {
  const [sessions, setSessions] = useState(null);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("registration");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = (pickId) => API.get("exam-sessions/").then((r) => {
    setSessions(r.data);
    const pick = r.data.find((s) => s.id === pickId) || r.data.find((s) => s.is_current) || r.data[0] || null;
    setSelected(pick ? pick.id : null);
  }).catch((err) => setError(errorText(err, "Couldn't load exam sessions.")));

  useEffect(() => { load(); }, []);

  const s = sessions?.find((x) => x.id === selected);
  const replace = (row) => setSessions((list) => list.map((x) => (x.id === row.id ? { ...x, ...row } : x)));

  const act = async (fn, text) => {
    setNotice("");
    try {
      const r = await fn();
      replace(r.data);
      setNotice(text);
    } catch (err) {
      setNotice(errorText(err, "That didn't work. Please try again."));
    }
  };

  const actions = !creating && (
    <button type="button" className="kb-btn kb-btn--primary" onClick={() => { setCreating(true); setNotice(""); }}>New exam session</button>
  );

  return (
    <Shell title="Exam sessions" subtitle="One session per exam season. Registration, the timetable and hall tickets all belong to it." actions={actions}>
      <div className="xs-page">
        {error && <p className="xs-note bad">{error}</p>}
        {creating && (
          <section className="kb-card">
            <div className="xs-head"><h2 className="xs-h2">New exam session</h2></div>
            <SessionForm onCancel={() => setCreating(false)}
              onSaved={(row) => { setCreating(false); setTab("settings"); load(row.id); setNotice(`${row.name} created.${row.is_current ? "" : " Make it current when students should register for it."}`); }} />
          </section>
        )}

        {sessions && sessions.length === 0 && !creating && (
          <section className="kb-card"><p className="xs-muted">No exam sessions yet. Create one for the next exam season, for example "Nov/Dec 2026".</p></section>
        )}

        {sessions && sessions.length > 0 && (
          <div className="xs-sessions" role="group" aria-label="Exam sessions">
            {sessions.map((x) => (
              <button key={x.id} type="button" className={`kb-btn${x.id === selected ? " kb-btn--primary" : ""}`}
                aria-pressed={x.id === selected} onClick={() => { setSelected(x.id); setNotice(""); }}>
                {x.name}{x.is_current ? " · current" : ""}
              </button>
            ))}
          </div>
        )}

        {notice && <p className="xs-note vio" role="status">{notice}</p>}

        {s && (
          <section className="kb-card xs-stack">
            <div className="xs-head" style={{ marginBottom: 0 }}>
              <div className="xs-stack" style={{ gap: 4 }}>
                <div className="xs-row">
                  <h2 className="xs-h2" style={{ fontSize: 20 }}>{s.name}</h2>
                  {s.is_current && <span className="xs-chip vio">Current</span>}
                  {s.registration_required && <span className={`xs-chip ${WINDOW_LABEL[s.window].tone}`}>{WINDOW_LABEL[s.window].text}</span>}
                  <span className="xs-chip grey">{s.kind === "regular" ? "Regular + arrear" : "Supplementary"}</span>
                </div>
                <p className="xs-muted">
                  Exams {s.exam_start ? `${longDate(s.exam_start)} – ${longDate(s.exam_end)}` : "dates not set"}
                  {s.registration_required && s.reg_opens ? ` · Registration ${longDate(s.reg_opens)} – ${longDate(s.reg_closes)}` : ""}
                  {s.late_until ? ` · late until ${longDate(s.late_until)}` : ""}
                  {s.fee_required && s.registration_required ? ` · ${rupees(s.regular_fee)} a paper, arrears ${rupees(s.arrear_fee)}` : ""}
                </p>
              </div>
              <div className="xs-row">
                {!s.is_current && <button type="button" className="kb-btn" onClick={() => act(() => API.post(`exam-sessions/${s.id}/make-current/`), `${s.name} is now the current session.`).then(() => load(s.id))}>Make current</button>}
                {s.registration_required && ["open", "late"].includes(s.window) && (
                  <button type="button" className="kb-btn" onClick={() => act(() => API.patch(`exam-sessions/${s.id}/`, { registration_closed: true }), "Registration closed.")}>Close registration now</button>
                )}
                {s.registration_required && s.registration_closed && (
                  <button type="button" className="kb-btn" onClick={() => act(() => API.patch(`exam-sessions/${s.id}/`, { registration_closed: false }), "Registration reopened (within its dates).")}>Reopen registration</button>
                )}
              </div>
            </div>
            <Steps s={s} />

            <div className="xs-tabs" role="tablist" aria-label="Session">
              {[["registration", "Registration"], ["timetable", "Timetable check"], ["seating", "Seating"], ["duties", "Invigilation"], ["settings", "Settings"]].map(([id, label]) => (
                <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
              ))}
            </div>
            {tab === "registration" && <RegistrationProgress key={s.id} session={s} />}
            {tab === "timetable" && <TimetableCheck key={s.id} session={s} onSessionChange={replace} />}
            {tab === "seating" && <SeatingTab key={s.id} session={s} />}
            {tab === "duties" && <DutiesTab key={s.id} session={s} />}
            {tab === "settings" && (
              <SessionForm key={s.id} session={s} onSaved={(row) => { replace(row); setNotice("Settings saved."); }} />
            )}
          </section>
        )}
      </div>
    </Shell>
  );
}
