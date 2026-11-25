// ============================================================
// CO-PO PART B - IA question paper, marks by question, CO attainment
//   IAPaperAndMarks   inside the teacher's IA screen (Results -> IA): the
//                     question paper of one IA (each question tagged to a CO)
//                     and the marks grid, question by question. The total
//                     goes to IA marks as before.
//   CoAttainmentTab   the subject page's "CO attainment" tab
//   GET/PUT ia-papers/   GET/POST ia-question-marks/   GET co-attainment/<ta>/   PUT co-attainment/<ta>/plan/
// ============================================================
import { useEffect, useState } from "react";

import API from "../../api";

const errText = (err, fallback) => {
  const d = err?.response?.data;
  if (d?.detail) return d.detail;
  if (d && typeof d === "object") return Object.values(d).flat().join(" ");
  return fallback;
};
const LEVELS = [["", "–"], ["remember", "Remember"], ["understand", "Understand"], ["apply", "Apply"],
  ["analyse", "Analyse"], ["evaluate", "Evaluate"], ["create", "Create"]];
const fmt = (n) => (n == null ? "" : Number.isInteger(n) ? String(n) : Number(n).toFixed(1).replace(/\.0$/, ""));
const blankRow = (i) => ({ id: null, label: `Q${i}`, max_marks: "", outcome: "", bloom: "" });

