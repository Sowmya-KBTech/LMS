// COURSE PLAN (Part B) - planned vs delivered.
// After each class the teacher records what happened: as planned, partly
// covered, a different topic, or class not held. The HOD sees the same page
// read-only. Attendance comes from the register for that period.
//
// Data: GET/POST teaching-plans/<id>/delivery/ (see delivery_report in views.py).
import { useCallback, useEffect, useMemo, useState } from "react";
import API from "../../api";
import "../../styles/CoursePlan.css";

const PAGE = 15;
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const dmy = (iso) => { if (!iso) return ""; const [y, m, d] = iso.split("-"); return `${d}-${m}-${y}`; };
const dayLabel = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return `${WD[new Date(y, m - 1, d).getDay()]} ${dmy(iso)}`;
};
const keyOf = (s) => `${s.date}__${s.period_no ?? ""}`;
const TONE = { as_planned: "ok", partly: "part", different: "part", not_held: "none" };

export default function DeliveryView({ planId, readOnly = false, onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [show, setShow] = useState("all");
  const [page, setPage] = useState(0);
  const [editKey, setEditKey] = useState(null);
  const [form, setForm] = useState({ status: "as_planned", covered: "", remarks: "", carry_forward: true });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => {
    if (!planId) return;
    API.get(`teaching-plans/${planId}/delivery/`)
      .then((r) => { setData(r.data); setError(""); })
      .catch((e) => setError(e?.response?.data?.detail || "Could not load what was delivered."));
  }, [planId]);
  useEffect(() => { setData(null); setEditKey(null); setPage(0); load(); }, [load]);

  // newest first: the class the teacher just took is at the top
  const rows = useMemo(() => {
    const all = [...(data?.sessions || [])].reverse();
    return all.filter((s) => {
      if (show === "unrecorded") return !s.delivery;
      if (show === "changed") return s.delivery && s.delivery.status !== "as_planned";
      return true;
    });
  }, [data, show]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE);
  const canRecord = !readOnly && data?.can_record;

  if (!planId) {
    return <div className="tp-note">Save the plan first. Then you can record what was delivered in each class.</div>;
  }
  if (error) return <div className="cp-msg bad" role="alert">{error}</div>;
  if (!data) return <p className="cp-muted">Loading…</p>;

  const c = data.counts;
  const pct = (a, b) => (b ? Math.round((a * 100) / b) : 0);

  const open = (s) => {
    setEditKey(keyOf(s));
    setMsg(null);
    setForm({
      status: s.delivery?.status || "as_planned",
      covered: s.delivery && s.delivery.status !== "as_planned" ? s.delivery.covered : "",
      remarks: s.delivery?.remarks || "",
      carry_forward: !s.delivery?.carried_to,
    });
  };

  const save = async (s) => {
    if (["partly", "different"].includes(form.status) && !form.covered.trim()) {
      setMsg({ tone: "bad", text: "Write what was actually covered." }); return;
    }
    if (form.status === "not_held" && !form.remarks.trim()) {
      setMsg({ tone: "bad", text: "Give the reason the class was not held." }); return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await API.post(`teaching-plans/${planId}/delivery/`, {
        date: s.date, period_no: s.period_no, ...form,
        carry_forward: form.status !== "as_planned" && form.carry_forward,
      });
      setData(r.data);
      setEditKey(null);
      setMsg({ tone: "ok", text: r.data.message || "Saved." });
      onChanged?.();
    } catch (e) {
      setMsg({ tone: "bad", text: e?.response?.data?.detail || "Not saved. Try again." });
    } finally {
      setBusy(false);
    }
  };

  const statusPill = (s) => {
    if (!s.delivery) {
      return s.date < data.today
        ? <span className="cp-pill cp-pill-grey">Not recorded</span>
        : <span className="cp-pill cp-pill-grey">Today</span>;
    }
    return <span className={`cp-pill cp-pill-${TONE[s.delivery.status]}`}>{s.delivery.status_label}</span>;
  };

  return (
    <div className="cp">
      <div className="cp-counts">
        <div><span>Sessions held so far</span><b>{c.held}</b>
          <small>up to today, {dmy(data.today)}{c.not_held ? ` · ${c.not_held} not held` : ""}</small></div>
        <div><span>Delivered as planned</span><b>{c.as_planned}</b><small>{pct(c.as_planned, c.held)}% of sessions held</small></div>
        <div><span>Changed or partly covered</span><b>{c.changed}</b><small>different or unfinished topic</small></div>
        <div><span>Not recorded yet</span><b className={c.not_recorded ? "cp-warn" : ""}>{c.not_recorded}</b>
          <small>{readOnly ? "the teacher has not filled these in" : "past classes to fill in"}</small></div>
      </div>

      {data.units.length > 0 && (
        <section className="cp-box">
          <div className="cp-box-head"><h3>Syllabus progress by unit</h3><span>delivered sessions / planned sessions</span></div>
          {data.units.map((u) => {
            const p = pct(u.done, u.planned);
            return (
              <div className="cp-prog" key={u.unit_no}>
                <b>Unit {u.unit_no}</b>
                <span className="cp-bar"><span style={{ width: `${p}%` }} className={p === 100 ? "done" : ""} /></span>
                <span className="cp-nowrap">{u.done} / {u.planned} <small>({p}%)</small></span>
              </div>
            );
          })}
        </section>
      )}

      <div className="cp-filters no-print">
        <label>Show
          <select value={show} onChange={(e) => { setShow(e.target.value); setPage(0); }}>
            <option value="all">All past sessions</option>
            <option value="unrecorded">Not recorded yet</option>
            <option value="changed">Changed, partly covered or not held</option>
          </select>
        </label>
      </div>

      {msg && <div className={msg.tone === "ok" ? "cp-msg ok" : "cp-msg bad"} role={msg.tone === "ok" ? "status" : "alert"}>{msg.text}</div>}
      <div className="cp-table-wrap">
        <table className="cp-table cp-table-dv">
          <thead>
            <tr>
              <th>Date · period</th><th className="cp-topic-col">Planned topic</th><th className="cp-topic-col">Actually covered</th>
              <th>Status</th><th>Attendance</th>
              {canRecord && <th className="no-print"><span className="cp-sr">Actions</span></th>}
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={6} className="cp-empty">
                {data.sessions.length ? "No sessions match this filter." : "No planned sessions up to today yet."}
              </td></tr>
            )}
            {shown.map((s) => {
              const k = keyOf(s);
              const att = s.attendance ? `${s.attendance.present} / ${s.attendance.total}` : "—";
              const when = (
                <td className="cp-nowrap"><b>{dayLabel(s.date)}</b>
                  <small>Period {s.period_no ?? "?"}{s.today ? " · today" : ""}</small></td>
              );
              const planned = (
                <td><b className="cp-topic">{s.topic || "(no longer in the plan)"}</b>
                  {(s.unit_no || s.outcome_codes.length > 0) && (
                    <small>{[s.unit_no ? `Unit ${s.unit_no}` : "", s.outcome_codes.join(" · ")].filter(Boolean).join(" · ")}</small>
                  )}</td>
              );
              if (canRecord && editKey === k) {
                const changed = form.status !== "as_planned";
                return (
                  <tr key={k} className="cp-row-edit">
                    {when}{planned}
                    <td colSpan={2}>
                      <fieldset className="cp-radio">
                        <legend>What happened</legend>
                        {data.statuses.map((o) => (
                          <label key={o.value}>
                            <input type="radio" name={`st-${k}`} value={o.value} checked={form.status === o.value}
                              onChange={() => setForm({ ...form, status: o.value })} />{o.label}
                          </label>
                        ))}
                      </fieldset>
                      {["partly", "different"].includes(form.status) && (
                        <label className="cp-cell-field"><span className="cp-sr">What was covered</span>
                          <input value={form.covered} maxLength={200} className={!form.covered.trim() ? "cp-need" : ""}
                            placeholder={form.status === "partly" ? "What part was covered?" : "What was taught instead?"}
                            onChange={(e) => setForm({ ...form, covered: e.target.value })} /></label>
                      )}
                      <label className="cp-cell-field"><span className="cp-sr">Remarks</span>
                        <textarea rows={2} value={form.remarks}
                          className={form.status === "not_held" && !form.remarks.trim() ? "cp-need" : ""}
                          placeholder={form.status === "not_held" ? "Why was the class not held?" : "Remarks (optional)"}
                          onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></label>
                      {changed && !s.delivery?.carried_to && (
                        <label className="cp-check">
                          <input type="checkbox" checked={form.carry_forward}
                            onChange={(e) => setForm({ ...form, carry_forward: e.target.checked })} />
                          Move the {form.status === "partly" ? "unfinished" : "planned"} topic to the next free session
                        </label>
                      )}
                      {changed && s.delivery?.carried_to && (
                        <small className="cp-muted">Already moved to {dmy(s.delivery.carried_to)}.</small>
                      )}
                    </td>
                    <td>{att}</td>
                    <td className="no-print">
                      <div className="cp-row-actions">
                        <button type="button" className="tp-btn-primary tp-btn-sm" onClick={() => save(s)} disabled={busy}>
                          {busy ? "Saving…" : "Save"}</button>
                        <button type="button" className="tp-btn-outline tp-btn-sm" onClick={() => setEditKey(null)}>Cancel</button>
                      </div>
                    </td>
                  </tr>
                );
              }
              const d = s.delivery;
              return (
                <tr key={k} className={!d && s.date < data.today ? "cp-row-un" : ""}>
                  {when}{planned}
                  <td>
                    {d ? (d.status === "not_held" ? "—" : d.covered) : <span className="cp-un-text">Not recorded</span>}
                    {d && (d.remarks || d.carried_to) && (
                      <small>{[d.status === "not_held" ? `Not held: ${d.remarks}` : d.remarks,
                        d.carried_to ? `moved to ${dmy(d.carried_to)}` : ""].filter(Boolean).join(" · ")}</small>
                    )}
                  </td>
                  <td>{statusPill(s)}</td>
                  <td className="cp-nowrap">{att}</td>
                  {canRecord && (
                    <td className="no-print">
                      <button type="button" className={`cp-btn${d ? "" : " cp-btn-accent"}`} onClick={() => open(s)}
                        aria-label={`${d ? "Edit" : "Record"} ${dayLabel(s.date)} period ${s.period_no}`}>
                        {d ? "Edit" : "Record"}</button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="cp-pager no-print">
        <span>Showing {shown.length ? page * PAGE + 1 : 0}–{page * PAGE + shown.length} of {rows.length} · newest first</span>
        <div>
          <button type="button" className="cp-btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <button type="button" className="cp-btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
      {canRecord && (
        <p className="cp-muted">“Partly covered”, “Different topic” and “Class not held” can move the topic to the next
          free session, so the plan stays complete. Attendance comes from the register for that period.</p>
      )}
    </div>
  );
}
