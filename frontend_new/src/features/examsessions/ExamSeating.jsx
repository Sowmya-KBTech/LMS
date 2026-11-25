// WAVE 3 PART 2b - halls, seating and invigilation for an exam session.
// Everything for this part lives in this one file:
//   SeatingTab     the halls, seat allotment per sitting, hall plans + door lists to print
//   DutiesTab      invigilation duties per sitting, staff on leave, fair share of duties
//   MyExamDuties   a staff member's own duties (Results > Exam duties)
import { useCallback, useEffect, useState } from "react";
import API from "../../api";
import { dayLabel, errorText, plural } from "./examSessionUtil";
import "../../styles/ExamSessions.css";

const sitKey = (s) => `${s.date}|${s.sitting}`;

// the sittings (date + FN/AN) of a session, with a picker
function useSittings(sessionId) {
  const [info, setInfo] = useState(null);
  const [pick, setPick] = useState("");
  const [error, setError] = useState("");
  const reload = useCallback(() => API.get(`exam-sessions/${sessionId}/sittings/`)
    .then((r) => {
      setInfo(r.data);
      setPick((p) => p || (r.data.sittings[0] ? sitKey(r.data.sittings[0]) : ""));
    })
    .catch((err) => setError(errorText(err, "Couldn't load the exam sittings."))), [sessionId]);
  useEffect(() => { reload(); }, [reload]);
  const cur = info?.sittings.find((s) => sitKey(s) === pick) || null;
  return { info, pick, setPick, cur, reload, error };
}

function SittingPicker({ info, pick, setPick, field }) {
  return (
    <label className="xs-field" style={{ minWidth: 220 }}>Exam
      <select className="kb-input" value={pick} onChange={(e) => setPick(e.target.value)}>
        {info.sittings.map((s) => (
          <option key={sitKey(s)} value={sitKey(s)}>
            {dayLabel(s.date)} · {s.sitting} — {s.papers.join(", ")} ({field === "duties" ? `${s.duties} on duty` : `${s.seated} seated`})
          </option>
        ))}
      </select>
    </label>
  );
}

