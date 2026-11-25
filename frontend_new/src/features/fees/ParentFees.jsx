import { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";
import { payFeeOnline } from "../../utils/razorpay";
import "../../styles/ParentModule.css";

export default function ParentFees() {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState([]);
  const [activeChild, setActiveChild] = useState(null);
  const [fees, setFees] = useState([]);
  const [loading, setLoading] = useState(true);

  // pay popup state
  const [payFee, setPayFee] = useState(null);
  const [payAmount, setPayAmount] = useState("");
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState("");

  // PHASE 3: online payment works only once this college has saved its own
  // Razorpay keys. null = still checking.
  const [onlineReady, setOnlineReady] = useState(null);

  useEffect(() => {
    API.get("/payments/status/")
      .then((res) => setOnlineReady(Boolean(res.data?.online_payments)))
      .catch(() => setOnlineReady(false));
  }, []);

  useEffect(() => {
    API.get("/parent/dashboard/")
      .then((res) => setChildren(res.data?.children || []))
      .catch((err) => console.log("children fetch error:", err));
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      // FeeViewSet already scopes to the parent's children.
      const res = await API.get("/fees/");
      setFees(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Parent fees fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 15000);
    return () => clearInterval(t);
  }, []);

  // filter by selected child (client-side; Fee has student + student_name)
  const visible = fees.filter((f) => {
    if (activeChild === null) return true;
    const child = children.find((c) => c.id === activeChild);
    return (f.student?.id || f.student) === activeChild || f.student_name === child?.username;
  });

  // ── amount helpers (fall back gracefully if backend fields are missing) ──
  const paidVal = (f) =>
    Number(f.paid_amount ?? (f.status === "paid" ? f.amount : 0));
  const pendingVal = (f) =>
    Number(f.pending_amount ?? (Number(f.amount || 0) - paidVal(f)));

  const totalFees = visible.reduce((s, f) => s + Number(f.amount || 0), 0);
  const paid = visible.reduce((s, f) => s + paidVal(f), 0);
  const pending = totalFees - paid;
  const nextDue = visible
    .filter((f) => f.status !== "paid" && f.due_date)
    .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))[0];

  const fmtDate = (iso) =>
    iso ? new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";
  const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN")}`;

  // ── status badge (now handles "partial") ──
  const statusBadge = (f) => {
    if (f.status === "paid")
      return <span className="pm-badge green">Paid</span>;
    if (f.status === "partial")
      return <span className="pm-badge" style={{ background: "#fef3c7", color: "#92400e" }}>Partial</span>;
    return <span className="pm-badge red">Pending</span>;
  };

  // ── open / submit payment ──
  const openPay = (f) => {
    setPayFee(f);
    setPayAmount(String(pendingVal(f)));
    setPayError("");
  };

  // Shared validation. Both buttons enforce the same rule, and the server
  // enforces it again from the payment rows - the browser's answer is a
  // convenience, never the authority.
  const validAmount = () => {
    const amt = Number(payAmount);
    const remaining = pendingVal(payFee);
    if (!amt || amt <= 0) { setPayError("Enter an amount greater than 0."); return null; }
    if (amt > remaining)  { setPayError(`You can pay at most ${money(remaining)}.`); return null; }
    return amt;
  };

  const submitPay = async () => {
    const amt = validAmount();
    if (amt === null) return;
    try {
      setPaying(true);
      setPayError("");
      await API.post(`/fees/${payFee.id}/pay/`, { amount: amt });
      setPayFee(null);
      await fetchData();
    } catch (err) {
      setPayError(err.response?.data?.detail || "Payment failed. Try again.");
    } finally {
      setPaying(false);
    }
  };

  // Online payment. Nothing is recorded here - the server verifies Razorpay's
  // signature before a payment row exists, so a closed popup or a failed card
  // leaves the fee untouched.
  const submitPayOnline = async () => {
    const amt = validAmount();
    if (amt === null) return;
    try {
      setPaying(true);
      setPayError("");
      await payFeeOnline({ feeId: payFee.id, amount: amt });
      setPayFee(null);
      await fetchData();
    } catch (err) {
      // Closing the popup is a choice, not an error - don't shout about it.
      if (err.code !== "dismissed") {
        setPayError(err.message || "Payment failed. Try again.");
      }
    } finally {
      setPaying(false);
    }
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="pm-page">

              <div className="pm-header">
                <h1>Fee Details</h1>
                <p>Payment history and pending dues</p>
              </div>

              <div className="pm-tabs">
                <div
                  className={`pm-tab ${activeChild === null ? "active" : ""}`}
                  onClick={() => setActiveChild(null)}
                >
                  All Children
                </div>
                {children.map((c) => (
                  <div
                    key={c.id}
                    className={`pm-tab ${activeChild === c.id ? "active" : ""}`}
                    onClick={() => setActiveChild(c.id)}
                  >
                    {c.username}
                  </div>
                ))}
              </div>

              {loading ? (
                <div className="pm-loading">Loading fees…</div>
              ) : (
                <div className="pm-two-col">
                  {/* ── Summary ── */}
                  <div className="pm-card">
                    <div className="pm-card-title">Fee Summary</div>
                    <div className="pm-fee-row">
                      <span className="pm-fee-label">Total fees</span>
                      <span className="pm-fee-val">{money(totalFees)}</span>
                    </div>
                    <div className="pm-fee-row">
                      <span className="pm-fee-label">Paid</span>
                      <span className="pm-fee-val green">{money(paid)}</span>
                    </div>
                    <div className="pm-fee-row">
                      <span className="pm-fee-label">Pending</span>
                      <span className="pm-fee-val red">{money(pending)}</span>
                    </div>
                    <div className="pm-fee-row">
                      <span className="pm-fee-label">Next due date</span>
                      <span className="pm-fee-val">{fmtDate(nextDue?.due_date)}</span>
                    </div>
                  </div>

                  {/* ── History ── */}
                  <div className="pm-card">
                    <div className="pm-card-title">Payment History</div>
                    {visible.length === 0 ? (
                      <div className="pm-empty">No fee records</div>
                    ) : (
                      <table className="pm-table">
                        <thead>
                          <tr>
                            <th>Child</th><th>Term</th><th>Total</th>
                            <th>Paid</th><th>Pending</th><th>Status</th><th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {visible.map((f) => (
                            <tr key={f.id}>
                              <td>{f.student_name}</td>
                              <td>{f.term}</td>
                              <td>{money(f.amount)}</td>
                              <td className="green">{money(paidVal(f))}</td>
                              <td className="red">{money(pendingVal(f))}</td>
                              <td>{statusBadge(f)}</td>
                              <td>
                                {f.status !== "paid" && (
                                  <button
                                    onClick={() => openPay(f)}
                                    style={{
                                      padding: "5px 14px", borderRadius: 8, border: "none",
                                      background: "#17151F", color: "#fff", fontSize: 13,
                                      fontWeight: 600, cursor: "pointer",
                                    }}
                                  >
                                    Pay
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── PAY POPUP ── */}
      {payFee && (
        <div
          style={{
            position: "fixed", inset: 0, background: "rgba(15,23,42,.5)",
            zIndex: 1000, display: "flex", alignItems: "center",
            justifyContent: "center", padding: 20,
          }}
          onClick={(e) => e.target === e.currentTarget && !paying && setPayFee(null)}
        >
          <div style={{ background: "#fff", borderRadius: 16, width: "100%", maxWidth: 380, padding: 22 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#17151F", marginBottom: 4 }}>
              Pay Fee
            </div>
            <div style={{ fontSize: 14, color: "#5D5A6B", marginBottom: 16 }}>
              {payFee.student_name} · {payFee.term}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 6 }}>
              <span style={{ color: "#5D5A6B" }}>Total</span>
              <span style={{ fontWeight: 600 }}>{money(payFee.amount)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 16 }}>
              <span style={{ color: "#5D5A6B" }}>Remaining</span>
              <span style={{ fontWeight: 700, color: "#B42318" }}>{money(pendingVal(payFee))}</span>
            </div>

            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#5D5A6B", marginBottom: 5 }}>
              Amount to pay (₹)
            </label>
            <input
              type="number"
              value={payAmount}
              onChange={(e) => setPayAmount(e.target.value)}
              style={{
                width: "100%", padding: "9px 12px", borderRadius: 8,
                border: "1px solid #E7E7EC", fontSize: 15, boxSizing: "border-box",
              }}
            />

            {payError && (
              <div style={{ color: "#B42318", fontSize: 13, marginTop: 8 }}>{payError}</div>
            )}

            {onlineReady === false && (
              <div style={{
                marginTop: 12, padding: "9px 12px", borderRadius: 8,
                background: "#fff7ed", border: "1px solid #fed7aa",
                color: "#8A4B0A", fontSize: 13.5, lineHeight: 1.45,
              }}>
                Online payment isn't set up for this college yet. Please contact the college office.
              </div>
            )}

            <div style={{
              display: "flex", gap: 10, justifyContent: "flex-end",
              marginTop: 18, flexWrap: "wrap",
            }}>
              <button
                onClick={() => setPayFee(null)}
                disabled={paying}
                style={{
                  padding: "9px 16px", borderRadius: 10, border: "1px solid #E7E7EC",
                  background: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer", color: "#5D5A6B",
                }}
              >
                Cancel
              </button>

              {/* Writes a payment row without money moving - for a payment
                  already made at the counter. */}
              <button
                onClick={submitPay}
                disabled={paying}
                style={{
                  padding: "9px 18px", borderRadius: 10, border: "1px solid #17151F",
                  background: "#fff", color: "#17151F", fontSize: 14, fontWeight: 600,
                  cursor: paying ? "default" : "pointer", opacity: paying ? 0.7 : 1,
                }}
              >
                {paying ? "Please wait…" : "Record Payment"}
              </button>

              {/* Real money through Razorpay. */}
              <button
                onClick={submitPayOnline}
                disabled={paying || !onlineReady}
                title={onlineReady === false ? "Online payment isn't set up for this college yet" : undefined}
                style={{
                  padding: "9px 18px", borderRadius: 10, border: "none",
                  background: "#4B32C3", color: "#fff", fontSize: 14, fontWeight: 600,
                  cursor: paying || !onlineReady ? "default" : "pointer",
                  opacity: paying || !onlineReady ? 0.5 : 1,
                }}
              >
                {paying ? "Please wait…" : "Pay Online"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}