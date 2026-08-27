// frontend/src/features/mentoring/StaffRaiseRequest.jsx
import { useCallback, useEffect, useState } from "react";

import {
  errorText,
  getMyRaisedRequests,
  raiseMenteeRequest,
  when,
  withdrawMyRequest,
  yearLabel,
} from "./staffApi";

export default function StaffRaiseRequest() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const [studentId, setStudentId] = useState("");
  const [reason, setReason] = useState("");
  const [detail, setDetail] = useState("");

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getMyRaisedRequests());
    } catch (err) {
      setError(errorText(err, "Could not load your requests."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doRaise = async () => {
    if (!studentId) { flash("Choose one of your mentees."); return; }
    if (!reason) { flash("Choose a reason."); return; }
    setBusy(true);
    try {
      const cr = await raiseMenteeRequest({
        student_id: Number(studentId), reason, detail,
      });
      flash(`Sent to the HOD. ${cr.student_name} has not been told.`);
      setStudentId(""); setReason(""); setDetail("");
      await load();
    } catch (err) {
      flash(errorText(err, "Could not send that request."));
      if (err?.response?.status === 409) await load();
    } finally {
      setBusy(false);
    }
  };

  const doWithdraw = async (id) => {
    if (!window.confirm("Withdraw this request?")) return;
    setBusy(true);
    try {
      await withdrawMyRequest(id);
      flash("Request withdrawn.");
      await load();
    } catch (err) {
      flash(errorText(err, "Could not withdraw."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="ma-panel"><div className="ma-empty">Loading…</div></div>;
  }
  if (error) {
    return <div className="ma-note red"><b>Could not load</b>{error}</div>;
  }
  if (!data) return null;

  const mentees = data.mentees || [];
  const free = mentees.filter((m) => !m.has_open_request);
  const over = data.over_capacity_by || 0;

  return (
    <>
      {/* ---------- load ---------- */}
      <div className="ma-cards" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}>
        <div className="ma-card">
          <div className="l">My mentees</div>
          <div className="n">{data.my_load}</div>
          <div className="d">
            {data.capacity ? `Capacity ${data.capacity}` : "Allocated by the HOD"}
          </div>
        </div>
        <div className="ma-card">
          <div className="l">Over capacity by</div>
          <div className={`n ${over ? "amber" : ""}`}>{over}</div>
          <div className="d">{over ? "A warning, not a block" : "Within your limit"}</div>
        </div>
        <div className="ma-card">
          <div className="l">Waiting on the HOD</div>
          <div className="n">{(data.open || []).length}</div>
          <div className="d">Raised by you</div>
        </div>
      </div>

      {/* ---------- open ---------- */}
      {(data.open || []).map((r) => (
        <div key={r.id} className="ma-batch" style={{ borderLeft: "3px solid #2563eb", marginTop: 16 }}>
          <div className="ma-batch-head">
            <div className="ma-batch-title">
              <b>{r.student_name}</b>
              <div style={{ fontSize: 12, color: "#6b7280" }}>
                {r.student_roll} · raised {when(r.created_at)}
              </div>
            </div>
            <div className="ma-batch-actions">
              <span className="ma-pill ma-blue">With the HOD</span>
              <button className="ma-btn small" disabled={busy}
                      onClick={() => doWithdraw(r.id)}>
                Withdraw
              </button>
            </div>
          </div>
          <div className="ma-batch-body" style={{ padding: "12px 14px" }}>
            <b style={{ fontSize: 13 }}>{r.reason_label}</b>
            {r.detail && (
              <div style={{ fontSize: 13, color: "#374151", fontStyle: "italic", marginTop: 5 }}>
                “{r.detail}”
              </div>
            )}
            <div className="ma-small">
              {r.student_name} is not told unless the HOD moves them.
            </div>
          </div>
        </div>
      ))}

      {/* ---------- decided ---------- */}
      {(data.decided || []).map((r) => (
        <div key={r.id} className="ma-batch" style={{ marginTop: 12 }}>
          <div className="ma-batch-head">
            <div className="ma-batch-title">
              <b>{r.student_name}</b>
              <div style={{ fontSize: 12, color: "#6b7280" }}>
                {r.status === "approved"
                  ? `Moved to ${r.new_mentor_name}`
                  : r.status === "rejected"
                  ? "Stayed with you"
                  : r.status_label}
              </div>
            </div>
            <div className="ma-batch-actions">
              <span className={`ma-pill ${
                r.status === "approved" ? "ma-green" :
                r.status === "rejected" ? "ma-red" : "ma-grey"
              }`}>
                {r.status_label}
              </span>
            </div>
          </div>
          {r.decision_note && (
            <div className="ma-batch-body" style={{ padding: "12px 14px" }}>
              <div className="ma-why">
                <b>{r.decided_by_name} — HOD</b>
                <ul><li>{r.decision_note}</li></ul>
              </div>
            </div>
          )}
        </div>
      ))}

      {/* ---------- form ---------- */}
      <div className="ma-panel" style={{ marginTop: 16 }}>
        <div className="ma-panel-head">
          <div>
            <h3>Ask for a mentee to be moved</h3>
            <p>Goes straight to the HOD — there is no advisor step when a mentor asks</p>
          </div>
        </div>
        <div className="ma-panel-body">
          {mentees.length === 0 && (
            <div className="ma-empty">
              You have no mentees, so there is nothing to hand over.
            </div>
          )}

          {mentees.length > 0 && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <span className="ma-label">Student *</span>
                  <select value={studentId} onChange={(e) => setStudentId(e.target.value)}>
                    <option value="">Choose one of your mentees…</option>
                    {mentees.map((m) => (
                      <option key={m.id} value={m.id} disabled={m.has_open_request}>
                        {m.name} · {m.roll_number}
                        {m.has_open_request ? " — already has an open request" : ""}
                      </option>
                    ))}
                  </select>
                  {free.length === 0 && (
                    <p style={{ fontSize: 12, color: "#b45309", marginTop: 6 }}>
                      Every mentee already has a request in progress.
                    </p>
                  )}
                </div>
                <div>
                  <span className="ma-label">Reason *</span>
                  <select value={reason} onChange={(e) => setReason(e.target.value)}>
                    <option value="">Choose a reason…</option>
                    {(data.reasons || []).map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ marginTop: 14 }}>
                <span className="ma-label">Detail</span>
                <textarea
                  rows={3}
                  value={detail}
                  onChange={(e) => setDetail(e.target.value)}
                  placeholder="Required if you chose Other. The HOD reads this."
                  style={{
                    width: "100%", padding: 10, borderRadius: 8,
                    border: "1px solid #e6e9ef", font: "inherit",
                  }}
                />
              </div>

              <div className="ma-actions" style={{ marginTop: 16 }}>
                <button className="ma-btn primary"
                        disabled={busy || !studentId || !reason}
                        onClick={doRaise}>
                  Send to the HOD
                </button>
                <button className="ma-btn" disabled={busy}
                        onClick={() => { setStudentId(""); setReason(""); setDetail(""); }}>
                  Clear
                </button>
              </div>
            </>
          )}
        </div>
        <div className="ma-panel-foot">
          You cannot pick who takes the student — the HOD does, so every group
          stays balanced on grade and load.
        </div>
      </div>

      <div className="ma-note lock" style={{ marginTop: 16, background: "#f3efff",
             borderColor: "#e3d6fb", color: "#6b21a8" }}>
        <b>Requests about you are not shown here</b>
        If one of your mentees asks to change mentor, it goes to their class
        advisor and the HOD. You are not told that a request exists, who raised
        it, or why — only that a student has moved, if the HOD approves it.
      </div>

      {toast && <div className="ma-toast">{toast}</div>}
    </>
  );
}