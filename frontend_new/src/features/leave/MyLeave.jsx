import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";
import "../../styles/StaffLeave.css";

// must match StaffLeaveRequest.LeaveType in attendance/models.py
const LEAVE_TYPES = [
  { value: "casual", label: "Casual leave", proof: false },
  { value: "earned", label: "Earned leave", proof: false },            // HRIS PART A
  { value: "medical", label: "Medical leave", proof: true },
  { value: "on_duty", label: "On duty (conference / FDP / workshop)", proof: true },
  { value: "compensatory", label: "Compensatory leave", proof: false },
  { value: "other", label: "Other", proof: false },
];

const SESSIONS = [
  { value: "full", label: "Full day" },
  { value: "forenoon", label: "Forenoon" },
  { value: "afternoon", label: "Afternoon" },
];

const STATUS_HELP = [
  { key: "pending", text: "Waiting for HOD", help: "Waiting for HOD approval" },
  { key: "approved", text: "Approved", help: "HOD approved the leave" },
  { key: "rejected", text: "Rejected", help: "HOD rejected the leave" },
  { key: "cancelled", text: "Cancelled", help: "Teacher cancelled the request" },
  { key: "recorded", text: "Recorded", help: "HOD leave saved and backup informed. No approval needed (no Principal is set)" },
];
// WAVE 2 Part 1b: an HOD's own leave waits for the Principal
const PRINCIPAL_PENDING = { key: "pending", text: "Waiting for Principal", help: "HOD leave waiting for the Principal's approval" };

const todayISO = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};

const badgeOf = (status, level) =>
  (status === "pending" && level === "principal" ? PRINCIPAL_PENDING : null)
  || STATUS_HELP.find((s) => s.key === status) || { key: status, text: status };

const typeLabel = (r) => r.leave_type_label || r.leave_type;

const errText = (err) => {
  const data = err?.response?.data;
  if (!data) return "Something went wrong. Try again.";
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  const first = Object.values(data)[0];
  return Array.isArray(first) ? first[0] : String(first);
};

// #50 ACTING HOD: how a nomination made with a leave is described to the HOD
const ACTING_LABEL = {
  pending: "Waiting for admin approval",
  upcoming: "Approved – starts on the leave date",
  active: "Approved – acting now",
  finished: "Finished",
  rejected: "Rejected by admin",
  expired: "Expired – not approved in time",
  cancelled: "Cancelled",
  ended_early: "Ended early",
};

