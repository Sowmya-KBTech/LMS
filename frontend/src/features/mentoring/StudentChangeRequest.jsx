// frontend/src/features/mentoring/StudentChangeRequest.jsx
import { useCallback, useEffect, useState } from "react";

import {
  errorText,
  getChangeRequest,
  raiseChangeRequest,
  when,
  withdrawChangeRequest,
} from "./studentApi";

/** Small timeline dot. No new CSS file — these are local styles. */
function Dot({ state, children }) {
  const bg =
    state === "done" ? "#059669" :
    state === "now" ? "#2563eb" :
    state === "skip" ? "#fff" : "#eef1f6";
  const fg = state === "done" || state === "now" ? "#fff" : "#94a3b8";
  return (
    <div style={{
      width: 24, height: 24, borderRadius: "50%", flex: "none",
      display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700,
      background: bg, color: fg,
      border: state === "skip" ? "2px dashed #cbd5e1" : "none",
    }}>
      {children}
    </div>
  );
}

function Step({ state, title, sub, last }) {
  return (
    <div style={{ display: "flex", gap: 12, position: "relative", paddingBottom: last ? 0 : 18 }}>
      {!last && (
        <span style={{
          position: "absolute", left: 11, top: 26, bottom: 0,
          width: 2, background: "#e6e9ef",
        }} />
      )}
      <Dot state={state}>{state === "done" ? "✓" : state === "skip" ? "—" : ""}</Dot>
      <div>
        <div style={{ fontWeight: 600, fontSize: 13.5 }}>{title}</div>
        <div style={{ fontSize: 12.5, color: "#6b7280" }}>{sub}</div>
      </div>
    </div>
  );
}

