// WAVE 2 Part 1b - the Principal approves an HOD's own leave.
// Shown on the Principal's college overview. A teacher's leave still goes to
// their HOD; only an HOD's leave comes here.
//   GET  users/principal/staff-leave/                 waiting
//   GET  users/principal/staff-leave/history/         decided (last 50)
//   POST users/principal/staff-leave/<id>/action/     {action, remark}
import { useCallback, useEffect, useState } from "react";
import API from "../../api";

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return `${d}-${m}-${y}`;
};
const range = (r) => (r.from_date === r.to_date ? fmtDate(r.from_date) : `${fmtDate(r.from_date)} to ${fmtDate(r.to_date)}`);
const days = (r) => (r.session !== "full" ? r.session_label : `${Number(r.days)} day${Number(r.days) === 1 ? "" : "s"}`);
const ACTING = { pending: "waiting for admin approval", upcoming: "approved", active: "approved", rejected: "rejected" };

export default function HodLeaveApprovals() {
  const [waiting, setWaiting] = useState(null);
  const [history, setHistory] = useState([]);
  const [remarks, setRemarks] = useState({});
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => {
    API.get("users/principal/staff-leave/").then((r) => setWaiting(r.data)).catch(() => setWaiting([]));
    API.get("users/principal/staff-leave/history/").then((r) => setHistory(r.data)).catch(() => setHistory([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const decide = async (r, action) => {
    const remark = (remarks[r.id] || "").trim();
    if (action === "reject" && !remark) {
      setMsg({ tone: "bad", text: `Add a remark so ${r.teacher_name} knows why the leave was rejected.` });
      return;
    }
    setBusy(r.id);
    setMsg(null);
    try {
      await API.post(`users/principal/staff-leave/${r.id}/action/`, { action, remark });
      setMsg({ tone: "ok", text: `${r.teacher_name}'s leave ${action === "approve" ? "approved" : "rejected"}.` });
      load();
    } catch (err) {
      setMsg({ tone: "bad", text: err?.response?.data?.detail || "Not saved. Try again." });
    } finally {
      setBusy(null);
    }
  };

  if (waiting === null) return null;
  return (
    <section className="kb-card pr-approvals">
      <div className="pr-head">
        <h2 className="kb-at-h2">HOD leave waiting for you{waiting.length ? ` · ${waiting.length}` : ""}</h2>
      </div>
      <p className="rp-muted">An HOD’s own leave comes to you. A teacher’s leave stays with their HOD.</p>
      {msg && <div className={`pr-msg ${msg.tone}`} role={msg.tone === "ok" ? "status" : "alert"}>{msg.text}</div>}
      {waiting.length === 0 ? <p className="rp-muted">Nothing waiting.</p> : (
        <ul className="pr-leave-list">
          {waiting.map((r) => (
            <li key={r.id}>
              <div className="pr-leave-top">
                <b>{r.teacher_name}</b>
                <span className="rp-muted">HOD, {r.department_name}</span>
              </div>
              <div className="pr-leave-grid">
                <span>Leave</span><b>{r.leave_type_label} · {range(r)} · {days(r)}</b>
                <span>Reason</span><span>{r.reason}</span>
                <span>Backup</span><span>{r.backup_name || "—"}
                  {r.acting_hod && <> · nominated as Acting HOD ({ACTING[r.acting_hod.status] || r.acting_hod.status})</>}</span>
                {r.covering_warning && <><span>Note</span><span className="rp-warn">{r.covering_warning}</span></>}
                {r.proof_url && <><span>Proof</span><a href={r.proof_url} target="_blank" rel="noreferrer">View proof</a></>}
              </div>
              <label className="pr-remark">
                <span className="pr-sr">Remark for {r.teacher_name}</span>
                <textarea rows={2} maxLength={255} value={remarks[r.id] || ""}
                  placeholder="Remark (needed to reject)"
                  onChange={(e) => setRemarks({ ...remarks, [r.id]: e.target.value })} />
              </label>
              <div className="pr-leave-actions">
                <button type="button" className="kb-btn kb-btn--sm" disabled={busy === r.id} onClick={() => decide(r, "reject")}>Reject</button>
                <button type="button" className="kb-btn kb-btn--primary kb-btn--sm" disabled={busy === r.id} onClick={() => decide(r, "approve")}>
                  {busy === r.id ? "Saving…" : "Approve"}</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {history.length > 0 && (
        <details className="pr-history">
          <summary>Decided recently ({history.length})</summary>
          <ul className="pr-list">
            {history.map((r) => (
              <li key={r.id}>
                <b>{r.teacher_name}</b>
                <span className={r.status === "approved" ? "kb-pill ok pr-pill" : "kb-pill bad pr-pill"}>{r.status_label}</span>
                <span className="rp-muted">{r.department_name} · {r.leave_type_label} · {range(r)}
                  {r.decided_at ? ` · decided ${fmtDate(r.decided_at)}` : ""}{r.hod_remark ? ` · “${r.hod_remark}”` : ""}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
