// WAVE 2 - build or edit a draft survey.
//   /surveys/manage/new                 blank
//   /surveys/manage/new?template=key    filled from a template
//   /surveys/manage/:id/edit            a draft
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { errorText, KINDS, Shell, svApi } from "./surveysApi";
import "../../App.css";
import "../../styles/Surveys.css";

const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
let nextKey = 1;
const blankQuestion = (kind = "rating") => ({ key: nextKey++, kind, text: "", required: kind !== "text", optionsText: "" });
const fromServer = (q) => ({
  key: nextKey++, kind: q.kind, text: q.text, required: q.required, optionsText: (q.options || []).join("\n"),
});

export default function SurveyBuilder() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [opts, setOpts] = useState(null);
  const [form, setForm] = useState({
    title: "", description: "", audience: "students", department: "", course: "", year: "", semester: "",
    anonymous: true, start_date: today(), end_date: "", template: "",
  });
  const [questions, setQuestions] = useState([blankQuestion()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    svApi.options().then((o) => {
      setOpts(o);
      if (!o.college_wide && o.departments.length) {
        setForm((f) => ({ ...f, department: f.department || String(o.departments[0].id) }));
      }
    }).catch((err) => setError(errorText(err, "You can't build surveys.")));

    if (id) {
      svApi.get(id).then((s) => {
        if (s.status !== "draft") { navigate(`/surveys/manage/${id}/results`, { replace: true }); return; }
        setForm({
          title: s.title, description: s.description, audience: s.audience,
          department: s.department ? String(s.department) : "", course: s.course ? String(s.course) : "",
          year: s.year ? String(s.year) : "", semester: s.semester ? String(s.semester) : "",
          anonymous: s.anonymous, start_date: s.start_date, end_date: s.end_date || "", template: s.template,
        });
        setQuestions(s.questions.map(fromServer));
      }).catch((err) => setError(errorText(err, "Survey not found.")));
    } else if (params.get("template")) {
      svApi.templates().then((list) => {
        const t = list.find((x) => x.key === params.get("template"));
        if (!t) return;
        setForm((f) => ({ ...f, title: t.title, description: t.description, audience: t.audience,
          anonymous: t.anonymous, template: t.key }));
        setQuestions(t.questions.map(fromServer));
      });
    }
  }, [id, params, navigate]);

  const set = (k) => (e) => {
    const v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };
  const setQ = (key, patch) => setQuestions((qs) => qs.map((q) => (q.key === key ? { ...q, ...patch } : q)));
  const move = (i, dir) => setQuestions((qs) => {
    const j = i + dir;
    if (j < 0 || j >= qs.length) return qs;
    const copy = [...qs];
    [copy[i], copy[j]] = [copy[j], copy[i]];
    return copy;
  });

  const body = () => ({
    ...form,
    department: form.department || null, course: form.course || null,
    year: form.year || null, semester: form.semester || null, end_date: form.end_date || null,
    questions: questions.map((q) => ({
      kind: q.kind, text: q.text, required: q.required,
      options: ["choice", "multi"].includes(q.kind)
        ? q.optionsText.split("\n").map((o) => o.trim()).filter(Boolean) : [],
    })),
  });

  const save = async (andPublish) => {
    setError("");
    setBusy(true);
    try {
      const saved = id ? await svApi.update(id, body()) : await svApi.create(body());
      if (andPublish) {
        if (!window.confirm("Publish now? Everyone in the audience gets a notification, and the questions can't be changed after this.")) {
          navigate(`/surveys/manage/${saved.id}/edit`, { replace: true });
          return;
        }
        await svApi.publish(saved.id);
      }
      navigate("/surveys/manage");
    } catch (err) {
      setError(errorText(err, "The survey wasn't saved. Check the form and try again."));
    } finally {
      setBusy(false);
    }
  };

  const students = form.audience === "students";
  return (
    <Shell title={id ? "Edit survey" : "New survey"} subtitle="Saved as a draft until you publish it.">
      <section className="kb-card sv-form">
        <h2 className="kb-at-h2">About the survey</h2>
        <label className="kb-at-field"><span>Title</span>
          <input value={form.title} onChange={set("title")} maxLength={200} placeholder="Course-end feedback · Odd semester" />
        </label>
        <label className="kb-at-field"><span>Note for the people answering (optional)</span>
          <textarea rows={2} value={form.description} onChange={set("description")} />
        </label>

        <div className="sv-grid">
          <label className="kb-at-field"><span>Who answers</span>
            <select value={form.audience} onChange={set("audience")}>
              <option value="students">Students</option>
              <option value="staff">Teaching staff</option>
            </select>
          </label>
          <label className="kb-at-field"><span>Department</span>
            <select value={form.department} onChange={set("department")}>
              {opts?.college_wide && <option value="">All departments</option>}
              {(opts?.departments || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          {students && (
            <>
              <label className="kb-at-field"><span>Course</span>
                <select value={form.course} onChange={set("course")}>
                  <option value="">All courses</option>
                  {(opts?.courses || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <label className="kb-at-field"><span>Year</span>
                <select value={form.year} onChange={set("year")}>
                  <option value="">All years</option>
                  {[1, 2, 3, 4].map((y) => <option key={y} value={y}>Year {y}</option>)}
                </select>
              </label>
              <label className="kb-at-field"><span>Semester</span>
                <select value={form.semester} onChange={set("semester")}>
                  <option value="">All semesters</option>
                  {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => <option key={s} value={s}>Semester {s}</option>)}
                </select>
              </label>
            </>
          )}
          <label className="kb-at-field"><span>Opens on</span>
            <input type="date" value={form.start_date} onChange={set("start_date")} />
          </label>
          <label className="kb-at-field"><span>Last day (optional)</span>
            <input type="date" value={form.end_date} onChange={set("end_date")} />
          </label>
        </div>

        <label className="sv-check">
          <input type="checkbox" checked={form.anonymous} onChange={set("anonymous")} />
          <span><b>Anonymous</b> — results never show who gave which answer. We still record who has answered,
            so nobody can answer twice and you can see the response rate.</span>
        </label>
      </section>

      <section className="kb-card sv-form">
        <h2 className="kb-at-h2">Questions ({questions.length})</h2>
        <ol className="sv-qlist">
          {questions.map((q, i) => (
            <li key={q.key} className="sv-q">
              <div className="sv-q-top">
                <span className="sv-q-no">{i + 1}</span>
                <select value={q.kind} onChange={(e) => setQ(q.key, { kind: e.target.value })} aria-label="Question type">
                  {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select>
                <label className="sv-req">
                  <input type="checkbox" checked={q.required} onChange={(e) => setQ(q.key, { required: e.target.checked })} />
                  Required
                </label>
                <div className="sv-q-tools">
                  <button type="button" className="kb-btn kb-btn--sm" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up">↑</button>
                  <button type="button" className="kb-btn kb-btn--sm" onClick={() => move(i, 1)} disabled={i === questions.length - 1} aria-label="Move down">↓</button>
                  <button type="button" className="kb-btn kb-btn--sm" disabled={questions.length === 1}
                    onClick={() => setQuestions((qs) => qs.filter((x) => x.key !== q.key))}>Remove</button>
                </div>
              </div>
              <input className="sv-q-text" value={q.text} onChange={(e) => setQ(q.key, { text: e.target.value })}
                placeholder={q.kind === "rating" ? "A statement to agree or disagree with" : "The question"} maxLength={500} />
              {["choice", "multi"].includes(q.kind) && (
                <textarea className="sv-q-opts" rows={3} value={q.optionsText}
                  onChange={(e) => setQ(q.key, { optionsText: e.target.value })} placeholder={"One option per line\nExcellent\nGood\nPoor"} />
              )}
              {q.kind === "rating" && <p className="sv-muted sv-hint">Answered 1 (strongly disagree) to 5 (strongly agree).</p>}
            </li>
          ))}
        </ol>
        <div className="sv-add">
          {KINDS.map((k) => (
            <button key={k.value} type="button" className="kb-btn kb-btn--sm"
              onClick={() => setQuestions((qs) => [...qs, blankQuestion(k.value)])}>+ {k.label}</button>
          ))}
        </div>
      </section>

      {error && <div className="kb-at-error" role="alert">{error}</div>}
      <div className="sv-footer">
        <button type="button" className="kb-btn" onClick={() => navigate("/surveys/manage")} disabled={busy}>Cancel</button>
        <button type="button" className="kb-btn" onClick={() => save(false)} disabled={busy}>Save draft</button>
        <button type="button" className="kb-btn kb-btn--primary" onClick={() => save(true)} disabled={busy}>
          {busy ? "Saving…" : "Save & publish"}
        </button>
      </div>
    </Shell>
  );
}