export default function StudentChangeRequest() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

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
      setData(await getChangeRequest());
    } catch (err) {
      setError(errorText(err, "Could not load your request."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ---------- route notice, driven by the server, never guessed ----------
  const routeNotice = () => {
    if (!reason || !data) return null;

    const confidential = (data.confidential_reasons || []).includes(reason);
    if (confidential) {
      return {
        cls: "ma-note amber",
        title: "This goes straight to the HOD",
        body: "For this reason your class advisor is skipped entirely. " +
              "Only the HOD reads what you write.",
      };
    }
    if (!data.advisor_step_enabled) {
      return {
        cls: "ma-note blue",
        title: "This goes straight to the HOD",
        body: "Your department has the class advisor step turned off.",
      };
    }
    if (!data.advisor) {
      return {
        cls: "ma-note blue",
        title: "This goes straight to the HOD",
        body: "Your class has no class advisor assigned, so there is no advisor step.",
      };
    }
    if (data.advisor.is_my_mentor) {
      return {
        cls: "ma-note amber",
        title: "This goes straight to the HOD",
        body: `${data.advisor.name} is both your mentor and your class advisor, ` +
              "so the advisor step is dropped. Nobody reviews a complaint about themselves.",
      };
    }
    return {
      cls: "ma-note blue",
      title: "This goes to your class advisor first",
      body: `${data.advisor.name} will read it, add a note, and pass it to the HOD. ` +
            "Your current mentor is not told.",
    };
  };

  const doRaise = async () => {
    if (!reason) { flash("Choose a reason first."); return; }
    setBusy(true);
    try {
      await raiseChangeRequest({ reason, detail });
      setReason("");
      setDetail("");
      flash("Request sent. You will be notified when it is decided.");
      await load();
    } catch (err) {
      if (err?.response?.status === 409) {
        flash(errorText(err, "You already have a request in progress."));
        await load();
      } else {
        flash(errorText(err, "Could not send your request."));
      }
    } finally {
      setBusy(false);
    }
  };

  const doWithdraw = async (id) => {
    if (!window.confirm("Withdraw this request? You can raise a new one afterwards."))
      return;
    setBusy(true);
    try {
      await withdrawChangeRequest(id);
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

  const open = data.open_request;
  const last = (data.past_requests || [])[0];
  const notice = routeNotice();

  return (
    <>
      {/* ================= IN PROGRESS ================= */}
      {open && (
        <div className="ma-panel" style={{ maxWidth: 840 }}>
          <div className="ma-panel-head">
            <div>
              <h3>Your request</h3>
              <p>Sent {when(open.created_at)}</p>
            </div>
            <div className="ma-batch-actions">
              <span className="ma-pill ma-amber">In progress</span>
            </div>
          </div>

          <div className="ma-panel-body">
            <table className="ma-table" style={{ marginBottom: 14 }}>
              <tbody>
                <tr><td>Reason given</td><td className="ma-right">{open.reason_label}</td></tr>
                <tr><td>Current mentor</td><td className="ma-right"><b>{open.current_mentor_name}</b></td></tr>
              </tbody>
            </table>

            {open.detail && (
              <div className="ma-note" style={{ fontStyle: "italic", marginBottom: 14 }}>
                “{open.detail}”
              </div>
            )}

            {open.is_confidential && (
              <div className="ma-note amber" style={{ marginBottom: 14 }}>
                <b>Only the HOD can read this</b>
                Your class advisor was skipped and {open.current_mentor_name} has
                not been told that you asked.
              </div>
            )}

            <Step
              state="done"
              title="Sent"
              sub={`By you · ${when(open.created_at)}`}
            />
            {open.advisor ? (
              <Step
                state={open.status === "advisor" ? "now" : "done"}
                title="Class advisor"
                sub={
                  open.status === "advisor"
                    ? `${open.advisor_name} is reviewing it`
                    : `${open.advisor_name} passed it on`
                }
              />
            ) : (
              <Step
                state="skip"
                title="Class advisor"
                sub="Skipped for this request"
              />
            )}

            {/* the advisor writes this expecting the student to read it */}
            {open.advisor_note && (
              <div className="ma-why" style={{ marginLeft: 36, marginBottom: 18 }}>
                <b>{open.advisor_name} — class advisor</b>
                <ul><li>{open.advisor_note}</li></ul>
              </div>
            )}

            <Step
              state={open.status === "hod" ? "now" : ""}
              title="With the HOD"
              sub={open.status === "hod" ? "Waiting for a decision" : "Not yet"}
            />
            <Step
              state=""
              title="Decision"
              sub="You are notified either way"
              last
            />

            <div className="ma-actions" style={{ marginTop: 16 }}>
              <button className="ma-btn" disabled={busy} onClick={() => doWithdraw(open.id)}>
                Withdraw this request
              </button>
            </div>
          </div>

          <div className="ma-panel-foot">
            Nothing changes until it is decided. Keep meeting{" "}
            {open.current_mentor_name} in the meantime.
          </div>
        </div>
      )}

      {/* ================= LAST OUTCOME ================= */}
      {!open && last && (
        <div className="ma-panel" style={{ maxWidth: 840 }}>
          <div className="ma-panel-head">
            <div>
              <h3>Your last request</h3>
              <p>Decided {when(last.decided_at || last.updated_at)}</p>
            </div>
            <div className="ma-batch-actions">
              <span className={`ma-pill ${
                last.status === "approved" ? "ma-green" :
                last.status === "rejected" ? "ma-red" : "ma-grey"
              }`}>
                {last.status_label}
              </span>
            </div>
          </div>
          <div className="ma-panel-body">
            {last.status === "approved" && (
              <div className="ma-note green">
                <b>Your mentor is now {last.new_mentor_name}</b>
                They have been told you are one of their mentees.
              </div>
            )}
            {last.status === "rejected" && (
              <div className="ma-note red">
                <b>Your mentor stays as {last.current_mentor_name}</b>
                {last.decision_note}
              </div>
            )}
            {last.status === "withdrawn" && (
              <div className="ma-note">
                <b>You withdrew this request</b>
                Nothing was changed and {last.current_mentor_name} was never told.
                You can raise a new one below.
              </div>
            )}
            {last.status === "resolved" && (
              <div className="ma-note">
                <b>Your class advisor resolved this without a change</b>
                Your mentor stays as {last.current_mentor_name}.
              </div>
            )}
            {last.advisor_note && (
              <div className="ma-why">
                <b>{last.advisor_name} — class advisor</b>
                <ul><li>{last.advisor_note}</li></ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ================= FORM ================= */}
      {data.can_raise ? (
        <div className="ma-panel" style={{ maxWidth: 840 }}>
          <div className="ma-panel-head">
            <div>
              <h3>Ask for a different mentor</h3>
              <p>One request at a time</p>
            </div>
          </div>
          <div className="ma-panel-body">
            {data.current_mentor && (
              <table className="ma-table" style={{ marginBottom: 16 }}>
                <tbody>
                  <tr>
                    <td>Current mentor</td>
                    <td className="ma-right"><b>{data.current_mentor.name}</b></td>
                  </tr>
                </tbody>
              </table>
            )}

            <span className="ma-label">Reason *</span>
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="">Choose a reason…</option>
              {(data.reasons || []).map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>

            {notice && (
              <div className={notice.cls} style={{ marginTop: 14 }}>
                <b>{notice.title}</b>{notice.body}
              </div>
            )}

            <div style={{ marginTop: 14 }}>
              <span className="ma-label">Tell them a little more</span>
              <textarea
                rows={3}
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
                placeholder="Required if you chose Other."
                style={{
                  width: "100%", padding: 10, borderRadius: 8,
                  border: "1px solid #e6e9ef", font: "inherit",
                }}
              />
            </div>

            <div className="ma-actions" style={{ marginTop: 16 }}>
              <button
                className="ma-btn primary"
                disabled={busy || !reason}
                onClick={doRaise}
              >
                Send request
              </button>
              <button
                className="ma-btn"
                disabled={busy}
                onClick={() => { setReason(""); setDetail(""); }}
              >
                Clear
              </button>
            </div>
          </div>
          <div className="ma-panel-foot">
            You cannot choose the new mentor — the HOD decides, so every group
            stays balanced. Your current mentor is never shown this.
          </div>
        </div>
      ) : (
        !open && (
          <div className="ma-note blue" style={{ maxWidth: 840 }}>
            <b>You cannot raise a request right now</b>
            {data.why_not}
          </div>
        )
      )}

      {toast && <div className="ma-toast">{toast}</div>}
    </>
  );
}