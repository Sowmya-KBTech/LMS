// WAVE 2 - surveys I manage (/surveys/manage): HODs, the Principal, admins, IQAC.
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { errorText, fmtDate, Shell, statusPill, svApi } from "./surveysApi";
import "../../App.css";
import "../../styles/Surveys.css";

export default function SurveysManage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    svApi.list().then(setRows).catch((err) => {
      setRows([]);
      setNotice({ tone: "bad", text: errorText(err, "Couldn't load your surveys.") });
    });
  }, []);
  useEffect(() => {
    load();
    svApi.templates().then(setTemplates).catch(() => setTemplates([]));
  }, [load]);

  const act = async (fn, ok, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return;
    setNotice(null);
    try {
      const r = await fn();
      setNotice({ tone: "ok", text: typeof ok === "function" ? ok(r) : ok });
      load();
    } catch (err) {
      setNotice({ tone: "bad", text: errorText(err, "That didn't work. Try again.") });
    }
  };

  return (
    <Shell
      title="Surveys"
      subtitle="Build feedback surveys, send them to students or staff, and read the results."
      actions={<Link to="/surveys/manage/new" className="kb-btn kb-btn--primary">New survey</Link>}
    >
      {templates.length > 0 && (
        <section className="kb-card">
          <h2 className="kb-at-h2">Start from a template</h2>
          <div className="sv-templates">
            {templates.map((t) => (
              <button key={t.key} type="button" className="sv-template"
                onClick={() => navigate(`/surveys/manage/new?template=${t.key}`)}>
                <b>{t.title}</b>
                <span>{t.audience === "staff" ? "Teaching staff" : "Students"} · {t.questions.length} questions
                  {t.anonymous ? " · anonymous" : ""}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {notice && (
        <div className={notice.tone === "ok" ? "kb-sa-ok" : "kb-at-error"} role={notice.tone === "ok" ? "status" : "alert"}>
          {notice.text}
        </div>
      )}

      <section className="kb-card">
        <h2 className="kb-at-h2">Your surveys</h2>
        {rows === null ? <p className="sv-muted">Loading…</p> : rows.length === 0 ? (
          <p className="sv-muted">No surveys yet. Start from a template or click New survey.</p>
        ) : (
          <div className="sv-list">
            {rows.map((s) => {
              const pill = statusPill(s);
              const rate = s.eligible ? Math.round((s.answered * 100) / s.eligible) : 0;
              return (
                <article key={s.id} className="sv-row">
                  <div className="sv-row-main">
                    <div className="sv-row-title">
                      <b>{s.title}</b>
                      <span className={`kb-pill ${pill.tone}`}>{pill.text}</span>
                      {s.anonymous && <span className="kb-pill">Anonymous</span>}
                    </div>
                    <div className="sv-muted">
                      {s.audience_text} · {s.questions_count} questions
                      {s.end_date ? ` · until ${fmtDate(s.end_date)}` : ""}
                    </div>
                    {s.status !== "draft" && (
                      <div className="sv-progress" title={`${s.answered} of ${s.eligible} answered`}>
                        <span style={{ width: `${rate}%` }} />
                        <em>{s.answered} of {s.eligible} answered ({rate}%)</em>
                      </div>
                    )}
                  </div>
                  <div className="sv-row-actions">
                    {s.status === "draft" ? (
                      <>
                        <Link to={`/surveys/manage/${s.id}/edit`} className="kb-btn kb-btn--sm">Edit</Link>
                        <button type="button" className="kb-btn kb-btn--sm kb-btn--primary"
                          onClick={() => act(() => svApi.publish(s.id), (r) => `Published. ${r.notified} people were told.`,
                            `Publish "${s.title}"? Everyone in the audience gets a notification, and the questions can't be changed after this.`)}>
                          Publish
                        </button>
                        <button type="button" className="kb-btn kb-btn--sm"
                          onClick={() => act(() => svApi.remove(s.id), "Draft deleted.", `Delete the draft "${s.title}"?`)}>
                          Delete
                        </button>
                      </>
                    ) : (
                      <>
                        <Link to={`/surveys/manage/${s.id}/results`} className="kb-btn kb-btn--sm kb-btn--primary">Results</Link>
                        {s.status === "open" && (
                          <button type="button" className="kb-btn kb-btn--sm"
                            onClick={() => act(() => svApi.close(s.id), "Survey closed.", `Close "${s.title}"? Nobody can answer after this.`)}>
                            Close
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </Shell>
  );
}
