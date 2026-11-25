// WAVE 3 PART 3 - Online tests (the quiz, upgraded), teacher side.
// One subject's "Online tests" tab:
//   Tests          the tests of this class, with their state and actions
//   Question bank  the subject's questions (shared by its teachers), AI drafts
//   Builder        settings + sections (random from the bank, or chosen) + live summary
//   Live status    who started / submitted, how far they got, tab leaves
//   Marking        (Part 3b) one written question across every student, model answer alongside
//   Results        (Part 3b) marks by section, by CO, hardest questions; release to students
import { useCallback, useEffect, useMemo, useState } from "react";
import API from "../../api";
import ImportExport from "../../components/ImportExport";
import "../../styles/Quiz.css";

const KINDS = [["mcq", "MCQ · one answer"], ["multi", "MCQ · many answers"], ["tf", "True / false"], ["short", "Short answer"], ["long", "Long answer"]];
const KIND = Object.fromEntries(KINDS);
const SHORT = { mcq: "MCQ", multi: "MCQ (many)", tf: "True/false", short: "Short", long: "Long" };
const BLOOMS = ["remember", "understand", "apply", "analyse", "evaluate", "create"];
const STATE = {
  draft: ["Draft", "grey"], upcoming: ["Scheduled", "vio"], open: ["Open now", "ok"], closed: ["Closed", "grey"],
};
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
const errText = (err, fb) => {
  const d = err?.response?.data;
  if (typeof d?.detail === "string") return d.detail + (Array.isArray(d.errors) && d.errors.length > 1 ? ` ${d.errors.join(" ")}` : "");
  return fb;
};
const toLocal = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};
const fromLocal = (v) => (v ? new Date(v).toISOString() : null);
const when = (iso) => (iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");

export default function QuizTeacher({ teachingId }) {
  const [view, setView] = useState("tests");          // tests | bank | builder | live | marking | results
  const [tests, setTests] = useState(null);
  const [subject, setSubject] = useState(null);       // {id, ...meta}
  const [editing, setEditing] = useState(null);       // test being built (null = new)
  const [liveId, setLiveId] = useState(null);
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState(null);

  const loadTests = useCallback(() => API.get("online-tests/tests/", { params: { teaching_assignment: teachingId } })
    .then((r) => setTests(r.data)).catch(() => setTests([])), [teachingId]);
  const loadMeta = useCallback((subjectId) => API.get("online-tests/bank/meta/", { params: { subject: subjectId } })
    .then((r) => setSubject({ id: subjectId, ...r.data })), []);

  useEffect(() => {
    if (!teachingId) return;
    loadTests();
    API.get(`teaching-assignments/${teachingId}/`).then((r) => {
      const sid = typeof r.data.subject === "object" ? r.data.subject.id : r.data.subject;
      return loadMeta(sid);
    }).catch(() => setMsg({ tone: "bad", text: "Couldn't load this subject." }));
  }, [teachingId, loadTests, loadMeta]);

  const act = async (fn, ok) => {
    setMsg(null);
    try { await fn(); setMsg({ tone: "ok", text: ok }); await loadTests(); } catch (err) { setMsg({ tone: "bad", text: errText(err, "That didn't work.") }); }
  };

  const openPreview = (t) => API.get(`online-tests/tests/${t.id}/preview/`).then((r) => setPreview(r.data))
    .catch((err) => setMsg({ tone: "bad", text: errText(err, "Couldn't open the preview.") }));

  if (view === "builder" && subject) {
    return <Builder teachingId={teachingId} subject={subject} test={editing}
      onDone={(text) => { setView("tests"); setEditing(null); if (text) setMsg({ tone: "ok", text }); loadTests(); }} />;
  }
  if (view === "live" && liveId) {
    return <Live testId={liveId} onBack={() => { setView("tests"); setLiveId(null); loadTests(); }} />;
  }
  if (view === "marking" && liveId) {
    return <Marking testId={liveId} onBack={() => { setView("tests"); setLiveId(null); loadTests(); }}
      onResults={() => setView("results")} />;
  }
  if (view === "results" && liveId) {
    return <Results testId={liveId} onBack={() => { setView("tests"); setLiveId(null); loadTests(); }}
      onMark={() => setView("marking")} />;
  }

  return (
    <div className="ot-wrap">
      <div className="ot-between">
        <div className="ot-seg" role="group" aria-label="View">
          <button type="button" aria-pressed={view === "tests"} onClick={() => setView("tests")}>Tests</button>
          <button type="button" aria-pressed={view === "bank"} onClick={() => setView("bank")}>Question bank{subject ? ` · ${subject.count}` : ""}</button>
        </div>
        {view === "tests" && <button type="button" className="ot-btn pri" disabled={!subject} onClick={() => { setEditing(null); setView("builder"); }}>+ New online test</button>}
      </div>
      {msg && <p className={`ot-note ${msg.tone}`} role="status">{msg.text}</p>}

      {view === "bank" && subject && <Bank subject={subject} onChange={() => loadMeta(subject.id)} />}

      {view === "tests" && (
        <section className="ot-card ot-stack">
          <h2 className="ot-h2">Online tests</h2>
          {tests === null ? <p className="ot-muted">Loading…</p> : tests.length === 0 ? (
            <p className="ot-muted">No tests yet. Add questions to the question bank, then make a test from them.</p>
          ) : tests.map((t) => {
            const [label, tone] = STATE[t.state] || ["", "grey"];
            return (
              <div key={t.id} className="ot-test">
                <div className="ot-stack" style={{ gap: 6 }}>
                  <div className="ot-row"><b style={{ fontSize: 16 }}>{t.title}</b>
                    <span className={`ot-chip ${tone}`}>{t.state === "open" && t.writing ? `Open now · ${t.writing} writing` : label}</span>
                    {t.to_mark > 0 && <span className="ot-chip warn">{t.to_mark} to mark</span>}</div>
                  <div className="ot-stats">
                    <span><b>{t.question_count}</b> questions</span><span><b>{t.total_marks}</b> marks</span><span><b>{t.duration}</b> min</span>
                    {t.opens_at && t.state !== "closed" && <span>Opens <b>{when(t.opens_at)}</b></span>}
                    {t.closes_at && <span>{t.state === "closed" ? "Closed" : "Closes"} <b>{when(t.closes_at)}</b></span>}
                    {t.is_published && <span><b>{t.submitted} / {t.students}</b> submitted</span>}
                    {t.average != null && <span>Average <b>{t.average}</b></span>}
                  </div>
                </div>
                <div className="ot-row">
                  <button type="button" className="ot-btn sm" onClick={() => openPreview(t)}>Preview</button>
                  {t.started === 0 && <button type="button" className="ot-btn sm" onClick={() => { setEditing(t); setView("builder"); }}>Edit</button>}
                  {!t.is_published && <button type="button" className="ot-btn sm pri" onClick={() => act(() => API.post(`online-tests/tests/${t.id}/publish/`), `${t.title} is published. Students have been told.`)}>Publish</button>}
                  {t.is_published && t.started === 0 && <button type="button" className="ot-btn sm" onClick={() => act(() => API.post(`online-tests/tests/${t.id}/unpublish/`), `${t.title} is a draft again.`)}>Unpublish</button>}
                  {t.is_published && t.state !== "closed" && <button type="button" className="ot-btn sm" onClick={() => { setLiveId(t.id); setView("live"); }}>Live status</button>}
                  {t.to_mark > 0 && <button type="button" className="ot-btn sm pri" onClick={() => { setLiveId(t.id); setView("marking"); }}>Mark answers</button>}
                  {t.submitted > 0 && <button type="button" className="ot-btn sm" onClick={() => { setLiveId(t.id); setView("results"); }}>Results</button>}
                  {t.started === 0 && <button type="button" className="ot-btn sm danger" onClick={() => { if (window.confirm(`Delete ${t.title}?`)) act(() => API.delete(`online-tests/tests/${t.id}/`), "Test deleted."); }}>Delete</button>}
                </div>
              </div>
            );
          })}
        </section>
      )}
      {preview && <PreviewDialog data={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

// ============================================================ the question bank
const blankQ = { kind: "mcq", text: "", options: ["", "", "", ""], answer: [0], model_answer: "", marks: 1, negative_marks: 0,
  unit: "", outcome: "", bloom: "", difficulty: "medium", explanation: "" };

function Bank({ subject, onChange }) {
  const [rows, setRows] = useState(null);
  const [f, setF] = useState({ q: "", unit: "", outcome: "", kind: "" });
  const [form, setForm] = useState(null);           // question being added / edited
  const [ai, setAi] = useState(false);
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => API.get("online-tests/bank/", { params: { subject: subject.id, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) } })
    .then((r) => setRows(r.data)).catch(() => setRows([])), [subject.id, f]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  const done = (text) => { setForm(null); setAi(false); setMsg({ tone: "ok", text }); load(); onChange(); };
  const archive = async (q) => {
    if (!window.confirm("Remove this question from the bank?")) return;
    try {
      const r = await API.delete(`online-tests/bank/${q.id}/`);
      done(r.data?.archived ? r.data.detail : "Question deleted.");
    } catch (err) { setMsg({ tone: "bad", text: errText(err, "Couldn't remove it.") }); }
  };

  return (
    <div className="ot-two">
      <section className="ot-card ot-main ot-stack">
        <div className="ot-between">
          <h2 className="ot-h2">Question bank · {subject.subject?.code} {subject.subject?.name}</h2>
          <div className="ot-row">
            <ImportExport importer="question_bank" label="questions" modes={["add"]} options={{ subject: subject.id }}
              align="right" note="One row per question, any type. Rows are added to the bank." onDone={() => { load(); onChange(); }} />
            <button type="button" className="ot-btn" onClick={() => { setAi(true); setForm(null); }}>Generate questions with AI</button>
            <button type="button" className="ot-btn pri" onClick={() => { setForm({ ...blankQ }); setAi(false); }}>+ Add question</button>
          </div>
        </div>
        <p className="ot-muted">Shared by every teacher of this subject. Unit, course outcome and Bloom level let tests pick by topic and feed the CO reports later.</p>
        {msg && <p className={`ot-note ${msg.tone}`} role="status">{msg.text}</p>}
        <div className="ot-row">
          <label className="ot-field" style={{ flex: "1 1 220px" }}><span className="ot-sr">Search</span><input placeholder="Search questions" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></label>
          <label className="ot-field" style={{ width: 130 }}><span className="ot-sr">Unit</span><select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}><option value="">All units</option>{subject.units.map((u) => <option key={u} value={u}>Unit {u}</option>)}</select></label>
          <label className="ot-field" style={{ width: 130 }}><span className="ot-sr">Course outcome</span><select value={f.outcome} onChange={(e) => setF({ ...f, outcome: e.target.value })}><option value="">All COs</option>{subject.outcomes.map((o) => <option key={o.id} value={o.id}>{o.code}</option>)}</select></label>
          <label className="ot-field" style={{ width: 170 }}><span className="ot-sr">Type</span><select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="">All types</option>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        </div>
        {rows === null ? <p className="ot-muted">Loading…</p> : rows.length === 0 ? <p className="ot-muted">No questions match.</p> : (
          <div className="ot-table-wrap">
            <table className="ot-table">
              <thead><tr><th>Question</th><th>Type</th><th>Marks</th><th>Unit</th><th>CO</th><th>Level</th><th>Used</th><th><span className="ot-sr">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((q) => (
                  <tr key={q.id}>
                    <td style={{ minWidth: 260 }}>{q.text}{q.bloom && <small>{cap(q.bloom)}</small>}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{SHORT[q.kind]}</td><td>{q.marks}</td><td>{q.unit || "—"}</td>
                    <td>{q.outcome_code ? <span className="ot-chip vio">{q.outcome_code}</span> : "—"}</td>
                    <td><span className={`ot-chip ${q.difficulty === "easy" ? "ok" : q.difficulty === "hard" ? "bad" : "warn"}`}>{cap(q.difficulty)}</span></td>
                    <td>{q.used_in ? `${q.used_in} test${q.used_in === 1 ? "" : "s"}` : "—"}</td>
                    <td><div className="ot-row" style={{ flexWrap: "nowrap" }}>
                      <button type="button" className="ot-link" onClick={() => { setForm({ ...blankQ, ...q, unit: q.unit || "", outcome: q.outcome || "" }); setAi(false); }}>Edit</button>
                      <button type="button" className="ot-link" onClick={() => archive(q)}>Remove</button></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {form && <QuestionForm subject={subject} initial={form} onCancel={() => setForm(null)} onSaved={done} />}
      {ai && <AiPanel subject={subject} onCancel={() => setAi(false)} onSaved={done} />}
    </div>
  );
}

function QuestionForm({ subject, initial, onCancel, onSaved }) {
  const [q, setQ] = useState(initial);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setQ((p) => ({ ...p, [k]: v }));
  const choice = q.kind === "mcq" || q.kind === "multi";
  const setKind = (kind) => setQ((p) => ({
    ...p, kind,
    options: kind === "mcq" || kind === "multi" ? (p.options?.length >= 2 && p.kind !== "tf" ? p.options : ["", "", "", ""]) : [],
    answer: kind === "tf" ? true : kind === "mcq" || kind === "multi" ? [0] : null,
  }));
  const toggleAns = (i) => {
    if (q.kind === "mcq") return set("answer", [i]);
    const cur = Array.isArray(q.answer) ? q.answer : [];
    set("answer", cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i].sort());
  };
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    const body = { ...q, subject: subject.id, outcome: q.outcome || null, unit: q.unit || null };
    try {
      if (q.id) await API.patch(`online-tests/bank/${q.id}/`, body);
      else await API.post("online-tests/bank/", body);
      onSaved(q.id ? "Question saved." : "Question added to the bank.");
    } catch (er) { setErr(errText(er, "Couldn't save the question.")); } finally { setBusy(false); }
  };
  return (
    <form className="ot-card ot-side ot-stack" onSubmit={save}>
      <div className="ot-between"><h2 className="ot-h2">{q.id ? "Edit question" : "New question"}</h2>{q.used_in > 0 && <span className="ot-chip warn">Used in {q.used_in} test{q.used_in === 1 ? "" : "s"}</span>}</div>
      <label className="ot-field">Type<select value={q.kind} onChange={(e) => setKind(e.target.value)} disabled={q.used_in > 0}>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      <label className="ot-field">Question<textarea value={q.text} onChange={(e) => set("text", e.target.value)} required /></label>
      {choice && (
        <fieldset className="ot-fieldset">
          <legend>Options · tick the right {q.kind === "multi" ? "answers" : "answer"}</legend>
          {q.options.map((o, i) => (
            <div key={i} className="ot-opt">
              <input type={q.kind === "mcq" ? "radio" : "checkbox"} name="ans" aria-label={`Option ${i + 1} is right`} checked={(q.answer || []).includes(i)} onChange={() => toggleAns(i)} disabled={q.used_in > 0} />
              <input className="ot-input" aria-label={`Option ${i + 1}`} value={o} disabled={q.used_in > 0} onChange={(e) => set("options", q.options.map((x, j) => (j === i ? e.target.value : x)))} />
              {q.options.length > 2 && !q.used_in && <button type="button" className="ot-link" aria-label={`Remove option ${i + 1}`} onClick={() => setQ((p) => ({ ...p, options: p.options.filter((_, j) => j !== i), answer: (p.answer || []).filter((x) => x !== i).map((x) => (x > i ? x - 1 : x)) }))}>Remove</button>}
            </div>
          ))}
          {q.options.length < 8 && !q.used_in && <button type="button" className="ot-btn sm" style={{ alignSelf: "flex-start" }} onClick={() => set("options", [...q.options, ""])}>Add option</button>}
        </fieldset>
      )}
      {q.kind === "tf" && (
        <fieldset className="ot-fieldset" style={{ flexDirection: "row", gap: 18 }}>
          <legend>The statement is</legend>
          <label className="ot-check"><input type="radio" name="tf" checked={q.answer === true} onChange={() => set("answer", true)} disabled={q.used_in > 0} /> True</label>
          <label className="ot-check"><input type="radio" name="tf" checked={q.answer === false} onChange={() => set("answer", false)} disabled={q.used_in > 0} /> False</label>
        </fieldset>
      )}
      {(q.kind === "short" || q.kind === "long") && (
        <label className="ot-field">Model answer and marking points (only teachers see this)<textarea value={q.model_answer} onChange={(e) => set("model_answer", e.target.value)} /></label>
      )}
      <div className="ot-grid2">
        <label className="ot-field">Marks<input type="number" min="1" value={q.marks} onChange={(e) => set("marks", e.target.value)} /></label>
        <label className="ot-field">Difficulty<select value={q.difficulty} onChange={(e) => set("difficulty", e.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
        <label className="ot-field">Unit<input type="number" min="1" value={q.unit} onChange={(e) => set("unit", e.target.value)} placeholder="1" /></label>
        <label className="ot-field">Course outcome<select value={q.outcome} onChange={(e) => set("outcome", e.target.value)}><option value="">Not set</option>{subject.outcomes.map((o) => <option key={o.id} value={o.id}>{o.code} · {o.text.slice(0, 40)}</option>)}</select></label>
        <label className="ot-field">Bloom level<select value={q.bloom} onChange={(e) => set("bloom", e.target.value)}><option value="">Not set</option>{BLOOMS.map((b) => <option key={b} value={b}>{cap(b)}</option>)}</select></label>
        {choice || q.kind === "tf" ? <label className="ot-field">Negative mark (if the test uses them)<input type="number" min="0" step="0.25" value={q.negative_marks} onChange={(e) => set("negative_marks", e.target.value)} /></label> : <span />}
      </div>
      <label className="ot-field">Explanation shown after results (optional)<textarea style={{ minHeight: 60 }} value={q.explanation} onChange={(e) => set("explanation", e.target.value)} /></label>
      {err && <p className="ot-note bad" role="alert">{err}</p>}
      <div className="ot-row"><button className="ot-btn pri" type="submit" disabled={busy}>{busy ? "Saving…" : "Save question"}</button><button className="ot-btn" type="button" onClick={onCancel}>Cancel</button></div>
    </form>
  );
}

function AiPanel({ subject, onCancel, onSaved }) {
  const [notes, setNotes] = useState("");
  const [count, setCount] = useState(10);
  const [draft, setDraft] = useState([]);
  const [meta, setMeta] = useState({ unit: "", outcome: "", difficulty: "medium" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const gen = async () => {
    setBusy(true); setErr("");
    try {
      const r = await API.post("online-tests/bank/generate/", { subject: subject.id, notes, count });
      setDraft(r.data.draft.map((d) => ({ ...d, keep: true })));
      if (r.data.note) setErr(r.data.note);
    } catch (er) { setErr(errText(er, "Couldn't make questions.")); } finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setErr("");
    const rows = draft.filter((d) => d.keep).map((d) => {
      const r = { ...d, ...meta, unit: meta.unit || null, outcome: meta.outcome || null };
      delete r.keep;
      return r;
    });
    try {
      const r = await API.post("online-tests/bank/", { subject: subject.id, questions: rows });
      onSaved(`${r.data.created} questions added to the bank.`);
    } catch (er) { setErr(errText(er, "Couldn't save them.")); } finally { setBusy(false); }
  };
  return (
    <section className="ot-card ot-side ot-stack">
      <h2 className="ot-h2">Generate questions with AI</h2>
      {draft.length === 0 ? (
        <>
          <label className="ot-field">Paste your notes<textarea style={{ minHeight: 160 }} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
          <label className="ot-field" style={{ width: 140 }}>How many<input type="number" min="1" max="30" value={count} onChange={(e) => setCount(e.target.value)} /></label>
          <p className="ot-muted ot-small">Only the subject name and these notes are sent. Nothing is saved until you check the questions.</p>
          <div className="ot-row"><button type="button" className="ot-btn pri" disabled={busy || !notes.trim()} onClick={gen}>{busy ? "Making questions…" : "Make questions"}</button><button type="button" className="ot-btn" onClick={onCancel}>Cancel</button></div>
        </>
      ) : (
        <>
          <p className="ot-muted">Untick any question you don't want. The right answer is in bold.</p>
          <div className="ot-pick">
            {draft.map((d, i) => (
              <label key={i} className="ot-check" style={{ padding: "8px 0", borderBottom: "1px solid #F0F0F4" }}>
                <input type="checkbox" checked={d.keep} onChange={() => setDraft(draft.map((x, j) => (j === i ? { ...x, keep: !x.keep } : x)))} />
                <span>{d.text}<br /><span className="ot-muted ot-small">{d.options.map((o, k) => (k === d.answer[0] ? <b key={k}>{o}</b> : <span key={k}>{o}</span>)).reduce((a, b) => [a, " · ", b])}</span></span>
              </label>
            ))}
          </div>
          <div className="ot-grid3">
            <label className="ot-field">Unit<input type="number" min="1" value={meta.unit} onChange={(e) => setMeta({ ...meta, unit: e.target.value })} /></label>
            <label className="ot-field">CO<select value={meta.outcome} onChange={(e) => setMeta({ ...meta, outcome: e.target.value })}><option value="">Not set</option>{subject.outcomes.map((o) => <option key={o.id} value={o.id}>{o.code}</option>)}</select></label>
            <label className="ot-field">Difficulty<select value={meta.difficulty} onChange={(e) => setMeta({ ...meta, difficulty: e.target.value })}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
          </div>
          <div className="ot-row"><button type="button" className="ot-btn pri" disabled={busy || !draft.some((d) => d.keep)} onClick={save}>Add {draft.filter((d) => d.keep).length} to the bank</button><button type="button" className="ot-btn" onClick={() => setDraft([])}>Start again</button></div>
        </>
      )}
      {err && <p className="ot-note warn" role="status">{err}</p>}
    </section>
  );
}

// ============================================================ the test builder
const blankSection = (n) => ({ title: `Section ${String.fromCharCode(64 + n)}`, pick: "random", count: 10, units: [], kinds: ["mcq", "tf"], easy: 0, medium: 0, hard: 0, question_ids: [], marks_each: 1 });

function Builder({ teachingId, subject, test, onDone }) {
  const [s, setS] = useState(() => (test ? {
    title: test.title, duration: test.duration, opens_at: toLocal(test.opens_at), closes_at: toLocal(test.closes_at),
    shuffle_questions: test.shuffle_questions, shuffle_options: test.shuffle_options, negative_marking: test.negative_marking,
    show_answers: test.show_answers, sections: test.sections.map((x) => { const c = { ...x }; delete c.id; delete c.order; return c; }),
  } : { title: "", duration: 30, opens_at: "", closes_at: "", shuffle_questions: true, shuffle_options: true, negative_marking: false, show_answers: false, sections: [blankSection(1)] }));
  const [bank, setBank] = useState([]);
  const [check, setCheck] = useState(null);
  const [checkErr, setCheckErr] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setS((p) => ({ ...p, [k]: v }));
  const setSec = (i, patch) => setS((p) => ({ ...p, sections: p.sections.map((x, j) => (j === i ? { ...x, ...patch } : x)) }));

  useEffect(() => { API.get("online-tests/bank/", { params: { subject: subject.id } }).then((r) => setBank(r.data)); }, [subject.id]);
  const sectionsKey = JSON.stringify(s.sections);
  useEffect(() => {
    const t = setTimeout(() => {
      API.post("online-tests/tests/check/", { teaching_assignment: teachingId, sections: JSON.parse(sectionsKey) })
        .then((r) => { setCheck(r.data); setCheckErr(""); })
        .catch((er) => { setCheck(null); setCheckErr(errText(er, "")); });
    }, 400);
    return () => clearTimeout(t);
  }, [sectionsKey, teachingId]);

  const save = async (publish) => {
    setBusy(true); setErr("");
    const body = { ...s, teaching_assignment: teachingId, opens_at: fromLocal(s.opens_at), closes_at: fromLocal(s.closes_at) };
    try {
      const r = test ? await API.put(`online-tests/tests/${test.id}/`, body) : await API.post("online-tests/tests/", body);
      if (publish) await API.post(`online-tests/tests/${r.data.id}/publish/`);
      onDone(publish ? `${r.data.title} is published. Students have been told.` : `${r.data.title} saved as a draft.`);
    } catch (er) { setErr(errText(er, "Couldn't save the test.")); } finally { setBusy(false); }
  };

  const units = subject.units.length ? subject.units : [1];
  const maxCo = check ? Math.max(1, ...Object.values(check.by_outcome)) : 1;
  return (
    <div className="ot-wrap">
      <div className="ot-between">
        <div><h2 className="ot-h2" style={{ fontSize: 22 }}>{test ? `Edit · ${test.title}` : "New online test"}</h2><p className="ot-muted">{subject.subject?.code} {subject.subject?.name}</p></div>
        <div className="ot-row">
          <button type="button" className="ot-btn" onClick={() => onDone(null)}>Cancel</button>
          <button type="button" className="ot-btn" disabled={busy} onClick={() => save(false)}>Save draft</button>
          <button type="button" className="ot-btn pri" disabled={busy || (check && !check.ok)} onClick={() => save(true)}>Publish to students</button>
        </div>
      </div>
      {err && <p className="ot-note bad" role="alert">{err}</p>}
      <div className="ot-two">
        <div className="ot-main ot-stack">
          <section className="ot-card ot-stack">
            <h3 className="ot-h3">Settings</h3>
            <label className="ot-field">Title<input value={s.title} onChange={(e) => set("title", e.target.value)} placeholder="Unit 1–2 test" /></label>
            <div className="ot-grid3">
              <label className="ot-field">Opens (empty = when published)<input type="datetime-local" value={s.opens_at} onChange={(e) => set("opens_at", e.target.value)} /></label>
              <label className="ot-field">Closes (no new starts after)<input type="datetime-local" value={s.closes_at} onChange={(e) => set("closes_at", e.target.value)} /></label>
              <label className="ot-field">Time allowed (minutes)<input type="number" min="1" value={s.duration} onChange={(e) => set("duration", e.target.value)} /></label>
            </div>
            <div className="ot-grid2">
              <label className="ot-check"><input type="checkbox" checked={s.shuffle_questions} onChange={(e) => set("shuffle_questions", e.target.checked)} /> <span><b>Shuffle questions</b> for each student</span></label>
              <label className="ot-check"><input type="checkbox" checked={s.shuffle_options} onChange={(e) => set("shuffle_options", e.target.checked)} /> <span><b>Shuffle options</b> of MCQs</span></label>
              <label className="ot-check"><input type="checkbox" checked={s.negative_marking} onChange={(e) => set("negative_marking", e.target.checked)} /> <span><b>Negative marks</b> as set on each question</span></label>
              <label className="ot-check"><input type="checkbox" checked={s.show_answers} onChange={(e) => set("show_answers", e.target.checked)} /> <span><b>Students see answers</b> after results</span></label>
            </div>
            <p className="ot-muted ot-small">One sitting per student; the clock keeps running if the page is closed. Leaving the test tab is recorded.</p>
          </section>

          <section className="ot-card ot-stack">
            <div className="ot-between"><h3 className="ot-h3">Paper</h3><button type="button" className="ot-btn sm" onClick={() => set("sections", [...s.sections, blankSection(s.sections.length + 1)])}>Add section</button></div>
            {s.sections.map((sec, i) => {
              const chk = check?.sections[i];
              return (
                <div key={i} className="ot-section">
                  <div className="ot-between">
                    <label className="ot-field" style={{ flex: "1 1 200px" }}><span className="ot-sr">Section title</span><input value={sec.title} onChange={(e) => setSec(i, { title: e.target.value })} /></label>
                    <div className="ot-row">
                      {chk && <span className={`ot-chip ${chk.ok ? "grey" : "bad"}`}>{chk.count} question{chk.count === 1 ? "" : "s"} · {chk.marks} mark{chk.marks === 1 ? "" : "s"}</span>}
                      {s.sections.length > 1 && <button type="button" className="ot-link" onClick={() => set("sections", s.sections.filter((_, j) => j !== i))}>Remove section</button>}
                    </div>
                  </div>
                  <div className="ot-seg" role="group" aria-label="How questions are picked" style={{ alignSelf: "flex-start" }}>
                    <button type="button" aria-pressed={sec.pick === "random"} onClick={() => setSec(i, { pick: "random" })}>At random from the bank</button>
                    <button type="button" aria-pressed={sec.pick === "fixed"} onClick={() => setSec(i, { pick: "fixed" })}>Questions I choose</button>
                  </div>
                  {sec.pick === "random" ? (
                    <>
                      <div className="ot-row" style={{ alignItems: "flex-end" }}>
                        <label className="ot-field" style={{ width: 110 }}>How many<input type="number" min="1" value={sec.count} onChange={(e) => setSec(i, { count: Number(e.target.value) })} /></label>
                        <label className="ot-field" style={{ width: 130 }}>Marks each<input type="number" min="1" value={sec.marks_each} onChange={(e) => setSec(i, { marks_each: Number(e.target.value) })} /></label>
                        <label className="ot-field" style={{ width: 90 }}>Easy<input type="number" min="0" value={sec.easy} onChange={(e) => setSec(i, { easy: Number(e.target.value) })} /></label>
                        <label className="ot-field" style={{ width: 90 }}>Medium<input type="number" min="0" value={sec.medium} onChange={(e) => setSec(i, { medium: Number(e.target.value) })} /></label>
                        <label className="ot-field" style={{ width: 90 }}>Hard<input type="number" min="0" value={sec.hard} onChange={(e) => setSec(i, { hard: Number(e.target.value) })} /></label>
                      </div>
                      <p className="ot-muted ot-small">Easy / medium / hard: leave all at 0 for any mix, or make them add up to "How many".</p>
                      <div className="ot-row">
                        <span className="ot-muted ot-small" style={{ fontWeight: 600 }}>Units:</span>
                        {units.map((u) => <label key={u} className="ot-check"><input type="checkbox" checked={sec.units.includes(u)} onChange={() => setSec(i, { units: sec.units.includes(u) ? sec.units.filter((x) => x !== u) : [...sec.units, u] })} /> {u}</label>)}
                        <span className="ot-muted ot-small">{sec.units.length ? "" : "(none ticked = all)"}</span>
                      </div>
                      <div className="ot-row">
                        <span className="ot-muted ot-small" style={{ fontWeight: 600 }}>Types:</span>
                        {KINDS.map(([k, l]) => <label key={k} className="ot-check"><input type="checkbox" checked={sec.kinds.includes(k)} onChange={() => setSec(i, { kinds: sec.kinds.includes(k) ? sec.kinds.filter((x) => x !== k) : [...sec.kinds, k] })} /> {l}</label>)}
                      </div>
                      {chk && <p className={`ot-muted ot-small ${chk.ok ? "" : "ot-bad"}`}>{chk.ok ? `Each student gets a different ${chk.count} from the ${chk.available} that match.` : chk.problem}</p>}
                    </>
                  ) : (
                    <ChooseQuestions bank={bank} chosen={sec.question_ids} taken={s.sections.flatMap((x, j) => (j !== i ? x.question_ids : []))}
                      onChange={(ids) => setSec(i, { question_ids: ids, count: ids.length })} marksEach={sec.marks_each}
                      onMarks={(m) => setSec(i, { marks_each: m })} />
                  )}
                </div>
              );
            })}
            {checkErr && <p className="ot-note warn">{checkErr}</p>}
          </section>
        </div>

        <aside className="ot-side ot-stack">
          <section className="ot-card ot-stack">
            <h3 className="ot-h3">This paper</h3>
            <div className="ot-kv"><span>Total marks</span><b>{check ? check.total_marks : "—"}</b></div>
            <div className="ot-kv"><span>Questions</span><b>{s.sections.reduce((t, x) => t + (Number(x.count) || 0), 0)}</b></div>
            <div className="ot-kv"><span>Marked automatically</span><b>{check ? `${check.auto_marks} marks` : "—"}</b></div>
            <div className="ot-kv"><span>You mark by hand</span><b>{check ? `${check.hand_marks} marks` : "—"}</b></div>
          </section>
          {check && (
            <section className="ot-card ot-stack">
              <h3 className="ot-h3">Marks by course outcome</h3>
              {Object.entries(check.by_outcome).map(([k, v]) => (
                <div key={k} className="ot-row" style={{ flexWrap: "nowrap" }}><span style={{ width: 60 }}>{k}</span><span className="ot-bar" aria-hidden="true"><span style={{ width: `${(v * 100) / maxCo}%` }} /></span><b style={{ width: 40, textAlign: "right" }}>{v}</b></div>
              ))}
              <h3 className="ot-h3" style={{ marginTop: 6 }}>Bloom levels</h3>
              <div className="ot-row">{Object.entries(check.by_bloom).map(([k, v]) => <span key={k} className="ot-chip grey">{cap(k)} {v}</span>)}</div>
              <p className="ot-muted ot-small">Random sections show expected marks.</p>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

function ChooseQuestions({ bank, chosen, taken, onChange, marksEach, onMarks }) {
  const [q, setQ] = useState("");
  const shown = useMemo(() => bank.filter((b) => !taken.includes(b.id) && (!q || b.text.toLowerCase().includes(q.toLowerCase()))), [bank, taken, q]);
  const toggle = (id) => onChange(chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id]);
  return (
    <div className="ot-stack" style={{ gap: 8 }}>
      <div className="ot-row" style={{ alignItems: "flex-end" }}>
        <label className="ot-field" style={{ flex: "1 1 220px" }}><span className="ot-sr">Search the bank</span><input placeholder="Search the bank" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label className="ot-field" style={{ width: 170 }}>Marks each (0 = own)<input type="number" min="0" value={marksEach} onChange={(e) => onMarks(Number(e.target.value))} /></label>
      </div>
      <div className="ot-pick">
        {shown.length === 0 ? <p className="ot-muted">No questions. Add some in the question bank first.</p> : shown.map((b) => (
          <label key={b.id} className="ot-check" style={{ padding: "6px 0" }}>
            <input type="checkbox" checked={chosen.includes(b.id)} onChange={() => toggle(b.id)} />
            <span>{b.text} <span className="ot-muted ot-small">· {KIND[b.kind]} · {b.marks} mark{b.marks === 1 ? "" : "s"}{b.outcome_code ? ` · ${b.outcome_code}` : ""}</span></span>
          </label>
        ))}
      </div>
      <p className="ot-muted ot-small">{chosen.length} chosen.</p>
    </div>
  );
}

// ============================================================ live status
function Live({ testId, onBack }) {
  const [d, setD] = useState(null);
  const load = useCallback(() => API.get(`online-tests/tests/${testId}/attempts/`).then((r) => setD(r.data)), [testId]);
  useEffect(() => { load(); const t = setInterval(load, 20000); return () => clearInterval(t); }, [load]);
  if (!d) return <p className="ot-muted">Loading…</p>;
  const t = d.test;
  return (
    <div className="ot-wrap">
      <div className="ot-between">
        <div><h2 className="ot-h2" style={{ fontSize: 22 }}>{t.title}</h2>
          <p className="ot-muted">{t.submitted} submitted · {t.writing} writing now · {d.not_started.length} not started · out of {t.total_marks}</p></div>
        <div className="ot-row"><button type="button" className="ot-btn" onClick={load}>Refresh</button><button type="button" className="ot-btn" onClick={onBack}>Back to tests</button></div>
      </div>
      {t.to_mark > 0 && <p className="ot-note vio">{t.to_mark} submissions have written answers to mark. Marking comes with the next update; the scores below are the auto-marked part.</p>}
      <section className="ot-card">
        <div className="ot-table-wrap">
          <table className="ot-table">
            <thead><tr><th>Student</th><th>Status</th><th>Answered</th><th>Left the tab</th><th>Score</th></tr></thead>
            <tbody>
              {d.attempts.map((a) => (
                <tr key={a.id}>
                  <td><b>{a.roll_number}</b> {a.name}</td>
                  <td>{a.status === "submitted" ? <span className="ot-chip ok">Submitted</span> : <span className="ot-chip warn">Writing</span>}</td>
                  <td>{a.answered} / {a.questions}</td>
                  <td>{a.tab_leaves ? <span className={`ot-chip ${a.tab_leaves >= 3 ? "bad" : "warn"}`}>{a.tab_leaves}</span> : "0"}</td>
                  <td>{a.status === "submitted" ? `${a.score}${a.written_pending ? " + written" : ""}` : "—"}</td>
                </tr>
              ))}
              {d.not_started.map((s) => (
                <tr key={`n${s.student}`}><td><b>{s.roll_number}</b> {s.name}</td><td><span className="ot-chip grey">Not started</span></td><td>—</td><td>—</td><td>—</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function PreviewDialog({ data, onClose }) {
  return (
    <div className="ot-screen" role="dialog" aria-modal="true" aria-label={`Preview of ${data.test.title}`}>
      <div className="ot-screen-top">
        <div><b>Preview · {data.test.title}</b><div className="ot-muted ot-small">A sample paper as one student would get it, with the answers. Nothing is saved.</div></div>
        <button type="button" className="ot-btn" onClick={onClose}>Close preview</button>
      </div>
      <div className="ot-screen-body" style={{ flexDirection: "column", alignItems: "stretch" }}>
        {data.questions.map((q) => (
          <section key={q.n} className="ot-card ot-stack">
            <div className="ot-between"><span className="ot-chip vio">{q.section}</span><span className="ot-muted">Question {q.n} · {q.marks} mark{q.marks === 1 ? "" : "s"} · {KIND[q.kind]}</span></div>
            <p className="ot-q">{q.text}</p>
            {q.options.map((o) => {
              const right = Array.isArray(q.answer) ? q.answer.includes(o.i) : (q.kind === "tf" && ((o.i === 0) === q.answer));
              return <div key={o.i} className={`ot-ans${right ? " on" : ""}`}>{o.t}{right && <span className="ot-chip ok" style={{ marginLeft: "auto" }}>Right answer</span>}</div>;
            })}
            {q.model_answer && <p className="ot-note vio">Model answer: {q.model_answer}</p>}
          </section>
        ))}
      </div>
    </div>
  );
}

// ============================================================ WAVE 3 PART 3b: marking written answers
function Marking({ testId, onBack, onResults }) {
  const [ov, setOv] = useState(null);
  const [qid, setQid] = useState(null);
  const [data, setData] = useState(null);
  const [pos, setPos] = useState(0);
  const [marks, setMarks] = useState("");
  const [comment, setComment] = useState("");
  const [hide, setHide] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const loadOv = useCallback(() => API.get(`online-tests/tests/${testId}/marking/`).then((r) => {
    setOv(r.data);
    setQid((cur) => cur || (r.data.questions.find((x) => x.marked < x.answers) || r.data.questions[0] || {}).id || null);
  }), [testId]);
  useEffect(() => { loadOv(); }, [loadOv]);
  useEffect(() => {
    if (!qid) return;
    API.get(`online-tests/tests/${testId}/marking/${qid}/`).then((r) => {
      const rows = r.data.answers.filter((a) => !a.blank);
      const first = Math.max(0, rows.findIndex((a) => a.marks === null));
      setData({ ...r.data, answers: rows });
      setPos(first);
      setMarks(rows[first]?.marks ?? "");
      setComment(rows[first]?.comment || "");
    });
  }, [testId, qid]);

  const goTo = (n) => {
    const a = data.answers[n];
    setPos(n); setMarks(a?.marks ?? ""); setComment(a?.comment || ""); setErr("");
  };
  const save = async (next) => {
    const a = data.answers[pos];
    setBusy(true); setErr("");
    try {
      const r = await API.post(`online-tests/tests/${testId}/marking/${qid}/`, { attempt: a.attempt, marks, comment });
      const rows = data.answers.map((x, j) => (j === pos ? { ...x, marks: r.data.marks, comment: r.data.comment } : x));
      setData({ ...data, answers: rows });
      loadOv();
      if (next) {
        const after = rows.findIndex((x, j) => j > pos && x.marks === null);
        const n = after >= 0 ? after : Math.min(pos + 1, rows.length - 1);
        setPos(n); setMarks(rows[n]?.marks ?? ""); setComment(rows[n]?.comment || "");
      }
    } catch (er) { setErr(errText(er, "Couldn't save the mark.")); } finally { setBusy(false); }
  };

  if (!ov) return <p className="ot-muted">Loading…</p>;
  const a = data?.answers[pos];
  const max = a?.max || 0;
  const steps = max <= 5 ? Array.from({ length: max * 2 + 1 }, (_, i) => i / 2) : null;
  const doneQ = data ? data.answers.filter((x) => x.marks !== null).length : 0;
  return (
    <div className="ot-wrap">
      <div className="ot-between">
        <div><h2 className="ot-h2" style={{ fontSize: 22 }}>Marking · {ov.test.title}</h2>
          <p className="ot-muted">{ov.test.submitted} submitted · {ov.left ? `${ov.left} written answers left to mark` : "every written answer is marked"}</p></div>
        <div className="ot-row">
          <label className="ot-check" style={{ alignItems: "center" }}><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Hide names while marking</label>
          <button type="button" className="ot-btn" onClick={onResults}>Results</button>
          <button type="button" className="ot-btn" onClick={onBack}>Back to tests</button>
        </div>
      </div>
      {ov.questions.length === 0 ? <section className="ot-card"><p className="ot-muted">This test has no written answers to mark.</p></section> : (
        <div className="ot-two">
          <aside className="ot-card ot-side ot-stack" style={{ flex: "1 1 280px" }}>
            <h3 className="ot-h3">Mark one question at a time</h3>
            {ov.questions.map((x, n) => (
              <button key={x.id} type="button" className={`ot-test${x.id === qid ? " sel" : ""}`} style={{ textAlign: "left", font: "inherit", background: "#fff", cursor: "pointer" }}
                aria-pressed={x.id === qid} onClick={() => setQid(x.id)}>
                <span><b>Q{n + 1}</b> {x.text.length > 60 ? `${x.text.slice(0, 57)}…` : x.text}</span>
                <span className={`ot-chip ${x.marked >= x.answers ? "ok" : x.marked ? "warn" : "grey"}`}>{x.marked} / {x.answers}</span>
              </button>
            ))}
            <p className="ot-muted ot-small">Marking one question across every student keeps it even. Blank answers get 0 and aren't listed.</p>
          </aside>

          <section className="ot-card ot-main ot-stack">
            {!data ? <p className="ot-muted">Loading…</p> : data.answers.length === 0 ? <p className="ot-muted">Nobody wrote an answer to this question.</p> : (
              <>
                <div className="ot-between">
                  <span className="ot-chip vio">{max} mark{max === 1 ? "" : "s"}{data.question.outcome_code ? ` · ${data.question.outcome_code}` : ""}{data.question.bloom ? ` · ${data.question.bloom}` : ""}</span>
                  <span className="ot-muted">Answer {pos + 1} of {data.answers.length} · {hide ? `Student #${a.n}` : `${a.roll_number} ${a.name}`}
                    {a.tab_leaves > 0 && <span className={`ot-chip ${a.tab_leaves >= 3 ? "bad" : "warn"}`} style={{ marginLeft: 8 }}>Left the tab {a.tab_leaves}×</span>}</span>
                </div>
                <p className="ot-q" style={{ fontSize: 16 }}>{data.question.text}</p>
                <div style={{ border: "1px solid #E7E7EC", borderRadius: 12, padding: 14, background: "#FAFAFD", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                  <span className="ot-muted ot-small" style={{ fontWeight: 700 }}>STUDENT'S ANSWER</span><br />{a.answer}
                </div>
                <details open style={{ border: "1px solid #E7E7EC", borderRadius: 12, padding: "10px 14px" }}>
                  <summary style={{ cursor: "pointer", fontWeight: 600 }}>Model answer and marking points</summary>
                  <p style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>{data.question.model_answer || "No model answer was added to this question."}</p>
                </details>
                <div className="ot-row" style={{ alignItems: "flex-end" }}>
                  {steps ? (
                    <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
                      <legend className="ot-muted ot-small" style={{ fontWeight: 600, marginBottom: 6 }}>Marks (out of {max})</legend>
                      <div className="ot-row">{steps.map((v) => (
                        <button key={v} type="button" className={`ot-btn sm${Number(marks) === v && marks !== "" ? " pri" : ""}`} aria-pressed={Number(marks) === v && marks !== ""} onClick={() => setMarks(v)}>{v}</button>
                      ))}</div>
                    </fieldset>
                  ) : (
                    <label className="ot-field" style={{ width: 160 }}>Marks (out of {max})<input type="number" min="0" max={max} step="0.5" value={marks} onChange={(e) => setMarks(e.target.value)} /></label>
                  )}
                  <label className="ot-field" style={{ flex: "1 1 240px" }}>Comment for the student (optional)<input value={comment} onChange={(e) => setComment(e.target.value)} /></label>
                </div>
                {err && <p className="ot-note bad" role="alert">{err}</p>}
                <div className="ot-between" style={{ borderTop: "1px solid #F0F0F4", paddingTop: 14 }}>
                  <div className="ot-row">
                    <button type="button" className="ot-btn" disabled={pos === 0} onClick={() => goTo(pos - 1)}>Previous answer</button>
                    <button type="button" className="ot-btn" disabled={pos >= data.answers.length - 1} onClick={() => goTo(pos + 1)}>Next answer</button>
                  </div>
                  <div className="ot-row">
                    <span className="ot-muted ot-small">{doneQ} of {data.answers.length} marked</span>
                    <button type="button" className="ot-btn pri" disabled={busy || marks === ""} onClick={() => save(true)}>{busy ? "Saving…" : "Save and next"}</button>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

// ============================================================ WAVE 3 PART 3b: results
function Results({ testId, onBack, onMark }) {
  const [d, setD] = useState(null);
  const [msg, setMsg] = useState(null);
  const [view, setView] = useState(null);
  const load = useCallback(() => API.get(`online-tests/tests/${testId}/results/`).then((r) => setD(r.data)), [testId]);
  useEffect(() => { load(); }, [load]);
  const act = async (path, ok) => {
    setMsg(null);
    try { await API.post(`online-tests/tests/${testId}/${path}/`); setMsg({ tone: "ok", text: ok }); load(); } catch (er) { setMsg({ tone: "bad", text: errText(er, "That didn't work.") }); }
  };
  const openAnswers = (s) => API.get(`online-tests/tests/${testId}/attempts/${s.attempt}/`).then((r) => setView(r.data));
  if (!d) return <p className="ot-muted">Loading…</p>;
  const t = d.test;
  const sm = d.summary;
  const download = () => {
    const head = ["Register no.", "Name", ...d.sections.map((x) => x.title), `Total (${t.total_marks})`, "Left the tab", "Status"];
    const rows = d.students.map((s) => [s.roll_number, s.name, ...s.sections, s.score, s.tab_leaves, s.pending ? "Marking" : "Done"]);
    d.absent.forEach((s) => rows.push([s.roll_number, s.name, ...d.sections.map(() => ""), "", "", "Absent"]));
    const csv = [head, ...rows].map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url; link.download = `${t.title}-results.csv`; link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="ot-wrap">
      <div className="ot-between">
        <div><div className="ot-row"><h2 className="ot-h2" style={{ fontSize: 22 }}>Results · {t.title}</h2>
          {sm.to_mark ? <span className="ot-chip warn">{sm.to_mark} still to mark</span> : t.results_released ? <span className="ot-chip ok">Released to students</span> : <span className="ot-chip vio">All marked · not released</span>}</div>
          <p className="ot-muted">Out of {t.total_marks} · {sm.wrote} wrote it · {sm.absent} didn't{d.writing.length ? ` · ${d.writing.length} still writing` : ""}</p></div>
        <div className="ot-row">
          <button type="button" className="ot-btn" onClick={download}>Download marks</button>
          {sm.to_mark > 0 && <button type="button" className="ot-btn" onClick={onMark}>Mark answers</button>}
          {!t.results_released && <button type="button" className="ot-btn pri" disabled={sm.to_mark > 0} onClick={() => act("release", "Results released. Students and parents have been told.")}>Release results to students</button>}
          {t.results_released && <button type="button" className="ot-btn" onClick={() => act("withdraw", "Results hidden from students again.")}>Hide results</button>}
          <button type="button" className="ot-btn" onClick={onBack}>Back to tests</button>
        </div>
      </div>
      {msg && <p className={`ot-note ${msg.tone}`} role="status">{msg.text}</p>}
      <div className="ot-grid2" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        {[["Average", sm.average != null ? `${sm.average} / ${t.total_marks}` : "—"], ["Highest · lowest", sm.highest != null ? `${sm.highest} · ${sm.lowest}` : "—"],
          ["Scored under half", sm.under_half], ["Left the tab 3+ times", sm.left_tab_3]].map(([k, v]) => (
          <div key={k} className="ot-card" style={{ padding: 14 }}><span className="ot-muted ot-small">{k}</span><div style={{ fontSize: 22, fontWeight: 700 }}>{v}</div></div>
        ))}
      </div>
      <div className="ot-two">
        <section className="ot-card ot-main ot-stack">
          <h3 className="ot-h3">Students</h3>
          <div className="ot-table-wrap">
            <table className="ot-table">
              <thead><tr><th>Student</th>{d.sections.map((x, i) => <th key={i}>{x.title}{x.marks ? ` (${x.marks})` : ""}</th>)}<th>Total ({t.total_marks})</th><th>Left the tab</th><th><span className="ot-sr">Answers</span></th></tr></thead>
              <tbody>
                {d.students.map((s) => (
                  <tr key={s.attempt}>
                    <td><b>{s.roll_number}</b> {s.name}</td>
                    {s.sections.map((v, i) => <td key={i}>{v}</td>)}
                    <td><b>{s.score}</b>{s.pending && <small>marking</small>}</td>
                    <td>{s.tab_leaves ? <span className={`ot-chip ${s.tab_leaves >= 3 ? "bad" : "warn"}`}>{s.tab_leaves}</span> : 0}</td>
                    <td><button type="button" className="ot-link" onClick={() => openAnswers(s)}>Answers</button></td>
                  </tr>
                ))}
                {d.absent.map((s) => (
                  <tr key={`a${s.roll_number}${s.name}`}><td><b>{s.roll_number}</b> {s.name}</td><td colSpan={d.sections.length + 3}><span className="ot-chip grey">Absent</span></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <aside className="ot-side ot-stack">
          <section className="ot-card ot-stack">
            <h3 className="ot-h3">By course outcome</h3>
            {d.by_outcome.length === 0 ? <p className="ot-muted">No marks yet.</p> : d.by_outcome.map((c) => (
              <div key={c.code} className="ot-row" style={{ flexWrap: "nowrap" }}><span style={{ width: 60 }}>{c.code}</span><span className="ot-bar" aria-hidden="true"><span style={{ width: `${c.pct}%`, background: c.pct < 55 ? "#C06A12" : undefined }} /></span><b style={{ width: 52, textAlign: "right" }}>{c.pct}%</b></div>
            ))}
            <p className="ot-muted ot-small">Share of the marks students scored on each outcome's questions.</p>
          </section>
          <section className="ot-card ot-stack">
            <h3 className="ot-h3">Hardest questions</h3>
            {d.hardest.slice(0, 5).map((h) => (
              <div key={h.id} className="ot-kv"><span>{h.text.length > 50 ? `${h.text.slice(0, 47)}…` : h.text}</span>
                <b style={{ whiteSpace: "nowrap" }}>{h.kind === "short" || h.kind === "long" ? `${h.average} / ${h.marks}` : `${h.right_pct}% right`}</b></div>
            ))}
            <p className="ot-muted ot-small">If most students got an MCQ wrong, check its answer key in the question bank.</p>
          </section>
        </aside>
      </div>
      {view && (
        <div className="ot-screen" role="dialog" aria-modal="true" aria-label={`Answers of ${view.student.name}`}>
          <div className="ot-screen-top">
            <div><b>{view.student.roll_number} {view.student.name}</b><div className="ot-muted ot-small">{view.score} out of {t.total_marks}{view.pending ? " so far" : ""} · left the tab {view.tab_leaves} time{view.tab_leaves === 1 ? "" : "s"}</div></div>
            <button type="button" className="ot-btn" onClick={() => setView(null)}>Close</button>
          </div>
          <div className="ot-screen-body" style={{ flexDirection: "column", alignItems: "stretch" }}>
            {view.questions.map((q) => (
              <section key={q.n} className="ot-card ot-stack">
                <div className="ot-between"><span className="ot-muted">Question {q.n} · {KIND[q.kind]}</span><span className={`ot-chip ${q.awarded > 0 ? "ok" : q.awarded === null ? "warn" : "grey"}`}>{q.awarded ?? "to mark"} / {q.marks}</span></div>
                <p className="ot-q" style={{ fontSize: 16 }}>{q.text}</p>
                {q.options.length > 0 ? q.options.map((o) => {
                  const picked = Array.isArray(q.given) ? q.given.includes(o.i) : (q.kind === "tf" ? (o.i === 0) === q.given && q.given !== null && q.given !== undefined : q.given === o.i);
                  const right = Array.isArray(q.answer) ? q.answer.includes(o.i) : (q.kind === "tf" && (o.i === 0) === q.answer);
                  return <div key={o.i} className={`ot-ans${picked ? " on" : ""}`}>{o.t}{right && <span className="ot-chip ok" style={{ marginLeft: "auto" }}>Right answer</span>}{picked && !right && <span className="ot-chip bad" style={{ marginLeft: "auto" }}>Picked</span>}</div>;
                }) : <div style={{ whiteSpace: "pre-wrap", border: "1px solid #E7E7EC", borderRadius: 12, padding: 12 }}>{q.given || <span className="ot-muted">Not answered</span>}</div>}
                {q.comment && <p className="ot-note vio">Comment: {q.comment}</p>}
              </section>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
