// WAVE 3 PART 1A - Regulations (/regulations): grade scale, pass rules and
// degree class, and which admission batches follow each regulation.
// Every number is a college setting; a template is offered to start from.
//   GET/POST regulations/            GET/PUT/DELETE regulations/<id>/
//   POST regulations/<id>/default/   POST/DELETE regulations/<id>/batches/[<year>/]
import { useCallback, useEffect, useMemo, useState } from "react";
import API from "../../api";
import { errorText, num } from "./cbcsUtil";
import Shell from "./CbcsShell";

const blankGrade = { code: "", meaning: "", outcome: "pass", min_mark: "", points: "" };
const blankClass = { name: "", min_cgpa: "", first_attempt_only: false, extra_years: "" };

function NewRegulation({ regulations, onCreated, onCancel }) {
  const [name, setName] = useState("");
  const [start, setStart] = useState("template");
  const [copyFrom, setCopyFrom] = useState(regulations[0]?.id || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await API.post("regulations/", { name: name.trim(), start_from: start, copy_from: copyFrom || null });
      onCreated(r.data);
    } catch (err) {
      setError(errorText(err, "Not created. Try again."));
      setBusy(false);
    }
  };

  return (
    <form className="kb-card rg-new" onSubmit={create}>
      <h2 className="rg-h2">New regulation</h2>
      <div className="rg-row">
        <label className="rg-field">Name
          <input className="kb-input" value={name} maxLength={30} placeholder="e.g. R2025" onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="rg-start">
          <legend>Start from</legend>
          <label><input type="radio" name="rg-start" checked={start === "template"} onChange={() => setStart("template")} />
            Template <small>common grade scale and pass rules, to check and change</small></label>
          {regulations.length > 0 && (
            <label><input type="radio" name="rg-start" checked={start === "copy"} onChange={() => setStart("copy")} />
              A copy of
              <select className="kb-input rg-inline" value={copyFrom} disabled={start !== "copy"} aria-label="Regulation to copy"
                onChange={(e) => setCopyFrom(e.target.value)}>
                {regulations.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select></label>
          )}
          <label><input type="radio" name="rg-start" checked={start === "blank"} onChange={() => setStart("blank")} />
            Blank <small>fill in every rule yourself</small></label>
        </fieldset>
      </div>
      {error && <p className="rg-msg bad" role="alert">{error}</p>}
      <div className="rg-foot-actions">
        <button type="button" className="kb-btn" onClick={onCancel}>Cancel</button>
        <button type="submit" className="kb-btn kb-btn--primary" disabled={busy || !name.trim()}>{busy ? "Creating…" : "Create"}</button>
      </div>
    </form>
  );
}

