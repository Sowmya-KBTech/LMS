// WAVE 3 PART 2 - create or edit an exam session (exam admin).
import { useState } from "react";
import API from "../../api";
import { errorText } from "./examSessionUtil";

const SEMS = [1, 2, 3, 4, 5, 6, 7, 8];

const blank = {
  name: "", kind: "regular", exam_start: "", exam_end: "",
  registration_required: true, reg_opens: "", reg_closes: "", late_until: "",
  semesters: [], students_pick_arrears: true, fee_required: true,
  regular_fee: "", arrear_fee: "", late_fee: "",
};

function toForm(s) {
  if (!s) return blank;
  const f = { ...blank };
  Object.keys(blank).forEach((k) => {
    if (s[k] !== undefined && s[k] !== null) f[k] = s[k];
  });
  ["regular_fee", "arrear_fee", "late_fee"].forEach((k) => { f[k] = s[k] ? String(s[k]) : ""; });
  return f;
}

export default function SessionForm({ session, onSaved, onCancel }) {
  const [f, setF] = useState(() => toForm(session));
  const [errors, setErrors] = useState({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggleSem = (n) => set("semesters", f.semesters.includes(n) ? f.semesters.filter((x) => x !== n) : [...f.semesters, n].sort());

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    setMsg("");
    try {
      const body = { ...f };
      const r = session
        ? await API.patch(`exam-sessions/${session.id}/`, body)
        : await API.post("exam-sessions/", body);
      onSaved(r.data);
    } catch (err) {
      setErrors(err?.response?.data?.errors || {});
      setMsg(errorText(err, "Couldn't save the session."));
    } finally {
      setBusy(false);
    }
  };

  const field = (k, label, type = "text", extra = {}) => (
    <label className="xs-field">{label}
      <input className="kb-input" type={type} value={f[k] ?? ""} onChange={(e) => set(k, e.target.value)}
        aria-invalid={errors[k] ? "true" : undefined} {...extra} />
      {errors[k] && <span className="xs-err">{errors[k]}</span>}
    </label>
  );

  return (
    <form className="xs-stack" onSubmit={save} noValidate>
      <div className="xs-form">
        {field("name", "Name", "text", { placeholder: "Nov/Dec 2026", maxLength: 30 })}
        <label className="xs-field">Kind
          <select className="kb-input" value={f.kind} onChange={(e) => set("kind", e.target.value)}>
            <option value="regular">Regular + arrear</option>
            <option value="supplementary">Supplementary (arrears only)</option>
          </select>
        </label>
        {field("exam_start", "Exams from", "date")}
        {field("exam_end", "Exams to", "date")}
      </div>

      {f.kind === "regular" && (
        <fieldset className="xs-fieldset">
          <legend>Semesters that write regular papers (none ticked = every semester)</legend>
          {SEMS.map((n) => (
            <label key={n} className="xs-check"><input type="checkbox" checked={f.semesters.includes(n)} onChange={() => toggleSem(n)} /> Sem {n}</label>
          ))}
          {errors.semesters && <span className="xs-err">{errors.semesters}</span>}
        </fieldset>
      )}

      <label className="xs-check"><input type="checkbox" checked={f.registration_required} onChange={(e) => set("registration_required", e.target.checked)} />
        <span><b>Students register for this session.</b> <span className="xs-muted">Off = hall tickets list the class subjects, as before.</span></span></label>

      {f.registration_required && (
        <>
          <div className="xs-form">
            {field("reg_opens", "Registration opens", "date")}
            {field("reg_closes", "Registration closes", "date")}
            {field("late_until", "Late registration until (optional)", "date")}
          </div>
          <label className="xs-check"><input type="checkbox" checked={f.students_pick_arrears} onChange={(e) => set("students_pick_arrears", e.target.checked)} />
            <span><b>Students pick their own arrear subjects.</b> <span className="xs-muted">Off = every arrear is added for them.</span></span></label>
          <label className="xs-check"><input type="checkbox" checked={f.fee_required} onChange={(e) => set("fee_required", e.target.checked)} />
            <span><b>Charge an exam fee on registration.</b> <span className="xs-muted">Registration is complete once it is paid.</span></span></label>
          {f.fee_required && (
            <div className="xs-form">
              {field("regular_fee", "Fee per regular paper (₹)", "number", { min: 0, step: "1" })}
              {field("arrear_fee", "Fee per arrear paper (₹)", "number", { min: 0, step: "1" })}
              {field("late_fee", "Late fee, once (₹)", "number", { min: 0, step: "1" })}
            </div>
          )}
        </>
      )}

      {msg && <p className="xs-note bad" role="alert">{msg}</p>}
      <div className="xs-row">
        <button className="kb-btn kb-btn--primary" type="submit" disabled={busy}>{busy ? "Saving…" : session ? "Save settings" : "Create session"}</button>
        {onCancel && <button className="kb-btn" type="button" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}
