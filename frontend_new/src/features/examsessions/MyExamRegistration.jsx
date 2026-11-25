// WAVE 3 PART 2 - a student's exam registration for the current session:
// this semester's subjects (automatic) + the arrear subjects they tick, the
// fee, and paying it (the same fee payment the hall ticket uses).
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import API from "../../api";
import Shell from "../regulations/CbcsShell";
import { WINDOW_LABEL, dayLabel, errorText, longDate, plural, rupees } from "./examSessionUtil";
import "../../styles/ExamSessions.css";

const GRADE_NOTE = { AB: "Absent", RA: "Arrear" };

export default function MyExamRegistration() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const apply = (d) => {
    setData(d);
    setPicked(new Set((d.arrears || []).filter((a) => a.picked).map((a) => a.id)));
  };
  useEffect(() => {
    API.get("exam-registration/me/").then((r) => apply(r.data))
      .catch((err) => setError(errorText(err, "Couldn't load your exam registration.")));
  }, []);

  const send = async (submit) => {
    setBusy(true);
    setNotice(null);
    try {
      const r = await API.post("exam-registration/me/", { arrear_subjects: [...picked], submit });
      apply(r.data);
      setNotice({ tone: "ok", text: submit
        ? (r.data.fee && r.data.fee.status !== "paid" ? "Registration submitted. Pay the exam fee to complete it." : "Registration submitted and complete.")
        : "Saved. Submit it before registration closes." });
      return r.data;
    } catch (err) {
      setNotice({ tone: "bad", text: errorText(err, "Couldn't save your registration.") });
      return null;
    } finally {
      setBusy(false);
    }
  };

  const pay = async (fee) => {
    if (!window.confirm(`Pay the exam fee of ${rupees(fee.amount - fee.paid_amount)}?`)) return;
    setBusy(true);
    try {
      await API.post(`/fees/${fee.id}/pay/`, { amount: fee.amount - fee.paid_amount });
      const r = await API.get("exam-registration/me/");
      apply(r.data);
      setNotice({ tone: "ok", text: "Fee paid. Your registration is complete." });
    } catch (err) {
      setNotice({ tone: "bad", text: errorText(err, "Payment failed. Please try again.") });
    } finally {
      setBusy(false);
    }
  };

  const submitAndPay = async () => {
    const d = await send(true);
    if (d?.fee && d.fee.status !== "paid") await pay(d.fee);
  };

  if (error) return <Shell title="Exam registration"><p className="xs-note bad">{error}</p></Shell>;
  if (!data) return <Shell title="Exam registration"><p className="xs-muted">Loading…</p></Shell>;
  if (!data.session) {
    return <Shell title="Exam registration"><section className="kb-card"><p className="xs-muted">{data.detail || "There is no exam registration open right now."}</p></section></Shell>;
  }

  const s = data.session;
  const canEdit = ["open", "late"].includes(data.window) && !data.locked;
  const toggle = (id) => setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const nArrear = data.can_pick_arrears ? picked.size : data.arrears.length;
  const fp = data.fee_preview;
  const total = s.fee_required ? fp.regular_papers * fp.regular_fee + nArrear * fp.arrear_fee + (data.window === "late" || data.is_late ? s.late_fee : 0) : 0;
  const lateFee = data.window === "late" || data.is_late ? s.late_fee : 0;
  const nothing = !data.regular.length && !data.arrears.length;
  const submitted = data.status === "submitted";
  const unpaid = !!(data.fee && data.fee.status !== "paid");
  const savedPicks = new Set(data.arrears.filter((a) => a.picked).map((a) => a.id));
  const changed = data.can_pick_arrears && (savedPicks.size !== picked.size || [...picked].some((id) => !savedPicks.has(id)));
  // a ticked arrear on the same date + session as a regular paper (the exam cell fixes it before publishing)
  const regularSlot = {};
  data.regular.forEach((r) => { if (r.exam_date) regularSlot[`${r.exam_date}|${r.session}`] = r.code; });

  return (
    <Shell title={`Exam registration · ${s.name}`}
      subtitle={`${data.student.roll_number || ""}${data.student.semester ? ` · Semester ${data.student.semester}` : ""}${s.exam_start ? ` · exams ${longDate(s.exam_start)} – ${longDate(s.exam_end)}` : ""}`}>
      <div className="xs-page">
        <div className={`xs-note ${data.complete ? "ok" : data.window === "closed" ? "bad" : "vio"}`}>
          <span>
            {data.complete ? <b>Your registration is complete.</b>
              : data.window === "open" ? <><b>Registration closes on {longDate(s.reg_closes)}.</b>{s.late_until ? ` After that a late fee of ${rupees(s.late_fee)} applies until ${longDate(s.late_until)}.` : ""}</>
                : data.window === "late" ? <><b>Late registration</b> is open until {longDate(s.late_until)}, with a late fee of {rupees(s.late_fee)}.</>
                  : data.window === "not_open" ? <>Registration opens on <b>{longDate(s.reg_opens)}</b>.</>
                    : <>Registration is closed.{data.status === "none" ? " Please contact the exam cell." : ""}</>}
          </span>
          <span className={`xs-chip ${data.complete ? "ok" : data.status === "submitted" ? "warn" : "grey"}`}>
            {data.complete ? "Complete" : data.status === "submitted" ? "Submitted · fee not paid" : data.status === "draft" ? "Saved, not submitted" : WINDOW_LABEL[data.window].text}
          </span>
        </div>
        {notice && <p className={`xs-note ${notice.tone}`} role="status">{notice.text}</p>}

        {nothing ? (
          <section className="kb-card"><p className="xs-muted">You have nothing to write in this session.</p></section>
        ) : (
          <div className="xs-two">
            <div className="xs-main xs-stack">
              {data.writes_regular && (
                <section className="kb-card">
                  <div className="xs-head"><h2 className="xs-h2">Semester {data.student.semester} subjects</h2><span className="xs-muted">Added for you</span></div>
                  {!data.eligible && (
                    <p className="xs-note warn" style={{ marginBottom: 12 }}>
                      {data.eligibility_reason === "exam_fee_unpaid"
                        ? "Your semester exam fee is unpaid, so these papers will be withheld on the hall ticket until it is paid."
                        : `Your attendance is ${data.attendance_percent ?? "not recorded"}${data.attendance_percent != null ? "%" : ""}. These papers will be withheld on the hall ticket unless the college approves it. Arrear papers are not affected.`}
                    </p>
                  )}
                  <div className="xs-table-wrap">
                    <table className="xs-table">
                      <thead><tr><th>Subject</th><th>Credits</th><th>Exam</th><th>Attendance</th></tr></thead>
                      <tbody>
                        {data.regular.map((r) => (
                          <tr key={r.id}>
                            <td><b>{r.code}</b> {r.name}</td>
                            <td>{r.credits}</td>
                            <td>{r.exam_date ? `${dayLabel(r.exam_date)} · ${r.session}` : <span className="xs-muted">not set yet</span>}</td>
                            <td>{r.attendance != null ? `${r.attendance}%` : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              <section className="kb-card">
                <div className="xs-head">
                  <h2 className="xs-h2">Arrear subjects</h2>
                  <span className="xs-muted">{data.can_pick_arrears ? "Tick the ones you will write" : "The exam cell adds all of them"}</span>
                </div>
                {data.arrears.length === 0 ? <p className="xs-muted">You have no arrears.</p> : (
                  <fieldset className="xs-stack" style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend className="sr-only">Arrear subjects</legend>
                    {data.arrears.map((a) => {
                      const on = data.can_pick_arrears ? picked.has(a.id) : true;
                      return (
                        <label key={a.id} className={`xs-pick${on ? " on" : ""}`}>
                          <input type="checkbox" checked={on} disabled={!canEdit || !data.can_pick_arrears} onChange={() => toggle(a.id)} />
                          <span>
                            <span className="xs-row"><b>{a.code} {a.name}</b>
                              <span className={`xs-chip ${a.grade === "AB" ? "grey" : "bad"}`}>{a.grade}{GRADE_NOTE[a.grade] ? ` · ${GRADE_NOTE[a.grade]}` : ""}</span>
                              <span className="xs-muted">Sem {a.semester} · {a.credits} credits</span></span>
                            <span className="xs-muted">
                              Attempt {a.next_attempt}
                              {a.attempts.length ? ` · earlier: ${a.attempts.map((t) => `${t.exam_session || `attempt ${t.attempt}`} ${t.grade || ""}`.trim()).join(", ")}` : ""}
                              {a.exam_date ? ` · exam ${dayLabel(a.exam_date)} ${a.session}` : ""}
                              {a.internal_marks != null ? ` · internal ${a.internal_marks} kept` : ""}
                            </span>
                            {on && regularSlot[`${a.exam_date}|${a.session}`] && (
                              <span className="xs-chip warn" style={{ alignSelf: "flex-start", whiteSpace: "normal" }}>
                                Same date and session as {regularSlot[`${a.exam_date}|${a.session}`]} right now. The exam cell will move one of them before the timetable is published.
                              </span>
                            )}
                          </span>
                        </label>
                      );
                    })}
                  </fieldset>
                )}
                <p className="xs-muted xs-small" style={{ marginTop: 10 }}>Arrear papers don't need attendance. The timetable is checked so your arrear and regular papers never fall in the same session.</p>
              </section>
            </div>

            <aside className="kb-card xs-side xs-stack">
              <h2 className="xs-h2">Summary</h2>
              <div className="xs-sum"><span>Semester subjects</span><b>{fp.regular_papers}</b></div>
              <div className="xs-sum"><span>Arrear subjects</span><b>{nArrear}</b></div>
              {s.fee_required && (
                <>
                  {fp.regular_papers > 0 && <div className="xs-sum"><span>Exam fee · {plural(fp.regular_papers, "paper")}</span><b>{rupees(fp.regular_papers * fp.regular_fee)}</b></div>}
                  {nArrear > 0 && <div className="xs-sum"><span>Arrear fee · {plural(nArrear, "paper")}</span><b>{rupees(nArrear * fp.arrear_fee)}</b></div>}
                  {lateFee > 0 && <div className="xs-sum"><span>Late fee</span><b>{rupees(lateFee)}</b></div>}
                  <div className="xs-sum total"><span>Total</span><span>{rupees(data.fee && !canEdit ? data.fee.amount : total)}</span></div>
                </>
              )}
              {submitted && unpaid && (
                <button type="button" className="kb-btn kb-btn--primary xs-full" disabled={busy || changed} onClick={() => pay(data.fee)}>
                  Pay {rupees(data.fee.amount - data.fee.paid_amount)}
                </button>
              )}
              {canEdit && !submitted && (
                <>
                  <button type="button" className="kb-btn kb-btn--primary xs-full" disabled={busy} onClick={total > 0 ? submitAndPay : () => send(true)}>
                    {busy ? "Working…" : total > 0 ? "Submit and pay" : "Submit registration"}
                  </button>
                  <button type="button" className="kb-btn xs-full" disabled={busy} onClick={() => send(false)}>Save without submitting</button>
                </>
              )}
              {canEdit && submitted && (
                <button type="button" className={`kb-btn xs-full${changed ? " kb-btn--primary" : ""}`} disabled={busy || !changed} onClick={() => send(true)}>
                  {changed ? "Save the change in subjects" : "No changes to save"}
                </button>
              )}
              {submitted && unpaid && changed && <p className="xs-muted xs-small">Save the change first. The fee is updated to match.</p>}
              {data.locked && <p className="xs-muted xs-small">Your fee is paid, so the registration is final. Ask the exam cell for any change.</p>}
              <div className="xs-stack" style={{ gap: 4, background: "#F6F5FB", borderRadius: 10, padding: 12, fontSize: 13 }}>
                <b>What happens next</b>
                <span className="xs-muted">1 · Submit your subjects{data.status === "submitted" ? " (done)" : ""}</span>
                <span className="xs-muted">2 · Pay the exam fee{data.complete ? " (done)" : ""}</span>
                <span className="xs-muted">3 · Download your hall ticket once the exam cell releases it, in <Link to="/results?tab=ht">Results › Hall Ticket</Link></span>
              </div>
            </aside>
          </div>
        )}
      </div>
    </Shell>
  );
}
