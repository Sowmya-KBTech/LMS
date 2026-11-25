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

// The count lives on the tab now. It used to appear twice — once in a row of
// cards, then again as the tab you press to see the same list.
const BUCKETS = [
  { key: "waiting", label: "Waiting on you", countKey: "waiting" },
  { key: "forwarded", label: "Sent to the HOD", countKey: "forwarded" },
  { key: "resolved", label: "Closed by you", countKey: "resolved" },
];

export default function StaffChangeRequests() {
  const [counts, setCounts] = useState({});
  const [rows, setRows] = useState([]);
  const [bucket, setBucket] = useState("waiting");
  const [isAdvisor, setIsAdvisor] = useState(true);

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
      // the backend tells us this and the page used to ignore it, then guess
      // in the empty-state text instead
      setIsAdvisor(d.is_advisor !== false);
    } catch (err) {
      setError(errorText(err, "Could not load the change requests."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [bucket]);

  useEffect(() => {
    load();
  }, [load]);

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
      flash("Write a note first — the student is shown it either way.");
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
    const open = detail.status === "advisor";

    return (
      <>
        <button
          className="ma-btn link"
          style={{ marginBottom: 12 }}
          onClick={() => {
            setDetail(null);
            setNote("");
          }}
        >
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
            <span className={`ma-pill ${open ? "ma-amber" : "ma-grey"}`}>
              {open ? "Waiting on you" : detail.status_label}
            </span>
          </div>

          <div className="ma-panel-body">
            <div className="ma-note" style={{ marginBottom: 14 }}>
              <b>What is being asked</b>
              {detail.student_name} would like to move away from{" "}
              {detail.current_mentor_name}. You decide whether to pass it to the HOD
              or close it here. You do not pick a replacement.
            </div>

            <table className="ma-table" style={{ marginBottom: 14 }}>
              <tbody>
                <tr>
                  <td>Their mentor now</td>
                  <td className="ma-right">
                    <b>{detail.current_mentor_name}</b>
                  </td>
                </tr>
                <tr>
                  <td>Reason given</td>
                  <td className="ma-right">{detail.reason_label}</td>
                </tr>
                <tr>
                  <td>Raised</td>
                  <td className="ma-right">{when(detail.created_at)}</td>
                </tr>
              </tbody>
            </table>

            {detail.detail && (
              <div className="ma-note" style={{ marginBottom: 14 }}>
                <b>In their own words</b>
                <span style={{ fontStyle: "italic" }}>“{detail.detail}”</span>
              </div>
            )}

            {open ? (
              <>
                <span className="ma-label">
                  Your note — required, and {detail.student_name} will read it
                </span>
                <textarea
                  rows={3}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Keep it factual. Say what you looked at and why you decided this."
                  style={{
                    width: "100%",
                    padding: 10,
                    borderRadius: 8,
                    border: "1px solid #E7E7EC",
                    font: "inherit",
                  }}
                />

                <div className="ma-actions" style={{ marginTop: 16 }}>
                  <button
                    className="ma-btn primary"
                    disabled={busy || !note.trim()}
                    onClick={() => act("forward")}
                  >
                    Pass to the HOD
                  </button>
                  <button
                    className="ma-btn"
                    disabled={busy || !note.trim()}
                    onClick={() => act("resolve")}
                  >
                    Close — no change needed
                  </button>
                </div>
              </>
            ) : (
              <div className="ma-note">
                <b>Already decided</b>
                This request is no longer waiting on you.
                {detail.advisor_note ? ` Your note was: “${detail.advisor_note}”` : ""}
              </div>
            )}
          </div>

          <div className="ma-panel-foot">
            Only the HOD can choose a replacement mentor, so groups stay balanced.{" "}
            {detail.current_mentor_name} is never told a request exists.
          </div>
        </div>

        {toast && <div className="ma-toast">{toast}</div>}
      </>
    );
  }

  // ================= LIST =================
  return (
    <>
      {/* ---------------- part one: requests about your class ---------------- */}
      <div className="ma-note blue" style={{ marginBottom: 16 }}>
        <b>Students in your class asking to change mentor</b>
        You see these because you are the class in-charge. Read the request, then either pass
        it to the HOD with a note or close it yourself. Sensitive reasons skip you
        entirely and go straight to the HOD.
      </div>

      {/* counts and navigation in one control, instead of three cards above
          three tabs showing the same three numbers */}
      <div className="ma-toggle" style={{ marginBottom: 16 }}>
        {BUCKETS.map((b) => {
          const n = counts[b.countKey] ?? 0;
          return (
            <button
              key={b.key}
              className={bucket === b.key ? "on" : ""}
              onClick={() => setBucket(b.key)}
            >
              {b.label}
              {n > 0 ? ` (${n})` : ""}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="ma-note red" style={{ marginBottom: 16 }}>
          <b>Could not load</b>
          {error}
        </div>
      )}

      {loading && (
        <div className="ma-panel">
          <div className="ma-empty">Loading…</div>
        </div>
      )}

      {!loading && rows.length === 0 && (
        <div className="ma-panel">
          <div className="ma-empty">
            {!isAdvisor ? (
              <>
                <b style={{ display: "block", marginBottom: 6 }}>
                  You are not a class in-charge
                </b>
                Only a class in-charge reviews change requests. You can still raise one about
                your own mentees, below.
              </>
            ) : bucket === "waiting" ? (
              <>
                <b style={{ display: "block", marginBottom: 6 }}>
                  Nothing waiting on you
                </b>
                No student in your class has asked to change mentor.
              </>
            ) : (
              "No request in this list yet."
            )}
          </div>
        </div>
      )}

      {!loading &&
        rows.map((r) => (
          <div key={r.id} className="ma-batch">
            <div className="ma-batch-head">
              <div className="ma-batch-title">
                <b>{r.student_name}</b>
                <div style={{ fontSize: 13, color: "#5D5A6B" }}>
                  {r.student_roll} · {yearLabel(r.student_year)} Year · mentor{" "}
                  {r.current_mentor_name}
                </div>
              </div>
              <div className="ma-chips">
                <span className="ma-chip">{when(r.created_at)}</span>
              </div>
              <div className="ma-batch-actions">
                {r.status === "advisor" ? (
                  <button
                    className="ma-btn primary small"
                    onClick={() => openDetail(r.id)}
                  >
                    Read and decide
                  </button>
                ) : (
                  <span className="ma-pill ma-grey">{r.status_label}</span>
                )}
              </div>
            </div>
            <div className="ma-batch-body" style={{ padding: "12px 14px" }}>
              <b style={{ fontSize: 14 }}>{r.reason_label}</b>
              {r.detail && (
                <div
                  style={{
                    fontSize: 14,
                    color: "#5D5A6B",
                    fontStyle: "italic",
                    marginTop: 5,
                  }}
                >
                  “{r.detail}”
                </div>
              )}
              {r.advisor_note && (
                <div className="ma-why">
                  <b>Your note</b>
                  <ul>
                    <li>{r.advisor_note}</li>
                  </ul>
                </div>
              )}
              <div className="ma-small">
                {r.current_mentor_name} has not been told about this.
              </div>
            </div>
          </div>
        ))}

      {/* ---------------- part two: requests you raise ----------------
          A different job from everything above: there you review what students
          ask, here you ask for one of your own mentees to be moved. It used to
          sit under a small grey label with nothing else marking the change. */}
      <div className="ma-panel" style={{ marginTop: 34, background: "transparent", border: "none", boxShadow: "none" }}>
        <div className="ma-note" style={{ marginBottom: 0 }}>
          <b>Asking for one of your own mentees to be moved</b>
          A separate thing from the queue above. This goes straight to the HOD with
          no class in-charge step, and the student is never told a request exists — only that
          they moved, if it is approved.
        </div>
      </div>

      <StaffRaiseRequest />

      {toast && <div className="ma-toast">{toast}</div>}
    </>
  );
}