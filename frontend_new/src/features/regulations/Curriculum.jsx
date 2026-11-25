// WAVE 3 PART 1A - Credits and categories (/curriculum): for one course and
// regulation, the credits needed in each category against the credits in the
// subject list, and every subject's category, type, L-T-P and credits.
//   GET curriculum/?course=&regulation=     PUT curriculum/requirements/
//   GET/POST course-categories/ (+ template/)   PATCH subjects/<id>/
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import API from "../../api";
import ImportExport from "../../components/ImportExport";
import { errorText, num } from "./cbcsUtil";
import Shell from "./CbcsShell";

const KINDS = [["theory", "Theory"], ["practical", "Practical"], ["project", "Project"]];
const CHECK = {
  ok: ["ok", "Matches"], short: ["bad", "short"], over: ["warn", "over"], no_credit: ["info", "Pass needed"],
};

function checkLabel(c) {
  const [tone, text] = CHECK[c.check] || ["info", c.check];
  if (c.check === "short" || c.check === "over") return [tone, `${num(Math.abs(c.difference))} ${text}`];
  return [tone, text];
}

export default function Curriculum() {
  const [params, setParams] = useSearchParams();
  const [courses, setCourses] = useState([]);
  const [regs, setRegs] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [req, setReq] = useState({});                 // category id -> credits typed
  const [rows, setRows] = useState({});               // subject id -> edited fields
  const [sem, setSem] = useState(null);
  const [newCat, setNewCat] = useState(null);
  const [editCat, setEditCat] = useState(null);       // {id, name, carries_credit} while renaming
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const course = params.get("course") || "";
  const regulation = params.get("regulation") || "";

  useEffect(() => {
    API.get("courses/").then((r) => setCourses(r.data)).catch(() => setCourses([]));
    API.get("regulations/").then((r) => setRegs(r.data.regulations || [])).catch(() => setRegs([]));
  }, []);

  // default picks: the first course, the default regulation
  useEffect(() => {
    if (!course && courses.length) setParams((p) => { p.set("course", courses[0].id); return p; }, { replace: true });
  }, [course, courses, setParams]);
  useEffect(() => {
    const def = regs.find((r) => r.is_default) || regs[0];
    if (!regulation && def) setParams((p) => { p.set("regulation", def.id); return p; }, { replace: true });
  }, [regulation, regs, setParams]);

  const load = useCallback(() => {
    if (!course || !regulation) return;
    API.get(`curriculum/?course=${course}&regulation=${regulation}`)
      .then((r) => {
        setData(r.data);
        setError("");
        setReq(Object.fromEntries(r.data.categories.map((c) => [c.id, num(c.required)])));
        setRows({});
        setSem((cur) => (r.data.semesters.some((s) => s.semester === cur) ? cur : r.data.semesters[0]?.semester ?? null));
      })
      .catch((err) => { setData(null); setError(errorText(err, "Couldn't load the credits.")); });
  }, [course, regulation]);
  useEffect(() => { load(); }, [load]);

  const pick = (key, value) => setParams((p) => { p.set(key, value); return p; });
  const ro = !data?.can_edit;

  const run = async (fn, ok) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg({ tone: "ok", text: ok });
      load();
      return true;
    } catch (err) {
      setMsg({ tone: "bad", text: err?.message && !err.response ? err.message : errorText(err, "Not saved. Try again.") });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const saveRequirements = () => run(() => API.put("curriculum/requirements/", {
    course: Number(course), regulation: Number(regulation),
    items: data.categories.filter((c) => c.carries_credit).map((c) => ({ category: c.id, credits: req[c.id] === "" ? 0 : req[c.id] })),
  }), "Credits required saved.");
  // Categories are the college's own (no fixed list): add, rename, delete.
  const addCategory = (e) => {
    e.preventDefault();
    run(() => API.post("course-categories/", newCat), `${newCat.code.toUpperCase()} added.`).then((ok) => ok && setNewCat(null));
  };
  const saveCategory = () => run(
    () => API.patch(`course-categories/${editCat.id}/`, { name: editCat.name, carries_credit: editCat.carries_credit }),
    "Category saved.",
  ).then((ok) => ok && setEditCat(null));
  const deleteCategory = (c) => {
    if (!window.confirm(`Delete the category ${c.code} (${c.name})?`)) return;
    run(() => API.delete(`course-categories/${c.id}/`), `${c.code} deleted.`);
  };

  const semester = data?.semesters.find((s) => s.semester === sem);
  const edited = (s) => ({ ...s, ...(rows[s.id] || {}) });
  const editRow = (s, patch) => setRows({ ...rows, [s.id]: { ...(rows[s.id] || {}), ...patch } });
  const dirty = semester ? semester.subjects.filter((s) => rows[s.id]) : [];
  const badRow = () => {
    for (const s of dirty) {
      const e = edited(s);
      const c = Number(e.credits === "" ? 0 : e.credits);
      if (Number.isNaN(c) || c < 0 || c > 30 || !Number.isInteger(c * 2)) return `${s.code || s.name}: credits must be whole or half (like 3 or 1.5), 0 to 30.`;
      for (const [k, l] of [["lecture_hours", "L"], ["tutorial_hours", "T"], ["practical_hours", "P"]]) {
        const h = Number(e[k] === "" ? 0 : e[k]);
        if (!Number.isInteger(h) || h < 0 || h > 40) return `${s.code || s.name}: ${l} must be a whole number of hours, 0 to 40.`;
      }
    }
    return "";
  };
  const saveSubjects = () => {
    const problem = badRow();
    if (problem) { setMsg({ tone: "bad", text: problem }); return; }
    return saveDirty();
  };
  const saveDirty = () => run(async () => {
    for (const s of dirty) {
      const e = edited(s);
      await API.patch(`subjects/${s.id}/`, {
        category: e.category || null, kind: e.kind, credits: e.credits === "" ? 0 : e.credits,
        lecture_hours: e.lecture_hours === "" ? 0 : e.lecture_hours,
        tutorial_hours: e.tutorial_hours === "" ? 0 : e.tutorial_hours,
        practical_hours: e.practical_hours === "" ? 0 : e.practical_hours,
      }).catch((err) => { throw new Error(`${s.code || s.name}: ${errorText(err, "not saved")}`); });
    }
  }, `${dirty.length} subject${dirty.length === 1 ? "" : "s"} saved.`);

  const diff = data ? data.difference : 0;
  const cell = (s, key, label, wide) => (
    <input className={`kb-input rg-num${wide ? " rg-num-wide" : ""}`} aria-label={`${s.code || s.name}: ${label}`} disabled={ro}
      inputMode="decimal" value={edited(s)[key]} onChange={(e) => editRow(s, { [key]: e.target.value })} />
  );

  return (
    <Shell title="Credits and categories" subtitle="How many credits a course needs, by category, and what each subject carries."
      actions={
        <div className="rg-row">
          <label className="rg-field">Course
            <select className="kb-input" value={course} onChange={(e) => pick("course", e.target.value)}>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="rg-field">Regulation
            <select className="kb-input" value={regulation} onChange={(e) => pick("regulation", e.target.value)}>
              {regs.map((r) => <option key={r.id} value={r.id}>{r.name}{r.is_default ? " (default)" : ""}</option>)}
            </select>
          </label>
        </div>
      }>
      {regs.length === 0 && <section className="kb-card"><p className="rg-muted">Create a regulation first, on the Regulations page.</p></section>}
      {error && <section className="kb-card"><p className="rg-msg bad">{error}</p></section>}
      {msg && <p className={`rg-msg ${msg.tone}`} role={msg.tone === "ok" ? "status" : "alert"}>{msg.text}</p>}

      {data && (
        <>
          <div className="rg-stats">
            <div><span>Credits to graduate</span><b>{num(data.total_required)}</b><small>set for {data.course.name} under {data.regulation.name}</small></div>
            <div><span>Credits in the subject list</span><b>{num(data.total_have)}</b><small>all semesters added up</small></div>
            <div><span>Difference</span>
              <b className={diff === 0 ? "rg-ok" : "rg-bad"}>{diff === 0 ? "None" : `${num(Math.abs(diff))} ${diff < 0 ? "short" : "over"}`}</b>
              <small>{data.no_category ? `${data.no_category} subject${data.no_category === 1 ? " has" : "s have"} no category yet` : "every subject has a category"}</small></div>
          </div>

          <section className="kb-card">
            <div className="rg-head">
              <h2 className="rg-h2">Categories</h2>
              {!ro && (
                <span className="rg-foot-actions">
                  <button type="button" className="kb-btn kb-btn--sm" onClick={() => setNewCat({ code: "", name: "", carries_credit: true })}>+ Add category</button>
                </span>
              )}
            </div>
            {newCat && (
              <form className="rg-row rg-newcat" onSubmit={addCategory}>
                <label className="rg-field">Code<input className="kb-input rg-num-wide" maxLength={10} value={newCat.code} onChange={(e) => setNewCat({ ...newCat, code: e.target.value })} /></label>
                <label className="rg-field rg-grow">Name<input className="kb-input" maxLength={80} value={newCat.name} onChange={(e) => setNewCat({ ...newCat, name: e.target.value })} /></label>
                <label className="rg-check"><input type="checkbox" checked={newCat.carries_credit} onChange={(e) => setNewCat({ ...newCat, carries_credit: e.target.checked })} />Carries credit</label>
                <button type="button" className="kb-btn" onClick={() => setNewCat(null)}>Cancel</button>
                <button type="submit" className="kb-btn kb-btn--primary" disabled={busy || !newCat.code.trim() || !newCat.name.trim()}>Add</button>
              </form>
            )}
            {data.categories.length === 0 ? (
              <p className="rg-muted">No categories yet.{!ro && " Use “+ Add category” for each kind of subject your regulation counts (for example Core, Elective, Laboratory, Project). Tick “Carries credit” unless students only need to pass it."}</p>
            ) : (
              <div className="rg-table-wrap">
                <table className="rg-table">
                  <thead><tr><th>Code</th><th>Category</th><th>Credits required</th><th>In subject list</th><th>Check</th>{!ro && <th></th>}</tr></thead>
                  <tbody>
                    {data.categories.map((c) => {
                      const [tone, text] = checkLabel(c);
                      const editing = editCat?.id === c.id;
                      return (
                        <tr key={c.id}>
                          <td><b>{c.code}</b></td>
                          <td>{editing ? (
                            <span className="rg-row">
                              <input className="kb-input" maxLength={80} aria-label={`${c.code}: name`} value={editCat.name}
                                onChange={(e) => setEditCat({ ...editCat, name: e.target.value })} />
                              <label className="rg-check"><input type="checkbox" checked={editCat.carries_credit}
                                onChange={(e) => setEditCat({ ...editCat, carries_credit: e.target.checked })} />Carries credit</label>
                            </span>
                          ) : c.name}</td>
                          <td>{c.carries_credit
                            ? <input className="kb-input rg-num" aria-label={`${c.code}: credits required`} inputMode="decimal" disabled={ro}
                                value={req[c.id] ?? ""} onChange={(e) => setReq({ ...req, [c.id]: e.target.value })} />
                            : <span className="rg-muted">no credit</span>}</td>
                          <td>{num(c.have)}</td>
                          <td><span className={`kb-pill ${tone} rg-pill`}>{text}</span></td>
                          {!ro && (
                            <td>
                              <span className="rg-foot-actions">
                                {editing ? (
                                  <>
                                    <button type="button" className="kb-btn kb-btn--sm kb-btn--primary" disabled={busy || !editCat.name.trim()} onClick={saveCategory}>Save</button>
                                    <button type="button" className="kb-btn kb-btn--sm" onClick={() => setEditCat(null)}>Cancel</button>
                                  </>
                                ) : (
                                  <>
                                    <button type="button" className="kb-btn kb-btn--sm" disabled={busy}
                                      onClick={() => setEditCat({ id: c.id, name: c.name, carries_credit: c.carries_credit })}>Edit</button>
                                    <button type="button" className="kb-btn kb-btn--sm" disabled={busy} onClick={() => deleteCategory(c)}>Delete</button>
                                  </>
                                )}
                              </span>
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {!ro && data.categories.length > 0 && (
              <div className="rg-foot-actions rg-right">
                <button type="button" className="kb-btn kb-btn--primary" disabled={busy} onClick={saveRequirements}>Save credits required</button>
              </div>
            )}
          </section>

          <section className="kb-card">
            <div className="rg-head">
              <h2 className="rg-h2">Subjects{semester ? ` · Semester ${semester.semester}` : ""}</h2>
              {!ro && (
                <ImportExport importer="subjects" label="subjects" matchLabel="course, year, semester and subject name"
                  align="right" exportParams={{ course }} onDone={load}
                  note="Category, Type, L, T, P and Regulation columns fill in this page. Empty cells never erase saved values." />
              )}
            </div>
            {data.semesters.length === 0 ? (
              <p className="rg-muted">No subjects for this course under {data.regulation.name} yet. Add them on the Courses page or by import.</p>
            ) : (
              <>
                <div className="rg-tabs" role="tablist" aria-label="Semester">
                  {data.semesters.map((s) => (
                    <button key={s.semester} type="button" role="tab" aria-selected={s.semester === sem}
                      className={s.semester === sem ? "on" : ""} onClick={() => setSem(s.semester)}>
                      Sem {s.semester} <small>{num(s.credits)} cr</small>
                    </button>
                  ))}
                </div>
                {semester && (
                  <div className="rg-table-wrap">
                    <table className="rg-table rg-subjects">
                      <thead><tr><th>Code</th><th>Subject</th><th>Category</th><th>Type</th><th>L</th><th>T</th><th>P</th><th>Credits</th></tr></thead>
                      <tbody>
                        {semester.subjects.map((s) => {
                          const e = edited(s);
                          return (
                            <tr key={s.id} className={rows[s.id] ? "rg-dirty" : ""}>
                              <td><b>{s.code || "—"}</b></td>
                              <td>{s.name}{s.is_elective && <small className="rg-muted"> · elective</small>}</td>
                              <td><select className={`kb-input${!e.category ? " rg-need" : ""}`} aria-label={`${s.code || s.name}: category`} disabled={ro}
                                value={e.category || ""} onChange={(ev) => editRow(s, { category: ev.target.value ? Number(ev.target.value) : null })}>
                                <option value="">Choose…</option>
                                {data.categories.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
                              </select></td>
                              <td><select className="kb-input" aria-label={`${s.code || s.name}: type`} disabled={ro}
                                value={e.kind} onChange={(ev) => editRow(s, { kind: ev.target.value })}>
                                {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                              </select></td>
                              <td>{cell(s, "lecture_hours", "L")}</td>
                              <td>{cell(s, "tutorial_hours", "T")}</td>
                              <td>{cell(s, "practical_hours", "P")}</td>
                              <td>{cell(s, "credits", "credits")}</td>
                            </tr>
                          );
                        })}
                        <tr className="rg-total"><td colSpan={7}><b>Semester {semester.semester} total</b></td><td><b>{num(semester.credits)}</b></td></tr>
                      </tbody>
                    </table>
                  </div>
                )}
                {!ro && (
                  <div className="rg-foot-actions rg-right">
                    {dirty.length > 0 && <span className="rg-muted">{dirty.length} changed</span>}
                    <button type="button" className="kb-btn" disabled={!dirty.length || busy} onClick={() => setRows({})}>Undo</button>
                    <button type="button" className="kb-btn kb-btn--primary" disabled={!dirty.length || busy} onClick={saveSubjects}>Save subjects</button>
                  </div>
                )}
                <p className="rg-muted">L-T-P = lecture, tutorial and practical hours a week. Credits may be whole or half (1.5).
                  A subject with no regulation set belongs to the default regulation.</p>
              </>
            )}
          </section>
        </>
      )}
    </Shell>
  );
}