export default function MyLeave() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("apply");

  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);

  // form — dates default to today so the preview runs as soon as the page opens
  const [type, setType] = useState("casual");
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [session, setSession] = useState("full");
  const [reason, setReason] = useState("");
  const [proof, setProof] = useState(null);
  const [backup, setBackup] = useState("");
  const [nominate, setNominate] = useState(false);   // #50 ACTING HOD
  const [covering, setCovering] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  // preview from the server (day count + affected periods + approver)
  const [preview, setPreview] = useState(null);
  // why the preview failed, if it did — never swallowed silently
  const [previewError, setPreviewError] = useState("");

  // Who this user IS does not change with the dates they pick, so the HOD flag
  // and the backup list are fetched ONCE. Reading them from the dated preview
  // meant a failed preview hid the backup dropdown, and the form could then be
  // submitted with no backup — which the server rejects.
  const [meta, setMeta] = useState(null);

  // details view
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const singleDay = from && from === to;
  const isHod = !!(meta?.is_hod ?? preview?.is_hod);
  // #50 ACTING HOD: only the REGULAR HOD may nominate (not an Acting HOD)
  const canNominate = !!(meta?.can_nominate ?? preview?.can_nominate);
  const backupOptions =
    (preview?.backup_options?.length ? preview.backup_options : meta?.backup_options) || [];
  const needsProof = LEAVE_TYPES.find((t) => t.value === type)?.proof;

  // HRIS PART A: leave left this year, from the server (rules set by the admin)
  const [balance, setBalance] = useState(null);
  const balanceOf = (t) => balance?.rows?.find((r) => r.leave_type === t);

  const loadList = async () => {
    setLoading(true);
    try {
      const res = await API.get("users/staff-leave/");
      setList(res.data?.results || res.data || []);
      API.get("users/hris/leave-balance/").then((r) => setBalance(r.data)).catch(() => setBalance(null));
    } catch (err) {
      console.error("Staff leave load error:", err?.response?.status, err?.response?.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { loadList(); }, []);

  const loadCovering = async () => {
    try {
      const res = await API.get("users/staff-leave/covering/");
      setCovering(res.data?.results || res.data || []);
    } catch (err) {
      console.error("Covering load error:", err?.response?.status, err?.response?.data);
    }
  };
  useEffect(() => { loadCovering(); }, []);

  // one-time: am I an HOD, and who can cover for me
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const day = todayISO();
      try {
        const res = await API.get("users/staff-leave/preview/", {
          params: { from: day, to: day, session: "full" },
        });
        if (!cancelled) setMeta(res.data);
      } catch (err) {
        console.error("Leave meta failed:", err?.response?.status, err?.response?.data);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // server decides the day count and the affected periods — never the browser
  useEffect(() => {
    if (!from || !to || to < from) { setPreview(null); setPreviewError(""); return; }
    let cancelled = false;
    (async () => {
      try {
        const res = await API.get("users/staff-leave/preview/", {
          params: { from, to, session, leave_type: type },
        });
        if (!cancelled) { setPreview(res.data); setPreviewError(""); }
      } catch (err) {
        console.error("Preview failed:", err?.response?.status, err?.response?.data);
        if (!cancelled) {
          setPreview(null);
          setPreviewError(
            `Could not check these dates (${err?.response?.status || "no response"}). ` +
            `${errText(err)} You can still submit; the server will re-check.`
          );
        }
      }
    })();
    return () => { cancelled = true; };
  }, [from, to, session, type]);

  useEffect(() => { setFormError(""); }, [type, from, to, session, backup]);

  const onFromChange = (value) => {
    setFrom(value);
    if (!to || to < value) setTo(value);
  };
  const onToChange = (value) => {
    setTo(value);
    if (value !== from) setSession("full");
  };

  const submit = async () => {
    setFormError("");
    if (!from || !to) return setFormError("Choose the leave dates.");
    if (to < from) return setFormError("The end date cannot be before the start date.");
    if (reason.trim().length < 5) return setFormError("Write a short reason.");
    if (needsProof && !proof) return setFormError("Attach proof for this leave type.");
    if (isHod && !backup) return setFormError("Choose who will cover your work during this leave.");

    const body = new FormData();
    body.append("leave_type", type);
    body.append("from_date", from);
    body.append("to_date", to);
    body.append("session", singleDay ? session : "full");
    body.append("reason", reason.trim());
    if (proof) body.append("proof", proof);
    if (isHod) body.append("backup", backup);
    if (isHod && canNominate && nominate && backup) body.append("nominate_acting", "true");   // #50

    setSubmitting(true);
    try {
      await API.post("users/staff-leave/create/", body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setType("casual");
      setFrom(todayISO()); setTo(todayISO()); setSession("full");
      setReason(""); setProof(null); setBackup(""); setNominate(false);
      const input = document.getElementById("leave-proof-input");
      if (input) input.value = "";
      await loadList();
      setView("mine");
    } catch (err) {
      console.error("Leave submit failed:", err?.response?.status, err?.response?.data);
      setFormError(errText(err));
    } finally {
      setSubmitting(false);
    }
  };

  const cancel = async (id) => {
    try {
      await API.post(`users/staff-leave/${id}/cancel/`);
      await loadList();
    } catch (err) {
      alert(errText(err));
    }
  };

  const openDetail = async (id) => {
    setDetailLoading(true);
    setDetail({ id });
    try {
      const res = await API.get(`users/staff-leave/${id}/`);
      setDetail(res.data);
    } catch (err) {
      alert(errText(err));
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  // stat cards — approved days this year, by type
  const year = String(new Date().getFullYear());
  const takenDays = (t) =>
    list
      .filter((r) => (r.status === "approved" || r.status === "recorded") && r.leave_type === t && String(r.from_date).startsWith(year))
      .reduce((sum, r) => sum + Number(r.days || 0), 0);
  const pendingCount = list.filter((r) => r.status === "pending").length;

  const periodsBox = (periods, note) => (
    <div className="sl-classes">
      <div className="sl-classes-title">Classes during this leave ({periods.length})</div>
      {periods.length === 0 ? (
        <div className="sl-classes-empty">No classes in the selected dates.</div>
      ) : (
        <ul className="sl-classes-list">
          {periods.map((p) => (
            <li key={p.entry_id + p.date}>
              <span className="sl-classes-day">{p.day_of_week.slice(0, 3)} {fmtDate(p.date)}</span>
              <span>Period {p.period_no}: {p.subject}, {p.course} Year {p.year}</span>
            </li>
          ))}
        </ul>
      )}
      {note && <div className="sl-classes-note">{note}</div>}
    </div>
  );

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="att-page">

              <div className="att-header">
                <div>
                  <h1 className="att-title">My Leave</h1>
                  <p className="att-subtitle">
                    {isHod
                      ? "Record your leave and name the teacher who will cover for you."
                      : "Apply for leave and follow your HOD's decision."}
                  </p>
                </div>
              </div>

              <div className="att-summary-grid">
                {(balance?.rows || []).filter((b) => b.limited).map((b) => (
                  <div className="att-sum-card" key={b.leave_type}>
                    <div className="att-sum-label">{b.label}</div>
                    <div className="att-sum-value dark">
                      {b.left} <span className="sl-bal-of">of {b.allowed} left</span>
                    </div>
                    <div className="sl-bal-bar" aria-hidden="true">
                      <span style={{ width: `${b.allowed ? Math.min(100, (b.used / b.allowed) * 100) : 0}%` }} />
                    </div>
                    <div className="att-sum-hint">
                      {b.used} used{b.waiting ? ` · ${b.waiting} waiting for approval` : ""}
                    </div>
                  </div>
                ))}
                {balance && (
                  <div className="att-sum-card">
                    <div className="att-sum-label">On duty taken</div>
                    <div className="att-sum-value dark">{takenDays("on_duty")}</div>
                    <div className="att-sum-hint">Days in {balance.year} · no limit</div>
                  </div>
                )}
                <div className="att-sum-card">
                  <div className="att-sum-label">Waiting for approval</div>
                  <div className="att-sum-value dark">{pendingCount}</div>
                  <div className="att-sum-hint">Requests</div>
                </div>
              </div>

              {covering.length > 0 && (
                <div className="sl-covering">
                  <div className="sl-covering-title">You are covering for your HOD</div>
                  {covering.map((c) => (
                    <div key={c.id} className="sl-covering-row">
                      <b>{c.teacher_name}</b> is on leave from {fmtDate(c.from_date)}
                      {c.to_date !== c.from_date ? ` to ${fmtDate(c.to_date)}` : ""}.
                      You are handling department work during this period.
                    </div>
                  ))}
                </div>
              )}

              <div className="att-tabs">
                <button
                  className={`att-tab${view === "apply" ? " active" : ""}`}
                  onClick={() => { setView("apply"); setDetail(null); }}
                >
                  Apply leave
                </button>
                <button
                  className={`att-tab${view === "mine" ? " active" : ""}`}
                  onClick={() => { setView("mine"); setDetail(null); }}
                >
                  My requests ({list.length})
                </button>
              </div>

              {/* ════════ APPLY ════════ */}
              {view === "apply" && (
                <div className="att-card">
                  <h2 className="att-card-title">Apply for leave</h2>

                  <div className="att-od-form-grid">
                    <div className="att-field">
                      <label className="att-label">Leave type</label>
                      <select className="att-input" value={type} onChange={(e) => setType(e.target.value)}>
                        {LEAVE_TYPES.map((t) => {
                          const b = balanceOf(t.value);
                          return (
                            <option key={t.value} value={t.value}>
                              {t.label}{b?.limited ? ` · ${b.available} left` : ""}
                            </option>
                          );
                        })}
                      </select>
                    </div>
                    <div className="att-field">
                      <label className="att-label">From Date</label>
                      <input
                        className="att-input att-input-date"
                        type="date"
                        value={from}
                        onChange={(e) => onFromChange(e.target.value)}
                      />
                    </div>
                    <div className="att-field">
                      <label className="att-label">To Date</label>
                      <input
                        className="att-input att-input-date"
                        type="date"
                        value={to}
                        min={from || undefined}
                        onChange={(e) => onToChange(e.target.value)}
                      />
                    </div>
                    <div className="att-field">
                      <label className="att-label">Session</label>
                      <select
                        className="att-input"
                        value={session}
                        disabled={!singleDay}
                        onChange={(e) => setSession(e.target.value)}
                      >
                        {SESSIONS.map((s) => (
                          <option key={s.value} value={s.value}>{s.label}</option>
                        ))}
                      </select>
                      <div className="sl-hint">
                        {singleDay ? "Half day allowed for a single date" : "Full day only for more than one date"}
                      </div>
                    </div>
                  </div>

                  <div className="sl-two-col">
                    <div>
                      <div className="att-field">
                        <label className="att-label">Reason</label>
                        <textarea
                          className="att-od-textarea"
                          rows={2}
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="e.g. Attending a two-day FDP on concrete technology at Anna University"
                        />
                      </div>
                      <div className="att-field">
                        <label className="att-label">
                          Proof {needsProof ? "(required)" : "(optional)"}
                        </label>
                        <input
                          id="leave-proof-input"
                          className="att-od-file"
                          type="file"
                          onChange={(e) => setProof(e.target.files?.[0] || null)}
                        />
                        <div className="sl-hint">Medical certificate or invitation letter. PDF or image.</div>
                      </div>
                    </div>

                    {periodsBox(
                      preview?.periods || [],
                      preview?.substitute_note ||
                        "These classes may need a substitute teacher. Approving leave does not assign one."
                    )}
                  </div>

                  {isHod && (
                    <div className="att-field sl-backup">
                      <label className="att-label">During my absence (backup)</label>
                      <select className="att-input" value={backup} onChange={(e) => setBackup(e.target.value)}>
                        <option value="">Select a teacher from your department</option>
                        {backupOptions.map((t) => (
                          <option key={t.id} value={t.id}>{t.username}</option>
                        ))}
                      </select>
                      <div className="sl-hint">
                        {backupOptions.length === 0
                          ? "No other active teacher in your department can be chosen. Ask the admin."
                          : preview?.approver_role === "principal"
                            ? `As HOD, your leave goes to the Principal (${preview.approver}) for approval. The teacher you choose will see a handover notice.`
                            : "As HOD, your leave is recorded, not approved. The teacher you choose will see a handover notice."}
                      </div>

                      {/* #50 ACTING HOD: regular HOD nominates the backup */}
                      {canNominate && (
                        <label
                          className="sl-hint"
                          style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 10,
                                   cursor: backup ? "pointer" : "not-allowed" }}
                        >
                          <input
                            type="checkbox"
                            checked={nominate && !!backup}
                            disabled={!backup}
                            onChange={(e) => setNominate(e.target.checked)}
                            style={{ marginTop: 3 }}
                          />
                          <span>
                            <b>
                              Nominate{" "}
                              {backupOptions.find((t) => String(t.id) === String(backup))?.username || "the backup teacher"}
                              {" "}as Acting HOD
                            </b>{" "}
                            for these dates. The main admin must approve it first. Until then you stay HOD.
                            {!backup && " (Choose a backup first.)"}
                          </span>
                        </label>
                      )}
                    </div>
                  )}

                  {preview?.covering_warning && (
                    <div className="sl-warn">⚠ {preview.covering_warning}</div>
                  )}

                  {previewError && <div className="sl-warn">⚠ {previewError}</div>}

                  {preview?.blocked_reason && (
                    <div className="sl-blocked">{preview.blocked_reason}</div>
                  )}
                  {preview?.balance_problem && (
                    <div className="sl-blocked">{preview.balance_problem}</div>
                  )}
                  {formError && <div className="sl-error">{formError}</div>}

                  <div className="sl-foot">
                    <span className="sl-total">
                      {preview
                        ? `Total: ${preview.days ?? 0} ${Number(preview.days) === 1 ? "day" : "days"}`
                        : "Total: not checked"}
                    </span>
                    {preview?.approver && (
                      <span className="sl-to">
                        Goes to <b>{preview.approver}</b>
                        {preview.approver_role === "principal" ? ", the Principal,"
                          : preview.approver_department ? `, HOD of ${preview.approver_department},` : ""} for approval
                      </span>
                    )}
                    {isHod && !preview?.approver && (
                      <span className="sl-to">Recorded as HOD leave. No approval needed.</span>
                    )}
                    <button
                      className="att-btn-primary sl-submit"
                      onClick={submit}
                      disabled={submitting || !!preview?.blocked_reason || !!preview?.balance_problem}
                    >
                      {submitting ? "Sending…" : isHod ? "Submit leave" : "Send to HOD"}
                    </button>
                  </div>
                </div>
              )}

              {/* ════════ MY REQUESTS ════════ */}
              {view === "mine" && (
                <div className="att-card">
                  {detail ? (
                    <>
                      <div className="sl-detail-head">
                        <button className="att-btn-outline" onClick={() => setDetail(null)}>← Back</button>
                        <h2 className="att-card-title sl-detail-title">Leave details</h2>
                        {detail.status && (
                          <span className={`att-od-badge ${badgeOf(detail.status, detail.level).key}`}>
                            {badgeOf(detail.status, detail.level).text}
                          </span>
                        )}
                      </div>
                      {detailLoading ? (
                        <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
                      ) : (
                        <div className="sl-detail">
                          <div className="sl-row"><div className="sl-k">Leave type</div><div>{typeLabel(detail)}</div></div>
                          <div className="sl-row"><div className="sl-k">From and to</div>
                            <div>{fmtDate(detail.from_date)}{detail.to_date !== detail.from_date ? ` to ${fmtDate(detail.to_date)}` : ""}{detail.session !== "full" ? `, ${detail.session_label}` : ""}</div>
                          </div>
                          <div className="sl-row"><div className="sl-k">Number of days</div><div>{Number(detail.days)}</div></div>
                          <div className="sl-row"><div className="sl-k">Reason</div><div>{detail.reason}</div></div>
                          <div className="sl-row"><div className="sl-k">Proof</div>
                            <div>{detail.proof_url
                              ? <a className="att-od-proof" href={detail.proof_url} target="_blank" rel="noreferrer">View proof</a>
                              : <span className="sl-na">Not attached</span>}</div>
                          </div>
                          <div className="sl-row"><div className="sl-k">Approver</div><div>{detail.hod_name
                            ? `${detail.hod_name}${detail.level === "principal" ? " (Principal)" : ""}`
                            : (detail.backup_name ? "Not needed (HOD leave)" : "—")}</div></div>
                          {detail.backup_name && (
                            <div className="sl-row"><div className="sl-k">Backup</div><div>{detail.backup_name}</div></div>
                          )}
                          {detail.acting_hod && (
                            <div className="sl-row"><div className="sl-k">Acting HOD</div>
                              <div>
                                {detail.acting_hod.teacher} · {ACTING_LABEL[detail.acting_hod.status] || detail.acting_hod.status}
                                {detail.acting_hod.reject_reason ? ` — ${detail.acting_hod.reject_reason}` : ""}
                              </div>
                            </div>
                          )}
                          <div className="sl-row"><div className="sl-k">Applied on</div><div>{fmtDate((detail.created_at || "").slice(0, 10))}</div></div>
                          <div className="sl-row"><div className="sl-k">Decision</div>
                            <div>{detail.decided_at
                              ? `${badgeOf(detail.status).text} on ${fmtDate(detail.decided_at.slice(0, 10))}`
                                + (detail.decided_by_name ? ` by ${detail.decided_by_name}` : "")
                                + (detail.decided_as_acting ? " (Acting HOD)" : "")
                              : detail.status === "recorded"
                                ? "Recorded, no approval needed"
                                : <span className="sl-na">Not decided yet</span>}</div>
                          </div>
                          <div className="sl-row"><div className="sl-k">{detail.level === "principal" ? "Principal's remark" : "HOD remark"}</div>
                            <div>{detail.hod_remark || <span className="sl-na">None</span>}</div>
                          </div>
                          <div className="sl-row"><div className="sl-k">Affected periods</div>
                            <div>{periodsBox(detail.affected_periods || [], "")}</div>
                          </div>
                          <div className="sl-row"><div className="sl-k">Substitute status</div>
                            <div><span className="sl-na">Not arranged. Substitution is a later phase.</span></div>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <h2 className="att-card-title">My requests</h2>
                      {loading ? (
                        <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
                      ) : list.length === 0 ? (
                        <div className="att-state"><p>Your leave requests will show here once you apply.</p></div>
                      ) : (
                        <div className="att-od-list">
                          {list.map((r) => {
                            const badge = badgeOf(r.status, r.level);
                            return (
                              <div key={r.id} className="att-od-item">
                                <div className="att-od-row">
                                  <div className="att-od-main">
                                    <div className="att-od-cat">{typeLabel(r)}</div>
                                    <div className="att-od-dates">
                                      {fmtDate(r.from_date)}
                                      {r.to_date !== r.from_date ? ` → ${fmtDate(r.to_date)}` : ""}
                                      {", "}{r.session !== "full" ? r.session_label : `${Number(r.days)} ${Number(r.days) === 1 ? "day" : "days"}`}
                                    </div>
                                  </div>
                                  <div className="att-od-reason-cell">{r.reason}</div>
                                  <div className="att-od-actions">
                                    <button className="att-btn-outline" onClick={() => openDetail(r.id)}>Details</button>
                                    {(r.status === "pending" || r.status === "recorded") && (
                                      <button className="att-btn-outline" onClick={() => cancel(r.id)}>Cancel request</button>
                                    )}
                                    <span className={`att-od-badge ${badge.key}`}>{badge.text}</span>
                                  </div>
                                </div>
                                {r.hod_remark && <div className="att-od-remark"><b>HOD:</b> {r.hod_remark}</div>}
                                {r.backup_name && <div className="att-od-remark"><b>Backup:</b> {r.backup_name}</div>}
                                {r.acting_hod && (
                                  <div className="att-od-remark">
                                    <b>Acting HOD:</b> {r.acting_hod.teacher} · {ACTING_LABEL[r.acting_hod.status] || r.acting_hod.status}
                                    {r.acting_hod.reject_reason ? ` — ${r.acting_hod.reject_reason}` : ""}
                                  </div>
                                )}
                                {r.proof_url && (
                                  <a className="att-od-proof" href={r.proof_url} target="_blank" rel="noreferrer">View proof</a>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}

                      <div className="sl-legend">
                        <div className="sl-legend-title">What each status means</div>
                        {(isHod ? [STATUS_HELP[0], PRINCIPAL_PENDING, ...STATUS_HELP.slice(1)] : STATUS_HELP).map((s) => (
                          <div key={s.text} className="sl-legend-row">
                            <span className={`att-od-badge ${s.key}`}>{s.text}</span>
                            <span>{s.help}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}