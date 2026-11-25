// ============================================================
// ElectivesManage — HOD / admin electives screen (meeting point 9, Step 4)
// ============================================================
// One page, top to bottom:
//   1. College setting (admin only): Students choose / HOD allocates
//   2. Elective groups: "Professional Elective I · pick 1" for a class
//   3. The selected group: its electives, seat limits, "Give to whole class"
//   4. The class: each student's elective - allocate / move / remove
//   5. History of every change
//
// The server decides everything (who may edit which group, seat limits,
// reasons for moving). This page only calls /api/electives/... and shows
// the server's message when something is refused.
// ============================================================

import { Fragment, useEffect, useMemo, useState } from "react";

import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import "../../App.css";
import { PrerequisiteEditor, RegistrationAdmin } from "./CourseRegistration";   // CBCS PART A / B

const errText = (err, fallback) => err?.response?.data?.detail || fallback;
const fmt = (iso) =>
  iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "";
// <input type="datetime-local"> wants "YYYY-MM-DDTHH:mm" in local time
const toLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);
const WINDOW_LABEL = { open: "Open", not_open: "Not open yet", closed: "Closed" };
const EMPTY_FORM = { course: "", year: "", semester: "", name: "", department: "", picks: 1, opens_at: "", closes_at: "",
  open_elective: false, open_to: [] };   // CBCS PART B: open elective

