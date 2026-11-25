// ============================================================
// CO-PO PART A - Outcomes (/outcomes): POs and PSOs, the CO-PO mapping of
// each subject, and the attainment rules. One page, three tabs.
//   GET/POST outcomes/programme/?course=    PATCH/DELETE outcomes/programme/<id>/
//   POST outcomes/programme/standard/       GET outcomes/subjects/?course=
//   GET/PUT outcomes/mapping/<subject>/     GET/PUT/DELETE outcomes/rules/?department=
// The server decides who may change what; this page shows what it sends back.
// ============================================================
import { useEffect, useState } from "react";

import API from "../../api";
import Shell from "../regulations/CbcsShell";

const errText = (err, fallback) => {
  const d = err?.response?.data;
  if (d?.detail) return d.detail;
  if (d && typeof d === "object") return Object.values(d).flat().join(" ");
  return fallback;
};

const TABS = [["programme", "POs and PSOs"], ["mapping", "CO–PO mapping"], ["attainment", "Attainment"], ["rules", "Rules"]];

export default function Outcomes() {
  const [tab, setTab] = useState(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    return TABS.some(([k]) => k === t) ? t : "programme";
  });
  const [courses, setCourses] = useState([]);
  const [course, setCourse] = useState("");

  useEffect(() => {
    API.get("/courses/")
      .then((r) => {
        const list = r.data.results || r.data;
        setCourses(list);
        if (list.length) setCourse((c) => c || String(list[0].id));
      })
      .catch(() => setCourses([]));
  }, []);

  return (
    <Shell title="Outcomes" subtitle="Programme outcomes, how each subject's course outcomes map to them, and the attainment rules.">
      <div className="oc-bar">
        <div className="ems-seg crg-tabs" role="tablist">
          {TABS.map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""}
              onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>
        {tab !== "rules" && courses.length > 0 && (
          <label className="oc-pick">Course
            <select value={course} onChange={(e) => setCourse(e.target.value)}>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {tab === "programme" && <ProgrammeTab key={course} course={course} />}
      {tab === "mapping" && <MappingTab key={course} course={course} />}
      {tab === "attainment" && <AttainmentTab key={course} course={course} />}
      {tab === "rules" && <RulesTab />}
    </Shell>
  );
}

// ============================================================ POs / PSOs
function ProgrammeTab({ course }) {
  const [data, setData] = useState(null);
  const [tick, setTick] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [newPso, setNewPso] = useState("");
  const [newPo, setNewPo] = useState("");
  const [editing, setEditing] = useState(null);     // {id, text}

  useEffect(() => {
    let live = true;
    API.get(`/outcomes/programme/?course=${course || ""}`)
      .then((r) => live && setData(r.data))
      .catch((err) => live && setError(errText(err, "Could not load the outcomes.")));
    return () => { live = false; };
  }, [course, tick]);

  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      setEditing(null);
      setTick((t) => t + 1);
      return true;
    } catch (err) {
      setError(errText(err, "Could not save."));
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (!data) return error ? <div className="tb-error">{error}</div> : <div className="card"><p className="el-muted">Loading…</p></div>;

  const list = (rows, canEdit) => (
    <ul className="oc-list">
      {rows.map((p) => (
        <li key={p.id}>
          <b>{p.code}</b>
          {editing?.id === p.id ? (
            <form className="oc-inline" onSubmit={(e) => { e.preventDefault(); run(() => API.patch(`/outcomes/programme/${p.id}/`, { text: editing.text })); }}>
              <input value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} aria-label={`${p.code} text`} />
              <button type="submit" className="btn-primary" disabled={busy}>Save</button>
              <button type="button" className="btn-edit" onClick={() => setEditing(null)}>Cancel</button>
            </form>
          ) : (
            <span>{p.text}</span>
          )}
          {canEdit && editing?.id !== p.id && (
            <span className="oc-row-actions">
              <button type="button" className="btn-edit" onClick={() => setEditing({ id: p.id, text: p.text })}>Edit</button>
              <button type="button" className="btn-delete" disabled={busy}
                title={p.links ? `${p.links} CO(s) mapped` : undefined}
                onClick={() => window.confirm(`Delete ${p.code}?`) && run(() => API.delete(`/outcomes/programme/${p.id}/`))}>
                Delete
              </button>
            </span>
          )}
        </li>
      ))}
    </ul>
  );

  return (
    <div className="crg-cols">
      {error && <div className="tb-error" style={{ flexBasis: "100%" }}>{error}</div>}
      <section className="card crg-main">
        <div className="ems-head">
          <div>
            <h3>Programme outcomes (POs)</h3>
            <span className="el-muted">The same for every programme in the college.</span>
          </div>
          {data.can_edit_pos && data.pos.length < 12 && (
            <button type="button" className="btn-primary" disabled={busy}
              onClick={() => run(() => API.post("/outcomes/programme/standard/"))}>
              Add the 12 standard POs
            </button>
          )}
        </div>
        {data.pos.length === 0 ? <p className="el-muted">No POs yet.</p> : list(data.pos, data.can_edit_pos)}
        {data.can_edit_pos && (
          <form className="oc-inline" onSubmit={async (e) => { e.preventDefault(); if (await run(() => API.post("/outcomes/programme/", { kind: "po", text: newPo }))) setNewPo(""); }}>
            <input value={newPo} onChange={(e) => setNewPo(e.target.value)} placeholder="Add a PO" aria-label="New PO" />
            <button type="submit" className="btn-secondary" disabled={busy || !newPo.trim()}>Add PO</button>
          </form>
        )}
      </section>
      <section className="card crg-side">
        <div>
          <h3>Programme specific outcomes (PSOs)</h3>
          <span className="el-muted">This course's own. The HOD writes them.</span>
        </div>
        {data.psos.length === 0 ? <p className="el-muted">No PSOs for this course yet.</p> : list(data.psos, data.can_edit_psos)}
        {data.can_edit_psos && (
          <form className="oc-inline" onSubmit={async (e) => { e.preventDefault(); if (await run(() => API.post("/outcomes/programme/", { kind: "pso", course, text: newPso }))) setNewPso(""); }}>
            <input value={newPso} onChange={(e) => setNewPso(e.target.value)} placeholder="Add a PSO" aria-label="New PSO" />
            <button type="submit" className="btn-secondary" disabled={busy || !newPso.trim()}>Add PSO</button>
          </form>
        )}
      </section>
    </div>
  );
}

