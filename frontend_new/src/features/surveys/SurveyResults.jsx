// WAVE 2 - survey results (/surveys/manage/:id/results). Printable.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { errorText, fmtDate, RATING_WORDS, Shell, statusPill, svApi } from "./surveysApi";
import "../../App.css";
import "../../styles/Surveys.css";

const pct = (n, d) => (d ? Math.round((n * 100) / d) : 0);

function Bar({ label, count, total, strong }) {
  const p = pct(count, total);
  return (
    <div className={`sv-bar${strong ? " strong" : ""}`}>
      <span className="sv-bar-label">{label}</span>
      <span className="sv-bar-track"><span style={{ width: `${p}%` }} /></span>
      <span className="sv-bar-num">{strong ? `${count} of ${total}` : count} <em>({p}%)</em></span>
    </div>
  );
}

function QuestionResult({ q, n }) {
  return (
    <section className="kb-card sv-result">
      <div className="sv-result-head">
        <span className="sv-q-no">{n}</span>
        <h3>{q.text}</h3>
        <span className="sv-muted">{q.count} answer{q.count === 1 ? "" : "s"}</span>
      </div>

      {q.kind === "rating" && (
        <div className="sv-rating">
          <div className="sv-avg">
            <b>{q.average ?? "—"}</b>
            <span>average of 5</span>
          </div>
          <div className="sv-bars">
            {[5, 4, 3, 2, 1].map((v) => (
              <Bar key={v} label={`${v} · ${RATING_WORDS[v]}`} count={q.distribution[String(v)]} total={q.count} />
            ))}
          </div>
        </div>
      )}

      {(q.kind === "choice" || q.kind === "multi") && (
        <div className="sv-bars">
          {q.kind === "multi" && <p className="sv-muted sv-hint">People could pick several, so percentages add up to more than 100%.</p>}
          {q.counts.map((c) => <Bar key={c.option} label={c.option} count={c.count} total={q.count} />)}
        </div>
      )}

      {q.kind === "text" && (q.answers.length === 0 ? <p className="sv-muted">No written answers.</p> : (
        <ul className="sv-texts">
          {q.answers.map((a, i) => (
            <li key={i}>{a.text}{a.by && <span className="sv-muted"> — {a.by}</span>}</li>
          ))}
        </ul>
      ))}
    </section>
  );
}

export default function SurveyResults() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    svApi.results(id).then(setData).catch((err) => setError(errorText(err, "Couldn't load the results.")));
  }, [id]);

  if (error || !data) {
    return (
      <Shell title="Survey results">
        <section className="kb-card">{error ? <p className="sv-bad">{error}</p> : <p className="sv-muted">Loading…</p>}</section>
      </Shell>
    );
  }

  const pill = statusPill(data);
  return (
    <Shell
      title={data.title}
      subtitle={`${data.audience_text}${data.end_date ? ` · until ${fmtDate(data.end_date)}` : ""}`}
      actions={(
        <>
          <Link to="/surveys/manage" className="kb-btn">All surveys</Link>
          <button type="button" className="kb-btn kb-btn--primary" onClick={() => window.print()}>Print / save as PDF</button>
        </>
      )}
    >
      <div className="sv-stats">
        <div><span>Status</span><b><span className={`kb-pill ${pill.tone}`}>{pill.text}</span></b></div>
        <div><span>Answered</span><b>{data.answered} <small>of {data.eligible}</small></b></div>
        <div><span>Response rate</span><b>{data.rate ?? "—"}{data.rate != null ? "%" : ""}</b></div>
        <div><span>Answers</span><b className="sv-small-b">{data.anonymous ? "Anonymous" : "With names"}</b></div>
      </div>

      <section className="kb-card">
        <h2 className="kb-at-h2">Response rate by {data.audience === "staff" ? "department" : "class"}</h2>
        <div className="sv-bars">
          {data.by_group.map((g) => (
            <Bar key={g.group} label={g.group} count={g.answered} total={g.eligible} strong />
          ))}
        </div>
        <p className="sv-muted sv-hint">Counts who has answered, never what they answered.</p>
      </section>

      {data.questions.map((q, i) => <QuestionResult key={q.id} q={q} n={i + 1} />)}
    </Shell>
  );
}
