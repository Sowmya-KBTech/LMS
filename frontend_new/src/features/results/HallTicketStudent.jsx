import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";

export default function HallTicketStudent({ embedded = false }) {
  const [open, setOpen]       = useState(false);
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying]   = useState(false);

  const load = () => {
    setLoading(true);
    API.get("/hall-ticket/")
      .then((res) => setData(res.data))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  // pay the attendance fine via the existing fee pay endpoint
  const payFine = async () => {
    if (!data?.fine_id) return;
    if (!window.confirm(`Pay ₹${data.fine_amount} attendance fine to unlock your hall ticket?`)) return;
    setPaying(true);
    try {
      await API.post(`/fees/${data.fine_id}/pay/`, { amount: data.fine_amount });
      load(); // re-check eligibility — should now be unlocked
    } catch (err) {
      alert(err.response?.data?.detail || "Payment failed. Please try again.");
    } finally {
      setPaying(false);
    }
  };

  // WAVE 3 PART 2: pay the exam-registration fee from here too
  const payRegistrationFee = async () => {
    const fee = data?.registration_fee;
    if (!fee) return;
    const due = fee.amount - (fee.paid_amount || 0);
    if (!window.confirm(`Pay the exam fee of ₹${due}?`)) return;
    setPaying(true);
    try {
      await API.post(`/fees/${fee.id}/pay/`, { amount: due });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Payment failed. Please try again.");
    } finally {
      setPaying(false);
    }
  };

  const WITHHELD = {
    blocked: "WITHHELD · attendance",
    exam_fee_unpaid: "WITHHELD · exam fee",
    registration_fee_unpaid: "WITHHELD · fee",
  };
  const ddmmyyyy = (d) => (d ? String(d).slice(0, 10).split("-").reverse().join("-") : "-");

  // build + print the hall ticket PDF (browser print)
  const downloadTicket = () => {
    const sessionMode = !!data.registration_required;
    const rows = (data.subjects || []).map((s, i) => `
      <tr${s.withheld ? ' style="background:#f3f3f3"' : ""}>
        <td style="border:1px solid #ccc;padding:8px;text-align:center">${i + 1}</td>
        <td style="border:1px solid #ccc;padding:8px;text-align:center">${s.code || "-"}</td>
        <td style="border:1px solid #ccc;padding:8px">${s.name}</td>
        ${sessionMode ? `<td style="border:1px solid #ccc;padding:8px;text-align:center">${s.semester || "-"}</td>
        <td style="border:1px solid #ccc;padding:8px;text-align:center">${s.kind === "arrear" ? "<b>Arrear</b>" : "Regular"}</td>` : ""}
        <td style="border:1px solid #ccc;padding:8px;text-align:center">${ddmmyyyy(s.exam_date)}</td>
        <td style="border:1px solid #ccc;padding:8px;text-align:center">${s.withheld ? `<b>${WITHHELD[s.withheld] || "WITHHELD"}</b>` : s.session || "-"}</td>
        ${sessionMode ? `<td style="border:1px solid #ccc;padding:8px;text-align:center">${s.hall ? `${s.hall} · ${s.seat}` : "-"}</td>` : ""}
      </tr>`).join("");

    const html = `<html><head><title>Hall Ticket</title>
      <style>
        *{box-sizing:border-box;margin:0;padding:0}
        body{font-family:Arial,sans-serif;font-size:14px;padding:28px}
        .title{text-align:center;font-size:18px;font-weight:700}
        .sub{text-align:center;font-size:15px;font-weight:600;border:2px solid #000;padding:8px;margin:8px 0 16px}
        .head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}
        .info{font-size:15px;margin-bottom:6px}
        .photo{width:110px;height:130px;border:1px solid #000;display:flex;align-items:center;justify-content:center;font-size:12px;color:#888;text-align:center}
        table{width:100%;border-collapse:collapse;margin-top:10px}
        th{background:#ECECF0;border:1px solid #ccc;padding:8px;font-weight:700}
        .sign{margin-top:50px;display:flex;justify-content:space-between;font-size:14px}
        @media print{@page{size:A4;margin:16mm}}
      </style></head>
      <body>
        <div class="title">Learning Management System</div>
        <div class="sub">Examination Hall Ticket${data.session ? ` · ${data.session.name}` : ""}</div>

        <div class="head">
          <div>
            <p class="info"><b>Name:</b> ${data.student_name || ""}</p>
            <p class="info"><b>Register No:</b> ${data.roll_number || ""}</p>
          </div>
          <div class="photo">Affix<br/>Photo</div>
        </div>

        <table>
          <thead><tr>
            <th style="width:60px">Sl.No</th>
            <th style="width:110px">Code</th>
            <th>Subject</th>
            ${sessionMode ? '<th style="width:60px">Sem</th><th style="width:90px">Type</th>' : ""}
            <th style="width:120px">Date</th>
            <th style="width:90px">Session</th>
            ${sessionMode ? '<th style="width:110px">Hall · Seat</th>' : ""}
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>

        <div class="sign">
          <span>Student Signature</span>
          <span>Controller of Examinations</span>
        </div>
      </body></html>`;

    const win = window.open("", "_blank");
    win.document.write(html);
    win.document.close();
    win.print();
  };

  const body = (
    <>
      <div className="att-header">
        <div>
          <h1 className="att-title">Hall Ticket</h1>
          <p className="att-subtitle">Download your examination hall ticket</p>
        </div>
      </div>

      <div className="att-card">
        {loading ? (
          <div className="att-state"><div className="att-spinner" /><p>Checking eligibility…</p></div>
        ) : !data ? (
          <div className="att-state"><p>Unable to load hall ticket status.</p></div>
        ) : (
          data.registration_required ? (
            <SessionTicket data={data} paying={paying} onPay={payRegistrationFee} onPayFine={payFine}
              onDownload={downloadTicket} withheldText={WITHHELD} ddmmyyyy={ddmmyyyy} />
          ) : (
          <>
            {/* Status summary */}
            <div className="att-summary-row" style={{ alignItems: "center", marginBottom: 12 }}>
              <span className="att-chip">
                Attendance: {data.attendance_percent != null ? `${data.attendance_percent}%` : "No records"}
              </span>
              <span className="att-chip">Required: {data.threshold}%</span>
              <span className={`att-chip ${data.eligible ? "present" : "absent"}`}>
                {data.eligible
                  ? (data.reason === "override" ? "Eligible (approved by college)" : "Eligible")
                  : "Not eligible"}
              </span>
            </div>

            {/* Eligible → download */}
            {data.eligible ? (
              <>
                <p style={{ fontSize: 15, color: "#5D5A6B", marginBottom: 12 }}>
                  {data.reason === "fine_paid"
                    ? "Your attendance fine is paid. You can download your hall ticket."
                    : data.reason === "override"
                      ? "The college has approved your hall ticket for this semester. You can download your hall ticket."
                      : "You meet the attendance requirement. You can download your hall ticket."}
                </p>

                <div className="att-table-wrap" style={{ marginBottom: 12 }}>
                  <table className="att-table">
                    <thead>
                      <tr>
                        <th>Sl.No</th>
                        <th>Code</th>
                        <th>Subject</th>
                        <th className="center">Date</th>
                        <th className="center">Session</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.subjects || []).map((s, i) => (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <td>{s.code || "—"}</td>
                          <td className="att-td-name">{s.name}</td>
                          <td className="center">{s.exam_date ? String(s.exam_date).slice(0, 10).split("-").reverse().join("-") : "—"}</td>
                          <td className="center">{s.session || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <button className="att-save-btn" onClick={downloadTicket}>
                  Download Hall Ticket
                </button>
              </>
            ) : (
              // Not eligible → explain + pay if a fine exists
              <div className="att-state" style={{ color: "#8A4B0A" }}>
                <p style={{ marginBottom: 12 }}>
                  Your attendance is{" "}
                  <b>{data.attendance_percent != null ? `${data.attendance_percent}%` : "below requirement"}</b>
                  , under the required {data.threshold}%.
                </p>

                {data.fine_id ? (
                  <>
                    <p style={{ marginBottom: 12 }}>
                      Pay the attendance shortage fine of <b>₹{data.fine_amount}</b> to unlock your hall ticket.
                    </p>
                    <button className="att-save-btn" onClick={payFine} disabled={paying}>
                      {paying ? "Processing…" : `Pay ₹${data.fine_amount} Fine`}
                    </button>
                  </>
                ) : (
                  <p>
                    Please contact the examination office regarding your attendance shortage.
                  </p>
                )}
              </div>
            )}
          </>
          )
        )}
      </div>
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

// WAVE 3 PART 2 - the hall ticket of an exam session that uses registration:
// this semester's papers and arrear papers, each one either writable or withheld.
function SessionTicket({ data, paying, onPay, onPayFine, onDownload, withheldText, ddmmyyyy }) {
  const papers = data.subjects || [];
  const arrears = papers.filter((p) => p.kind === "arrear").length;
  const withheld = papers.filter((p) => p.withheld).length;
  const name = data.session?.name || "this exam session";

  if (data.reason === "not_registered") {
    return (
      <div className="att-state" style={{ color: "#5D5A6B" }}>
        <p style={{ marginBottom: 12 }}>You haven't registered for the <b>{name}</b> exams yet.</p>
        <Link className="att-save-btn" to="/exam-registration" style={{ display: "inline-block", textDecoration: "none" }}>Go to exam registration</Link>
      </div>
    );
  }

  return (
    <>
      <div className="att-summary-row" style={{ alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <span className="att-chip">{name}</span>
        <span className="att-chip">{papers.length} paper{papers.length === 1 ? "" : "s"}{arrears ? ` · ${arrears} arrear` : ""}</span>
        {withheld > 0 && <span className="att-chip absent">{withheld} withheld</span>}
        <span className={`att-chip ${data.eligible ? "present" : "absent"}`}>
          {data.eligible ? "Ready to download" : data.reason === "not_released" ? "Not released yet" : "Not ready"}
        </span>
      </div>

      {data.reason === "registration_fee_unpaid" && data.registration_fee && (
        <div style={{ background: "#FDF0E3", color: "#6B3307", borderRadius: 10, padding: "12px 14px", marginBottom: 12 }}>
          <p style={{ marginBottom: 10 }}>Your exam fee of <b>₹{Number(data.registration_fee.amount).toLocaleString("en-IN")}</b> is not paid, so every paper is withheld.</p>
          <button className="att-save-btn" onClick={onPay} disabled={paying}>{paying ? "Processing…" : `Pay ₹${(data.registration_fee.amount - (data.registration_fee.paid_amount || 0)).toLocaleString("en-IN")}`}</button>
        </div>
      )}
      {data.reason === "not_released" && (
        <p style={{ fontSize: 15, color: "#5D5A6B", marginBottom: 12 }}>
          You are registered. Your hall ticket can be downloaded once the exam cell releases it.
        </p>
      )}
      {data.eligible && data.regular_reason === "blocked" && withheld > 0 && (
        <div style={{ background: "#FDECEA", color: "#7F1D1D", borderRadius: 10, padding: "12px 14px", marginBottom: 12 }}>
          <p style={{ marginBottom: data.fine_id ? 10 : 0 }}>
            Your attendance is <b>{data.attendance_percent != null ? `${data.attendance_percent}%` : "not recorded"}</b>, under the required {data.threshold}%, so this semester's papers are withheld. Your arrear papers are not affected.
          </p>
          {data.fine_id && <button className="att-save-btn" onClick={onPayFine} disabled={paying}>{paying ? "Processing…" : `Pay ₹${data.fine_amount} fine`}</button>}
        </div>
      )}

      <div className="att-table-wrap" style={{ marginBottom: 12 }}>
        <table className="att-table">
          <thead>
            <tr>
              <th>Date</th>
              <th className="center">Session</th>
              <th>Code</th>
              <th>Subject</th>
              <th className="center">Sem</th>
              <th className="center">Type</th>
              <th className="center">Hall · Seat</th>
            </tr>
          </thead>
          <tbody>
            {papers.map((p) => (
              <tr key={p.subject_id} style={p.withheld ? { background: "#FDECEA" } : undefined}>
                <td style={{ whiteSpace: "nowrap" }}>{p.exam_date ? ddmmyyyy(p.exam_date) : "—"}</td>
                <td className="center">{p.withheld ? <b style={{ color: "#A3201A" }}>{withheldText[p.withheld] || "WITHHELD"}</b> : p.session || "—"}</td>
                <td>{p.code || "—"}</td>
                <td className="att-td-name">{p.name}</td>
                <td className="center">{p.semester}</td>
                <td className="center">{p.kind === "arrear" ? <b>Arrear</b> : "Regular"}</td>
                <td className="center">{p.hall ? <b>{p.hall} · {p.seat}</b> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.eligible && papers.some((p) => !p.withheld && !p.hall) && (
        <p style={{ fontSize: 13.5, color: "#5D5A6B", marginBottom: 12 }}>Hall and seat appear here once the exam cell gives seats, usually the day before each exam.</p>
      )}
      {data.eligible && <button className="att-save-btn" onClick={onDownload}>Download Hall Ticket</button>}
    </>
  );
}