function Editor({ reg, options, unassigned, onSaved, onDeleted }) {
  const [draft, setDraft] = useState(null);
  const [year, setYear] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const reset = useCallback(() => {
    setDraft({
      name: reg.name, description: reg.description || "",
      arrears_in_gpa: reg.arrears_in_gpa, reattempt_internal: reg.reattempt_internal,
      pass_rules: reg.pass_rules.map((p) => ({ ...p, min_end_pct: num(p.min_end_pct), min_total_pct: num(p.min_total_pct) })),
      grades: reg.grades.map((g) => ({ ...g, min_mark: num(g.min_mark), points: num(g.points) })),
      classes: reg.classes.map((c) => ({ ...c, min_cgpa: num(c.min_cgpa), extra_years: c.extra_years ?? "" })),
    });
  }, [reg]);
  useEffect(() => { reset(); }, [reset]);

  // each pass grade runs up to the next one's start (the top one to 100)
  const upTo = useMemo(() => {
    if (!draft) return {};
    const passes = draft.grades.map((g, i) => ({ ...g, i }))
      .filter((g) => g.outcome === "pass" && g.min_mark !== "" && !Number.isNaN(Number(g.min_mark)))
      .sort((a, b) => Number(b.min_mark) - Number(a.min_mark));
    const out = {};
    let top = 100;
    passes.forEach((g) => { out[g.i] = top; top = Number(g.min_mark) - 1; });
    return out;
  }, [draft]);

  if (!draft) return null;
  const ro = !reg.can_edit;
  const set = (patch) => setDraft({ ...draft, ...patch });
  const setRow = (key, i, patch) => set({ [key]: draft[key].map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const dropRow = (key, i) => set({ [key]: draft[key].filter((_, j) => j !== i) });

  const call = async (fn, ok) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fn();
      if (ok) setMsg({ tone: "ok", text: ok });
      onSaved(r?.data);
    } catch (err) {
      setMsg({ tone: "bad", text: errorText(err, "Not saved. Try again.") });
    } finally {
      setBusy(false);
    }
  };

  const save = () => call(() => API.put(`regulations/${reg.id}/`, {
    ...draft,
    classes: draft.classes.map((c) => ({ ...c, extra_years: c.extra_years === "" ? null : c.extra_years })),
  }), "Regulation saved.");
  const addBatch = () => {
    if (!/^\d{4}$/.test(year.trim())) { setMsg({ tone: "bad", text: "Give the batch's admission year, like 2024." }); return; }
    call(() => API.post(`regulations/${reg.id}/batches/`, { batch_year: Number(year) }), `Batch ${year} now follows ${reg.name}.`)
      .then(() => setYear(""));
  };
  const removeBatch = (y) => call(() => API.delete(`regulations/${reg.id}/batches/${y}/`), `Batch ${y} now follows the default regulation.`);
  const makeDefault = () => call(() => API.post(`regulations/${reg.id}/default/`), `${reg.name} is now the default.`);
  const remove = async () => {
    if (!window.confirm(`Delete ${reg.name}? This cannot be undone.`)) return;
    try {
      await API.delete(`regulations/${reg.id}/`);
      onDeleted();
    } catch (err) {
      setMsg({ tone: "bad", text: errorText(err, "Not deleted.") });
    }
  };

  const input = (value, onChange, label, extra = {}) => (
    <input className="kb-input rg-num" aria-label={label} value={value} disabled={ro} inputMode="decimal"
      onChange={(e) => onChange(e.target.value)} {...extra} />
  );

  return (
    <div className="rg-editor">
      <section className="kb-card">
        <div className="rg-head">
          <div className="rg-row">
            <label className="rg-field">Name
              <input className="kb-input" value={draft.name} maxLength={30} disabled={ro} onChange={(e) => set({ name: e.target.value })} />
            </label>
            <label className="rg-field rg-grow">Description
              <input className="kb-input" value={draft.description} maxLength={200} disabled={ro} placeholder="Optional"
                onChange={(e) => set({ description: e.target.value })} />
            </label>
          </div>
          {!ro && (
            <div className="rg-head-actions">
              {!reg.is_default && <button type="button" className="kb-btn" disabled={busy} onClick={makeDefault}>Make default</button>}
              {!reg.can_delete_reason && <button type="button" className="kb-btn" disabled={busy} onClick={remove}>Delete</button>}
            </div>
          )}
        </div>
        <h2 className="rg-h2">Batches that follow it</h2>
        <div className="rg-chips">
          {reg.batches.length === 0 && <span className="rg-muted">{reg.is_default ? "Every batch not given another regulation." : "No batch yet."}</span>}
          {reg.batches.map((y) => (
            <span key={y} className="rg-chip">{y}–{y + 4}
              {!ro && <button type="button" aria-label={`Remove batch ${y}`} onClick={() => removeBatch(y)}>×</button>}
            </span>
          ))}
        </div>
        {!ro && (
          <div className="rg-row rg-batch-add">
            <label className="rg-field">Admission year
              <input className="kb-input rg-num" value={year} inputMode="numeric" placeholder="2024" onChange={(e) => setYear(e.target.value)} />
            </label>
            <button type="button" className="kb-btn" disabled={busy} onClick={addBatch}>Assign batch</button>
          </div>
        )}
        {reg.is_default && unassigned.length > 0 && (
          <p className="rg-muted">Batches with students and no regulation of their own follow this default: {unassigned.join(", ")}.</p>
        )}
        <p className="rg-muted">{reg.students} student{reg.students === 1 ? "" : "s"} in the batches listed · {reg.subjects} subject{reg.subjects === 1 ? "" : "s"} set to this regulation.</p>
      </section>

      <section className="kb-card">
        <h2 className="rg-h2">Marks split and pass rules</h2>
        <div className="rg-table-wrap">
          <table className="rg-table">
            <thead><tr><th>Subject type</th><th>Internal marks</th><th>End-semester marks</th><th>Pass needs end-sem at least</th><th>Pass needs total at least</th></tr></thead>
            <tbody>
              {draft.pass_rules.map((p, i) => (
                <tr key={p.kind}>
                  <td><b>{p.kind_label}</b></td>
                  <td>{input(p.internal_max, (v) => setRow("pass_rules", i, { internal_max: v }), `${p.kind_label}: internal marks`)}</td>
                  <td>{input(p.end_max, (v) => setRow("pass_rules", i, { end_max: v }), `${p.kind_label}: end-semester marks`)}</td>
                  <td>{input(p.min_end_pct, (v) => setRow("pass_rules", i, { min_end_pct: v }), `${p.kind_label}: pass mark in end-semester`)} %</td>
                  <td>{input(p.min_total_pct, (v) => setRow("pass_rules", i, { min_total_pct: v }), `${p.kind_label}: pass mark in total`)} %</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="rg-row">
          <label className="rg-field">Arrear subjects in SGPA / CGPA
            <select className="kb-input" value={draft.arrears_in_gpa} disabled={ro} onChange={(e) => set({ arrears_in_gpa: e.target.value })}>
              {options.arrears_in_gpa.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="rg-field">Internal mark in a later attempt
            <select className="kb-input" value={draft.reattempt_internal} disabled={ro} onChange={(e) => set({ reattempt_internal: e.target.value })}>
              {options.reattempt_internal.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        </div>
        <p className="rg-muted">Internal comes from the IA marks already entered; the end-semester mark is entered by the exam cell.</p>
      </section>

      <section className="kb-card">
        <div className="rg-head">
          <h2 className="rg-h2">Grade scale</h2>
          {!ro && <button type="button" className="kb-btn kb-btn--sm" onClick={() => set({ grades: [...draft.grades, { ...blankGrade }] })}>+ Add grade</button>}
        </div>
        <div className="rg-table-wrap">
          <table className="rg-table">
            <thead><tr><th>Grade</th><th>Meaning</th><th>Counts as</th><th>Total marks</th><th>Grade points</th>{!ro && <th><span className="rg-sr">Remove</span></th>}</tr></thead>
            <tbody>
              {draft.grades.length === 0 && <tr><td colSpan={6} className="rg-muted">No grades yet. Add the grade scale, with one “Arrear · write again” grade (RA).</td></tr>}
              {draft.grades.map((g, i) => (
                <tr key={i}>
                  <td><input className="kb-input rg-code" aria-label="Grade code" value={g.code} maxLength={4} disabled={ro}
                    onChange={(e) => setRow("grades", i, { code: e.target.value.toUpperCase() })} /></td>
                  <td><input className="kb-input" aria-label="Meaning" value={g.meaning} maxLength={60} disabled={ro}
                    onChange={(e) => setRow("grades", i, { meaning: e.target.value })} /></td>
                  <td><select className="kb-input rg-outcome" aria-label="Counts as" value={g.outcome} disabled={ro}
                    onChange={(e) => setRow("grades", i, { outcome: e.target.value })}>
                    {options.outcomes.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select></td>
                  <td className="rg-nowrap">{g.outcome === "pass"
                    ? <>{input(g.min_mark, (v) => setRow("grades", i, { min_mark: v }), `Grade ${g.code}: marks from`)} to {upTo[i] ?? "…"}</>
                    : <span className="rg-muted">{g.outcome === "fail" ? "below the pass mark" : "given by hand"}</span>}</td>
                  <td>{g.outcome === "pass"
                    ? input(g.points, (v) => setRow("grades", i, { points: v }), `Grade ${g.code}: grade points`)
                    : <span className="rg-muted">{g.outcome === "excluded" ? "not counted" : "0"}</span>}</td>
                  {!ro && <td><button type="button" className="kb-btn kb-btn--sm" aria-label={`Remove grade ${g.code}`} onClick={() => dropRow("grades", i)}>×</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="kb-card">
        <div className="rg-head">
          <h2 className="rg-h2">Degree class</h2>
          {!ro && <button type="button" className="kb-btn kb-btn--sm" onClick={() => set({ classes: [...draft.classes, { ...blankClass }] })}>+ Add class</button>}
        </div>
        <div className="rg-table-wrap">
          <table className="rg-table">
            <thead><tr><th>Class</th><th>CGPA at least</th><th>All passed at first attempt</th><th>Within normal duration plus</th>{!ro && <th><span className="rg-sr">Remove</span></th>}</tr></thead>
            <tbody>
              {draft.classes.length === 0 && <tr><td colSpan={5} className="rg-muted">No degree classes yet.</td></tr>}
              {draft.classes.map((c, i) => (
                <tr key={i}>
                  <td><input className="kb-input rg-name" aria-label="Class name" value={c.name} maxLength={60} disabled={ro}
                    onChange={(e) => setRow("classes", i, { name: e.target.value })} /></td>
                  <td>{input(c.min_cgpa, (v) => setRow("classes", i, { min_cgpa: v }), "Minimum CGPA")}</td>
                  <td><input type="checkbox" aria-label="First attempt only" checked={!!c.first_attempt_only} disabled={ro}
                    onChange={(e) => setRow("classes", i, { first_attempt_only: e.target.checked })} /></td>
                  <td className="rg-nowrap">{input(c.extra_years, (v) => setRow("classes", i, { extra_years: v }), "Extra years", { placeholder: "any" })} years</td>
                  {!ro && <td><button type="button" className="kb-btn kb-btn--sm" aria-label={`Remove ${c.name || "class"}`} onClick={() => dropRow("classes", i)}>×</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="rg-muted">Classes are checked from the top. Leave “plus … years” empty for no time limit.</p>
      </section>

      {msg && <p className={`rg-msg ${msg.tone}`} role={msg.tone === "ok" ? "status" : "alert"}>{msg.text}</p>}
      {!ro && (
        <div className="rg-savebar">
          <span>Changes apply to results processed after saving. Published results keep the rules they were made with.</span>
          <span className="rg-foot-actions">
            <button type="button" className="kb-btn" disabled={busy} onClick={() => { reset(); setMsg(null); }}>Cancel</button>
            <button type="button" className="kb-btn kb-btn--primary" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save regulation"}</button>
          </span>
        </div>
      )}
    </div>
  );
}

export default function Regulations() {
  const [list, setList] = useState(null);
  const [selId, setSelId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const loadList = useCallback((pick) => {
    API.get("regulations/")
      .then((r) => {
        setList(r.data);
        const regs = r.data.regulations;
        setSelId((cur) => pick ?? (regs.find((x) => x.id === cur) ? cur : regs[0]?.id ?? null));
      })
      .catch((err) => setError(errorText(err, "Couldn't load the regulations.")));
  }, []);
  useEffect(() => { loadList(); }, [loadList]);

  useEffect(() => {
    if (!selId) return;
    API.get(`regulations/${selId}/`).then((r) => setDetail(r.data)).catch(() => setDetail(null));
  }, [selId]);

  const onSaved = (data) => {
    if (data?.id) setDetail(data);
    loadList(data?.id);
  };

  return (
    <Shell title="Regulations" subtitle="Grade scale, pass rules and degree class. Each admission batch follows one regulation."
      actions={list?.can_edit && !creating && <button type="button" className="kb-btn kb-btn--primary" onClick={() => setCreating(true)}>+ New regulation</button>}>
      {error && <section className="kb-card"><p className="rg-msg bad">{error}</p></section>}
      {!list && !error && <section className="kb-card"><p className="rg-muted">Loading…</p></section>}
      {creating && list && (
        <NewRegulation regulations={list.regulations}
          onCancel={() => setCreating(false)}
          onCreated={(reg) => { setCreating(false); setDetail(reg); loadList(reg.id); }} />
      )}
      {list && list.regulations.length === 0 && !creating && (
        <section className="kb-card"><p className="rg-muted">No regulation yet. {list.can_edit ? "Create one: the template gives a common grade scale and pass rules to check against your university's rules." : "Ask the academic admin to create one."}</p></section>
      )}
      {list && list.regulations.length > 0 && (
        <div className="rg-layout">
          <nav className="rg-list" aria-label="Regulations">
            {list.regulations.map((r) => (
              <button key={r.id} type="button" className={`rg-item${r.id === selId ? " on" : ""}`} aria-pressed={r.id === selId} onClick={() => setSelId(r.id)}>
                <span className="rg-item-top"><b>{r.name}</b>{r.is_default && <span className="kb-pill ok">Default</span>}</span>
                <span className="rg-muted">{r.batches.length} batch{r.batches.length === 1 ? "" : "es"} · {r.students} student{r.students === 1 ? "" : "s"}</span>
              </button>
            ))}
          </nav>
          {detail && detail.id === selId && <Editor key={detail.id} reg={detail} options={list.options} unassigned={list.unassigned_batches}
            onSaved={onSaved} onDeleted={() => { setDetail(null); loadList(null); setSelId(null); }} />}
        </div>
      )}
    </Shell>
  );
}
