// COURSE PLAN (Part B) - course outcomes (CO1, CO2 ...) of the subject and how
// well this plan covers them. The outcomes belong to the SUBJECT, so every
// section of the subject shares the same list. Sessions are linked to outcomes
// in the plan table; this tab counts those links per unit.
import { useMemo, useState } from "react";
import API from "../../api";
import "../../styles/CoursePlan.css";

const EMPTY = { text: "", level: "" };

export default function OutcomesView({ subjectId, info, sessions, onChanged }) {
  const [editId, setEditId] = useState(null);           // outcome id, "new" or null
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const outcomes = info?.outcomes || [];
  const canEdit = !!info?.can_edit;
  const low = info?.low_coverage || 3;
  const planned = sessions.filter((s) => s.topic.trim());

  // how many of THIS plan's planned sessions teach each outcome, overall and per unit
  const { perCo, units, grid } = useMemo(() => {
    const per = {};
    const g = {};
    const us = new Set();
    planned.forEach((s) => {
      const u = s.unit_no ? Number(s.unit_no) : 0;
      us.add(u);
      (s.outcomes || []).forEach((id) => {
        per[id] = (per[id] || 0) + 1;
        g[`${u}_${id}`] = (g[`${u}_${id}`] || 0) + 1;
      });
    });
    return { perCo: per, units: [...us].sort((a, b) => (a || 99) - (b || 99)), grid: g };
  }, [planned]);
  const max = Math.max(1, ...Object.values(perCo));
  const weak = planned.length ? outcomes.filter((o) => (perCo[o.id] || 0) < low) : [];
  const unlinked = planned.filter((s) => !(s.outcomes || []).length).length;

  const start = (o) => { setEditId(o ? o.id : "new"); setForm(o ? { text: o.text, level: o.level } : EMPTY); setMsg(null); };

  const errorText = (e, fallback) => {
    const d = e?.response?.data;
    if (typeof d?.detail === "string") return d.detail;
    for (const k of ["text", "level", "subject"]) if (Array.isArray(d?.[k])) return d[k][0];
    return fallback;
  };

  const save = async () => {
    if (form.text.trim().length < 5) { setMsg({ tone: "bad", text: "Describe the outcome in a short sentence." }); return; }
    setBusy(true);
    setMsg(null);
    try {
      if (editId === "new") await API.post("course-outcomes/", { subject: subjectId, ...form, text: form.text.trim() });
      else await API.patch(`course-outcomes/${editId}/`, { ...form, text: form.text.trim() });
      setEditId(null);
      setMsg({ tone: "ok", text: "Outcome saved." });
      onChanged?.();
    } catch (e) {
      setMsg({ tone: "bad", text: errorText(e, "Not saved. Try again.") });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (o) => {
    const n = perCo[o.id] || 0;
    const warn = n ? ` It is linked to ${n} session${n === 1 ? "" : "s"} in this plan; those links go too.` : "";
    if (!window.confirm(`Delete ${o.code}?${warn} Other sections of this subject share the list.`)) return;
    try {
      await API.delete(`course-outcomes/${o.id}/`);
      setMsg({ tone: "ok", text: `${o.code} deleted.` });
      onChanged?.();
    } catch (e) {
      setMsg({ tone: "bad", text: errorText(e, "Not deleted. Try again.") });
    }
  };

  const formRow = (
    <div className="cp-co-form">
      <label className="cp-cell-field"><span className="cp-sr">Outcome</span>
        <textarea rows={2} maxLength={300} value={form.text} autoFocus
          placeholder="After this course, students will be able to…"
          onChange={(e) => setForm({ ...form, text: e.target.value })} /></label>
      <label className="cp-cell-field cp-co-level"><span className="cp-sr">Level</span>
        <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
          <option value="">Level (optional)</option>
          {(info?.levels || []).map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
        </select></label>
      <div className="cp-row-actions">
        <button type="button" className="tp-btn-primary tp-btn-sm" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="tp-btn-outline tp-btn-sm" onClick={() => setEditId(null)}>Cancel</button>
      </div>
    </div>
  );

  return (
    <div className="cp">
      <section className="cp-box">
        <div className="cp-box-head">
          <h3>Course outcomes</h3>
          {canEdit && editId === null && outcomes.length < (info?.max || 12) && (
            <button type="button" className="cp-btn cp-btn-accent" onClick={() => start(null)}>+ Add outcome</button>
          )}
        </div>
        <p className="cp-muted">What students should be able to do after this course. Shared by every section of the subject.</p>
        {outcomes.length === 0 && editId !== "new" && (
          <div className="tp-note">No outcomes yet.{canEdit ? " Add the course outcomes from your syllabus, then link sessions to them in the table." : ""}</div>
        )}
        {outcomes.map((o) => (editId === o.id ? <div key={o.id} className="cp-co cp-co-editing"><b className="cp-co-code">{o.code}</b>{formRow}</div> : (
          <div key={o.id} className="cp-co">
            <b className="cp-co-code">{o.code}</b>
            <span className="cp-co-text">{o.text}{o.level_label && <small>Level: <b>{o.level_label}</b></small>}</span>
            <span className="cp-co-count">
              <span className="cp-bar"><span style={{ width: `${((perCo[o.id] || 0) * 100) / max}%` }}
                className={(perCo[o.id] || 0) < low ? "low" : ""} /></span>
              <small>{perCo[o.id] || 0} session{(perCo[o.id] || 0) === 1 ? "" : "s"} planned</small>
            </span>
            {canEdit && (
              <span className="cp-row-actions">
                <button type="button" className="cp-btn" onClick={() => start(o)} aria-label={`Edit ${o.code}`}>Edit</button>
                <button type="button" className="cp-btn" onClick={() => remove(o)} aria-label={`Delete ${o.code}`}>Delete</button>
              </span>
            )}
          </div>
        )))}
        {editId === "new" && <div className="cp-co cp-co-editing"><b className="cp-co-code">New</b>{formRow}</div>}
        {weak.length > 0 && (
          <div className="cp-alert" role="note">
            <b aria-hidden="true">!</b>
            <span><b>{weak.map((o) => o.code).join(", ")}</b> {weak.length === 1 ? "has" : "have"} fewer than {low} planned
              sessions. Link more sessions in the table so every outcome is taught.</span>
          </div>
        )}
        {msg && <div className={msg.tone === "ok" ? "cp-msg ok" : "cp-msg bad"} role={msg.tone === "ok" ? "status" : "alert"}>{msg.text}</div>}
      </section>

      {outcomes.length > 0 && (
        <section className="cp-box">
          <div className="cp-box-head"><h3>Outcome coverage by unit</h3><span>planned sessions that teach each outcome</span></div>
          {planned.length === 0 ? <p className="cp-muted">Plan some sessions first.</p> : (
            <div className="cp-table-wrap">
              <table className="cp-table cp-cov">
                <thead><tr><th>Unit</th>{outcomes.map((o) => <th key={o.id}>{o.code}</th>)}</tr></thead>
                <tbody>
                  {units.map((u) => (
                    <tr key={u}>
                      <td><b>{u ? `Unit ${u}` : "No unit"}</b></td>
                      {outcomes.map((o) => {
                        const n = grid[`${u}_${o.id}`] || 0;
                        return <td key={o.id}><span className={`cp-cov-n${n ? (n >= 3 ? " hi" : " mid") : ""}`}>{n || "–"}</span></td>;
                      })}
                    </tr>
                  ))}
                  <tr className="cp-cov-total">
                    <td><b>Total</b></td>
                    {outcomes.map((o) => <td key={o.id}><b className={(perCo[o.id] || 0) < low ? "cp-warn" : ""}>{perCo[o.id] || 0}</b></td>)}
                  </tr>
                </tbody>
              </table>
            </div>
          )}
          {unlinked > 0 && <p className="cp-muted">{unlinked} planned session{unlinked === 1 ? " is" : "s are"} not linked to any outcome yet.</p>}
        </section>
      )}
    </div>
  );
}
