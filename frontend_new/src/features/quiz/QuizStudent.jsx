// WAVE 3 PART 3 - Online tests (the quiz, upgraded), student side.
// The subject's "Online tests" tab: open / coming up / finished, the
// instructions, then the full-page test: timer, autosave, question palette,
// mark for review, and submit. When the time is up the saved answers are submitted.
import { useCallback, useEffect, useRef, useState } from "react";
import API from "../../api";
import "../../styles/Quiz.css";

const errText = (err, fb) => (typeof err?.response?.data?.detail === "string" ? err.response.data.detail : fb);
const when = (iso) => (iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
const KIND_HINT = { mcq: "Choose one answer", multi: "Choose all that apply", tf: "True or false", short: "Write a short answer", long: "Write your answer" };

export default function QuizStudent({ teachingId }) {
  const [tests, setTests] = useState(null);
  const [pick, setPick] = useState(null);
  const [agree, setAgree] = useState(false);
  const [sitting, setSitting] = useState(null);      // the attempt being written
  const [result, setResult] = useState(null);
  const [review, setReview] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => API.get("online-tests/tests/", { params: { teaching_assignment: teachingId } })
    .then((r) => setTests(r.data)).catch(() => setTests([])), [teachingId]);
  useEffect(() => { if (teachingId) load(); }, [teachingId, load]);

  const start = async (t) => {
    setMsg(null);
    try {
      const r = await API.post(`online-tests/tests/${t.id}/start/`);
      setSitting(r.data);
    } catch (err) { setMsg({ tone: "bad", text: errText(err, "Couldn't start the test.") }); load(); }
  };
  const openReview = (t) => API.get(`online-tests/attempts/${t.attempt.id}/review/`).then((r) => setReview(r.data))
    .catch((err) => setMsg({ tone: "bad", text: errText(err, "Answers aren't shown yet.") }));

  if (sitting) {
    return <TestScreen sitting={sitting} onDone={(res) => { setSitting(null); setPick(null); setAgree(false); setResult(res); load(); }} />;
  }

  const groups = { open: [], upcoming: [], finished: [] };
  (tests || []).forEach((t) => {
    if (t.attempt?.status === "submitted") groups.finished.push(t);
    else if (t.state === "open" || t.attempt?.status === "in_progress") groups.open.push(t);
    else if (t.state === "upcoming") groups.upcoming.push(t);
    else groups.finished.push(t);
  });
  const sel = (tests || []).find((t) => t.id === pick);

  const card = (t) => {
    const a = t.attempt;
    let chip = null;
    let btn = null;
    if (a?.status === "in_progress") { chip = <span className="ot-chip warn">Started · carry on</span>; btn = <button type="button" className="ot-btn pri" onClick={() => start(t)}>Continue</button>; }
    else if (a?.status === "submitted") {
      chip = a.being_marked ? <span className="ot-chip warn">Being marked</span> : <span className={`ot-chip ${a.score * 2 >= t.total_marks ? "ok" : "warn"}`}>{a.score} / {t.total_marks}</span>;
      btn = a.can_review ? <button type="button" className="ot-btn" onClick={() => openReview(t)}>See answers</button> : null;
    } else if (t.state === "open") { chip = <span className="ot-chip ok">Open{t.closes_at ? ` until ${when(t.closes_at)}` : ""}</span>; btn = <button type="button" className="ot-btn pri" onClick={() => { setPick(t.id); setAgree(false); }}>Open</button>; }
    else if (t.state === "upcoming") { chip = <span className="ot-chip grey">Opens {when(t.opens_at)}</span>; btn = <button type="button" className="ot-btn" disabled>Not open yet</button>; }
    else chip = <span className="ot-chip grey">Missed · closed</span>;
    return (
      <div key={t.id} className={`ot-test${pick === t.id ? " sel" : ""}`}>
        <div className="ot-stack" style={{ gap: 6 }}>
          <div className="ot-row"><b style={{ fontSize: 16 }}>{t.title}</b>{chip}</div>
          <div className="ot-stats"><span><b>{t.question_count}</b> questions</span><span><b>{t.total_marks}</b> marks</span><span><b>{t.duration}</b> min</span>
            {a?.submitted_at && <span>Submitted <b>{when(a.submitted_at)}</b></span>}</div>
        </div>
        {btn || <span />}
      </div>
    );
  };

  return (
    <div className="ot-wrap">
      {result && (
        <p className="ot-note ok" role="status">
          Test submitted. {result.being_marked ? "Your teacher will mark the written answers; the score appears here after that." : `You scored ${result.score} out of ${result.total_marks}.`}
        </p>
      )}
      {msg && <p className={`ot-note ${msg.tone}`} role="status">{msg.text}</p>}
      <div className="ot-two">
        <section className="ot-card ot-main ot-stack">
          <h2 className="ot-h2">Online tests</h2>
          {tests === null ? <p className="ot-muted">Loading…</p> : tests.length === 0 ? <p className="ot-muted">No tests in this subject yet.</p> : (
            <>
              {groups.open.length > 0 && <p className="ot-group">OPEN NOW</p>}{groups.open.map(card)}
              {groups.upcoming.length > 0 && <p className="ot-group">COMING UP</p>}{groups.upcoming.map(card)}
              {groups.finished.length > 0 && <p className="ot-group">FINISHED</p>}{groups.finished.map(card)}
            </>
          )}
        </section>
        {sel && sel.state === "open" && !sel.attempt && (
          <aside className="ot-card ot-side ot-stack">
            <span className="ot-chip ok" style={{ alignSelf: "flex-start" }}>Open{sel.closes_at ? ` until ${when(sel.closes_at)}` : ""}</span>
            <h2 className="ot-h2" style={{ fontSize: 20 }}>{sel.title}</h2>
            <div className="ot-grid3">
              {[["Time", `${sel.duration} min`], ["Questions", sel.question_count], ["Marks", sel.total_marks]].map(([k, v]) => (
                <div key={k} style={{ background: "#F4F4F7", borderRadius: 12, padding: 12 }}><span className="ot-muted ot-small">{k}</span><div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></div>
              ))}
            </div>
            <b>Before you start</b>
            <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6, lineHeight: 1.5 }}>
              <li>One sitting. The clock keeps running if you close the page.</li>
              <li>Answers save as you go. If the connection drops, open the test again and carry on.</li>
              <li>Leaving the test tab is recorded and your teacher sees it.</li>
              <li>When the time is up, the test is submitted with what you saved.</li>
            </ol>
            <label className="ot-check"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> <span>I have read the instructions.</span></label>
            <button type="button" className="ot-btn pri" disabled={!agree} onClick={() => start(sel)}>Start the test</button>
          </aside>
        )}
      </div>
      {review && <Review data={review} onClose={() => setReview(null)} />}
    </div>
  );
}