export default function ElectivesManage() {
  const user = useMemo(() => {
    try { return JSON.parse(localStorage.getItem("user") || "{}"); } catch { return {}; }
  }, []);
  const isAdmin = user.is_superuser === true || (user.role === "admin");

  const [open, setOpen] = useState(false);
  // CBCS PART A: "Elective groups" (this page as before) or "Course registration"
  const [view, setView] = useState(() =>
    new URLSearchParams(window.location.search).get("tab") === "registration" ? "registration" : "groups");
  const [setting, setSetting] = useState(null);
  const [groups, setGroups] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);       // { group, students, not_chosen }
  const [available, setAvailable] = useState([]);
  const [changes, setChanges] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [onlyMissing, setOnlyMissing] = useState(false);

  const [courses, setCourses] = useState([]);
  const [years, setYears] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [form, setForm] = useState(null);           // null = form closed; else EMPTY_FORM-like
  const [addTa, setAddTa] = useState({ teaching_assignment: "", seat_limit: "" });
  const [prereqFor, setPrereqFor] = useState(null);   // CBCS PART B: option whose prerequisites are open

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const say = (msg) => { setNotice(msg); setError(""); };
  const fail = (err, fallback) => { setError(errText(err, fallback)); setNotice(""); };

  // ---------------- loading ----------------
  const loadGroups = async (keepId) => {
    const r = await API.get("/electives/groups/");
    setGroups(r.data || []);
    const id = keepId ?? selectedId;
    if (id && !(r.data || []).some((g) => g.id === id)) setSelectedId(null);
  };

  const loadDetail = async (id) => {
    if (!id) { setDetail(null); return; }
    const [d, a] = await Promise.all([
      API.get(`/electives/groups/${id}/students/`),
      API.get(`/electives/groups/${id}/available/`),
    ]);
    setDetail(d.data);
    setAvailable(a.data || []);
    if (showHistory) loadHistory(id);
  };

  const loadHistory = async (id) => {
    const r = await API.get(`/electives/groups/${id}/changes/`);
    setChanges(r.data || []);
  };

  useEffect(() => {
    (async () => {
      try {
        const [s, c, d] = await Promise.all([
          API.get("/electives/setting/"),
          API.get("/courses/"),
          API.get("users/departments/").catch(() => ({ data: [] })),
        ]);
        setSetting(s.data);
        setCourses(c.data || []);
        setDepartments(Array.isArray(d.data) ? d.data : d.data?.results || []);
        await loadGroups();
      } catch (err) {
        fail(err, "Could not load electives.");
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setError(""); setNotice("");
    loadDetail(selectedId).catch((err) => fail(err, "Could not load this group."));
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (showHistory && selectedId) loadHistory(selectedId).catch(() => setChanges([]));
  }, [showHistory]); // eslint-disable-line react-hooks/exhaustive-deps

  // years of the course chosen in the form
  useEffect(() => {
    if (!form?.course) { setYears([]); return; }
    API.get(`/years/?course=${form.course}`).then((r) => setYears(r.data || [])).catch(() => setYears([]));
  }, [form?.course]);

  const refresh = async () => {
    await loadGroups(selectedId);
    await loadDetail(selectedId);
  };

  const run = async (fn, okMsg) => {
    setBusy(true);
    try {
      const res = await fn();
      say(res?.data?.detail || okMsg);
      await refresh();
      return true;
    } catch (err) {
      fail(err, "That didn't work.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  // ---------------- 1. setting ----------------
  const saveSetting = async (mode) => {
    if (mode === setting?.mode) return;
    const text = mode === "staff"
      ? "Switch to: HOD allocates electives? Students will no longer see the Choose buttons."
      : "Switch to: Students choose their electives?";
    if (!window.confirm(text)) return;
    setBusy(true);
    try {
      const r = await API.put("/electives/setting/", { mode });
      setSetting(r.data);
      say(`Saved: ${r.data.mode_display}.`);
    } catch (err) {
      fail(err, "Could not save the setting.");
    } finally {
      setBusy(false);
    }
  };

  // ---------------- 2. groups ----------------
  const yearNumber = years.find((y) => String(y.id) === String(form?.year))?.year_number;
  const semesterChoices = yearNumber ? [2 * yearNumber - 1, 2 * yearNumber] : [];

  const startEdit = (g) => {
    setForm({
      id: g.id, course: String(g.course), year: String(g.year), semester: String(g.semester), name: g.name,
      department: g.department ? String(g.department) : "", picks: g.picks,
      opens_at: toLocalInput(g.opens_at), closes_at: toLocalInput(g.closes_at),
      open_elective: g.open_elective, open_to: g.open_to || [],
    });
  };

  const saveGroup = async (e) => {
    e.preventDefault();
    const body = {
      course: form.course, year: form.year, semester: form.semester, name: form.name,
      picks: Number(form.picks) || 1,
      opens_at: fromLocalInput(form.opens_at), closes_at: fromLocalInput(form.closes_at),
      open_elective: form.open_elective, open_to: form.open_elective ? form.open_to : [],
    };
    if (isAdmin) body.department = form.department || null;
    setBusy(true);
    try {
      const r = form.id
        ? await API.patch(`/electives/groups/${form.id}/`, body)
        : await API.post("/electives/groups/", body);
      say(form.id ? "Group saved." : `Group "${r.data.name}" created. Now add its electives.`);
      setForm(null);
      await loadGroups(r.data.id);
      setSelectedId(r.data.id);
      if (form.id) await loadDetail(r.data.id);
    } catch (err) {
      fail(err, "Could not save the group.");
    } finally {
      setBusy(false);
    }
  };

  const deleteGroup = async (g) => {
    if (!window.confirm(`Delete "${g.name}"? This can't be undone.`)) return;
    setBusy(true);
    try {
      await API.delete(`/electives/groups/${g.id}/`);
      say("Group deleted.");
      setSelectedId(null);
      await loadGroups();
    } catch (err) {
      fail(err, "Could not delete the group.");
    } finally {
      setBusy(false);
    }
  };

  // ---------------- 3. electives in the group ----------------
  const group = detail?.group;

  const addOption = async (e) => {
    e.preventDefault();
    if (!addTa.teaching_assignment) return;
    const ok = await run(
      () => API.post(`/electives/groups/${selectedId}/options/`, {
        teaching_assignment: addTa.teaching_assignment, seat_limit: addTa.seat_limit || null,
      }),
      "Elective added."
    );
    if (ok) setAddTa({ teaching_assignment: "", seat_limit: "" });
  };

  const editSeats = (o) => {
    const v = window.prompt(`Seat limit for ${o.subject} (blank = no limit):`, o.seat_limit ?? "");
    if (v === null) return;
    run(() => API.patch(`/electives/options/${o.id}/`, { seat_limit: v.trim() || null }), "Seat limit saved.");
  };

  const removeOption = (o) => {
    if (!window.confirm(`Remove ${o.subject} from this group?`)) return;
    run(() => API.delete(`/electives/options/${o.id}/`), `${o.subject} removed.`);
  };

  const giveWholeClass = (o) => {
    if (!window.confirm(`Give ${o.subject} to every student in this class who doesn't have an elective here yet?`)) return;
    run(() => API.post(`/electives/options/${o.id}/assign-class/`), "Done.");
  };

  // ---------------- 4. students ----------------
  const allocate = (student, optionId) => {
    if (!optionId) return;
    const moving = student.options.length > 0 && group.picks === 1;
    let reason = "";
    if (moving) {
      reason = window.prompt(`Why move ${student.name} from ${student.options[0].subject}? (at least 10 characters)`);
      if (reason === null) return;
    }
    run(() => API.post("/electives/allocate/", { student: student.student, option: optionId, reason }), "Saved.");
  };

  const removeFromStudent = (student, o) => {
    const reason = window.prompt(`Why remove ${o.subject} from ${student.name}? (at least 10 characters)`);
    if (reason === null) return;
    run(() => API.post("/electives/remove/", { student: student.student, option: o.id, reason }), "Removed.");
  };

  const students = (detail?.students || []).filter((s) => !onlyMissing || !s.complete);

  // ---------------- render ----------------
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="header-box">
              <h2>Electives</h2>
              <p>Create elective groups for a class, set seat limits, and allocate students — one by one or the whole class.</p>
            </div>

            <div className="ems-seg crg-tabs" role="tablist">
              <button type="button" role="tab" aria-selected={view === "groups"} className={view === "groups" ? "on" : ""}
                onClick={() => setView("groups")}>Elective groups</button>
              <button type="button" role="tab" aria-selected={view === "registration"} className={view === "registration" ? "on" : ""}
                onClick={() => setView("registration")}>Course registration</button>
            </div>

            {view === "registration" && <RegistrationAdmin isAdmin={isAdmin} />}

            {view === "groups" && <>

            {error && <div className="tb-error">{error}</div>}
            {notice && <div className="card ems-notice" role="status">{notice}</div>}

            {/* ===== 1. SETTING ===== */}
            {setting && (
              <div className="card ems-setting">
                <div>
                  <h3>Who selects electives?</h3>
                  <span className="el-muted">For the whole college. Staff can always allocate and move students.</span>
                </div>
                {setting.can_edit ? (
                  <div className="ems-seg" role="radiogroup">
                    <button type="button" className={setting.mode === "students" ? "on" : ""} disabled={busy}
                      onClick={() => saveSetting("students")}>Students choose</button>
                    <button type="button" className={setting.mode === "staff" ? "on" : ""} disabled={busy}
                      onClick={() => saveSetting("staff")}>HOD allocates</button>
                  </div>
                ) : (
                  <span className="kb-pill">{setting.mode_display}</span>
                )}
              </div>
            )}

            {/* ===== 2. GROUPS ===== */}
            <div className="card">
              <div className="ems-head">
                <h3>Elective groups</h3>
                {!form && (
                  <button className="btn-primary" onClick={() => setForm({ ...EMPTY_FORM })}>+ New group</button>
                )}
              </div>

              {form && (
                <form className="ems-form" onSubmit={saveGroup}>
                  <label>Course
                    <select value={form.course} required
                      onChange={(e) => setForm({ ...form, course: e.target.value, year: "", semester: "" })}>
                      <option value="">Choose…</option>
                      {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </label>
                  <label>Year
                    <select value={form.year} required disabled={!form.course}
                      onChange={(e) => setForm({ ...form, year: e.target.value, semester: "" })}>
                      <option value="">Choose…</option>
                      {years.map((y) => <option key={y.id} value={y.id}>Year {y.year_number}</option>)}
                    </select>
                  </label>
                  <label>Semester
                    <select value={form.semester} required disabled={!form.year}
                      onChange={(e) => setForm({ ...form, semester: e.target.value })}>
                      <option value="">Choose…</option>
                      {semesterChoices.map((s) => <option key={s} value={s}>Semester {s}</option>)}
                    </select>
                  </label>
                  <label className="ems-wide">Group name
                    <input value={form.name} required placeholder="e.g. Professional Elective I"
                      onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </label>
                  {isAdmin && (
                    <label>Department (its HOD manages it)
                      <select value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}>
                        <option value="">— none —</option>
                        {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                      </select>
                    </label>
                  )}
                  <label>Each student takes
                    <input type="number" min="1" max="5" value={form.picks}
                      onChange={(e) => setForm({ ...form, picks: e.target.value })} />
                  </label>
                  <label>Students can choose from <small>(optional)</small>
                    <input type="datetime-local" value={form.opens_at}
                      onChange={(e) => setForm({ ...form, opens_at: e.target.value })} />
                  </label>
                  <label>Last date <small>(optional)</small>
                    <input type="datetime-local" value={form.closes_at}
                      onChange={(e) => setForm({ ...form, closes_at: e.target.value })} />
                  </label>
                  {/* CBCS PART B: open elective - offered to students of other courses */}
                  <div className="ems-wide">
                    <label className="crg-check">
                      <input type="checkbox" checked={form.open_elective}
                        onChange={(e) => setForm({ ...form, open_elective: e.target.checked })} />
                      Open elective: offered to other courses (any department's subjects of this semester)
                    </label>
                    {form.open_elective && (
                      <div className="crg-checks" style={{ marginTop: 8 }}>
                        <span className="el-muted">Offered to (none ticked = every course):</span>
                        {courses.map((c) => (
                          <label key={c.id} className="crg-check">
                            <input type="checkbox" checked={form.open_to.includes(c.id)}
                              onChange={() => setForm({ ...form, open_to: form.open_to.includes(c.id)
                                ? form.open_to.filter((x) => x !== c.id) : [...form.open_to, c.id] })} />
                            {c.name}
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="ems-actions ems-wide">
                    <button type="button" className="btn-edit" onClick={() => setForm(null)} disabled={busy}>Cancel</button>
                    <button type="submit" className="btn-primary" disabled={busy}>{form.id ? "Save group" : "Create group"}</button>
                  </div>
                </form>
              )}

              {groups.length === 0 && !form ? (
                <p className="el-muted">No elective groups yet. Create one for a class to get started.</p>
              ) : (
                <ul className="ems-groups">
                  {groups.map((g) => (
                    <li key={g.id} className={g.id === selectedId ? "on" : ""}>
                      <button type="button" className="ems-group-btn" onClick={() => setSelectedId(g.id)}>
                        <b>{g.name}</b>
                        <span className="el-muted">
                          {g.course_name} · Year {g.year_number} · Sem {g.semester}
                          {g.department_name ? ` · ${g.department_name}` : ""} · pick {g.picks} · {g.options.length} elective{g.options.length === 1 ? "" : "s"}
                          {g.open_elective ? " · open elective" : ""}
                        </span>
                      </button>
                      <span className={`el-window el-window--${g.window}`}>{WINDOW_LABEL[g.window]}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* ===== 3. SELECTED GROUP: ELECTIVES ===== */}
            {group && (
              <div className="card">
                <div className="ems-head">
                  <div>
                    <h3>{group.name}</h3>
                    <span className="el-muted">
                      {group.open_elective
                        ? `Open elective · offered to ${group.open_to_names.length ? group.open_to_names.join(", ") : "every course"} · Semester ${group.semester}`
                        : `${group.course_name} · Year ${group.year_number} · Semester ${group.semester}`} · each student takes {group.picks}
                      {group.closes_at ? ` · last date ${fmt(group.closes_at)}` : ""}
                    </span>
                  </div>
                  <div className="ems-actions">
                    <button className="btn-edit" onClick={() => startEdit(group)} disabled={busy}>Edit group</button>
                    <button className="btn-delete" onClick={() => deleteGroup(group)} disabled={busy}>Delete</button>
                  </div>
                </div>

                {group.options.length === 0 ? (
                  <p className="el-muted">No electives in this group yet. Add them below.</p>
                ) : (
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr><th>Elective</th><th>Teacher</th><th>Seats</th><th style={{ textAlign: "right" }}>Actions</th></tr>
                      </thead>
                      <tbody>
                        {group.options.map((o) => (
                          <Fragment key={o.id}>
                          <tr>
                            <td>
                              <b>{o.subject}</b>{o.code ? <span className="el-muted"> · {o.code}</span> : null}
                              {group.open_elective && <div className="el-muted">{o.course_name}</div>}
                              {o.requires.length > 0 && (
                                <div className="el-muted">Needs {o.requires.map((r) => r.code || r.name).join(", ")} passed</div>
                              )}
                            </td>
                            <td>{o.teacher_name}</td>
                            <td>
                              <span className={o.is_full ? "el-seats is-full" : "el-seats"}>
                                {o.seats_taken} / {o.seat_limit ?? "no limit"}
                              </span>
                            </td>
                            <td className="ems-row-actions">
                              <button className="btn-edit" onClick={() => editSeats(o)} disabled={busy}>Seat limit</button>
                              <button className="btn-edit" onClick={() => setPrereqFor(prereqFor === o.id ? null : o.id)} disabled={busy}>
                                Prerequisite
                              </button>
                              {!group.open_elective && (
                                <button className="btn-primary" onClick={() => giveWholeClass(o)} disabled={busy}>Give to whole class</button>
                              )}
                              <button className="btn-delete" onClick={() => removeOption(o)} disabled={busy}>Remove</button>
                            </td>
                          </tr>
                          {prereqFor === o.id && (
                            <tr><td colSpan={4}>
                              <PrerequisiteEditor option={o} busy={busy}
                                onSave={(ids) => run(() => API.patch(`/electives/options/${o.id}/`, { requires: ids }), "Prerequisite saved.")
                                  .then((ok) => ok && setPrereqFor(null))} />
                            </td></tr>
                          )}
                          </Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <form className="ems-add" onSubmit={addOption}>
                  <select value={addTa.teaching_assignment}
                    onChange={(e) => setAddTa({ ...addTa, teaching_assignment: e.target.value })}>
                    <option value="">
                      {available.length ? "Add an elective subject…" : "No more elective subjects for this class"}
                    </option>
                    {available.map((a) => (
                      <option key={a.teaching_assignment} value={a.teaching_assignment}>
                        {a.subject}{a.code ? ` (${a.code})` : ""} — {a.teacher_name}{group.open_elective ? ` · ${a.course_name}` : ""}
                      </option>
                    ))}
                  </select>
                  <input type="number" min="1" placeholder="Seat limit (blank = none)" value={addTa.seat_limit}
                    onChange={(e) => setAddTa({ ...addTa, seat_limit: e.target.value })} />
                  <button type="submit" className="btn-primary" disabled={busy || !addTa.teaching_assignment}>Add</button>
                </form>
                <p className="el-muted ems-hint">
                  Only subjects marked <b>elective</b> and assigned to a teacher for this class appear here
                  (Courses → subject → Elective, then Faculty Allocation).
                </p>
              </div>
            )}

            {/* ===== 4. STUDENTS ===== */}
            {group && group.options.length > 0 && (
              <div className="card">
                <div className="ems-head">
                  <div>
                    <h3>Students ({detail.students.length})</h3>
                    <span className="el-muted">{detail.not_chosen} without an elective in this group</span>
                  </div>
                  <label className="ems-check">
                    <input type="checkbox" checked={onlyMissing} onChange={(e) => setOnlyMissing(e.target.checked)} />
                    Show only students still to allocate
                  </label>
                </div>

                {students.length === 0 ? (
                  <p className="el-muted">{onlyMissing ? "Everyone has their elective." : "No students in this class."}</p>
                ) : (
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr><th>Roll no</th><th>Name</th><th>Elective</th><th>{group.picks === 1 ? "Allocate / move" : "Add"}</th></tr>
                      </thead>
                      <tbody>
                        {students.map((s) => (
                          <tr key={s.student}>
                            <td>{s.roll_number}</td>
                            <td>{s.name}</td>
                            <td>
                              {s.options.length === 0 ? (
                                <span className="el-muted">—</span>
                              ) : (
                                s.options.map((o) => (
                                  <span key={o.id} className="ems-chip">
                                    {o.subject}
                                    <button type="button" aria-label={`Remove ${o.subject}`} disabled={busy}
                                      onClick={() => removeFromStudent(s, o)}>×</button>
                                  </span>
                                ))
                              )}
                            </td>
                            <td>
                              {(group.picks === 1 || !s.complete) && (
                                <select value="" disabled={busy} onChange={(e) => allocate(s, e.target.value)}>
                                  <option value="">{s.options.length ? "Move to…" : "Choose…"}</option>
                                  {group.options
                                    .filter((o) => !s.options.some((x) => x.id === o.id))
                                    .map((o) => (
                                      <option key={o.id} value={o.id} disabled={o.is_full}>
                                        {o.subject}{o.is_full ? " (full)" : ""}
                                      </option>
                                    ))}
                                </select>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* ===== 5. HISTORY ===== */}
            {group && (
              <div className="card">
                <div className="ems-head">
                  <h3>History</h3>
                  <button className="btn-edit" onClick={() => setShowHistory(!showHistory)}>
                    {showHistory ? "Hide" : "Show"}
                  </button>
                </div>
                {showHistory && (
                  changes.length === 0 ? (
                    <p className="el-muted">No changes yet.</p>
                  ) : (
                    <div className="table-container">
                      <table>
                        <thead>
                          <tr><th>When</th><th>Student</th><th>Change</th><th>By</th><th>Reason</th></tr>
                        </thead>
                        <tbody>
                          {changes.map((c) => (
                            <tr key={c.id}>
                              <td>{fmt(c.changed_at)}</td>
                              <td>{c.student}<br /><span className="el-muted">{c.roll_number}</span></td>
                              <td>{c.from || "—"} → <b>{c.to || "removed"}</b></td>
                              <td>{c.changed_by}</td>
                              <td>{c.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}
              </div>
            )}
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}