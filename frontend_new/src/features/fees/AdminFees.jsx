// frontend/src/features/fees/AdminFees.jsx

import { useEffect, useState, useMemo, useRef } from "react";
import API from "../../api";
import "../../App.css";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import ImportExport from "../../components/ImportExport";
import PaymentSettings from "./PaymentSettings";   // PHASE 3: this college's Razorpay keys

// ================= DESIGN TOKENS (match App.css) =================
const BRAND = "#4B32C3";
const INK = "#17151F";
const MUTED = "#5D5A6B";
const LINE = "#E7E7EC";
const HAIR = "#ECECF0";

// The name printed on the receipt. Move this to a settings endpoint when one
// exists — a receipt with the wrong college name on it is worse than none.
const COLLEGE_NAME = "College of Engineering";
const COLLEGE_LINE2 = "Affiliated to Anna University";

// ================= HELPERS =================
const money = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");
const ini = (name) =>
  (name || "?").split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();

const owed = (f) => Number(f.amount || 0) - Number(f.paid_amount || 0);

const onDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
};

function getStatus(fee) {
  if (fee.status === "paid") return "paid";
  const today = new Date();
  const due = fee.due_date ? new Date(fee.due_date) : null;
  if (due && due < today) return "overdue";
  if (Number(fee.paid_amount || 0) > 0) return "partial";
  return "pending";
}

const STATUS_ORDER = ["overdue", "partial", "pending", "paid"];

const SM = {
  paid:    { label: "Paid",      bg: "#ecfdf3", color: "#15803d", bar: "#16a34a" },
  partial: { label: "Part paid", bg: "#eff6ff", color: "#4B32C3", bar: "#4B32C3" },
  pending: { label: "Pending",   bg: "#fff7ed", color: "#8A4B0A", bar: "#f59e0b" },
  overdue: { label: "Overdue",   bg: "#fef2f2", color: "#B42318", bar: "#ef4444" },
};

const AV_BG = { paid: "#ecfdf3", partial: "#eff6ff", pending: "#fff7ed", overdue: "#fef2f2" };
const AV_TC = { paid: "#15803d", partial: "#4B32C3", pending: "#8A4B0A", overdue: "#B42318" };
const GM = {
  overdue: { label: "Overdue",   rowBg: "#fef2f2", rowColor: "#B42318" },
  partial: { label: "Part paid", rowBg: "#eff6ff", rowColor: "#4B32C3" },
  pending: { label: "Pending",   rowBg: "#fff7ed", rowColor: "#8A4B0A" },
  paid:    { label: "Paid",      rowBg: "#ecfdf3", rowColor: "#15803d" },
};

const DEPT_COLORS = ["#4B32C3","#0ea5e9","#8b5cf6","#10b981","#f59e0b","#ef4444","#06b6d4","#84cc16"];

// Must match FeePayment.MODE_CHOICES on the server.
const PAY_MODES = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "card", label: "Card" },
  { value: "cheque", label: "Cheque" },
  { value: "dd", label: "Demand Draft" },
  { value: "netbanking", label: "Net banking" },
];

// Modes where a reference is what makes the payment traceable later. Cash has
// nothing to quote, so asking for one there is pure friction.
const MODE_NEEDS_REF = ["upi", "cheque", "dd", "netbanking", "card"];
const REF_LABEL = {
  upi: "UPI transaction ID",
  cheque: "Cheque number",
  dd: "DD number",
  netbanking: "Transaction reference",
  card: "Approval code",
};

const FEE_TYPE_SUGGESTIONS = [
  "Tuition", "Semester Exam Fee", "Van fees", "Lab fees", "Library", "Hostel",
];
const YEARS = [1, 2, 3, 4];

