// frontend/src/features/mentoring/StaffChangeRequests.jsx
import { useCallback, useEffect, useState } from "react";

import {
  actOnChangeRequest,
  errorText,
  getStaffChangeRequest,
  getStaffChangeRequests,
  when,
  yearLabel,
} from "./staffApi";

import StaffRaiseRequest from "./StaffRaiseRequest";

const BUCKETS = [
  { key: "waiting", label: "Waiting on you" },
  { key: "forwarded", label: "Forwarded" },
  { key: "resolved", label: "Resolved" },
];

export default function StaffChangeRequests() {
  const [counts, setCounts] = useState({});
  const [rows, setRows] = useState([]);
  const [bucket, setBucket] = useState("waiting");

  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState("");

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await getStaffChangeRequests({ bucket });
      setCounts(d.counts || {});
      setRows(d.results || []);
    } catch (err) {
      setError(errorText(err, "Could not load the change requests."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [bucket]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    setBusy(true);
    try {
      const d = await getStaffChangeRequest(id);
      setDetail(d.request);
      setNote("");
    } catch (err) {
      flash(errorText(err, "Could not open that request."));
    } finally {
      setBusy(false);
    }
  };

  const act = async (action) => {
    if (!note.trim()) {
      flash("A note is required — the student is shown it either way.");
      return;
    }
    setBusy(true);
    try {
      const d = await actOnChangeRequest(detail.id, { action, note });
      flash(
        d.action === "forward"
          ? `Sent to the HOD. ${d.request.student_name} has been told.`
          : `Closed. ${d.request.student_name} keeps ${d.request.current_mentor_name}.`
      );
      setDetail(null);
      setNote("");
      await load();
    } catch (err) {
      flash(errorText(err, "Could not save that."));
    } finally {
      setBusy(false);
    }
  };

  // ================= DETAIL =================
  if (detail) {
    return (
      <>
        <button className="ma-btn link" style={{ marginBottom: 12 }}
                onClick={() => { setDetail(null); setNote(""); }}>
          ← Back to the queue
        </button>

        <div className="ma-panel" style={{ maxWidth: 880 }}>
          <div className="ma-panel-head">
            <div>
              <h3>{detail.student_name}</h3>
              <p>
                {detail.student_roll} · {yearLabel(detail.student_year)} Year
                {detail.course_name ? ` · ${detail.course_name}` : ""}
              </p>
            </div>
            <div style={{ flex: 1 }} />
            <span className="ma-pill ma-amber">Waiting on you</span>
          </div>

          <div className="ma-panel-body">
            <table className="ma-table" style={{ marginBottom: 14 }}>
              <tbody>
                <tr>
                  <td>Mentor they want to leave</td>
                  <td className="ma-right"><b>{detail.current_mentor_name}</b></td>
                </tr>
                <tr><td>Reason</td><td className="ma-right">{detail.reason_label}</td></tr>
                <tr><td>Raised</td><td className="ma-right">{when(detail.created_at)}</td></tr>
              </tbody>
            </table>

            {detail.detail && (
              <div className="ma-note" style={{ fontStyle: "italic", marginBottom: 14 }}>
                “{detail.detail}”
              </div>
            )}

            <span className="ma-label">Your note *</span>
            <textarea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={`${detail.student_name} sees this on their own page, so keep it factual.`}
              style={{
                width: "100%", padding: 10, borderRadius: 8,
                border: "1px solid #e6e9ef", font: "inherit",
              }}
            />

            <div className="ma-actions" style={{ marginTop: 16 }}>
              <button className="ma-btn primary" disabled={busy || !note.trim()}
                      onClick={() => act("forward")}>
                Forward to the HOD
              </button>
              <button className="ma-btn" disabled={busy || !note.trim()}
                      onClick={() => act("resolve")}>
                Resolve without a change
              </button>
            </div>
          </div>

          <div className="ma-panel-foot">
            You cannot pick a replacement mentor — that is the HOD's decision, so
            groups stay balanced. {detail.current_mentor_name} is not told either way.
          </div>
        </div>

        {toast && <div className="ma-toast">{toast}</div>}
      </>
    );
  }

  // ================= LIST =================
  return (
    <>
      <div className="ma-note blue" style={{ marginBottom: 16 }}>
        <b>You see these because you are the class advisor</b>
        Read the request, then either pass it to the HOD with a note or close it
        yourself. Sensitive requests go straight to the HOD and never appear here.
      </div>

      <div className="ma-cards">
        <div className="ma-card">
          <div className="l">Waiting on you</div>
          <div className="n">{counts.waiting ?? 0}</div>
          <div className="d">Nothing moves until you act</div>
        </div>
        <div className="ma-card">
          <div className="l">Forwarded to the HOD</div>
          <div className="n">{counts.forwarded ?? 0}</div>
          <div className="d">Decision is theirs</div>
        </div>
        <div className="ma-card">
          <div className="l">Resolved by you</div>
          <div className="n green">{counts.resolved ?? 0}</div>
          <div className="d">No change needed</div>
        </div>
      </div>

      <div className="ma-toggle" style={{ margin: "16px 0" }}>
        {BUCKETS.map((b) => (
          <button key={b.key} className={bucket === b.key ? "on" : ""}
                  onClick={() => setBucket(b.key)}>
            {b.label}
          </button>
        ))}
      </div>

      {error && <div className="ma-note red" style={{ marginBottom: 16 }}>
        <b>Could not load</b>{error}
      </div>}

      {loading && <div className="ma-panel"><div className="ma-empty">Loading…</div></div>}

      {!loading && rows.length === 0 && (
        <div className="ma-panel">
          <div className="ma-empty">
            {bucket === "waiting"
              ? "Nothing waiting on you. If you are not a class advisor, nothing will ever appear here."
              : "No request in this list."}
          </div>
        </div>
      )}

      {!loading && rows.map((r) => (
        <div key={r.id} className="ma-batch">
          <div className="ma-batch-head">
            <div className="ma-batch-title">
              <b>{r.student_name}</b>
              <div style={{ fontSize: 12, color: "#6b7280" }}>
                {r.student_roll} · {yearLabel(r.student_year)} Year · mentor{" "}
                {r.current_mentor_name}
              </div>
            </div>
            <div className="ma-chips">
              <span className="ma-chip">{when(r.created_at)}</span>
            </div>
            <div className="ma-batch-actions">
              {r.status === "advisor" ? (
                <button className="ma-btn primary small" onClick={() => openDetail(r.id)}>
                  Review
                </button>
              ) : (
                <span className="ma-pill ma-grey">{r.status_label}</span>
              )}
            </div>
          </div>
          <div className="ma-batch-body" style={{ padding: "12px 14px" }}>
            <b style={{ fontSize: 13 }}>{r.reason_label}</b>
            {r.detail && (
              <div style={{ fontSize: 13, color: "#374151", fontStyle: "italic", marginTop: 5 }}>
                “{r.detail}”
              </div>
            )}
            {r.advisor_note && (
              <div className="ma-why">
                <b>Your note</b>
                <ul><li>{r.advisor_note}</li></ul>
              </div>
            )}
            <div className="ma-small">
              {r.current_mentor_name} has not been told about this.
            </div>
          </div>
        </div>
            ))}

      <div style={{
        fontSize: 11, letterSpacing: ".8px", textTransform: "uppercase",
        color: "#6b7280", fontWeight: 700, margin: "32px 0 12px",
      }}>
        Raised by you — about your own mentees
      </div>
      <StaffRaiseRequest />

      {toast && <div className="ma-toast">{toast}</div>}
    </>
  );
}