// ============================================================ IA paper + marks
export function IAPaperAndMarks({ ta, number, onMode }) {
  const [paper, setPaper] = useState(null);
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    API.get(`/ia-papers/?teaching_assignment=${ta}&number=${number}`)
      .then((r) => {
        if (!live) return;
        setPaper(r.data);
        onMode(r.data.questions.length > 0);
      })
      .catch((err) => live && setError(errText(err, "Could not load the question paper.")));
    return () => { live = false; };
  }, [ta, number, tick, onMode]);

  if (!paper) return error ? <div className="tb-error">{error}</div> : null;

  const startEdit = (from) => {
    const src = from || paper.questions;
    setRows(src.length ? src.map((q) => ({ id: from ? null : q.id, label: q.label, max_marks: q.max_marks,
      outcome: q.outcome ?? "", bloom: q.bloom || "" })) : [1, 2, 3].map(blankRow));
    setEditing(true);
    setNotice("");
  };
  const copyFrom = async (n) => {
    try {
      const r = await API.get(`/ia-papers/?teaching_assignment=${ta}&number=${n}`);
      if (!r.data.questions.length) { setError(`IA ${n} has no question paper to copy.`); return; }
      startEdit(r.data.questions);
    } catch (err) {
      setError(errText(err, "Could not copy."));
    }
  };
  const setRow = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const total = rows.reduce((s, r) => s + (Number(r.max_marks) || 0), 0);

  const savePaper = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await API.put(`/ia-papers/?teaching_assignment=${ta}&number=${number}`, {
        questions: rows.map((r) => ({ ...r, outcome: r.outcome || null })),
      });
      setPaper(r.data);
      onMode(r.data.questions.length > 0);
      setEditing(false);
      setNotice("Question paper saved.");
    } catch (err) {
      setError(errText(err, "Could not save the paper."));
    } finally {
      setBusy(false);
    }
  };

  const coTotals = {};
  for (const q of paper.questions) {
    const key = q.outcome_code || "No CO";
    coTotals[key] = (coTotals[key] || 0) + q.max_marks;
  }
  const others = [1, 2, 3].filter((n) => n !== Number(number));

  return (
    <div className="crg" style={{ marginBottom: 16 }}>
      {error && <div className="tb-error">{error}</div>}
      {notice && <div className="ems-notice" role="status">{notice}</div>}

      <section className="card">
        <div className="ems-head">
          <div>
            <h3>Question paper · IA {number}</h3>
            <span className="el-muted">
              {paper.questions.length
                ? `${paper.questions.length} questions · out of ${paper.max_marks}`
                : "Tag each question to a CO, then enter marks question by question. The total still goes to IA marks."}
            </span>
          </div>
          {paper.can_edit && !editing && (
            <div className="ems-actions">
              {others.map((n) => (
                <button key={n} type="button" className="btn-secondary" onClick={() => copyFrom(n)}>Copy from IA {n}</button>
              ))}
              <button type="button" className="btn-primary" onClick={() => startEdit()}>
                {paper.questions.length ? "Edit question paper" : "Set up question paper"}
              </button>
            </div>
          )}
        </div>

        {paper.cos.length === 0 && (
          <p className="el-muted">This subject has no course outcomes yet. Add them in the teaching plan to tag questions.</p>
        )}

        {editing ? (
          <>
            <div className="table-container">
              <table className="sd-tbl">
                <thead><tr><th>Question</th><th>Marks</th><th>CO</th><th>Level</th><th></th></tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td><input className="cm-in" value={r.label} aria-label="Question label" onChange={(e) => setRow(i, "label", e.target.value)} /></td>
                      <td><input className="cm-in cm-num" type="number" min="0.5" step="0.5" value={r.max_marks} aria-label={`${r.label} marks`} onChange={(e) => setRow(i, "max_marks", e.target.value)} /></td>
                      <td>
                        <select value={r.outcome} aria-label={`${r.label} CO`} onChange={(e) => setRow(i, "outcome", e.target.value)}>
                          <option value="">No CO</option>
                          {paper.cos.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
                        </select>
                      </td>
                      <td>
                        <select value={r.bloom} aria-label={`${r.label} level`} onChange={(e) => setRow(i, "bloom", e.target.value)}>
                          {LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                      </td>
                      <td><button type="button" className="btn-delete" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="ems-head" style={{ marginTop: 10 }}>
              <span className={total > 100 ? "kb-pill bad" : "kb-pill info"}>Adds up to {fmt(total)}</span>
              <div className="ems-actions">
                <button type="button" className="btn-secondary" onClick={() => setRows([...rows, blankRow(rows.length + 1)])}>+ Question</button>
                <button type="button" className="btn-edit" onClick={() => setEditing(false)}>Cancel</button>
                <button type="button" className="btn-primary" disabled={busy || !rows.length} onClick={savePaper}>
                  {busy ? "Saving…" : "Save question paper"}
                </button>
              </div>
            </div>
          </>
        ) : paper.questions.length > 0 && (
          <div className="crg-checks">
            {paper.questions.map((q) => (
              <span key={q.id} className="kb-pill">{q.label} · {fmt(q.max_marks)} · {q.outcome_code || "no CO"}</span>
            ))}
            {Object.entries(coTotals).map(([k, v]) => <span key={k} className="kb-pill info">{k}: {fmt(v)} marks</span>)}
          </div>
        )}
      </section>

      {paper.questions.length > 0 && !editing && (
        <QuestionMarks key={`${ta}-${number}-${tick}`} ta={ta} number={number} paper={paper}
          onSaved={() => { setNotice("Marks saved."); setTick((t) => t + 1); }} />
      )}
    </div>
  );
}

function QuestionMarks({ ta, number, paper, onSaved }) {
  const [data, setData] = useState(null);
  const [grid, setGrid] = useState({});        // {studentId: {absent, marks: {qid: value}}}
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    API.get(`/ia-question-marks/?teaching_assignment=${ta}&number=${number}`)
      .then((r) => {
        if (!live) return;
        setData(r.data);
        const g = {};
        for (const row of r.data.rows) g[row.student] = { absent: row.absent, marks: { ...row.marks } };
        setGrid(g);
      })
      .catch((err) => live && setError(errText(err, "Could not load the marks.")));
    return () => { live = false; };
  }, [ta, number]);

  if (!data) return error ? <div className="tb-error">{error}</div> : <div className="card"><p className="el-muted">Loading…</p></div>;

  const qs = data.questions;
  const codeOf = Object.fromEntries(paper.questions.map((q) => [q.id, q.outcome_code || "No CO"]));
  const cos = [...new Set(paper.questions.map((q) => q.outcome_code || "No CO"))];
  const coMax = Object.fromEntries(cos.map((c) => [c, paper.questions.filter((q) => (q.outcome_code || "No CO") === c)
    .reduce((s, q) => s + q.max_marks, 0)]));
  const bad = (q, v) => v !== "" && v != null && (Number.isNaN(Number(v)) || Number(v) < 0 || Number(v) > q.max_marks || (Number(v) * 2) % 1 !== 0);

  const setCell = (sid, qid, v) => setGrid({ ...grid, [sid]: { ...grid[sid], marks: { ...grid[sid].marks, [qid]: v } } });
  const toggleAbsent = (sid) => setGrid({ ...grid, [sid]: { ...grid[sid], absent: !grid[sid].absent } });

  const anyBad = data.rows.some((row) => !grid[row.student]?.absent && qs.some((q) => bad(q, grid[row.student]?.marks[q.id])));

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await API.post("/ia-question-marks/", {
        teaching_assignment: ta, number,
        records: data.rows.map((row) => ({ student: row.student, absent: grid[row.student].absent, marks: grid[row.student].marks })),
      });
      onSaved();
    } catch (err) {
      setError(errText(err, "Could not save the marks."));
    } finally {
      setBusy(false);
    }
  };

  let reached = Object.fromEntries(cos.map((c) => [c, 0]));
  const rows = data.rows.map((row) => {
    const g = grid[row.student] || { absent: false, marks: {} };
    const byCo = Object.fromEntries(cos.map((c) => [c, 0]));
    let total = 0;
    for (const q of qs) {
      const v = Number(g.marks[q.id]) || 0;
      if (!g.absent && !bad(q, g.marks[q.id])) { total += v; byCo[codeOf[q.id]] += v; }
    }
    for (const c of cos) if (!g.absent && coMax[c] && byCo[c] * 100 / coMax[c] >= 60) reached = { ...reached, [c]: reached[c] + 1 };
    return { row, g, total, byCo };
  });

  return (
    <section className="card">
      <div className="ems-head">
        <div>
          <h3>Marks by question</h3>
          <span className="el-muted">Tab moves to the next box · AB = absent · the total goes to IA marks</span>
        </div>
        {data.can_edit && (
          <button type="button" className="btn-primary" disabled={busy || anyBad} onClick={save}>{busy ? "Saving…" : "Save marks"}</button>
        )}
      </div>
      {error && <div className="tb-error">{error}</div>}
      {data.locked && <p className="el-muted">This IA is locked and declared to students. Marks are read-only.</p>}
      <div className="table-container">
        <table className="sd-tbl cm-grid">
          <thead>
            <tr>
              <th>Student</th>
              {qs.map((q) => <th key={q.id}>{q.label} <span className="el-muted">/{fmt(q.max_marks)}</span></th>)}
              <th>Total /{data.max_marks}</th>
              {cos.map((c) => <th key={c}>{c}</th>)}
              <th>AB</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ row, g, total, byCo }) => (
              <tr key={row.student}>
                <td><b>{row.name}</b><div className="el-muted">{row.roll_number}</div></td>
                {qs.map((q) => (
                  <td key={q.id}>
                    {g.absent ? <span className="el-muted">AB</span> : (
                      <input className={`cm-in cm-num${bad(q, g.marks[q.id]) ? " cm-bad" : ""}`} inputMode="decimal"
                        aria-label={`${row.name} ${q.label}`} disabled={!data.can_edit}
                        value={g.marks[q.id] ?? ""} onChange={(e) => setCell(row.student, q.id, e.target.value)} />
                    )}
                  </td>
                ))}
                <td><b>{g.absent ? "AB" : fmt(total)}</b></td>
                {cos.map((c) => <td key={c} className="el-muted">{g.absent ? "–" : `${fmt(byCo[c])}/${fmt(coMax[c])}`}</td>)}
                <td>
                  <button type="button" className={`cm-ab${g.absent ? " on" : ""}`} disabled={!data.can_edit}
                    aria-pressed={g.absent} aria-label={`${row.name} absent`} onClick={() => toggleAbsent(row.student)}>AB</button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={qs.length + 2} className="el-muted">Students who reached 60% of the CO's marks</td>
              {cos.map((c) => <td key={c}><b>{reached[c]} of {rows.length}</b></td>)}
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

// ============================================================ CO attainment tab
export function CoAttainmentTab({ ta }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [plans, setPlans] = useState({});
  const [saving, setSaving] = useState(null);
  const [notice, setNotice] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    API.get(`/co-attainment/${ta}/`)
      .then((r) => {
        if (!live) return;
        setData(r.data);
        setPlans(Object.fromEntries(r.data.cos.map((c) => [c.id, c.plan])));
      })
      .catch((err) => live && setError(errText(err, "Could not work out the attainment.")));
    return () => { live = false; };
  }, [ta, tick]);

  if (!data) return error ? <div className="tb-error">{error}</div> : <div className="card"><p className="el-muted">Working it out…</p></div>;
  const rule = data.rule;
  const met = data.cos.filter((c) => c.attained).length;
  const known = data.cos.filter((c) => c.final != null).length;
  const below = data.cos.filter((c) => c.attained === false);

  const savePlan = async (co) => {
    setSaving(co);
    try {
      await API.put(`/co-attainment/${ta}/plan/`, { outcome: co, text: plans[co] || "" });
      setNotice("Action plan saved.");
    } catch (err) {
      setError(errText(err, "Could not save."));
    } finally {
      setSaving(null);
    }
  };
  // CO-PO PART C: the course exit survey
  const sv = data.survey;
  const sendSurvey = async () => {
    if (!window.confirm("Send the course exit survey to this class now? Students get 14 days to answer.")) return;
    setSaving("survey");
    setError("");
    try {
      await API.post(`/co-attainment/${ta}/survey/`);
      setNotice("Course exit survey sent to the class.");
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err, "Could not send the survey."));
    } finally {
      setSaving(null);
    }
  };
  const lv = (n) => (n == null ? <span className="el-muted">–</span> : <span className={`cm-lv l${n}`}>{n}</span>);

  return (
    <div className="crg">
      {error && <div className="tb-error">{error}</div>}
      {notice && <div className="ems-notice" role="status">{notice}</div>}
      <div className="crg-stats">
        <div className="card"><span className="el-muted">COs attained</span><b>{known ? `${met} of ${known}` : "–"}</b></div>
        <div className="card"><span className="el-muted">Target level</span><b>{rule.co_target}</b></div>
        <div className="card"><span className="el-muted">End-semester results</span><b>{data.end_published ? "Published" : "Not yet"}</b></div>
        <div className="card">
          <span className="el-muted">Course exit survey</span>
          <b>{sv ? `${sv.responses} of ${sv.students}` : "Not sent"}</b>
          {sv && <span className="el-muted">{sv.rate}% answered · {sv.counted ? "counted" : `counts from ${rule.survey_min_pct}%`}</span>}
          {!sv && data.can_edit && data.cos.length > 0 && (
            <button type="button" className="btn-secondary" disabled={saving === "survey"} onClick={sendSurvey}>Send to the class</button>
          )}
        </div>
      </div>

      {data.cos.length === 0 ? (
        <div className="card"><p className="el-muted">This subject has no course outcomes yet. Add them in the teaching plan.</p></div>
      ) : (
        <section className="card">
          <h3>Attainment by course outcome</h3>
          <div className="table-container">
            <table className="sd-tbl">
              <thead>
                <tr>
                  <th>Course outcome</th>
                  <th>Internal<div className="el-muted">% reached {rule.student_target_pct}%</div></th>
                  <th>End semester<div className="el-muted">% scored ≥ {rule.student_target_pct}%</div></th>
                  <th>Direct<div className="el-muted">{rule.internal_share}% int + {100 - rule.internal_share}% end</div></th>
                  <th>Exit survey<div className="el-muted">out of 3</div></th>
                  <th>Final<div className="el-muted">{rule.direct_share}% direct + {100 - rule.direct_share}% survey</div></th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.cos.map((c) => (
                  <tr key={c.id}>
                    <td className="cm-co"><b>{c.code}</b> <span className="el-muted">{c.text}</span></td>
                    <td>{c.internal ? <>{lv(c.internal.level)} <span className="el-muted">{c.internal.pct}% · {c.internal.reached}/{c.internal.students}</span></> : <span className="el-muted">No marks yet</span>}</td>
                    <td>{c.end ? <>{lv(c.end.level)} <span className="el-muted">{c.end.pct}%</span></> : <span className="el-muted">Not published</span>}</td>
                    <td><b>{c.direct ?? "–"}</b></td>
                    <td>{c.survey ?? <span className="el-muted">–</span>}</td>
                    <td><b>{c.final ?? "–"}</b></td>
                    <td>{c.attained == null ? null : <span className={`kb-pill ${c.attained ? "ok" : "bad"}`}>{c.attained ? "Attained" : "Below target"}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="el-muted">
            Level 3 = {rule.level3_pct}% or more of students reached {rule.student_target_pct}% of that CO's marks · Level 2 = {rule.level2_pct}% · Level 1 = {rule.level1_pct}%.
            The end-semester result has no marks by question, so it counts the same for every CO. Until results are published, internal marks alone are shown.
            The exit survey (rated 1 to 5, shown out of 3) joins the final once {rule.survey_min_pct}% of the class has answered.
          </p>
        </section>
      )}

      <div className="crg-cols">
        <section className="card crg-main">
          <h3>Where the internal marks came from</h3>
          {data.sources.length === 0 ? (
            <p className="el-muted">No IA with a question paper, and no online test with CO-tagged questions, yet.</p>
          ) : (
            <div className="table-container">
              <table className="sd-tbl">
                <thead><tr><th>Assessment</th>{data.cos.map((c) => <th key={c.id}>{c.code}</th>)}</tr></thead>
                <tbody>
                  {data.sources.map((s) => (
                    <tr key={s.name}>
                      <td>{s.name}</td>
                      {data.cos.map((c) => <td key={c.id}>{s.by_co[c.id] ? `${fmt(s.by_co[c.id])} marks` : "–"}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        {below.length > 0 && (
          <section className="card crg-side cm-plan">
            <h3>Below target: what will you do?</h3>
            {below.map((c) => (
              <label key={c.id} className="crg-field">
                {c.code} action plan (goes into the NBA course file)
                <textarea rows={3} value={plans[c.id] || ""} disabled={!data.can_edit}
                  onChange={(e) => setPlans({ ...plans, [c.id]: e.target.value })} />
                {data.can_edit && (
                  <span className="ems-actions">
                    <button type="button" className="btn-primary" disabled={saving === c.id} onClick={() => savePlan(c.id)}>Save</button>
                  </span>
                )}
              </label>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