// ============================================================ mapping grid
function MappingTab({ course }) {
  const [subjects, setSubjects] = useState(null);
  const [subjectId, setSubjectId] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    API.get(`/outcomes/subjects/?course=${course || ""}`)
      .then((r) => live && setSubjects(r.data))
      .catch(() => live && setSubjects([]));
    return () => { live = false; };
  }, [course, tick]);

  if (!subjects) return <div className="card"><p className="el-muted">Loading…</p></div>;
  const mappedCount = subjects.filter((s) => s.cos && s.mapped === s.cos).length;
  return (
    <div className="crg-cols">
      <section className="card crg-side oc-subjects">
        <h3>Subjects</h3>
        <span className="el-muted">{mappedCount} of {subjects.length} fully mapped</span>
        <ul className="ems-groups">
          {subjects.map((s) => (
            <li key={s.id}>
              <button type="button" className={`crg-win${subjectId === s.id ? " on" : ""}`} onClick={() => setSubjectId(s.id)}>
                <b>{s.code} {s.name}</b>
                <span className="el-muted">Semester {s.semester} · {s.cos ? `${s.mapped} of ${s.cos} COs mapped` : "no COs yet"}</span>
                <span className={`kb-pill ${s.cos && s.mapped === s.cos ? "ok" : s.mapped ? "warn" : ""}`}>
                  {s.cos && s.mapped === s.cos ? "Done" : s.mapped ? "Part" : "To do"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      <div className="crg-main">
        {subjectId ? <MappingGrid key={subjectId} subjectId={subjectId} onSaved={() => setTick((t) => t + 1)} />
          : <div className="card"><p className="el-muted">Choose a subject.</p></div>}
      </div>
    </div>
  );
}

function MappingGrid({ subjectId, onSaved }) {
  const [data, setData] = useState(null);
  const [cells, setCells] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let live = true;
    API.get(`/outcomes/mapping/${subjectId}/`)
      .then((r) => { if (live) { setData(r.data); setCells(r.data.cells); } })
      .catch((err) => live && setError(errText(err, "Could not load the mapping.")));
    return () => { live = false; };
  }, [subjectId]);

  if (!data) return error ? <div className="tb-error">{error}</div> : <div className="card"><p className="el-muted">Loading…</p></div>;

  const cycle = (key) => {
    if (!data.can_edit) return;
    const next = ((cells[key] || 0) + 1) % 4;
    const copy = { ...cells };
    if (next) copy[key] = next; else delete copy[key];
    setCells(copy);
    setNotice("");
  };
  const avg = (po) => {
    const vals = data.cos.map((co) => cells[`${co.id}-${po.id}`]).filter(Boolean);
    return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : "–";
  };
  const changed = JSON.stringify(cells) !== JSON.stringify(data.cells);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const body = Object.entries(cells).map(([k, v]) => {
        const [co, po] = k.split("-");
        return { co: Number(co), po: Number(po), strength: v };
      });
      const r = await API.put(`/outcomes/mapping/${subjectId}/`, { cells: body });
      setData(r.data);
      setCells(r.data.cells);
      setNotice("Mapping saved.");
      onSaved();
    } catch (err) {
      setError(errText(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <div className="ems-head">
        <div>
          <h3>{data.subject.code} {data.subject.name}</h3>
          <span className="el-muted">
            Semester {data.subject.semester}{data.can_edit ? " · click a box: – → 1 → 2 → 3" : " · view only"}
          </span>
        </div>
        {data.can_edit && (
          <button type="button" className="btn-primary" disabled={busy || !changed} onClick={save}>
            {busy ? "Saving…" : "Save mapping"}
          </button>
        )}
      </div>
      {error && <div className="tb-error">{error}</div>}
      {notice && <div className="ems-notice" role="status">{notice}</div>}
      {data.cos.length === 0 ? (
        <p className="el-muted">This subject has no course outcomes yet. Its teacher adds them in the teaching plan (Course outcomes).</p>
      ) : data.columns.length === 0 ? (
        <p className="el-muted">No POs yet. Add them in the POs and PSOs tab.</p>
      ) : (
        <>
          <div className="table-container">
            <table className="oc-grid">
              <thead>
                <tr><th className="oc-co">CO</th>{data.columns.map((p) => <th key={p.id} title={p.text}>{p.code}</th>)}</tr>
              </thead>
              <tbody>
                {data.cos.map((co) => (
                  <tr key={co.id}>
                    <td className="oc-co"><b>{co.code}</b> <span className="el-muted">{co.text}</span></td>
                    {data.columns.map((p) => {
                      const key = `${co.id}-${p.id}`;
                      const v = cells[key] || 0;
                      return (
                        <td key={p.id}>
                          <button type="button" className={`oc-cell${v ? ` m${v}` : ""}`} disabled={!data.can_edit}
                            aria-label={`${co.code} to ${p.code}: ${v || "none"}`} onClick={() => cycle(key)}>
                            {v || "–"}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr>
                  <td className="oc-co el-muted">Average</td>
                  {data.columns.map((p) => <td key={p.id} className="el-muted">{avg(p)}</td>)}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="el-muted">1 = low · 2 = medium · 3 = high. The subject's teachers and its HOD can change this.</p>
        </>
      )}
    </section>
  );
}

// ============================================================ rules
const NUM_FIELDS = [
  ["student_target_pct", "A student reaches a CO at (% of that CO's marks)"],
  ["level3_pct", "Level 3 when at least this % of students reach it"],
  ["level2_pct", "Level 2 at"],
  ["level1_pct", "Level 1 at"],
  ["internal_share", "Internal share of direct attainment (%)"],
  ["direct_share", "Direct share of the final (rest = exit survey) (%)"],
  ["co_target", "Target level for every CO (0 to 3)"],
  ["po_target", "Target level for every PO (0 to 3)"],
  ["survey_min_pct", "Exit survey counts when at least this % respond"],
];
const BOOL_FIELDS = [["use_ia", "IA tests (question-wise)"], ["use_online_tests", "Online tests"], ["use_assignments", "Assignments"]];

function RulesTab() {
  const [departments, setDepartments] = useState([]);
  const [dept, setDept] = useState("");
  const [rule, setRule] = useState(null);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    API.get("/users/departments/").then((r) => setDepartments(r.data.results || r.data)).catch(() => setDepartments([]));
  }, []);
  useEffect(() => {
    let live = true;
    API.get(`/outcomes/rules/${dept ? `?department=${dept}` : ""}`)
      .then((r) => { if (live) { setRule(r.data); setErrors({}); setNotice(""); } })
      .catch((err) => live && setErrors({ detail: errText(err, "Could not load the rules.") }));
    return () => { live = false; };
  }, [dept]);

  if (!rule) return errors.detail ? <div className="tb-error">{errors.detail}</div> : <div className="card"><p className="el-muted">Loading…</p></div>;
  const q = dept ? `?department=${dept}` : "";
  const set = (k) => (e) => setRule({ ...rule, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const send = async (method) => {
    setBusy(true);
    setErrors({});
    try {
      const r = method === "delete" ? await API.delete(`/outcomes/rules/${q}`) : await API.put(`/outcomes/rules/${q}`, rule);
      setRule({ ...r.data, can_edit: rule.can_edit });
      setNotice(method === "delete" ? "This department now follows the college rules." : "Rules saved.");
    } catch (err) {
      const d = err?.response?.data || {};
      setErrors(d.detail ? { detail: d.detail } : d);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="crg-cols">
      <section className="card crg-main">
        <div className="ems-head">
          <div>
            <h3>{dept ? "Department rules" : "College rules"}</h3>
            <span className="el-muted">
              {dept && rule.inherited ? "This department follows the college rules. Save to give it its own." : "The numbers attainment is worked out with."}
            </span>
          </div>
          <label className="oc-pick">For
            <select value={dept} onChange={(e) => setDept(e.target.value)}>
              <option value="">The whole college</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
        </div>
        {errors.detail && <div className="tb-error">{errors.detail}</div>}
        {notice && <div className="ems-notice" role="status">{notice}</div>}
        <fieldset className="crg-fieldset" disabled={!rule.can_edit}>
          <div className="ems-form">
            {NUM_FIELDS.map(([k, label]) => (
              <label key={k}>{label}
                <input type="number" step={k.endsWith("target") ? "0.1" : "1"} value={rule[k]} onChange={set(k)} />
                {errors[k] && <small className="crg-err">{[].concat(errors[k]).join(" ")}</small>}
              </label>
            ))}
            <div className="ems-wide">
              <span className="crg-label">Internal marks come from</span>
              <div className="crg-checks">
                {BOOL_FIELDS.map(([k, label]) => (
                  <label key={k} className="crg-check"><input type="checkbox" checked={rule[k]} onChange={set(k)} /> {label}</label>
                ))}
              </div>
              {errors.use_ia && <small className="crg-err">{errors.use_ia}</small>}
            </div>
          </div>
        </fieldset>
        {rule.can_edit && (
          <div className="ems-actions">
            {dept && !rule.inherited && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => send("delete")}>Use the college rules</button>
            )}
            <button type="button" className="btn-primary" disabled={busy} onClick={() => send("put")}>Save rules</button>
          </div>
        )}
      </section>
      <aside className="card crg-side">
        <h3>How it works</h3>
        <p>A student reaches a CO when they score at least {rule.student_target_pct}% of that CO's marks.</p>
        <p>
          The CO's level is 3 when {rule.level3_pct}% or more of the students reach it, 2 at {rule.level2_pct}%,
          and 1 at {rule.level1_pct}%.
        </p>
        <p>
          Direct = {rule.internal_share}% internal + {100 - Number(rule.internal_share || 0)}% end semester.
          Final = {rule.direct_share}% direct + {100 - Number(rule.direct_share || 0)}% course exit survey.
        </p>
        <p>A CO is attained at level {rule.co_target} or above.</p>
      </aside>
    </div>
  );
}

// ============================================================ CO-PO PART C: PO / PSO attainment
function AttainmentTab({ course }) {
  const [batch, setBatch] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!course) return undefined;
    let live = true;
    API.get(`/po-attainment/?course=${course}${batch ? `&batch=${batch}` : ""}`)
      .then((r) => { if (live) { setData(r.data); setError(""); } })
      .catch((err) => live && setError(errText(err, "Could not work out the attainment.")));
    return () => { live = false; };
  }, [course, batch]);

  const download = async () => {
    setBusy(true);
    try {
      const r = await API.get(`/po-attainment/export/?course=${course}${batch ? `&batch=${batch}` : ""}`, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(r.data);
      a.download = "co-po-attainment.xlsx";
      a.click();
    } catch (err) {
      setError(errText(err, "Could not download."));
    } finally {
      setBusy(false);
    }
  };

  if (error) return <div className="tb-error">{error}</div>;
  if (!data) return <div className="card"><p className="el-muted">Working it out… this reads every subject's marks.</p></div>;
  const below = data.overall.filter((o) => o.attained === false);
  return (
    <div className="crg">
      <div className="ems-head">
        <label className="oc-pick">Batch
          <select value={batch} onChange={(e) => { setData(null); setBatch(e.target.value); }}>
            <option value="">All students</option>
            {data.batches.map((b) => <option key={b} value={b}>{b} batch</option>)}
          </select>
        </label>
        <button type="button" className="btn-secondary" disabled={busy} onClick={download}>
          {busy ? "Preparing…" : "Download NBA tables (Excel)"}
        </button>
      </div>

      {data.left_out.length > 0 && (
        <div className="card oc-warn">
          <b>{data.left_out.length} subject{data.left_out.length === 1 ? " is" : "s are"} left out:</b>{" "}
          {data.left_out.map((x) => `${x.subject} (${x.why})`).join(" · ")}
        </div>
      )}

      <section className="card">
        <div className="ems-head"><h3>Attainment against target {data.po_target}</h3><span className="el-muted">out of 3</span></div>
        {data.overall.length === 0 ? <p className="el-muted">No POs yet. Add them in the POs and PSOs tab.</p> : (
          <div className="oc-tiles">
            {data.overall.map((o) => (
              <div key={o.id} className={`oc-tile ${o.value == null ? "na" : o.attained ? "hi" : "lo"}`} title={o.text}>
                <b>{o.code}</b>
                <span className="oc-tile-v">{o.value == null ? "–" : o.value.toFixed(2)}</span>
                <span>{o.value == null ? "not mapped yet" : o.attained ? "attained" : "below target"}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="crg-cols">
        <section className="card crg-main">
          <h3>By subject</h3>
          {data.subjects.length === 0 ? <p className="el-muted">No subject has both a CO–PO mapping and marks by CO yet.</p> : (
            <div className="table-container">
              <table className="sd-tbl">
                <thead><tr><th>Subject</th><th>Sem</th>{data.columns.map((c) => <th key={c.id}>{c.code}</th>)}<th>COs met</th></tr></thead>
                <tbody>
                  {data.subjects.map((s) => (
                    <tr key={s.id}>
                      <td><b>{s.subject}</b></td><td>{s.semester}</td>
                      {data.columns.map((c) => <td key={c.id}>{s.values[c.id] == null ? "–" : s.values[c.id].toFixed(2)}</td>)}
                      <td>{s.cos_met} / {s.cos_total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="el-muted">Each cell: the subject's CO levels weighted by how strongly they map to that PO (1, 2, 3). Blank = not mapped.</p>
        </section>
        <aside className="crg-side">
          <section className="card">
            <h3>Below target</h3>
            {below.length === 0 ? <p className="el-muted">None.</p> : below.map((o) => (
              <div key={o.id} className="crg-line"><span><b>{o.code}</b> {o.text}</span><span className="kb-pill warn">{o.value.toFixed(2)}</span></div>
            ))}
          </section>
          <section className="card">
            <h3>COs below target</h3>
            <div className="crg-big">{data.cos_below} <span className="el-muted">of {data.cos_total}</span></div>
            <p className="el-muted">{data.cos_below_planned} have an action plan from their teacher.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
