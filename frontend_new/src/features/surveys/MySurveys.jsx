// WAVE 2 - answering surveys (students and teaching staff).
//   /surveys        surveys meant for me
//   /surveys/:id    answer one
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { errorText, fmtDate, RATING_WORDS, Shell, svApi } from "./surveysApi";
import "../../App.css";
import "../../styles/Surveys.css";

/** /surveys */
export default function MySurveys() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    svApi.mine().then(setRows).catch((err) => { setRows([]); setError(errorText(err, "Couldn't load surveys.")); });
  }, []);
  const todo = (rows || []).filter((r) => !r.answered);
  const done = (rows || []).filter((r) => r.answered);

  const card = (s) => (
    <article key={s.id} className="sv-row">
      <div className="sv-row-main">
        <div className="sv-row-title">
          <b>{s.title}</b>
          {s.answered ? <span className="kb-pill ok">Answered</span> : <span className="kb-pill warn">To answer</span>}
          {s.anonymous && <span className="kb-pill">Anonymous</span>}
        </div>
        <div className="sv-muted">
          {s.questions_count} questions{s.end_date ? ` · last day ${fmtDate(s.end_date)}` : ""} · from {s.created_by || "the college"}
        </div>
      </div>
      <div className="sv-row-actions">
        {!s.answered && <Link to={`/surveys/${s.id}`} className="kb-btn kb-btn--sm kb-btn--primary">Answer</Link>}
      </div>
    </article>
  );

  return (
    <Shell title="Surveys" subtitle="Feedback the college has asked you for.">
      {error && <div className="kb-at-error" role="alert">{error}</div>}
      <section className="kb-card">
        <h2 className="kb-at-h2">To answer</h2>
        {rows === null ? <p className="sv-muted">Loading…</p> : todo.length === 0
          ? <p className="sv-muted">Nothing to answer right now.</p>
          : <div className="sv-list">{todo.map(card)}</div>}
      </section>
      {done.length > 0 && (
        <section className="kb-card">
          <h2 className="kb-at-h2">Answered</h2>
          <div className="sv-list">{done.map(card)}</div>
        </section>
      )}
    </Shell>
  );
}

/** /surveys/:id */
export function AnswerSurvey() {
  const { id } = useParams();
  const [s, setS] = useState(null);
  const [answers, setAnswers] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    svApi.mineOne(id).then(setS).catch((err) => setError(errorText(err, "Survey not found.")));
  }, [id]);

  const put = (qid, v) => setAnswers((a) => ({ ...a, [qid]: v }));
  const toggle = (qid, opt) => setAnswers((a) => {
    const cur = a[qid] || [];
    return { ...a, [qid]: cur.includes(opt) ? cur.filter((x) => x !== opt) : [...cur, opt] };
  });

  const submit = async () => {
    setError("");
    const missing = s.questions.find((q) => q.required && (answers[q.id] == null || answers[q.id] === ""
      || (Array.isArray(answers[q.id]) && answers[q.id].length === 0)));
    if (missing) {
      setError(`Please answer question ${s.questions.indexOf(missing) + 1}.`);
      document.getElementById(`q-${missing.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setBusy(true);
    try {
      await svApi.submit(id, answers);
      setDone(true);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(errorText(err, "Your answers weren't saved. Try again."));
    } finally {
      setBusy(false);
    }
  };

  if (!s) {
    return (
      <Shell title="Survey">
        <section className="kb-card">{error ? <p className="sv-bad">{error}</p> : <p className="sv-muted">Loading…</p>}</section>
      </Shell>
    );
  }

  if (done || s.answered) {
    return (
      <Shell title={s.title}>
        <section className="kb-card sv-thanks">
          <h2>Thank you</h2>
          <p>{done ? "Your answers were saved." : "You have already answered this survey."}
            {s.anonymous ? " They are anonymous." : ""}</p>
          <Link to="/surveys" className="kb-btn kb-btn--primary">Back to surveys</Link>
        </section>
      </Shell>
    );
  }

  return (
    <Shell title={s.title} subtitle={s.description}>
      <div className="sv-banner">
        {s.anonymous
          ? "This survey is anonymous: your name is not shown with your answers."
          : "This survey is not anonymous: your name is shown with your answers."}
        {s.end_date && ` Last day: ${fmtDate(s.end_date)}.`}
      </div>

      {!s.accepting && <div className="kb-at-error">This survey is not taking answers now.</div>}

      {s.questions.map((q, i) => (
        <section key={q.id} id={`q-${q.id}`} className="kb-card sv-answer">
          <p className="sv-answer-q"><span className="sv-q-no">{i + 1}</span>{q.text}{q.required && <em className="sv-star" aria-label="required">*</em>}</p>

          {q.kind === "rating" && (
            <div className="sv-scale" role="radiogroup" aria-label={q.text}>
              {[1, 2, 3, 4, 5].map((v) => (
                <button key={v} type="button" role="radio" aria-checked={answers[q.id] === v}
                  className={answers[q.id] === v ? "on" : ""} onClick={() => put(q.id, v)}>
                  <b>{v}</b><span>{RATING_WORDS[v]}</span>
                </button>
              ))}
            </div>
          )}
          {q.kind === "rating" && <p className="sv-scale-key">1 = Strongly disagree · 5 = Strongly agree</p>}

          {q.kind === "choice" && (
            <div className="sv-options">
              {q.options.map((o) => (
                <label key={o} className={answers[q.id] === o ? "on" : ""}>
                  <input type="radio" name={`q${q.id}`} checked={answers[q.id] === o} onChange={() => put(q.id, o)} />{o}
                </label>
              ))}
            </div>
          )}

          {q.kind === "multi" && (
            <div className="sv-options">
              {q.options.map((o) => (
                <label key={o} className={(answers[q.id] || []).includes(o) ? "on" : ""}>
                  <input type="checkbox" checked={(answers[q.id] || []).includes(o)} onChange={() => toggle(q.id, o)} />{o}
                </label>
              ))}
            </div>
          )}

          {q.kind === "text" && (
            <textarea rows={3} maxLength={2000} value={answers[q.id] || ""} onChange={(e) => put(q.id, e.target.value)}
              placeholder="Type your answer" />
          )}
        </section>
      ))}

      {error && <div className="kb-at-error" role="alert">{error}</div>}
      <div className="sv-footer">
        <Link to="/surveys" className="kb-btn">Cancel</Link>
        <button type="button" className="kb-btn kb-btn--primary" onClick={submit} disabled={busy || !s.accepting}>
          {busy ? "Sending…" : "Submit answers"}
        </button>
      </div>
    </Shell>
  );
}
