// WAVE 1 - a student's leave requests (sick, personal, family ...).
// Opened from /student/attendance?tab=leave. Same road as on duty:
// class in-charge first, then the HOD. Approved leave is an excused absence
// (shown as "On leave"); it does not count as present.
import { useEffect, useState } from "react";
import API from "../../api";
import Icon from "../../components/Icon";

const TYPES = [
  { value: "sick", label: "Sick / medical" },
  { value: "personal", label: "Personal" },
  { value: "family", label: "Family function / emergency" },
  { value: "other", label: "Other" },
];
const PROOF_DAYS = 3;

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};
const pick = (res) => res?.data?.results || res?.data || [];
const daysBetween = (a, b) => (a && b ? Math.round((new Date(b) - new Date(a)) / 86400000) + 1 : 0);

const badgeFor = (r) => {
  if (r.status === "approved") return { tone: "ok", text: "Approved" };
  if (r.status === "rejected") return { tone: "bad", text: "Rejected" };
  if (r.status === "cancelled") return { tone: "", text: "Cancelled" };
  return { tone: "warn", text: r.stage === "awaiting_hod" ? "Awaiting HOD" : "Awaiting class in-charge" };
};

const errorText = (err, fallback) => {
  const d = err?.response?.data;
  if (typeof d?.detail === "string") return d.detail;
  if (Array.isArray(d?.non_field_errors)) return d.non_field_errors[0];
  if (d && typeof d === "object") {
    const first = Object.values(d)[0];
    if (Array.isArray(first)) return first[0];
  }
  return fallback;
};

export default function StudentLeave() {
  const [type, setType] = useState("personal");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const [proof, setProof] = useState(null);
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState(null);         // { tone, text }

  const load = async () => {
    setLoading(true);
    try {
      setList(pick(await API.get("users/leave/")));
    } catch {
      setNotice({ tone: "bad", text: "Couldn't load your leave requests. Refresh the page to try again." });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const days = daysBetween(from, to);
  const needsProof = type === "sick" && days >= PROOF_DAYS;

  const submit = async () => {
    setNotice(null);
    if (!from || !to) return setNotice({ tone: "bad", text: "Choose both the From and To dates." });
    if (to < from) return setNotice({ tone: "bad", text: "The To date can't be before the From date." });
    if (!reason.trim()) return setNotice({ tone: "bad", text: "Write a short reason for the leave." });
    if (needsProof && !proof) {
      return setNotice({ tone: "bad", text: `Sick leave of ${PROOF_DAYS} days or more needs a medical certificate.` });
    }
    setSending(true);
    try {
      const fd = new FormData();
      fd.append("leave_type", type);
      fd.append("from_date", from);
      fd.append("to_date", to);
      fd.append("reason", reason.trim());
      if (proof) fd.append("proof", proof);
      await API.post("users/leave/create/", fd);
      setFrom(""); setTo(""); setReason(""); setProof(null); setType("personal");
      const el = document.getElementById("leave-proof-input");
      if (el) el.value = "";
      await load();
      setNotice({ tone: "ok", text: "Leave request sent. You'll see its status below." });
    } catch (err) {
      setNotice({ tone: "bad", text: errorText(err, "The request wasn't sent. Try again.") });
    } finally {
      setSending(false);
    }
  };

  const cancel = async (id) => {
    if (!window.confirm("Cancel this leave request?")) return;
    setNotice(null);
    try {
      await API.post(`users/leave/${id}/cancel/`);
      await load();
    } catch (err) {
      setNotice({ tone: "bad", text: errorText(err, "Couldn't cancel it.") });
    }
  };

  return (
    <>
      <div className="header-box">
        <h1>Leave requests</h1>
        <p>Ask for leave when you can't come to college. Approved leave shows as "On leave" in your attendance; it does not count as present.</p>
      </div>

      <section className="kb-card">
        <h2 className="kb-at-h2">New request</h2>
        <div className="kb-sa-odgrid">
          <label className="kb-at-field">
            <span>From</span>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="kb-at-field">
            <span>To</span>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="kb-at-field">
            <span>Type of leave</span>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </label>
        </div>
        <label className="kb-at-field kb-sa-full">
          <span>Reason</span>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
            placeholder="Fever since yesterday; doctor advised rest" />
        </label>
        <label className="kb-at-field kb-sa-full">
          <span>{needsProof ? "Medical certificate (required)" : "Proof (optional)"}</span>
          <input id="leave-proof-input" type="file" accept=".pdf,.jpg,.jpeg,.png"
            onChange={(e) => setProof(e.target.files?.[0] || null)} />
        </label>

        {notice && (
          <div className={notice.tone === "ok" ? "kb-sa-ok" : "kb-at-error"} role={notice.tone === "ok" ? "status" : "alert"}>
            {notice.text}
          </div>
        )}

        <div className="kb-sa-actions">
          <span className="kb-muted">
            {days > 0 ? `${days} day${days === 1 ? "" : "s"} · ` : ""}Your class in-charge reviews it first, then your HOD.
          </span>
          <button type="button" className="kb-btn kb-btn--primary" onClick={submit} disabled={sending}>
            {sending ? "Sending…" : "Send request"}
          </button>
        </div>
      </section>

      <section className="kb-card">
        <h2 className="kb-at-h2">Your leave requests</h2>
        {loading ? (
          <div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading…</b></div>
        ) : list.length === 0 ? (
          <div className="kb-at-empty">
            <span className="kb-at-empty-ico"><Icon name="calendar" /></span>
            <b>No leave requests yet</b>
            <span>Requests you send appear here with their status.</span>
          </div>
        ) : (
          <div className="kb-sa-odlist">
            {list.map((r) => {
              const badge = badgeFor(r);
              return (
                <div key={r.id} className="kb-sa-od">
                  <div className="kb-sa-od-top">
                    <div className="kb-grow">
                      <div className="kb-sa-subj-name">{r.leave_type_label}</div>
                      <div className="kb-sa-subj-meta">
                        {fmtDate(r.from_date)} → {fmtDate(r.to_date)} · {r.days} day{r.days === 1 ? "" : "s"}
                      </div>
                    </div>
                    <span className={`kb-pill ${badge.tone}`}>{badge.text}</span>
                    {r.status === "pending" && (
                      <button type="button" className="kb-btn kb-btn--sm" onClick={() => cancel(r.id)}>Cancel</button>
                    )}
                  </div>
                  {r.reason && <p className="kb-sa-od-reason">{r.reason}</p>}
                  {r.tutor_remark && <p className="kb-sa-od-remark"><b>Class in-charge:</b> {r.tutor_remark}</p>}
                  {r.hod_remark && <p className="kb-sa-od-remark"><b>HOD:</b> {r.hod_remark}</p>}
                  {r.status === "approved" && <p className="kb-sa-od-ok">Shown as On leave in your attendance.</p>}
                  {r.proof && <a href={r.proof} target="_blank" rel="noreferrer" className="kb-sa-od-proof">View proof</a>}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