function printPage(title, bodyHtml) {
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(`<html><head><title>${title}</title><style>
    body{font-family:Arial,sans-serif;font-size:13px;padding:20px;color:#111}
    h1{font-size:18px;margin:0 0 4px} h2{font-size:15px;margin:18px 0 6px} p{margin:0 0 8px}
    table{border-collapse:collapse;width:100%;margin-bottom:10px} th,td{border:1px solid #999;padding:5px 7px;text-align:left}
    .grid{display:grid;gap:6px;margin:8px 0} .bench{border:1px solid #999;padding:4px;display:flex;gap:4px}
    .seat{flex:1;border:1px solid #ccc;padding:4px;text-align:center;font-size:11px}
    .page{page-break-after:always}
    @media print{@page{size:A4;margin:12mm}}
  </style></head><body>${bodyHtml}</body></html>`);
  win.document.close();
  win.print();
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ============================================================ halls
function Halls({ halls, onChange }) {
  const [form, setForm] = useState({ name: "", seats: 30, per_bench: 2 });
  const [msg, setMsg] = useState(null);
  const run = async (fn, ok) => {
    setMsg(null);
    try { await fn(); setMsg({ tone: "ok", text: ok }); onChange(); } catch (err) { setMsg({ tone: "bad", text: errorText(err, "That didn't work.") }); }
  };
  const total = halls.filter((h) => h.is_active).reduce((t, h) => t + h.seats, 0);
  return (
    <section className="kb-card xs-side xs-stack">
      <div className="xs-head" style={{ marginBottom: 0 }}>
        <h2 className="xs-h2">Exam halls</h2>
        <button type="button" className="kb-btn kb-btn--sm" onClick={() => run(() => API.post("exam-halls/from-rooms/"), "Rooms from the timetable added (half their seats; labs off).")}>Add timetable rooms</button>
      </div>
      {msg && <p className={`xs-note ${msg.tone}`} role="status">{msg.text}</p>}
      {halls.length === 0 ? <p className="xs-muted">No halls yet.</p> : (
        <div className="xs-table-wrap">
          <table className="xs-table">
            <thead><tr><th>Hall</th><th>Seats</th><th>Bench</th><th>Use</th></tr></thead>
            <tbody>
              {halls.map((h) => (
                <tr key={h.id}>
                  <td className="xs-nowrap"><b>{h.name}</b></td>
                  <td><input className="kb-input xs-num" type="number" min="1" aria-label={`Exam seats in ${h.name}`} defaultValue={h.seats}
                    onBlur={(e) => Number(e.target.value) !== h.seats && run(() => API.patch(`exam-halls/${h.id}/`, { seats: e.target.value }), `${h.name} updated.`)} /></td>
                  <td><select className="kb-input xs-num" aria-label={`Students per bench in ${h.name}`} value={h.per_bench}
                    onChange={(e) => run(() => API.patch(`exam-halls/${h.id}/`, { per_bench: e.target.value }), `${h.name} updated.`)}>
                    {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}</select></td>
                  <td><input type="checkbox" aria-label={`Use ${h.name} for exams`} checked={h.is_active}
                    onChange={(e) => run(() => API.patch(`exam-halls/${h.id}/`, { is_active: e.target.checked }), `${h.name} ${e.target.checked ? "switched on" : "switched off"}.`)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="xs-muted xs-small">{total} exam seats in halls that are switched on.</p>
      <form className="xs-row" onSubmit={(e) => { e.preventDefault(); run(() => API.post("exam-halls/", form), `${form.name} added.`).then(() => setForm({ name: "", seats: 30, per_bench: 2 })); }}>
        <label className="xs-field" style={{ flex: "1 1 120px" }}>New hall<input className="kb-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="C-104" /></label>
        <label className="xs-field" style={{ width: 90 }}>Seats<input className="kb-input" type="number" min="1" value={form.seats} onChange={(e) => setForm({ ...form, seats: e.target.value })} /></label>
        <button className="kb-btn" type="submit" style={{ alignSelf: "flex-end" }} disabled={!form.name.trim()}>Add</button>
      </form>
    </section>
  );
}

// ============================================================ seating
export function SeatingTab({ session }) {
  const { info, pick, setPick, cur, reload, error } = useSittings(session.id);
  const [plan, setPlan] = useState(null);
  const [hallId, setHallId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const loadPlan = useCallback(() => {
    if (!cur) return Promise.resolve();
    return API.get(`exam-sessions/${session.id}/seating/`, { params: { date: cur.date, sitting: cur.sitting } })
      .then((r) => setPlan(r.data)).catch((err) => setMsg({ tone: "bad", text: errorText(err, "Couldn't load the seats.") }));
  }, [session.id, cur]);
  useEffect(() => { loadPlan(); }, [loadPlan]);

  const allot = async (all) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await API.post(`exam-sessions/${session.id}/seating/allot/`, all ? { all: true } : { date: cur.date, sitting: cur.sitting });
      setMsg({ tone: r.data.unseated ? "warn" : "ok", text: r.data.detail });
      await reload();
      await loadPlan();
    } catch (err) {
      setMsg({ tone: "bad", text: errorText(err, "Couldn't give seats.") });
    } finally {
      setBusy(false);
    }
  };
  const setMode = (mode) => API.patch(`exam-sessions/${session.id}/rules/`, { seating_mode: mode }).then(reload);

  if (error) return <p className="xs-note bad">{error}</p>;
  if (!info) return <p className="xs-muted">Loading…</p>;
  const usedHalls = plan ? plan.halls.filter((h) => h.used) : [];
  const shown = usedHalls.find((h) => h.id === hallId) || usedHalls[0];

  const printPlans = () => {
    const title = `${session.name} · ${dayLabel(plan.date)} ${plan.sitting}`;
    printPage(`Hall plans · ${title}`, usedHalls.map((h) => {
      const per = h.per_bench || 2;
      const byBench = {};
      h.seat_map.forEach((s) => { (byBench[Math.floor((s.seat - 1) / per)] ||= []).push(s); });
      const benches = Object.keys(byBench).sort((a, b) => a - b).map((k) => byBench[k]);
      const door = [...h.seat_map].sort((a, b) => a.roll_number.localeCompare(b.roll_number));
      return `<div class="page"><h1>${esc(h.name)} · hall plan</h1><p>${esc(title)} · ${h.used} students</p>
        <p><b>Front · invigilator desk</b></p>
        <div class="grid" style="grid-template-columns:repeat(5,1fr)">${benches.map((b) => `<div class="bench">${b.map((s) => `<div class="seat"><b>${s.seat}</b><br>${esc(s.roll_number)}<br>${esc(s.code)}</div>`).join("")}</div>`).join("")}</div>
        <h2>Door list · ${esc(h.name)}</h2>
        <table><thead><tr><th>Register no.</th><th>Name</th><th>Paper</th><th>Seat</th><th>Signature</th></tr></thead><tbody>
        ${door.map((s) => `<tr><td>${esc(s.roll_number)}</td><td>${esc(s.name)}</td><td>${esc(s.code)}</td><td>${s.seat}</td><td></td></tr>`).join("")}
        </tbody></table></div>`;
    }).join(""));
  };

  return (
    <div className="xs-stack">
      {!info.timetable_published && <p className="xs-note warn">Publish the timetable first (Timetable check tab). Seats are given for the final dates only.</p>}
      {msg && <p className={`xs-note ${msg.tone}`} role="status">{msg.text}</p>}
      <div className="xs-two">
        <div className="xs-main xs-stack">
          <section className="kb-card xs-stack">
            <div className="xs-row" style={{ alignItems: "flex-end", justifyContent: "space-between" }}>
              {info.sittings.length ? <SittingPicker info={info} pick={pick} setPick={(v) => { setPick(v); setHallId(null); }} /> : <p className="xs-muted">No exam dates in this session yet.</p>}
              <div className="xs-row">
                <button type="button" className="kb-btn" disabled={busy || !cur || !info.timetable_published} onClick={() => allot(false)}>Give seats for this exam</button>
                <button type="button" className="kb-btn kb-btn--primary" disabled={busy || !info.sittings.length || !info.timetable_published} onClick={() => allot(true)}>Give seats for every exam</button>
              </div>
            </div>
            <fieldset className="xs-fieldset">
              <legend>How seats are given</legend>
              <label className="xs-check"><input type="radio" name="seatmode" checked={info.rules.seating_mode === "alternate"} onChange={() => setMode("alternate")} /> Different papers side by side on each bench</label>
              <label className="xs-check"><input type="radio" name="seatmode" checked={info.rules.seating_mode === "spaced"} onChange={() => setMode("spaced")} /> One student per bench</label>
            </fieldset>
            {plan && (
              <div className="xs-stats">
                <div><span>Students this exam</span><b>{plan.students}</b><span>{plan.papers.map((p) => `${p.code} ${p.students}`).join(" · ")}</span></div>
                <div><span>Seated</span><b>{plan.seated} <em>/ {plan.seats_available} seats</em></b></div>
                <div><span>Halls used</span><b>{usedHalls.length}</b></div>
                <div><span>Without a seat</span><b className={plan.students - plan.seated > 0 ? "xs-bad" : ""}>{plan.students - plan.seated}</b></div>
              </div>
            )}
            {plan && plan.same_neighbours > 0 && (
              <p className="xs-note warn">
                {plan.papers.length === 1
                  ? "Only one paper is written in this exam, so bench-mates write the same paper. Choose One student per bench to keep them apart."
                  : `${plural(plan.same_neighbours, "bench has", "benches have")} two students of the same paper; there weren't enough students of other papers to mix.`}
              </p>
            )}
            {plan && plan.not_seated.length > 0 && plan.seated > 0 && <p className="xs-note bad">No seat yet for: {plan.not_seated.map((s) => s.roll_number || s.name).join(", ")}. Add a hall or seats, then give seats again.</p>}
          </section>

          {plan && plan.seated > 0 && shown && (
            <section className="kb-card xs-stack">
              <div className="xs-head" style={{ marginBottom: 0 }}>
                <div className="xs-row" role="group" aria-label="Hall">
                  {usedHalls.map((h) => (
                    <button key={h.id} type="button" className={`kb-btn kb-btn--sm${h.id === shown.id ? " kb-btn--primary" : ""}`} aria-pressed={h.id === shown.id}
                      onClick={() => setHallId(h.id)}>{h.name} · {h.used}</button>
                  ))}
                </div>
                <button type="button" className="kb-btn" onClick={printPlans}>Print hall plans and door lists</button>
              </div>
              <div className="xs-front">Front · invigilator desk</div>
              <SeatMap hall={shown} />
            </section>
          )}
          {plan && plan.seated === 0 && plan.students > 0 && <section className="kb-card"><p className="xs-muted">No seats given for this exam yet.</p></section>}
        </div>
        <Halls halls={info.halls} onChange={() => reload().then(loadPlan)} />
      </div>
    </div>
  );
}

const TONES = ["t0", "t1", "t2", "t3", "t4"];

function SeatMap({ hall }) {
  const per = hall.per_bench || 2;
  const tone = {};
  hall.seat_map.forEach((s) => { if (!(s.code in tone)) tone[s.code] = TONES[Object.keys(tone).length % TONES.length]; });
  const benches = [];
  for (let b = 0; b * per < hall.seats; b += 1) {
    const seats = [];
    for (let k = 1; k <= per; k += 1) {
      const n = b * per + k;
      if (n > hall.seats) break;
      seats.push(hall.seat_map.find((s) => s.seat === n) || { seat: n, empty: true });
    }
    benches.push(seats);
  }
  return (
    <>
      <div className="xs-benches">
        {benches.map((b, i) => (
          <div className="xs-bench" key={i}>
            {b.map((s) => (
              <div key={s.seat} className={`xs-seat ${s.empty ? "empty" : tone[s.code]}`}>
                <b>{s.seat}</b>{s.empty ? <span>empty</span> : <><span>{s.roll_number || s.name}</span><span>{s.code}</span></>}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="xs-key">{Object.entries(tone).map(([code, t]) => <span key={code} className="xs-row"><span className={`xs-swatch ${t}`} aria-hidden="true" />{code}</span>)}</div>
    </>
  );
}

// ============================================================ invigilation
export function DutiesTab({ session }) {
  const { info, pick, setPick, cur, reload, error } = useSittings(session.id);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => {
    if (!cur) return Promise.resolve();
    return API.get(`exam-sessions/${session.id}/duties/`, { params: { date: cur.date, sitting: cur.sitting } })
      .then((r) => setData(r.data)).catch((err) => setMsg({ tone: "bad", text: errorText(err, "Couldn't load the duties.") }));
  }, [session.id, cur]);
  useEffect(() => { load(); }, [load]);

  const run = async (fn) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fn();
      setMsg({ tone: r.data?.unfilled ? "warn" : "ok", text: r.data?.detail || "Saved." });
      await reload();
      await load();
    } catch (err) {
      setMsg({ tone: "bad", text: errorText(err, "That didn't work.") });
    } finally {
      setBusy(false);
    }
  };
  const setRule = (k, v) => API.patch(`exam-sessions/${session.id}/rules/`, { [k]: v }).then(() => { reload(); load(); });
  const change = (dutyId, staff) => run(() => API.patch(`exam-duties/${dutyId}/`, { staff }).then((r) => ({ data: { detail: `${r.data.name} is on that duty now.` } })));

  if (error) return <p className="xs-note bad">{error}</p>;
  if (!info) return <p className="xs-muted">Loading…</p>;
  const staffOptions = data ? data.load : [];
  const maxLoad = Math.max(1, ...staffOptions.map((s) => s.duties));

  const staffCell = (s) => (
    <select key={s.duty_id} className="kb-input" aria-label={`Change ${s.name}`} value={s.id} disabled={busy}
      onChange={(e) => change(s.duty_id, Number(e.target.value))}>
      <option value={s.id}>{s.name}{s.on_leave ? " (on leave)" : ""}</option>
      {staffOptions.filter((o) => o.id !== s.id).map((o) => <option key={o.id} value={o.id}>{o.name} · {o.duties}</option>)}
    </select>
  );

  return (
    <div className="xs-stack">
      {msg && <p className={`xs-note ${msg.tone}`} role="status">{msg.text}</p>}
      {data && data.conflicts.map((c) => (
        <div key={c.duty_id} className="xs-note warn">
          <span><b>{c.staff.name}</b> is on leave on {dayLabel(c.date)} {c.sitting} but has {c.hall === "Relief" ? "a relief duty" : `${c.hall}`}.</span>
          {c.suggest ? <button type="button" className="kb-btn kb-btn--sm kb-btn--primary" disabled={busy} onClick={() => change(c.duty_id, c.suggest.id)}>Replace with {c.suggest.name} ({plural(c.suggest.duties, "duty", "duties")})</button>
            : <span>Nobody is free that day. Change the rules or pick someone below.</span>}
        </div>
      ))}
      <div className="xs-two">
        <section className="kb-card xs-main xs-stack">
          <div className="xs-row" style={{ alignItems: "flex-end", justifyContent: "space-between" }}>
            {info.sittings.length ? <SittingPicker info={info} pick={pick} setPick={setPick} field="duties" /> : <p className="xs-muted">No exam dates yet.</p>}
            <div className="xs-row">
              <button type="button" className="kb-btn" disabled={busy || !cur} onClick={() => run(() => API.post(`exam-sessions/${session.id}/duties/assign/`, { date: cur.date, sitting: cur.sitting }))}>Give duties for this exam</button>
              <button type="button" className="kb-btn kb-btn--primary" disabled={busy || !info.sittings.length}
                onClick={() => { if (window.confirm("Give duties for every exam? Any changes you made by hand are replaced.")) run(() => API.post(`exam-sessions/${session.id}/duties/assign/`, { all: true })); }}>Give duties for every exam</button>
            </div>
          </div>
          {data && !data.seated && <p className="xs-note vio">Give seats for this exam first. Duties follow the halls in use.</p>}
          {data && data.seated && (
            <div className="xs-table-wrap">
              <table className="xs-table">
                <thead><tr><th>Hall</th><th>Students</th><th>Invigilators</th></tr></thead>
                <tbody>
                  {data.halls.map((h) => (
                    <tr key={h.hall.id}>
                      <td><b>{h.hall.name}</b></td><td>{h.students}</td>
                      <td><div className="xs-row">{h.staff.map(staffCell)}
                        {h.staff.length < h.needed && <span className="xs-chip bad">{h.needed - h.staff.length} missing</span>}</div></td>
                    </tr>
                  ))}
                  <tr>
                    <td><b>Relief / flying squad</b></td><td>—</td>
                    <td><div className="xs-row">{data.relief.map(staffCell)}
                      {data.relief.length === 0 && <span className="xs-muted">—</span>}</div></td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
          {data && data.unfilled > 0 && <p className="xs-note bad">{plural(data.unfilled, "duty", "duties")} not filled: not enough free staff. Allow HODs, or allow two duties a day.</p>}
          {data && data.skipped.length > 0 && (
            <p className="xs-muted xs-small">Not on the list for this exam: {data.skipped.map((s) => `${s.name} (${s.reason})`).join(", ")}.</p>
          )}
        </section>

        <aside className="xs-side xs-stack">
          <section className="kb-card xs-stack">
            <h2 className="xs-h2">Rules</h2>
            <label className="xs-field">Two invigilators when a hall has more than
              <input className="kb-input" type="number" min="0" defaultValue={info.rules.two_invigilators_above} key={`t${info.rules.two_invigilators_above}`}
                onBlur={(e) => setRule("two_invigilators_above", e.target.value)} />
              <span className="xs-muted xs-small">students (0 = always two)</span></label>
            <label className="xs-field">Relief staff per exam
              <input className="kb-input" type="number" min="0" defaultValue={info.rules.relief_per_sitting} key={`r${info.rules.relief_per_sitting}`}
                onBlur={(e) => setRule("relief_per_sitting", e.target.value)} /></label>
            <label className="xs-check"><input type="checkbox" checked={info.rules.skip_own_subject} onChange={(e) => setRule("skip_own_subject", e.target.checked)} /> Don't put staff in the exam of a subject they teach</label>
            <label className="xs-check"><input type="checkbox" checked={info.rules.one_duty_per_day} onChange={(e) => setRule("one_duty_per_day", e.target.checked)} /> At most one duty a day per person</label>
            <label className="xs-check"><input type="checkbox" checked={info.rules.include_hods} onChange={(e) => setRule("include_hods", e.target.checked)} /> Include HODs</label>
            <p className="xs-muted xs-small">Staff on approved leave and the Principal are always left out. Rules apply the next time duties are given.</p>
          </section>
          {data && (
            <section className="kb-card xs-stack">
              <div className="xs-head" style={{ marginBottom: 0 }}><h2 className="xs-h2">Duties per person</h2><span className="xs-muted">whole session</span></div>
              {data.load.slice(0, 12).map((s) => (
                <div key={s.id} className="xs-load"><span>{s.name}</span><span className="xs-loadbar" aria-hidden="true"><span style={{ width: `${(s.duties * 100) / maxLoad}%` }} /></span><b>{s.duties}</b></div>
              ))}
              {data.load.length > 12 && <p className="xs-muted xs-small">and {data.load.length - 12} more staff</p>}
              <p className="xs-muted xs-small">Staff see their duties in Results › Exam duties.</p>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

// ============================================================ staff: my duties
export function MyExamDuties() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    API.get("exam-duties/me/").then((r) => setData(r.data)).catch((err) => setError(errorText(err, "Couldn't load your exam duties.")));
  }, []);
  if (error) return <div className="att-card"><p className="xs-bad">{error}</p></div>;
  if (!data) return <div className="att-card"><p className="xs-muted">Loading…</p></div>;
  return (
    <div className="att-card">
      <h2 className="att-card-title">My exam duties{data.session ? ` · ${data.session}` : ""}</h2>
      {data.duties.length === 0 ? <p className="xs-muted">You have no exam duties coming up.</p> : (
        <div className="xs-table-wrap">
          <table className="xs-table">
            <thead><tr><th>Date</th><th>Session</th><th>Hall</th></tr></thead>
            <tbody>
              {data.duties.map((d) => (
                <tr key={`${d.date}${d.sitting}`}><td><b>{dayLabel(d.date)}</b></td><td>{d.sitting === "FN" ? "FN · 10:00" : "AN · 14:00"}</td><td>{d.hall}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="xs-muted xs-small" style={{ marginTop: 10 }}>Need a swap? Ask the exam cell; they can change it.</p>
    </div>
  );
}