// ================= SHARED STYLES =================
const overlayStyle = {
  position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1100,
  display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
};
const modalStyle = {
  background: "#fff", borderRadius: 14, width: "100%", maxWidth: 480,
  overflow: "hidden", boxShadow: "0 20px 50px rgba(16,24,40,.18)",
};
const modalHeadStyle = {
  padding: "18px 20px 14px", borderBottom: `1px solid ${HAIR}`,
  display: "flex", justifyContent: "space-between", alignItems: "center",
};
const inputStyle = {
  width: "100%", padding: "10px 12px", borderRadius: 9,
  border: "1px solid #E7E7EC", fontSize: 15, color: INK, boxSizing: "border-box",
};
const labelStyle = {
  display: "block", fontSize: 13.5, fontWeight: 500, color: MUTED, marginBottom: 6,
};
const req = <span style={{ color: "#dc2626" }}> *</span>;
const closeBtnStyle = {
  width: 30, height: 30, borderRadius: "50%", border: "1px solid #E7E7EC",
  background: "#F6F6F8", cursor: "pointer", fontSize: 16, color: MUTED,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const primaryBtn = (enabled = true) => ({
  padding: "10px 18px", borderRadius: 9, border: "none",
  background: enabled ? BRAND : "#85839A", color: "#fff",
  fontSize: 15, fontWeight: 500, cursor: enabled ? "pointer" : "not-allowed",
});
const cancelBtn = {
  padding: "10px 18px", borderRadius: 9, border: "1px solid #E7E7EC",
  background: "#fff", fontSize: 15, fontWeight: 500, cursor: "pointer", color: "#5D5A6B",
};
const cardStyle = {
  background: "#fff", borderRadius: 14, border: `1px solid ${LINE}`,
  boxShadow: "0 1px 3px rgba(16,24,40,.04)",
};

// ================= RECEIPT =================
// Printed from a separate window rather than a hidden div. The app stylesheet
// fights print layout, and a popup starts clean with nothing inherited.
function printReceipt({ student, payment, fee }) {
  const w = window.open("", "_blank", "width=760,height=900");
  if (!w) {
    alert("Allow pop-ups for this site to print the receipt.");
    return;
  }

  w.document.write(`
<!doctype html>
<html><head><title>Receipt ${payment.receipt_no || ""}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         color: #17151F; margin: 0; padding: 34px 40px; font-size: 14px; }
  .head { text-align: center; border-bottom: 2px solid #17151F; padding-bottom: 14px; }
  .head h1 { margin: 0 0 3px; font-size: 19px; letter-spacing: .4px; }
  .head p { margin: 0; font-size: 13px; color: #5D5A6B; }
  .title { margin: 18px 0 4px; text-align: center; font-size: 15px;
           font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; }
  .meta { display: flex; justify-content: space-between; margin: 18px 0 6px; font-size: 13.5px; }
  .meta div { line-height: 1.9; }
  .k { color: #5D5A6B; display: inline-block; min-width: 108px; }
  table { width: 100%; border-collapse: collapse; margin-top: 16px; }
  th, td { border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }
  th { background: #ECECF0; font-size: 12.5px; text-transform: uppercase; letter-spacing: .5px; }
  .r { text-align: right; }
  .paid { margin-top: 18px; border: 2px solid #17151F; padding: 12px 14px;
          display: flex; justify-content: space-between; align-items: center; }
  .paid b { font-size: 17px; }
  .foot { margin-top: 46px; display: flex; justify-content: space-between;
          font-size: 13px; color: #5D5A6B; }
  .sign { border-top: 1px solid #85839A; padding-top: 5px; min-width: 190px; text-align: center; }
  .note { margin-top: 26px; font-size: 11.5px; color: #85839A; text-align: center;
          border-top: 1px dashed #cbd5e1; padding-top: 10px; }
  @media print { body { padding: 20px 26px; } }
</style></head>
<body>
  <div class="head">
    <h1>${COLLEGE_NAME}</h1>
    <p>${COLLEGE_LINE2}</p>
  </div>

  <div class="title">Fee Receipt</div>

  <div class="meta">
    <div>
      <span class="k">Receipt No</span><b>${payment.receipt_no || "—"}</b><br/>
      <span class="k">Date</span>${onDate(payment.paid_on)}<br/>
      <span class="k">Mode</span>${payment.mode_label || payment.mode || "—"}
      ${payment.reference ? `<br/><span class="k">Reference</span>${payment.reference}` : ""}
    </div>
    <div>
      <span class="k">Student</span><b>${student.username}</b><br/>
      <span class="k">Register No</span>${student.roll_number || "—"}<br/>
      <span class="k">Course</span>${student.course_name || "—"}<br/>
      <span class="k">Year / Sem</span>${student.year || "—"} / ${student.semester || "—"}
    </div>
  </div>

  <table>
    <thead>
      <tr><th>Particulars</th><th class="r">Amount</th>
          <th class="r">Paid to date</th><th class="r">Balance</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>${fee.term || "Fee"}</td>
        <td class="r">${money(fee.amount)}</td>
        <td class="r">${money(Number(fee.paid_amount || 0))}</td>
        <td class="r">${money(owed(fee))}</td>
      </tr>
    </tbody>
  </table>

  <div class="paid">
    <span>Amount received now</span>
    <b>${money(payment.amount)}</b>
  </div>

  <div class="foot">
    <div>
      Received by: ${payment.recorded_by || "—"}<br/>
      Printed: ${new Date().toLocaleString("en-IN")}
    </div>
    <div class="sign">Authorised Signatory</div>
  </div>

  <div class="note">
    This is a computer-generated receipt. Please retain it for your records.
    Cheques and demand drafts are subject to realisation.
  </div>

  <script>window.onload = function () { window.print(); };</script>
</body></html>`);
  w.document.close();
}

// ================= COLLECT: STUDENT SEARCH =================
function StudentSearch({ onPick, busy }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const run = async () => {
    const term = q.trim();
    if (!term) return;
    setSearching(true);
    try {
      const res = await API.get(`fee-ledger/?q=${encodeURIComponent(term)}`);
      setResults(res.data?.results || []);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div style={{ ...cardStyle, padding: 22 }}>
      <div style={{ fontSize: 16, fontWeight: 600, color: INK, marginBottom: 4 }}>
        Who is paying?
      </div>
      <div style={{ fontSize: 14, color: MUTED, marginBottom: 16 }}>
        Search by register number or name. Everything they owe appears in one place.
      </div>

      <div style={{ display: "flex", gap: 10, maxWidth: 560 }}>
        <input
          ref={inputRef}
          style={{ ...inputStyle, fontSize: 15 }}
          placeholder="e.g. 26ME001 or Aarthi"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        <button
          style={{ ...primaryBtn(!!q.trim() && !busy), whiteSpace: "nowrap" }}
          disabled={!q.trim() || busy || searching}
          onClick={run}
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </div>

      {results !== null && (
        <div style={{ marginTop: 18 }}>
          {results.length === 0 ? (
            <div style={{ fontSize: 14.5, color: MUTED }}>
              No student matches “{q}”. Check the register number.
            </div>
          ) : (
            <>
              <div style={{ fontSize: 13, color: MUTED, marginBottom: 8 }}>
                {results.length} match{results.length === 1 ? "" : "es"}
              </div>
              <div style={{ display: "grid", gap: 8 }}>
                {results.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => onPick(s.id)}
                    style={{
                      display: "flex", alignItems: "center", gap: 14, width: "100%",
                      padding: "12px 14px", borderRadius: 11, cursor: "pointer",
                      border: `1px solid ${LINE}`, background: "#fff", textAlign: "left",
                    }}
                  >
                    <span style={{
                      width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
                      background: s.outstanding > 0 ? "#fff7ed" : "#ecfdf3",
                      color: s.outstanding > 0 ? "#8A4B0A" : "#15803d",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 13, fontWeight: 600,
                    }}>
                      {ini(s.username)}
                    </span>
                    <span style={{ flex: 1 }}>
                      <span style={{ display: "block", fontSize: 15, fontWeight: 600, color: INK }}>
                        {s.username}
                      </span>
                      <span style={{ display: "block", fontSize: 13, color: MUTED, marginTop: 2 }}>
                        {s.roll_number || "—"} · {s.course_name || "—"} · Year {s.year} Sem {s.semester}
                      </span>
                    </span>
                    <span style={{ textAlign: "right" }}>
                      {s.outstanding > 0 ? (
                        <>
                          <span style={{ display: "block", fontSize: 15, fontWeight: 600, color: "#8A4B0A" }}>
                            {money(s.outstanding)}
                          </span>
                          <span style={{ fontSize: 12, color: MUTED }}>outstanding</span>
                        </>
                      ) : (
                        <span style={{
                          padding: "4px 12px", borderRadius: 999, fontSize: 13,
                          background: "#ecfdf3", color: "#15803d", fontWeight: 500,
                        }}>
                          All clear
                        </span>
                      )}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ================= COLLECT: ONE STUDENT'S LEDGER =================
function Ledger({ ledger, onBack, onCollect, busy }) {
  const { student, summary, fees } = ledger;
  const unpaid = fees.filter((f) => owed(f) > 0);
  const settled = fees.filter((f) => owed(f) <= 0);
  const [openHistory, setOpenHistory] = useState({});

  return (
    <>
      <button style={{ ...cancelBtn, marginBottom: 14 }} onClick={onBack}>
        ← Another student
      </button>

      {/* who is at the counter */}
      <div style={{ ...cardStyle, padding: 20, marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <div style={{
            width: 52, height: 52, borderRadius: "50%", background: "#EEEAFB",
            color: BRAND, display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 17, fontWeight: 600,
          }}>
            {ini(student.username)}
          </div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 600, color: INK }}>{student.username}</div>
            <div style={{ fontSize: 13.5, color: MUTED, marginTop: 3 }}>
              {student.roll_number || "—"} · {student.course_name || "—"} ·
              {" "}Year {student.year} Semester {student.semester}
              {student.batch_year ? ` · Batch ${student.batch_year}` : ""}
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", gap: 26, textAlign: "right", flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 12.5, color: MUTED }}>Billed</div>
              <div style={{ fontSize: 17, fontWeight: 600, color: INK }}>
                {money(summary.billed)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12.5, color: MUTED }}>Paid</div>
              <div style={{ fontSize: 17, fontWeight: 600, color: "#15803d" }}>
                {money(summary.collected)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12.5, color: MUTED }}>Outstanding</div>
              <div style={{
                fontSize: 17, fontWeight: 600,
                color: summary.outstanding > 0 ? "#8A4B0A" : "#15803d",
              }}>
                {money(summary.outstanding)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* what they owe — the reason they are standing there */}
      <div style={{ ...cardStyle, overflow: "hidden", marginBottom: 16 }}>
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${HAIR}` }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: INK }}>
            Outstanding dues
            {unpaid.length > 0 && (
              <span style={{ fontWeight: 400, color: MUTED, fontSize: 14 }}>
                {" "}— {unpaid.length} head{unpaid.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
        </div>

        {unpaid.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center" }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: "#15803d", marginBottom: 4 }}>
              Nothing outstanding
            </div>
            <div style={{ fontSize: 14, color: MUTED }}>
              This student has paid every fee raised against them.
            </div>
          </div>
        ) : (
          unpaid.map((f) => {
            const st = getStatus(f);
            const m = SM[st];
            return (
              <div key={f.id} style={{
                display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
                padding: "14px 18px", borderBottom: `1px solid ${HAIR}`,
              }}>
                <div style={{ flex: 1, minWidth: 180 }}>
                  <div style={{ fontSize: 15.5, fontWeight: 600, color: INK }}>{f.term}</div>
                  <div style={{ fontSize: 13, color: MUTED, marginTop: 3 }}>
                    Due {onDate(f.due_date)}
                    {Number(f.paid_amount) > 0 &&
                      ` · ${money(f.paid_amount)} of ${money(f.amount)} received`}
                  </div>
                </div>
                <span style={{
                  padding: "3px 11px", borderRadius: 999, fontSize: 12.5,
                  fontWeight: 500, background: m.bg, color: m.color,
                }}>
                  {m.label}
                </span>
                <div style={{ textAlign: "right", minWidth: 110 }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: "#8A4B0A" }}>
                    {money(owed(f))}
                  </div>
                  <div style={{ fontSize: 12, color: MUTED }}>to pay</div>
                </div>
                <button style={primaryBtn(!busy)} disabled={busy} onClick={() => onCollect(f)}>
                  Collect
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* already settled, with the receipts behind each one */}
      {settled.length > 0 && (
        <div style={{ ...cardStyle, overflow: "hidden" }}>
          <div style={{ padding: "14px 18px", borderBottom: `1px solid ${HAIR}` }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: INK }}>
              Already settled
              <span style={{ fontWeight: 400, color: MUTED, fontSize: 14 }}>
                {" "}— {settled.length}
              </span>
            </div>
          </div>
          {settled.map((f) => (
            <div key={f.id} style={{ borderBottom: `1px solid ${HAIR}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 18px" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 15, fontWeight: 500, color: INK }}>{f.term}</div>
                  <div style={{ fontSize: 13, color: MUTED, marginTop: 2 }}>
                    Paid {onDate(f.paid_date)}
                  </div>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "#15803d" }}>
                  {money(f.amount)}
                </div>
                <button
                  style={{ ...cancelBtn, padding: "6px 12px", fontSize: 13.5 }}
                  onClick={() => setOpenHistory((p) => ({ ...p, [f.id]: !p[f.id] }))}
                >
                  {openHistory[f.id] ? "Hide" : "Receipts"}
                </button>
              </div>

              {openHistory[f.id] && (
                <div style={{ padding: "0 18px 14px", background: "#fbfcfd" }}>
                  {(f.payments || []).length === 0 ? (
                    <div style={{ fontSize: 13.5, color: "#8A4B0A", padding: "10px 0" }}>
                      No payment record behind this fee. It was marked paid directly,
                      before payments were recorded properly — there is no receipt to
                      reprint.
                    </div>
                  ) : (
                    <table style={{ width: "100%", fontSize: 13.5, borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ color: MUTED, textAlign: "left" }}>
                          <th style={{ padding: "8px 0", fontWeight: 500 }}>Receipt</th>
                          <th style={{ padding: "8px 0", fontWeight: 500 }}>Date</th>
                          <th style={{ padding: "8px 0", fontWeight: 500 }}>Mode</th>
                          <th style={{ padding: "8px 0", fontWeight: 500 }}>Reference</th>
                          <th style={{ padding: "8px 0", fontWeight: 500, textAlign: "right" }}>Amount</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {f.payments.map((p) => (
                          <tr key={p.id} style={{ borderTop: `1px solid ${HAIR}` }}>
                            <td style={{ padding: "8px 0" }}><b>{p.receipt_no || "—"}</b></td>
                            <td style={{ padding: "8px 0" }}>{onDate(p.paid_on)}</td>
                            <td style={{ padding: "8px 0" }}>{p.mode_label}</td>
                            <td style={{ padding: "8px 0", color: MUTED }}>{p.reference || "—"}</td>
                            <td style={{ padding: "8px 0", textAlign: "right" }}>
                              <b>{money(p.amount)}</b>
                            </td>
                            <td style={{ padding: "8px 0", textAlign: "right" }}>
                              <button
                                style={{
                                  border: "none", background: "none", color: BRAND,
                                  cursor: "pointer", fontSize: 13.5, padding: 0,
                                }}
                                onClick={() => printReceipt({ student, payment: p, fee: f })}
                              >
                                Print
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

// ================= COLLECT MODAL =================
function CollectModal({ fee, student, onClose, onDone, busy }) {
  const left = owed(fee);
  const [form, setForm] = useState({
    amount: String(left), mode: "cash", reference: "", remarks: "",
  });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const amt = Number(form.amount || 0);
  const tooMuch = amt > left;
  const needsRef = MODE_NEEDS_REF.includes(form.mode);
  const missingRef = needsRef && !form.reference.trim();
  const ready = amt > 0 && !tooMuch && !missingRef;

  return (
    <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ ...modalStyle, maxWidth: 520 }}>
        <div style={modalHeadStyle}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: INK }}>Collect payment</div>
            <div style={{ fontSize: 13.5, color: MUTED, marginTop: 2 }}>
              {student.username} · {student.roll_number} · {fee.term}
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        <div style={{ padding: 20 }}>
          <div style={{
            background: "#F6F6F8", borderRadius: 10, padding: 14, marginBottom: 18,
            display: "flex", justifyContent: "space-between", fontSize: 14,
          }}>
            <div>
              <div style={{ color: MUTED, marginBottom: 3 }}>Fee</div>
              <b style={{ color: INK }}>{money(fee.amount)}</b>
            </div>
            <div>
              <div style={{ color: MUTED, marginBottom: 3 }}>Already paid</div>
              <b style={{ color: "#15803d" }}>{money(fee.paid_amount)}</b>
            </div>
            <div>
              <div style={{ color: MUTED, marginBottom: 3 }}>Balance</div>
              <b style={{ color: "#8A4B0A" }}>{money(left)}</b>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Amount received (₹){req}</label>
            <input
              style={{
                ...inputStyle, fontSize: 18, fontWeight: 600,
                borderColor: tooMuch ? "#fca5a5" : "#E7E7EC",
              }}
              type="number"
              autoFocus
              value={form.amount}
              onChange={(e) => set("amount", e.target.value)}
            />
            {tooMuch ? (
              <div style={{ fontSize: 13, color: "#B42318", marginTop: 6 }}>
                More than the {money(left)} outstanding.
              </div>
            ) : (
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                <button
                  style={{
                    ...cancelBtn, padding: "5px 12px", fontSize: 13,
                    borderColor: amt === left ? BRAND : "#E7E7EC",
                    color: amt === left ? BRAND : "#5D5A6B",
                  }}
                  onClick={() => set("amount", String(left))}
                >
                  Full {money(left)}
                </button>
                <button
                  style={{ ...cancelBtn, padding: "5px 12px", fontSize: 13 }}
                  onClick={() => set("amount", String(Math.round(left / 2)))}
                >
                  Half
                </button>
              </div>
            )}
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>How was it paid?{req}</label>
            <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
              {PAY_MODES.map((m) => (
                <button
                  key={m.value}
                  onClick={() => set("mode", m.value)}
                  style={{
                    padding: "7px 15px", borderRadius: 999, fontSize: 14,
                    cursor: "pointer", fontWeight: 500,
                    background: form.mode === m.value ? BRAND : "#fff",
                    color: form.mode === m.value ? "#fff" : "#5D5A6B",
                    border: `1px solid ${form.mode === m.value ? BRAND : "#E7E7EC"}`,
                  }}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* cash has no reference to quote, so it is never asked for */}
          {needsRef && (
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>{REF_LABEL[form.mode]}{req}</label>
              <input
                style={{ ...inputStyle, borderColor: missingRef ? "#fcd34d" : "#E7E7EC" }}
                placeholder={
                  form.mode === "cheque" ? "Cheque number and bank"
                    : form.mode === "upi" ? "12-digit UPI reference"
                    : "Reference number"
                }
                value={form.reference}
                onChange={(e) => set("reference", e.target.value)}
              />
              {missingRef && (
                <div style={{ fontSize: 13, color: "#8A4B0A", marginTop: 5 }}>
                  Needed so the payment can be traced back later.
                </div>
              )}
            </div>
          )}

          <div>
            <label style={labelStyle}>Remarks</label>
            <input
              style={inputStyle}
              placeholder="Optional"
              value={form.remarks}
              onChange={(e) => set("remarks", e.target.value)}
            />
          </div>
        </div>

        <div style={{ padding: "0 20px 20px", display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={cancelBtn}>Cancel</button>
          <button
            disabled={!ready || busy}
            onClick={() => onDone(fee, form)}
            style={primaryBtn(ready && !busy)}
          >
            {busy ? "Saving…" : `Receive ${money(amt)}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ================= AFTER PAYMENT =================
function DoneModal({ student, payment, fee, onClose }) {
  return (
    <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ ...modalStyle, maxWidth: 430 }}>
        <div style={{ padding: "28px 24px 20px", textAlign: "center" }}>
          <div style={{
            width: 54, height: 54, borderRadius: "50%", background: "#ecfdf3",
            color: "#15803d", fontSize: 26, margin: "0 auto 14px",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            ✓
          </div>
          <div style={{ fontSize: 20, fontWeight: 600, color: INK }}>
            {money(payment.amount)} received
          </div>
          <div style={{ fontSize: 14, color: MUTED, marginTop: 5 }}>
            {student.username} · {fee.term}
          </div>
          <div style={{
            marginTop: 16, padding: "10px 14px", borderRadius: 9,
            background: "#F6F6F8", fontSize: 14, display: "inline-block",
          }}>
            Receipt <b>{payment.receipt_no || "—"}</b> · {payment.mode_label}
          </div>
        </div>
        <div style={{ padding: "0 24px 24px", display: "flex", gap: 10, justifyContent: "center" }}>
          <button style={primaryBtn(true)} onClick={() => printReceipt({ student, payment, fee })}>
            Print receipt
          </button>
          <button style={cancelBtn} onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

// ================= ALL FEES: ROW + GROUPED LIST =================
function StuRow({ fee, onEdit, compact }) {
  const status = getStatus(fee);
  const m = SM[status];
  const pct = fee.amount > 0
    ? Math.round((Number(fee.paid_amount || 0) / Number(fee.amount)) * 100)
    : 0;
  const left = owed(fee);

  return (
    <div style={{
      display: "flex", alignItems: "center",
      padding: compact ? "9px 0" : "12px 18px",
      borderBottom: "1px solid #F6F6F8",
    }}>
      <div style={{
        width: 34, height: 34, borderRadius: "50%",
        background: AV_BG[status] || "#ECECF0", color: AV_TC[status] || "#5D5A6B",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 13, fontWeight: 600, flexShrink: 0, marginRight: 12,
      }}>
        {ini(fee.student_name || "?")}
      </div>
      <div style={{ minWidth: 110 }}>
        <div style={{ fontSize: 14.5, fontWeight: 500, color: INK }}>
          {fee.student_name || "Student"}
        </div>
        <div style={{ fontSize: 13, color: MUTED, marginTop: 1 }}>
          {fee.department || "—"}
        </div>
      </div>
      <div style={{ flex: 1, margin: "0 16px" }}>
        <div style={{ fontSize: 13, color: MUTED }}>{fee.term || "—"}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
          <div style={{ flex: 1, height: 5, borderRadius: 999, background: "#ECECF0" }}>
            <div style={{ height: 5, borderRadius: 999, background: m.bar, width: `${pct}%` }} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, minWidth: 28, color: m.bar }}>{pct}%</span>
        </div>
      </div>
      <div style={{ textAlign: "right", flexShrink: 0, minWidth: 128 }}>
        <div style={{ fontSize: 14.5, fontWeight: 600, color: INK }}>{money(fee.amount)}</div>
        {left > 0 && Number(fee.paid_amount || 0) > 0 && (
          <div style={{ fontSize: 12, color: "#4B32C3", fontWeight: 500, marginTop: 2 }}>
            {money(left)} still owed
          </div>
        )}
        <div style={{ fontSize: 12, color: "#85839A", marginTop: 2 }}>
          Due {onDate(fee.due_date)}
        </div>
        <span style={{
          display: "inline-block", padding: "3px 11px", borderRadius: 999,
          fontSize: 12.5, fontWeight: 500, marginTop: 4,
          background: m.bg, color: m.color,
        }}>
          {m.label}
        </span>
      </div>
      <button
        onClick={() => onEdit(fee)}
        style={{
          padding: "7px 14px", borderRadius: 9, border: "none", marginLeft: 12,
          background: "#EEEAFB", fontSize: 14, fontWeight: 500,
          cursor: "pointer", color: BRAND,
        }}
      >
        Edit
      </button>
    </div>
  );
}

function GroupedList({ fees, onEdit, compact = false }) {
  const sorted = [...fees].sort(
    (a, b) => STATUS_ORDER.indexOf(getStatus(a)) - STATUS_ORDER.indexOf(getStatus(b))
  );
  const groups = { overdue: [], partial: [], pending: [], paid: [] };
  sorted.forEach((f) => { const s = getStatus(f); if (groups[s]) groups[s].push(f); });

  if (!fees.length) return (
    <div style={{ padding: 30, textAlign: "center", color: "#85839A", fontSize: 15 }}>
      No fee matches these filters
    </div>
  );

  return (
    <>
      {STATUS_ORDER.map((g) => {
        if (!groups[g].length) return null;
        const m = GM[g];
        return (
          <div key={g}>
            <div style={{
              padding: "8px 18px", fontSize: 12, fontWeight: 600,
              background: m.rowBg, color: m.rowColor,
              borderBottom: `1px solid ${HAIR}`,
            }}>
              {m.label} — {groups[g].length} fee{groups[g].length > 1 ? "s" : ""}
            </div>
            {groups[g].map((fee) => (
              <StuRow key={fee.id} fee={fee} onEdit={onEdit} compact={compact} />
            ))}
          </div>
        );
      })}
    </>
  );
}

// ================= CSV =================
function downloadCSV(fees, filename) {
  const header = "Name,Department,Term,Total,Paid,Still owed,Due Date,Status\n";
  const rows = fees.map((f) => {
    const s = getStatus(f);
    return `"${f.student_name || ""}","${f.department || ""}","${f.term || ""}",${f.amount},${f.paid_amount || 0},${owed(f)},"${f.due_date || ""}","${SM[s]?.label || s}"`;
  });
  const blob = new Blob([header + rows.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ================= DEPT MODAL =================
function DeptModal({ dept, fees, onClose, onEdit }) {
  const [mf, setMf] = useState("all");

  const dFees = dept.filter ? fees.filter((f) => f.department === dept.filter) : fees;
  const filtered = mf === "all" ? dFees : dFees.filter((f) => getStatus(f) === mf);
  const counts = {
    overdue: dFees.filter((f) => getStatus(f) === "overdue").length,
    partial: dFees.filter((f) => getStatus(f) === "partial").length,
    pending: dFees.filter((f) => getStatus(f) === "pending").length,
    paid:    dFees.filter((f) => f.status === "paid").length,
  };
  const dlFees = mf === "all"
    ? dFees.filter((f) => getStatus(f) !== "paid")
    : filtered.filter((f) => getStatus(f) !== "paid");

  const pills = [
    { key: "all",     bg: "#EEEAFB", color: BRAND,     border: BRAND,     label: `All (${dFees.length})` },
    { key: "overdue", bg: "#fef2f2", color: "#B42318", border: "#dc2626", label: `Overdue (${counts.overdue})` },
    { key: "partial", bg: "#eff6ff", color: "#4B32C3", border: "#4B32C3", label: `Part paid (${counts.partial})` },
    { key: "pending", bg: "#fff7ed", color: "#8A4B0A", border: "#f59e0b", label: `Pending (${counts.pending})` },
    { key: "paid",    bg: "#ecfdf3", color: "#15803d", border: "#16a34a", label: `Paid (${counts.paid})` },
  ];

  const dlLabel = mf === "paid" ? null
    : mf === "all" ? "Download everything unpaid"
    : `Download ${GM[mf]?.label.toLowerCase() || mf} list`;

  return (
    <div style={{ ...overlayStyle, zIndex: 1000 }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ ...modalStyle, maxWidth: 660, maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "18px 20px 14px", borderBottom: `1px solid ${HAIR}`, flexShrink: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 17, fontWeight: 600, color: INK }}>{dept.name}</div>
              <div style={{ fontSize: 13.5, color: MUTED, marginTop: 2 }}>
                {dFees.length} fees · filter by status below
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {dlLabel && (
                <button
                  onClick={() => downloadCSV(dlFees, `${(dept.filter || "all").replace(/\s+/g, "-").toLowerCase()}-${mf}-fees.csv`)}
                  style={{ padding: "7px 14px", borderRadius: 9, border: "1px solid #DCD3FF",
                    background: "#EEEAFB", fontSize: 13, fontWeight: 500, cursor: "pointer", color: BRAND }}>
                  ⬇ {dlLabel}
                </button>
              )}
              <button onClick={onClose} style={closeBtnStyle}>✕</button>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {pills.map((p) => (
              <button key={p.key} onClick={() => setMf(p.key)}
                style={{ padding: "6px 14px", borderRadius: 999, fontSize: 13.5, fontWeight: 500,
                  cursor: "pointer", background: p.bg, color: p.color,
                  border: `1.5px solid ${mf === p.key ? p.border : "transparent"}` }}>
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ padding: "10px 18px", overflowY: "auto", flex: 1 }}>
          <GroupedList fees={filtered} onEdit={onEdit} compact />
        </div>
      </div>
    </div>
  );
}

// ================= RAISE FEES =================
function GenerateFeeForm({ courses, onClose, onGenerate, busy }) {
  const [form, setForm] = useState({
    course: "", year: "", fee_type: "", amount: "", due_date: "",
  });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const ready =
    form.course && form.year && form.fee_type && form.amount && form.due_date;

  return (
    <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={modalStyle}>
        <div style={modalHeadStyle}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: INK }}>Raise a fee</div>
            <div style={{ fontSize: 13.5, color: MUTED, marginTop: 2 }}>
              Applied to every student in the chosen course &amp; year
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        <div style={{ padding: 20 }}>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Course{req}</label>
            <select style={inputStyle} value={form.course} onChange={(e) => set("course", e.target.value)}>
              <option value="">— Select course —</option>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
            <div>
              <label style={labelStyle}>Year{req}</label>
              <select style={inputStyle} value={form.year} onChange={(e) => set("year", e.target.value)}>
                <option value="">— Year —</option>
                {YEARS.map((y) => <option key={y} value={y}>Year {y}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Fee type{req}</label>
              <input style={inputStyle} list="fee-type-list"
                placeholder="e.g. Semester Exam Fee - Sem 3"
                value={form.fee_type} onChange={(e) => set("fee_type", e.target.value)} />
              <datalist id="fee-type-list">
                {FEE_TYPE_SUGGESTIONS.map((t) => <option key={t} value={t} />)}
              </datalist>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={labelStyle}>Amount (₹){req}</label>
              <input style={inputStyle} type="number" placeholder="e.g. 25000"
                value={form.amount} onChange={(e) => set("amount", e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>Due date{req}</label>
              <input style={inputStyle} type="date" value={form.due_date}
                onChange={(e) => set("due_date", e.target.value)} />
            </div>
          </div>

          <div style={{ fontSize: 13, color: MUTED, marginTop: 14 }}>
            A student who already has a fee with this exact name is skipped, so
            running it twice creates no duplicates. Give each term its own name,
            such as “Semester Exam Fee - Sem 3”.
          </div>
        </div>

        <div style={{ padding: "0 20px 20px", display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={cancelBtn}>Cancel</button>
          <button disabled={!ready || busy} onClick={() => onGenerate(form)}
            style={primaryBtn(ready && !busy)}>
            {busy ? "Raising…" : "Raise fees"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ================= EDIT ONE FEE =================
function FeeForm({ fee, onClose, onSave, busy }) {
  const [form, setForm] = useState({
    term: fee?.term || "", amount: fee?.amount || "", due_date: fee?.due_date || "",
  });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const status = getStatus(fee);
  const ready = form.term && form.amount && form.due_date;
  const paid = Number(fee?.paid_amount || 0);
  const belowPaid = Number(form.amount || 0) < paid;

  return (
    <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={modalStyle}>
        <div style={modalHeadStyle}>
          <div style={{ fontSize: 16, fontWeight: 600, color: INK }}>Edit fee</div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        <div style={{ padding: 20 }}>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Student</label>
            <div style={{ ...inputStyle, background: "#F6F6F8", color: "#5D5A6B" }}>
              {fee?.student_name || "Student"}{fee?.department ? ` · ${fee.department}` : ""}
            </div>
          </div>

          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Fee type{req}</label>
            <input style={inputStyle} list="fee-type-list-edit" value={form.term}
              onChange={(e) => set("term", e.target.value)} />
            <datalist id="fee-type-list-edit">
              {FEE_TYPE_SUGGESTIONS.map((t) => <option key={t} value={t} />)}
            </datalist>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
            <div>
              <label style={labelStyle}>Amount (₹){req}</label>
              <input style={{ ...inputStyle, borderColor: belowPaid ? "#fca5a5" : "#E7E7EC" }}
                type="number" value={form.amount}
                onChange={(e) => set("amount", e.target.value)} />
              {belowPaid && (
                <div style={{ fontSize: 13, color: "#B42318", marginTop: 5 }}>
                  Less than the {money(paid)} already received.
                </div>
              )}
            </div>
            <div>
              <label style={labelStyle}>Due date{req}</label>
              <input style={inputStyle} type="date" value={form.due_date}
                onChange={(e) => set("due_date", e.target.value)} />
            </div>
          </div>

          {/* Status is derived from the payment rows on the server. It used to be
              an editable dropdown, so an admin could set "paid" with no payment
              behind it — and the next payment would overwrite it. */}
          <div style={{
            background: "#F6F6F8", borderRadius: 10, padding: 14,
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <div style={{ fontSize: 13.5, color: MUTED }}>
              Status follows the payments recorded
              <div style={{ fontSize: 13, marginTop: 3 }}>
                {money(fee?.paid_amount)} of {money(fee?.amount)} received
              </div>
            </div>
            <span style={{
              padding: "4px 12px", borderRadius: 999, fontSize: 13, fontWeight: 500,
              background: SM[status].bg, color: SM[status].color,
            }}>
              {SM[status].label}
            </span>
          </div>
        </div>

        <div style={{ padding: "0 20px 20px", display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={cancelBtn}>Cancel</button>
          <button disabled={!ready || belowPaid || busy} onClick={() => onSave(form, fee.id)}
            style={primaryBtn(ready && !belowPaid && !busy)}>
            {busy ? "Saving…" : "Update fee"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ================= MAIN =================
export default function AdminFees() {
  const [tab, setTab] = useState("collect");

  const [fees,    setFees]    = useState([]);
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy,    setBusy]    = useState(false);
  const [toast,   setToast]   = useState(null);

  // collect tab
  const [ledger,     setLedger]     = useState(null);
  const [collecting, setCollecting] = useState(null);
  const [done,       setDone]       = useState(null);

  // all-fees tab
  const [statusFilter, setStatusFilter] = useState("all");
  const [termFilter,   setTermFilter]   = useState("all");
  const [search,       setSearch]       = useState("");
  const [activeDept,   setActiveDept]   = useState(null);
  const [editingFee,   setEditingFee]   = useState(null);

  const [showGenerate, setShowGenerate] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => { fetchFees(); fetchCourses(); }, []);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const fetchFees = async () => {
    try {
      setLoading(true);
      const res = await API.get("fees/");
      const data = res.data?.results || res.data;
      setFees(Array.isArray(data) ? data : []);
    } catch {
      showToast("Could not load fees");
    } finally {
      setLoading(false);
    }
  };

  const fetchCourses = async () => {
    try {
      const res = await API.get("courses/");
      const data = res.data?.results || res.data;
      setCourses(Array.isArray(data) ? data : []);
    } catch { /* silent */ }
  };

  // ---------- collect ----------
  const openLedger = async (studentId) => {
    setBusy(true);
    try {
      const res = await API.get(`fee-ledger/?student=${studentId}`);
      setLedger(res.data);
    } catch (err) {
      showToast(err.response?.data?.detail || "Could not open that student");
    } finally {
      setBusy(false);
    }
  };

  const reloadLedger = async () => {
    if (ledger?.student?.id) {
      try {
        const res = await API.get(`fee-ledger/?student=${ledger.student.id}`);
        setLedger(res.data);
      } catch { /* the toast from the action already said enough */ }
    }
  };

  const handleCollect = async (fee, form) => {
    setBusy(true);
    try {
      const res = await API.post(`fees/${fee.id}/pay/`, {
        amount:    form.amount,
        mode:      form.mode,
        reference: form.reference,
        remarks:   form.remarks,
      });
      // the response is the refreshed fee. Its payments are newest-first, so
      // the first one is the payment just taken, carrying the receipt number
      // the server issued.
      const updated = res.data;
      const newest = (updated.payments || [])[0];

      setCollecting(null);
      setDone({
        student: ledger.student,
        fee: updated,
        payment: newest || {
          amount: form.amount,
          mode: form.mode,
          mode_label: PAY_MODES.find((m) => m.value === form.mode)?.label,
          receipt_no: "",
          paid_on: new Date().toISOString().slice(0, 10),
        },
      });
      await reloadLedger();
      fetchFees();
    } catch (err) {
      showToast(err.response?.data?.detail || "Could not record that payment");
    } finally {
      setBusy(false);
    }
  };

  // ---------- admin ----------
  const handleGenerate = async (form) => {
    setBusy(true);
    try {
      const res = await API.post("generate-fees/", {
        course: form.course, year: form.year, fee_type: form.fee_type,
        amount: form.amount, due_date: form.due_date,
      });
      showToast(res.data?.message || "Fees raised");
      setShowGenerate(false);
      fetchFees();
      reloadLedger();
    } catch (err) {
      showToast(err.response?.data?.detail || "Could not raise fees");
    } finally {
      setBusy(false);
    }
  };

  const handleSave = async (form, editId) => {
    setBusy(true);
    try {
      await API.patch(`fees/${editId}/`, {
        term: form.term, amount: form.amount, due_date: form.due_date,
      });
      showToast("Fee updated");
      setEditingFee(null);
      fetchFees();
      reloadLedger();
    } catch (err) {
      showToast(err.response?.data?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  const handleEdit = (fee) => { setEditingFee(fee); setActiveDept(null); };

  // ---------- computed ----------
  const enriched = useMemo(() =>
    fees.map((f) => ({
      ...f,
      department:   f.department || "Unknown",
      student_name: f.student_name || "Student",
    })), [fees]);

  const deptNames = useMemo(
    () => [...new Set(enriched.map((f) => f.department).filter(Boolean))].sort(),
    [enriched]);

  const depts = useMemo(() => [
    { name: "All departments", filter: null },
    ...deptNames.map((n) => ({ name: n, filter: n })),
  ], [deptNames]);

  const terms = useMemo(
    () => [...new Set(fees.map((f) => f.term).filter(Boolean))].sort(), [fees]);

  // Collected is money actually received. It used to count only fully paid fees
  // at face value, so a part payment showed as nothing collected.
  const stats = useMemo(() => {
    const total     = fees.reduce((s, f) => s + Number(f.amount || 0), 0);
    const collected = fees.reduce((s, f) => s + Number(f.paid_amount || 0), 0);
    const pending   = fees.filter((f) => getStatus(f) === "pending").reduce((s, f) => s + owed(f), 0);
    const partial   = fees.filter((f) => getStatus(f) === "partial").reduce((s, f) => s + owed(f), 0);
    const overdue   = fees.filter((f) => getStatus(f) === "overdue").reduce((s, f) => s + owed(f), 0);
    return {
      total, collected, pending, partial, overdue,
      outstanding: total - collected,
      paidCnt:    fees.filter((f) => f.status === "paid").length,
      pendingCnt: fees.filter((f) => getStatus(f) === "pending").length,
      partialCnt: fees.filter((f) => getStatus(f) === "partial").length,
      overdueCnt: fees.filter((f) => getStatus(f) === "overdue").length,
    };
  }, [fees]);

  const filtered = useMemo(() =>
    enriched.filter((f) => {
      if (statusFilter !== "all" && getStatus(f) !== statusFilter) return false;
      if (termFilter   !== "all" && f.term !== termFilter)         return false;
      if (search && !(f.student_name || "").toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    }), [enriched, statusFilter, termFilter, search]);

  const TABS = [
    { key: "collect", label: "Collect" },
    { key: "all", label: "All fees" },
    { key: "overview", label: "Overview" },
    { key: "online", label: "Online payments" },   // PHASE 3
  ];

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            {/* ── HEADER ── */}
            <div className="header-box" style={{
              display: "flex", justifyContent: "space-between",
              alignItems: "flex-start", gap: 16, flexWrap: "wrap",
            }}>
              <div>
                <h2>Fees</h2>
                <p>Take payments at the counter, and see where the money stands</p>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <ImportExport
                  align="right"
                  importer="fees"
                  label="fees"
                  matchLabel="roll number and term"
                  note="Raises new fees, or corrects the amount / due date of a fee already raised. Payments are never changed by an import."
                  onDone={fetchFees}
                />
                <button className="btn-primary" onClick={() => setShowGenerate(true)}>
                  + Raise a fee
                </button>
              </div>
            </div>

            {/* ── TABS ── */}
            <div style={{ display: "flex", gap: 6, borderBottom: `1px solid ${LINE}` }}>
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  style={{
                    padding: "10px 18px", border: "none", background: "none",
                    cursor: "pointer", fontSize: 15,
                    fontWeight: tab === t.key ? 600 : 500,
                    color: tab === t.key ? BRAND : MUTED,
                    borderBottom: `2px solid ${tab === t.key ? BRAND : "transparent"}`,
                    marginBottom: -1,
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* ================= COLLECT ================= */}
            {tab === "collect" && (
              ledger
                ? <Ledger
                    ledger={ledger}
                    busy={busy}
                    onBack={() => setLedger(null)}
                    onCollect={(fee) => setCollecting(fee)}
                  />
                : <StudentSearch onPick={openLedger} busy={busy} />
            )}

            {/* ================= ALL FEES ================= */}
            {tab === "all" && (
              <div style={{ ...cardStyle, overflow: "hidden" }}>
                <div style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "14px 18px", borderBottom: `1px solid ${HAIR}`,
                  flexWrap: "wrap", gap: 8,
                }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: INK }}>
                    Every fee raised
                    {loading && (
                      <span style={{ fontSize: 13, color: "#85839A", marginLeft: 8, fontWeight: 400 }}>
                        Loading…
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                      style={{ padding: "8px 12px", borderRadius: 9, border: "1px solid #E7E7EC", fontSize: 14, background: "#fff" }}>
                      <option value="all">Any status</option>
                      <option value="overdue">Overdue</option>
                      <option value="partial">Part paid</option>
                      <option value="pending">Pending</option>
                      <option value="paid">Paid</option>
                    </select>
                    <select value={termFilter} onChange={(e) => setTermFilter(e.target.value)}
                      style={{ padding: "8px 12px", borderRadius: 9, border: "1px solid #E7E7EC", fontSize: 14, background: "#fff" }}>
                      <option value="all">All fee types</option>
                      {terms.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <input placeholder="Search student…" value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      style={{ padding: "8px 12px", borderRadius: 9, border: "1px solid #E7E7EC", fontSize: 14, width: 170 }} />
                    <button style={{ ...cancelBtn, padding: "8px 14px", fontSize: 14 }}
                      onClick={() => downloadCSV(filtered, "fees.csv")}>
                      ⬇ CSV
                    </button>
                  </div>
                </div>
                <GroupedList fees={filtered} onEdit={handleEdit} />
              </div>
            )}

            {/* ================= ONLINE PAYMENTS (PHASE 3) ================= */}
            {tab === "online" && <PaymentSettings />}

            {/* ================= OVERVIEW ================= */}
            {tab === "overview" && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14 }}>
                  {[
                    { key: "all",     label: "Billed",      val: money(stats.total),     sub: `${fees.length} fees`,              color: INK,       accent: BRAND },
                    { key: "paid",    label: "Collected",   val: money(stats.collected), sub: `${stats.paidCnt} fully paid`,      color: "#15803d", accent: "#15803d" },
                    { key: "partial", label: "Part paid",   val: money(stats.partial),   sub: `${stats.partialCnt} owe a balance`, color: "#4B32C3", accent: "#4B32C3" },
                    { key: "pending", label: "Not started", val: money(stats.pending),   sub: `${stats.pendingCnt} students`,     color: "#8A4B0A", accent: "#f59e0b" },
                    { key: "overdue", label: "Overdue",     val: money(stats.overdue),   sub: `${stats.overdueCnt} students`,     color: "#dc2626", accent: "#dc2626" },
                  ].map((c) => (
                    <div key={c.key}
                      onClick={() => { setStatusFilter(c.key === "all" ? "all" : c.key); setTab("all"); }}
                      style={{ ...cardStyle, padding: "18px 18px 16px", cursor: "pointer",
                        borderBottom: `3px solid ${c.accent}` }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: MUTED, marginBottom: 6 }}>{c.label}</div>
                      <div style={{ fontSize: 24, fontWeight: 600, color: c.color }}>{c.val}</div>
                      <div style={{ fontSize: 13.5, marginTop: 6, fontWeight: 500, color: "#85839A" }}>{c.sub}</div>
                    </div>
                  ))}
                </div>

                <div style={{ fontSize: 13.5, color: MUTED, marginTop: -4 }}>
                  Collected is money actually received. The other three are what is
                  still owed — {money(stats.outstanding)} outstanding in total.
                </div>

                <div style={{ fontSize: 15, fontWeight: 600, color: INK, marginBottom: -4 }}>
                  By department{" "}
                  <span style={{ fontWeight: 400, color: MUTED, fontSize: 14 }}>
                    — click a card to see the students
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 14 }}>
                  {depts.map((d, i) => {
                    const dFees = d.filter ? enriched.filter((f) => f.department === d.filter) : enriched;
                    const total = dFees.reduce((s, f) => s + Number(f.amount || 0), 0);
                    const paid  = dFees.reduce((s, f) => s + Number(f.paid_amount || 0), 0);
                    const pct   = total > 0 ? Math.round((paid / total) * 100) : 0;
                    const c = {
                      overdue: dFees.filter((f) => getStatus(f) === "overdue").length,
                      partial: dFees.filter((f) => getStatus(f) === "partial").length,
                      pending: dFees.filter((f) => getStatus(f) === "pending").length,
                      paid:    dFees.filter((f) => f.status === "paid").length,
                    };
                    const accent = DEPT_COLORS[i % DEPT_COLORS.length];
                    return (
                      <div key={d.name} onClick={() => setActiveDept(d)}
                        style={{ ...cardStyle, borderTop: `3px solid ${accent}`, padding: 16, cursor: "pointer" }}>
                        <div style={{ fontSize: 14.5, fontWeight: 600, color: INK, marginBottom: 10 }}>{d.name}</div>
                        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 8 }}>
                          {c.overdue > 0 && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500, background: "#fef2f2", color: "#B42318" }}>{c.overdue} overdue</span>}
                          {c.partial > 0 && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500, background: "#eff6ff", color: "#4B32C3" }}>{c.partial} part paid</span>}
                          {c.pending > 0 && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500, background: "#fff7ed", color: "#8A4B0A" }}>{c.pending} pending</span>}
                          {c.paid    > 0 && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500, background: "#ecfdf3", color: "#15803d" }}>{c.paid} paid</span>}
                        </div>
                        <div style={{ fontSize: 13, color: MUTED, marginBottom: 6 }}>
                          {money(paid)} of {money(total)} · {pct}% collected
                        </div>
                        <div style={{ height: 5, borderRadius: 999, background: "#ECECF0" }}>
                          <div style={{ height: 5, borderRadius: 999, background: accent, width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* ── MODALS ── */}
            {collecting && ledger && (
              <CollectModal fee={collecting} student={ledger.student} busy={busy}
                onClose={() => setCollecting(null)} onDone={handleCollect} />
            )}

            {done && (
              <DoneModal student={done.student} payment={done.payment} fee={done.fee}
                onClose={() => setDone(null)} />
            )}

            {activeDept && (
              <DeptModal dept={activeDept} fees={enriched}
                onClose={() => setActiveDept(null)} onEdit={handleEdit} />
            )}

            {showGenerate && (
              <GenerateFeeForm courses={courses} busy={busy}
                onClose={() => setShowGenerate(false)} onGenerate={handleGenerate} />
            )}

            {editingFee && (
              <FeeForm fee={editingFee} busy={busy}
                onClose={() => setEditingFee(null)} onSave={handleSave} />
            )}

            {toast && (
              <div style={{
                position: "fixed", bottom: 24, right: 24, background: INK, color: "#fff",
                padding: "12px 20px", borderRadius: 12, fontSize: 14.5, zIndex: 9999,
                fontWeight: 500, boxShadow: "0 8px 25px rgba(0,0,0,.2)",
              }}>
                {toast}
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}