// frontend/src/features/mentoring/HodChangeRequests.jsx
import { useCallback, useEffect, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";

import {
  ageText,
  decideChangeRequest,
  errorText,
  getChangeRequest,
  getChangeRequests,
  getOptions,
  prettyYear,
  requestPill,
  yearLabel,
} from "./mentoringApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

const BUCKETS = [
  { key: "waiting", label: "Awaiting you" },
  { key: "advisor", label: "With advisor" },
  { key: "decided", label: "Decided" },
];

const onDateTime = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
};

export default function HodChangeRequests() {
  const [open, setOpen] = useState(false);

  const [years, setYears] = useState([]);
  const [academicYear, setAcademicYear] = useState("");

  const [counts, setCounts] = useState({});
  const [rows, setRows] = useState([]);
  const [bucket, setBucket] = useState("waiting");

  // the request currently opened for a decision
  const [detail, setDetail] = useState(null);
  const [newMentorId, setNewMentorId] = useState("");
  const [note, setNote] = useState("");

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  // ================= LOAD =================
  useEffect(() => {
    getOptions()
      .then((d) => {
        setYears(d.academic_years || []);
        if (d.academic_years?.length) setAcademicYear(d.academic_years[0]);
      })
      .catch(() => setYears([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await getChangeRequests({ bucket, academic_year: academicYear });
      setCounts(d.counts || {});
      setRows(d.results || []);
    } catch (err) {
      setError(errorText(err, "Could not load the change requests."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [bucket, academicYear]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    setBusy(true);
    try {
      const d = await getChangeRequest(id, { academic_year: academicYear });
      setDetail(d);
      setNewMentorId("");
      setNote("");
      window.scrollTo(0, 0);
    } catch (err) {
      flash(errorText(err, "Could not open that request."));
    } finally {
      setBusy(false);
    }
  };

  const closeDetail = () => {
    setDetail(null);
    setNewMentorId("");
    setNote("");
  };

  // ================= DECIDE =================
  const decide = async (decision, override = false) => {
    if (decision === "approve" && !newMentorId) {
      flash("Pick the mentor the student moves to.");
      return;
    }
    if (decision === "reject" && !note.trim()) {
      flash("A rejection needs a reason — the student is shown it.");
      return;
    }

    setBusy(true);
    try {
      const body = { decision, note, override };
      if (decision === "approve") body.new_mentor_id = Number(newMentorId);

      const d = await decideChangeRequest(detail.request.id, body);
      flash(
        d.decision === "approve"
          ? `${d.request.student_name} moved to ${d.request.new_mentor_name}`
          : `Request declined. ${d.request.student_name} has been notified.`
      );
      closeDetail();
      await load();
    } catch (err) {
      // 409 = capacity warning, not a failure. Same contract as assignMentor.
      if (err?.response?.status === 409) {
        const msg = err.response.data?.message || "That mentor would go over capacity.";
        if (window.confirm(`${msg}\n\nApprove anyway?`)) {
          setBusy(false);
          return decide(decision, true);
        }
      } else {
        flash(errorText(err, "Could not save that decision."));
      }
    } finally {
      setBusy(false);
    }
  };

  // ================= DETAIL VIEW =================
  const renderDetail = () => {
    const r = detail.request;
    const options = detail.mentor_options || [];
    const chosen = options.find((m) => String(m.id) === String(newMentorId));

    return (
      <>
        <button className="ma-btn link" onClick={closeDetail} style={{ marginBottom: 12 }}>
          ← Back to all requests
        </button>

        <div className="ma-panel">
          <div className="ma-panel-head">
            <div>
              <h3>{r.student_name}</h3>
              <p>
                {r.student_roll} · {yearLabel(r.student_year)} Year
                {r.course_name ? ` · ${r.course_name}` : ""}
                {detail.student_band ? ` · grade ${detail.student_band}` : ""}
              </p>
            </div>
            <div className="ma-batch-actions">
              {r.is_confidential && <span className="ma-pill ma-purple">Confidential</span>}
              <span className={`ma-pill ${requestPill(r.status).cls}`}>
                {requestPill(r.status).label}
              </span>
            </div>
          </div>

          <div className="ma-panel-body">
            <table className="ma-table">
              <tbody>
                <tr><td>Current mentor</td><td className="ma-right"><b>{r.current_mentor_name}</b></td></tr>
                <tr><td>Reason</td><td className="ma-right">{r.reason_label}</td></tr>
                <tr><td>Raised by</td><td className="ma-right">{r.raised_by_name} · {r.source_label}</td></tr>
                <tr><td>Raised on</td><td className="ma-right">{onDateTime(r.created_at)}</td></tr>
              </tbody>
            </table>

            {r.detail && (
              <div className="ma-note" style={{ marginTop: 14, fontStyle: "italic" }}>
                “{r.detail}”
              </div>
            )}

            {r.advisor_note && (
              <div className="ma-why">
                <b>{r.advisor_name} — class advisor</b>
                <ul><li>{r.advisor_note}</li></ul>
              </div>
            )}

            {r.is_confidential && (
              <div className="ma-note amber" style={{ marginTop: 14 }}>
                <b>The class advisor was skipped</b>
                This reason routes straight to you. Nobody else in the department
                can read it, and {r.current_mentor_name} has not been told.
              </div>
            )}
          </div>
        </div>

        <div className="ma-panel">
          <div className="ma-panel-head">
            <div>
              <h3>Move to a new mentor</h3>
              <p>Sorted by free places. The grade mix is shown so the group stays balanced.</p>
            </div>
          </div>
          <div className="ma-scroll">
            <table className="ma-table">
              <thead>
                <tr>
                  <th></th><th>Mentor</th><th>Capacity</th><th>Assigned</th>
                  <th>Available</th><th>A</th><th>B</th><th>C</th><th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {options.length === 0 && (
                  <tr><td colSpan={9} className="ma-empty">
                    No other mentor in this department.
                  </td></tr>
                )}
                {options.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <input
                        type="radio"
                        name="newmentor"
                        checked={String(newMentorId) === String(m.id)}
                        onChange={() => setNewMentorId(m.id)}
                      />
                    </td>
                    <td><b>{m.name}</b>
                      <div style={{ fontSize: 11.5, color: "#6b7280" }}>{m.employee_id}</div>
                    </td>
                    <td className="num">{m.capacity}</td>
                    <td className="num">{m.assigned}</td>
                    <td>
                      <span className={`ma-pill ${m.is_full ? "ma-red" : "ma-green"}`}>
                        {m.available}
                      </span>
                    </td>
                    <td className="num">{m.band_a}</td>
                    <td className="num">{m.band_b}</td>
                    <td className="num">{m.band_c}</td>
                    <td>
                      <span className={`ma-chip ${
                        m.balance_state === "bad" ? "bad" :
                        m.balance_state === "ok" ? "good" : ""
                      }`}>
                        {m.balance_message}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="ma-panel-foot">
            {r.current_mentor_name} is the current mentor and is not in this list.
            The API refuses that move too, not just this page.
          </div>
        </div>

        <div className="ma-panel">
          <div className="ma-panel-body">
            <span className="ma-label">Note — required when rejecting</span>
            <textarea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="The student is shown this. A rejection without a note is refused."
              style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #e6e9ef" }}
            />
            <div className="ma-actions" style={{ marginTop: 14 }}>
              <button
                className="ma-btn primary"
                disabled={busy || !newMentorId}
                onClick={() => decide("approve")}
              >
                {chosen ? `Approve — move to ${chosen.name}` : "Approve and reassign"}
              </button>
              <button
                className="ma-btn danger"
                disabled={busy || !note.trim()}
                onClick={() => decide("reject")}
              >
                Reject
              </button>
            </div>
          </div>
          <div className="ma-panel-foot">
            Approving closes the current allocation and opens a new one. Both rows
            stay in Allocation History.
          </div>
        </div>
      </>
    );
  };

  // ================= LIST VIEW =================
  const renderList = () => (
    <>
      <div className="ma-cards">
        <div className="ma-card">
          <div className="l">Awaiting your decision</div>
          <div className="n">{counts.waiting ?? 0}</div>
          <div className="d">Nothing moves until you act</div>
        </div>
        <div className="ma-card">
          <div className="l">With a class advisor</div>
          <div className="n">{counts.with_advisor ?? 0}</div>
          <div className="d">Not yours yet</div>
        </div>
        <div className="ma-card">
          <div className="l">Confidential</div>
          <div className="n amber">{counts.confidential ?? 0}</div>
          <div className="d">Advisor was skipped</div>
        </div>
        <div className="ma-card">
          <div className="l">Decided this year</div>
          <div className="n green">{counts.decided ?? 0}</div>
                    <div className="d">
            All in Allocation History
            {counts.resolved_by_advisor
              ? ` · ${counts.resolved_by_advisor} closed by an advisor`
              : ""}
          </div>
        </div>
      </div>

      <div className="ma-toggle" style={{ margin: "16px 0" }}>
        {BUCKETS.map((b) => (
          <button
            key={b.key}
            className={bucket === b.key ? "on" : ""}
            onClick={() => setBucket(b.key)}
          >
            {b.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
      )}

      {!loading && rows.length === 0 && (
        <div className="ma-panel">
          <div className="ma-empty">
            {bucket === "waiting"
              ? "Nothing waiting on you. Every request has been decided."
              : "No request in this list."}
          </div>
        </div>
      )}

      {!loading && rows.map((r) => (
        <div
          key={r.id}
          className="ma-batch"
          style={r.is_confidential ? { borderLeft: "3px solid #7c3aed" } : undefined}
        >
          <div className="ma-batch-head">
            <div className="ma-batch-title">
              <b>{r.student_name}</b>
              <div style={{ fontSize: 12, color: "#6b7280" }}>
                {r.student_roll} · {yearLabel(r.student_year)} Year · mentor{" "}
                {r.current_mentor_name}
              </div>
            </div>
            <div className="ma-chips">
              <span className="ma-chip">{r.source_label}</span>
              <span className="ma-chip">{ageText(r.created_at)}</span>
            </div>
            <div className="ma-batch-actions">
              <span className={`ma-pill ${requestPill(r.status).cls}`}>
                {requestPill(r.status).label}
              </span>
              {r.status === "hod" && (
                <button className="ma-btn primary small" onClick={() => openDetail(r.id)}>
                  Decide
                </button>
              )}
              {r.status !== "hod" && (
                <button className="ma-btn small" onClick={() => openDetail(r.id)}>
                  Open
                </button>
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
                <b>{r.advisor_name} — class advisor</b>
                <ul><li>{r.advisor_note}</li></ul>
              </div>
            )}
            <div className="ma-small">
              {r.current_mentor_name} has not been told about this.
            </div>
          </div>
        </div>
      ))}
    </>
  );

  // ================= RENDER =================
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2 style={{ margin: 0 }}>Change Requests</h2>
              <p>Students and mentors asking for a different allocation</p>
            </div>

            <MentoringTabs />

            <div className="ma-panel">
              <div className="ma-panel-body">
                <div className="ma-filters">
                  <div>
                    <span className="ma-label">Academic Year</span>
                    <select
                      value={academicYear}
                      onChange={(e) => { setAcademicYear(e.target.value); closeDetail(); }}
                    >
                      {years.map((y) => (
                        <option key={y} value={y}>{prettyYear(y)}</option>
                      ))}
                    </select>
                  </div>
                  <button className="ma-btn" onClick={load} disabled={busy}>
                    Refresh
                  </button>
                </div>
              </div>
            </div>

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>{error}
              </div>
            )}

            <div className="ma-note blue" style={{ marginBottom: 16 }}>
              <b>The current mentor is never shown a request</b>
              Not while it is open, and not after it is decided. Approving moves the
              student through the normal allocation flow, so Allocation History
              records it like any other change.
            </div>

            {detail ? renderDetail() : renderList()}

          </div>
        </div>
      </div>
      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );
}