// ============================================================ the test itself
function TestScreen({ sitting, onDone }) {
  const qs = sitting.questions;
  const [i, setI] = useState(0);
  const [answers, setAnswers] = useState(sitting.answers || {});
  const [flagged, setFlagged] = useState(sitting.flagged || []);
  const [saved, setSaved] = useState(null);         // time of the last good save
  const [saveErr, setSaveErr] = useState("");
  const [left, setLeft] = useState(sitting.tab_leaves || 0);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  // the server's clock decides; this is the difference between it and this computer
  const [skew] = useState(() => new Date(sitting.now).getTime() - Date.now());
  const endsAt = new Date(sitting.ends_at).getTime();
  const [now, setNow] = useState(() => Date.now() + skew);
  const pending = useRef({});
  const leftPending = useRef(0);
  const finished = useRef(false);
  const flaggedRef = useRef(flagged);
  const answersRef = useRef(answers);
  useEffect(() => { flaggedRef.current = flagged; }, [flagged]);
  useEffect(() => { answersRef.current = answers; }, [answers]);

  const flush = useCallback(async () => {
    const body = { answers: pending.current, flagged: flaggedRef.current, left: leftPending.current };
    pending.current = {};
    leftPending.current = 0;
    try {
      const r = await API.post(`online-tests/attempts/${sitting.id}/save/`, body);
      setSaved(new Date()); setSaveErr(""); setLeft(r.data.tab_leaves);
    } catch (err) {
      if (err?.response?.data?.status === "submitted") { finished.current = true; onDone({ being_marked: true, auto: true }); return; }
      pending.current = { ...body.answers, ...pending.current };
      leftPending.current += body.left || 0;
      setSaveErr("Not saved yet. Check your connection; we'll keep trying.");
    }
  }, [sitting.id, onDone]);
  const submit = useCallback(async (auto) => {
    if (finished.current) return;
    finished.current = true;
    setBusy(true);
    try {
      const r = await API.post(`online-tests/attempts/${sitting.id}/submit/`, { answers: { ...answersRef.current } });
      onDone({ ...r.data, auto });
    } catch (err) {
      if (err?.response?.status === 400) onDone({ being_marked: true, auto });
      else { finished.current = false; setBusy(false); setSaveErr(errText(err, "Couldn't submit. Check your connection and try again.")); }
    }
  }, [sitting.id, onDone]);
  // clock + autosave every 20 s
  useEffect(() => {
    const t = setInterval(() => {
      const n = Date.now() + skew;
      setNow(n);
      if (n >= endsAt && !finished.current) submit(true);      // time is up
    }, 1000);
    const s = setInterval(() => { if (Object.keys(pending.current).length || leftPending.current) flush(); }, 20000);
    return () => { clearInterval(t); clearInterval(s); };
  }, [flush, skew, endsAt, submit]);
  const remaining = Math.max(0, Math.floor((endsAt - now) / 1000));

  // leaving the tab is recorded
  useEffect(() => {
    const onVis = () => { if (document.visibilityState === "hidden" && !finished.current) { leftPending.current += 1; flush(); } };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [flush]);

  const q = qs[i];
  const key = String(q.id);
  const setAns = (v) => {
    setAnswers((p) => { const n = { ...p }; if (v === null || (Array.isArray(v) && !v.length) || v === "") delete n[key]; else n[key] = v; return n; });
    pending.current[key] = v;
    if (q.kind !== "short" && q.kind !== "long") flush();
  };
  const isDone = (x) => answers[String(x.id)] !== undefined;
  const toggleFlag = () => {
    const n = flagged.includes(q.id) ? flagged.filter((x) => x !== q.id) : [...flagged, q.id];
    setFlagged(n); flaggedRef.current = n; flush();
  };
  const go = (n) => { if (Object.keys(pending.current).length) flush(); setI(n); };
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");
  const answeredCount = qs.filter(isDone).length;
  const val = answers[key];

  return (
    <div className="ot-screen" role="dialog" aria-modal="true" aria-label={sitting.test.title}>
      <div className="ot-screen-top">
        <div><b>{sitting.test.title}</b><div className="ot-muted ot-small">{sitting.test.subject} · {sitting.test.total_marks} marks</div></div>
        <div className="ot-row">
          {saveErr ? <span className="ot-chip bad">{saveErr}</span> : saved ? <span className="ot-chip ok">Saved {saved.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> : null}
          <div className={`ot-timer${remaining < 300 ? " low" : ""}`} role="timer" aria-label={`Time left ${mm} minutes ${ss} seconds`}>{mm}:{ss} <span style={{ fontSize: 12, fontWeight: 500 }}>left</span></div>
        </div>
      </div>
      <div className="ot-screen-body">
        <section className="ot-card" style={{ flex: "999 1 560px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="ot-between"><span className="ot-chip vio">{q.section}</span><span className="ot-muted">Question {i + 1} of {qs.length} · {q.marks} mark{q.marks === 1 ? "" : "s"}</span></div>
          <p className="ot-q">{q.text}</p>
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 10 }}>
            <legend className="ot-muted ot-small" style={{ marginBottom: 8 }}>{KIND_HINT[q.kind]}</legend>
            {q.kind === "mcq" && q.options.map((o) => (
              <label key={o.i} className={`ot-ans${val === o.i ? " on" : ""}`}><input type="radio" name={`q${q.id}`} checked={val === o.i} onChange={() => setAns(o.i)} /> <span>{o.t}</span></label>
            ))}
            {q.kind === "multi" && q.options.map((o) => {
              const cur = Array.isArray(val) ? val : [];
              const on = cur.includes(o.i);
              return <label key={o.i} className={`ot-ans${on ? " on" : ""}`}><input type="checkbox" checked={on} onChange={() => setAns(on ? cur.filter((x) => x !== o.i) : [...cur, o.i].sort())} /> <span>{o.t}</span></label>;
            })}
            {q.kind === "tf" && [[true, "True"], [false, "False"]].map(([v, l]) => (
              <label key={l} className={`ot-ans${val === v ? " on" : ""}`}><input type="radio" name={`q${q.id}`} checked={val === v} onChange={() => setAns(v)} /> <span>{l}</span></label>
            ))}
            {(q.kind === "short" || q.kind === "long") && (
              <label className="ot-field"><span className="ot-sr">Your answer</span>
                <textarea style={{ minHeight: q.kind === "long" ? 260 : 120 }} value={val || ""} onChange={(e) => setAns(e.target.value)} onBlur={() => flush()} /></label>
            )}
          </fieldset>
          <div className="ot-between" style={{ borderTop: "1px solid #F0F0F4", paddingTop: 14 }}>
            <div className="ot-row">
              <button type="button" className="ot-btn" disabled={i === 0} onClick={() => go(i - 1)}>Previous</button>
              <button type="button" className="ot-btn" disabled={val === undefined} onClick={() => setAns(null)}>Clear answer</button>
              <button type="button" className="ot-btn" aria-pressed={flagged.includes(q.id)} onClick={toggleFlag}>{flagged.includes(q.id) ? "Unmark review" : "Mark for review"}</button>
            </div>
            {i < qs.length - 1 ? <button type="button" className="ot-btn pri" onClick={() => go(i + 1)}>Next</button>
              : <button type="button" className="ot-btn pri" onClick={() => setConfirm(true)}>Finish</button>}
          </div>
        </section>

        <aside className="ot-card" style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: 14 }}>
          <h2 className="ot-h3">Questions</h2>
          <div className="ot-pal">
            {qs.map((x, n) => {
              const cls = [isDone(x) ? "done" : "", flagged.includes(x.id) ? "rev" : "", n === i ? "cur" : ""].join(" ").trim();
              return <button key={x.id} type="button" className={cls} onClick={() => go(n)}
                aria-label={`Question ${n + 1}${isDone(x) ? ", answered" : ", not answered"}${flagged.includes(x.id) ? ", marked for review" : ""}`}>{n + 1}</button>;
            })}
          </div>
          <div className="ot-muted ot-small ot-row" style={{ gap: 12 }}>
            <span><span className="ot-key" style={{ background: "#4B32C3" }} />Answered {answeredCount}</span>
            <span><span className="ot-key" style={{ background: "#FDF0E3", border: "1px solid #C06A12" }} />For review {flagged.length}</span>
            <span><span className="ot-key" style={{ border: "1px solid #D9D7E3" }} />Not answered {qs.length - answeredCount}</span>
          </div>
          <button type="button" className="ot-btn" onClick={() => setConfirm(true)}>Submit test</button>
          <p className="ot-muted ot-small">Leaving this tab is recorded ({left} time{left === 1 ? "" : "s"} so far).</p>
        </aside>
      </div>

      {confirm && (
        <div className="ot-screen" style={{ background: "rgba(23,21,31,.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }} role="alertdialog" aria-modal="true" aria-labelledby="ot-confirm">
          <div className="ot-card ot-stack" style={{ maxWidth: 440, width: "100%" }}>
            <h2 className="ot-h2" id="ot-confirm">Submit the test?</h2>
            <p className="ot-muted">{answeredCount} of {qs.length} answered{flagged.length ? `, ${flagged.length} marked for review` : ""}. You can't change answers after submitting.</p>
            <div className="ot-row"><button type="button" className="ot-btn pri" disabled={busy} onClick={() => submit(false)}>{busy ? "Submitting…" : "Submit"}</button>
              <button type="button" className="ot-btn" onClick={() => setConfirm(false)}>Back to the test</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

function Review({ data, onClose }) {
  const shown = (q) => {
    const g = q.given;
    if (g === undefined || g === null) return "Not answered";
    if (q.kind === "tf") return g ? "True" : "False";
    if (q.kind === "mcq") return q.options.find((o) => o.i === g)?.t || "";
    if (q.kind === "multi") return q.options.filter((o) => g.includes(o.i)).map((o) => o.t).join(", ");
    return g;
  };
  const right = (q) => {
    if (q.kind === "tf") return q.answer ? "True" : "False";
    if (Array.isArray(q.answer)) return q.options.filter((o) => q.answer.includes(o.i)).map((o) => o.t).join(", ");
    return null;
  };
  return (
    <div className="ot-screen" role="dialog" aria-modal="true" aria-label={`Answers for ${data.test.title}`}>
      <div className="ot-screen-top">
        <div><b>{data.test.title}</b><div className="ot-muted ot-small">You scored {data.score} out of {data.test.total_marks}</div></div>
        <button type="button" className="ot-btn" onClick={onClose}>Close</button>
      </div>
      <div className="ot-screen-body" style={{ flexDirection: "column", alignItems: "stretch" }}>
        {data.questions.map((q) => (
          <section key={q.n} className="ot-card ot-stack">
            <div className="ot-between"><span className="ot-muted">Question {q.n}</span><span className={`ot-chip ${q.awarded > 0 ? "ok" : q.awarded < 0 ? "bad" : "grey"}`}>{q.awarded ?? "—"} / {q.marks}</span></div>
            <p className="ot-q" style={{ fontSize: 16 }}>{q.text}</p>
            <div className="ot-kv"><span>Your answer</span><b style={{ textAlign: "right" }}>{shown(q)}</b></div>
            {right(q) !== null && <div className="ot-kv"><span>Right answer</span><b style={{ textAlign: "right" }}>{right(q)}</b></div>}
            {q.comment && <p className="ot-note ok">Teacher's comment: {q.comment}</p>}
            {q.explanation && <p className="ot-note vio">{q.explanation}</p>}
          </section>
        ))}
      </div>
    </div>
  );
}
