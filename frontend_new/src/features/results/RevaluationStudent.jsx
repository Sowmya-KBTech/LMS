import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";

export default function RevaluationStudent({ embedded = false }) {
  const [open, setOpen] = useState(false);

  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const [results, setResults]   = useState([]);   // published semester results
  const [requests, setRequests] = useState([]);   // own revaluation requests
  // the student's LATEST examination - the only one revaluation is open for.
  // Worked out by the server (review items 4.6 / 4.7), not here.
  const [latest, setLatest]     = useState({ semester: null, window: null });
  const [loading, setLoading]   = useState(true);
  const [busy, setBusy]         = useState(null);  // entry id being acted on

  // ── load published results + own revaluation requests ──
  const load = async () => {
    setLoading(true);
    try {
      const [resR, reqR, latR] = await Promise.all([
        API.get("/semester-results/"),
        API.get("/revaluations/"),
        API.get("/revaluations/latest/"),
      ]);
      setResults(resR.data?.results || resR.data || []);
      setRequests(reqR.data?.results || reqR.data || []);
      setLatest(latR.data || { semester: null, window: null });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  // request for a given result entry (if any)
  const requestForEntry = (entryId) =>
    requests.find((r) => r.result_entry === entryId);

  // ── apply for revaluation ──
  const applyReval = async (entryId) => {
    setBusy(entryId);
    try {
      await API.post("/revaluations/apply/", { result_entry: entryId });
      await load();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not apply.");
    } finally {
      setBusy(null);
    }
  };

  // ── pay the revaluation fee, then confirm ──
  const payReval = async (req) => {
    if (!window.confirm(`Pay ₹${req.fee_amount} revaluation fee?`)) return;
    setBusy(req.result_entry);
    try {
      await API.post(`/fees/${req.fee}/pay/`, { amount: req.fee_amount });
      await API.post(`/revaluations/${req.id}/confirm-payment/`);
      await load();
    } catch (err) {
      alert(err.response?.data?.detail || "Payment failed.");
    } finally {
      setBusy(null);
    }
  };

  // ── cancel an unpaid request ──
  const cancelReval = async (req) => {
    if (!window.confirm("Cancel this revaluation request?")) return;
    setBusy(req.result_entry);
    try {
      await API.post(`/revaluations/${req.id}/cancel/`);
      await load();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not cancel.");
    } finally {
      setBusy(null);
    }
  };

  const statusChip = (status) => {
    const map = {
      pending_payment: { label: "Awaiting Payment", cls: "absent" },
      pending_review:  { label: "Under Review",     cls: "" },
      revised:         { label: "Revised",          cls: "present" },
      retained:        { label: "Retained",         cls: "" },
    };
    const s = map[status] || { label: status, cls: "" };
    return <span className={`att-chip ${s.cls}`}>{s.label}</span>;
  };

  // only the latest examination is shown for applying
  const latestSem = results.find((r) => r.semester === latest.semester);
  const win = latest.window || { is_open: false };
  // requests made earlier for other semesters stay visible as history
  const earlier = requests.filter((r) => r.semester !== latest.semester);

  const body = (
    <>
      <div className="att-header">
        <div>
          <h1 className="att-title">Revaluation</h1>
          <p className="att-subtitle">
            {latest.semester
              ? `Revaluation is available only for your latest examination — Semester ${latest.semester}.`
              : "Apply to re-evaluate a subject from your latest published results."}
          </p>
        </div>
      </div>

      {loading ? (
        <div className="att-card">
          <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
        </div>
      ) : !latestSem ? (
        <div className="att-card">
          <div className="att-state">
            <p>No published results yet. Revaluation opens once your results are released.</p>
          </div>
        </div>
      ) : (
        [latestSem].map((sem) => {
          return (
            <div className="att-card" key={sem.id} style={{ marginBottom: 16 }}>
              <div className="att-summary-row" style={{ alignItems: "center", marginBottom: 8 }}>
                <h2 className="att-card-title" style={{ margin: 0 }}>
                  Semester {sem.semester}
                </h2>
                <span className={`att-chip ${win.is_open ? "present" : "absent"}`}>
                  {win.is_open ? `Portal Open · ₹${win.fee_amount}` : "Portal Closed"}
                </span>
              </div>

              <div className="att-table-wrap">
                <table className="att-table">
                  <thead>
                    <tr>
                      <th>Subject</th>
                      <th className="center">Marks</th>
                      <th className="center">Result</th>
                      <th className="center">Revaluation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(sem.entries || []).map((en) => {
                      const req = requestForEntry(en.id);
                      return (
                        <tr key={en.id}>
                          <td className="att-td-name">{en.subject_name}</td>
                          <td className="center"><b>{en.marks_obtained ?? "—"}</b></td>
                          <td className="center">
                            {en.is_pass
                              ? <span style={{ color: "#16a34a", fontSize: 14 }}>Pass</span>
                              : <span style={{ color: "#dc2626", fontSize: 14 }}>Fail</span>}
                          </td>
                          <td className="center">
                            {req ? (
                              // already applied — show status / pay / cancel / outcome
                              <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "center" }}>
                                {statusChip(req.status)}
                                {req.status === "pending_payment" && (
                                  <>
                                    <button
                                      className="att-save-btn"
                                      style={{ padding: "4px 10px" }}
                                      onClick={() => payReval(req)}
                                      disabled={busy === en.id}
                                    >
                                      {busy === en.id ? "…" : `Pay ₹${req.fee_amount}`}
                                    </button>
                                    <button
                                      className="att-btn-outline"
                                      style={{ padding: "4px 10px" }}
                                      onClick={() => cancelReval(req)}
                                      disabled={busy === en.id}
                                    >
                                      Cancel
                                    </button>
                                  </>
                                )}
                                {req.status === "revised" && (
                                  <span style={{ fontSize: 14, color: "#16a34a" }}>
                                    → {req.revised_marks}
                                  </span>
                                )}
                              </div>
                            ) : win.is_open ? (
                              // no request yet, portal open — can apply
                              <button
                                className="att-btn-outline"
                                style={{ padding: "4px 10px" }}
                                onClick={() => applyReval(en.id)}
                                disabled={busy === en.id}
                              >
                                {busy === en.id ? "…" : "Apply"}
                              </button>
                            ) : (
                              <span style={{ color: "#85839A", fontSize: 14 }}>—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })
      )}

      {!loading && earlier.length > 0 && (
        <div className="att-card" style={{ marginTop: 16 }}>
          <h2 className="att-card-title">Earlier revaluation requests</h2>
          <div className="att-table-wrap">
            <table className="att-table">
              <thead>
                <tr>
                  <th>Subject</th>
                  <th className="center">Semester</th>
                  <th className="center">Status</th>
                  <th className="center">Revised marks</th>
                </tr>
              </thead>
              <tbody>
                {earlier.map((r) => (
                  <tr key={r.id}>
                    <td className="att-td-name">{r.subject_name}</td>
                    <td className="center">{r.semester}</td>
                    <td className="center">
                      <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "center" }}>
                        {statusChip(r.status)}
                        {/* an unpaid request from before the latest-exam rule can still be cancelled */}
                        {r.status === "pending_payment" && (
                          <button
                            className="att-btn-outline"
                            style={{ padding: "4px 10px" }}
                            onClick={() => cancelReval(r)}
                            disabled={busy === r.result_entry}
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="center">{r.status === "revised" ? r.revised_marks : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );

  if (embedded) return body;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="att-page">{body}</div>
          </div>
        </div>
      </div>
    </div>
  );
}