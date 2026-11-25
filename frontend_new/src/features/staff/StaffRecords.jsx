// ============================================================
// HRIS PART A - Staff records (/staff).
//   Admin / Principal: every staff member.  HOD: their department.
//   Anyone else: their own record only (the directory is refused, so we open theirs).
// One record has five tabs: Profile, Teaching (teachers only), Service record, Leave, Documents.
// The admin also gets a "Leave rules" tab (days a year per leave type).
// HRIS PART B adds: Verify achievements (HOD / Principal / admin), Appraisals
// (the reviews waiting for you, and the admin's appraisal years), My appraisal.
// The server decides who may see or change what; this page shows what it sends.
// PAN, Aadhaar and bank details are not kept here yet.
// ============================================================
import { useEffect, useState } from "react";

import API from "../../api";
import { API_BASE_URL } from "../../apiBase";
import Shell from "../regulations/CbcsShell";

const errText = (err, fallback) => {
  const d = err?.response?.data;
  if (d?.detail) return d.detail;
  if (d && typeof d === "object") return Object.values(d).flat().join(" ");
  return fallback;
};

const fmt = (iso) => {
  if (!iso) return "—";
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
};

const save = async (url, name) => {
  const r = await API.get(url, { responseType: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(r.data);
  a.download = name;
  a.click();
};

const EMPLOYMENT = [["permanent", "Permanent"], ["probation", "On probation"], ["contract", "Contract"], ["visiting", "Visiting / guest"]];
const SERVICE_KINDS = [["joined", "Joined"], ["promotion", "Promotion"], ["transfer", "Department change"],
  ["pay", "Pay revision"], ["role", "Role / responsibility"], ["relieved", "Relieved"], ["other", "Other"]];
const DOC_KINDS = [["qualification", "Qualification certificate"], ["experience", "Experience certificate"],
  ["order", "Appointment / order"], ["id_proof", "ID proof (only you and the admin)"], ["other", "Other"]];
const TEACHING = ["professor", "associate_professor", "assistant_professor"];

export default function StaffRecords() {
  const me = JSON.parse(localStorage.getItem("user") || "{}");
  const teacher = me.role === "teacher";
  const params = new URLSearchParams(window.location.search);
  const [tab, setTab] = useState(params.get("tab") || "staff");
  const [dir, setDir] = useState(null);         // directory payload, or "own" when refused
  const [openId, setOpenId] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    API.get("/users/hris/staff/")
      .then((r) => setDir(r.data))
      .catch((err) => {
        if (err?.response?.status === 403) { setDir("own"); setOpenId(me.id); }
        else setError(errText(err, "Could not load the staff list."));
      });
  }, [me.id]);

  const own = dir === "own";
  // HRIS PART B: achievements to verify, appraisals to review, and my own appraisal
  const tabs = own
    ? [["staff", "My record"], ...(teacher ? [["appraisal", "My appraisal"]] : [])]
    : [["staff", "Staff"], ["verify", "Verify achievements"], ["appraisals", "Appraisals"],
      ...(teacher ? [["appraisal", "My appraisal"]] : []), ["rules", "Leave rules"]];
  const current = tabs.some(([k]) => k === tab) ? tab : "staff";
  const pick = (k) => {
    setTab(k);
    if (!own && k !== "staff") setOpenId(null);
    window.history.replaceState(null, "", k === "staff" ? "/staff" : `/staff?tab=${k}`);
  };

  return (
    <Shell title={own ? "My staff record" : "Staff records"}
      subtitle={own ? "Your job details, service record, leave, documents and appraisal, as the office keeps them."
        : "Everyone who works here: job details, service record, leave, documents, achievements and appraisals."}>
      {error && <div className="rg-msg bad">{error}</div>}
      {dir && !(current === "staff" && openId && !own) && tabs.length > 1 && (
        <div className="ems-seg crg-tabs hr-tabs" role="tablist">
          {tabs.map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={current === k} className={current === k ? "on" : ""}
              onClick={() => pick(k)}>{l}</button>
          ))}
        </div>
      )}
      {!dir ? (
        !error && <div className="card"><p className="rg-muted">Loading…</p></div>
      ) : current === "appraisal" ? (
        <MyAppraisal />
      ) : current === "verify" ? (
        <VerifyAchievements />
      ) : current === "appraisals" ? (
        <Appraisals openFirst={params.get("open")} />
      ) : current === "rules" ? (
        <LeaveRules />
      ) : openId ? (
        <Record id={openId} designations={own ? [] : dir.designations}
          onBack={own ? null : () => setOpenId(null)} />
      ) : (
        <Directory first={dir} onOpen={setOpenId} />
      )}
    </Shell>
  );
}

// ============================================================ directory
function Directory({ first, onOpen }) {
  const [data, setData] = useState(first);
  const [f, setF] = useState({ q: "", department: "", designation: "", category: "", status: "active" });
  const [departments, setDepartments] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    API.get("/users/departments/").then((r) => setDepartments(r.data.results || r.data)).catch(() => setDepartments([]));
  }, []);

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      const p = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
      API.get(`/users/hris/staff/?${p}`)
        .then((r) => live && setData(r.data))
        .catch((err) => live && setError(errText(err, "Could not load the staff list.")));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [f]);

  const set = (k) => (e) => setF((o) => ({ ...o, [k]: e.target.value }));
  const s = data.summary;
  const download = (key) => save(`/users/hris/reports/${key}/${f.department ? `?department=${f.department}` : ""}`, `${key}.xlsx`)
    .catch((err) => setError(errText(err, "Could not download the report.")));

  return (
    <>
      <div className="hr-tiles">
        <div className="card"><span>Teaching staff</span><b>{s.teaching}</b></div>
        <div className="card"><span>Non-teaching</span><b>{s.non_teaching}</b></div>
        <div className="card"><span>With Ph.D</span><b>{s.phd}{s.teaching ? <small> {Math.round((s.phd / s.teaching) * 100)}%</small> : null}</b></div>
        <div className="card"><span>Students per teacher</span><b>{s.student_teacher_ratio ?? "—"}</b></div>
        <div className="card"><span>Profiles incomplete</span><b className={s.incomplete ? "hr-warn" : ""}>{s.incomplete}</b></div>
      </div>
      {error && <div className="rg-msg bad">{error}</div>}
      <section className="card hr-stack">
        <div className="hr-filters">
          <input value={f.q} onChange={set("q")} placeholder="Search name or employee ID" aria-label="Search staff" />
          <select value={f.department} onChange={set("department")} aria-label="Department">
            <option value="">All departments</option>
            {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <select value={f.designation} onChange={set("designation")} aria-label="Designation">
            <option value="">All designations</option>
            {data.designations.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
          <select value={f.category} onChange={set("category")} aria-label="Type">
            <option value="">Teaching and non-teaching</option>
            <option value="teaching">Teaching</option>
            <option value="non_teaching">Non-teaching</option>
          </select>
          <select value={f.status} onChange={set("status")} aria-label="Status">
            <option value="active">Active</option>
            <option value="relieved">Relieved</option>
            <option value="all">Everyone</option>
          </select>
        </div>
        <div className="rg-table-wrap">
          <table className="rg-table">
            <thead><tr><th>Staff</th><th>Department</th><th>Designation</th><th>Qualification</th><th>Joined</th><th>Experience</th><th>Profile</th></tr></thead>
            <tbody>
              {data.rows.length === 0 && <tr><td colSpan={7} className="rg-muted">No staff match these filters.</td></tr>}
              {data.rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <button type="button" className="hr-link" onClick={() => onOpen(r.id)}>{r.name}</button>
                    <div className="rg-muted hr-small">{r.employee_id || "No employee ID"}{r.category === "non_teaching" ? " · non-teaching" : ""}</div>
                  </td>
                  <td>{r.department_name || "—"}</td>
                  <td>{r.designation_label || <span className="rg-muted">Not set</span>}</td>
                  <td>{r.qualification || "—"}</td>
                  <td>{r.date_of_joining ? fmt(r.date_of_joining) : "—"}</td>
                  <td>{r.experience_years != null ? `${r.experience_years} yrs` : "—"}</td>
                  <td>
                    {!r.is_active ? <span className="kb-pill">Relieved</span>
                      : r.missing.length ? <span className="kb-pill warn" title={`Missing: ${r.missing.join(", ")}`}>Missing {r.missing.length}</span>
                        : <span className="kb-pill ok">Complete</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card hr-stack">
        <h3>Reports (Excel)</h3>
        <div className="hr-row">
          <button type="button" className="btn-edit" onClick={() => download("faculty-list")}>Faculty list for AICTE / NAAC</button>
          <button type="button" className="btn-edit" onClick={() => download("strength")}>Staff strength by department</button>
          <button type="button" className="btn-edit" onClick={() => download("leave-taken")}>Leave taken this year</button>
        </div>
        <p className="rg-muted">Reports cover staff working here now{f.department ? " in the chosen department" : ""}.</p>
      </section>
    </>
  );
}

// ============================================================ one record
const RECORD_TABS = [["profile", "Profile"], ["teaching", "Teaching"], ["service", "Service record"], ["leave", "Leave"], ["documents", "Documents"]];

function Record({ id, designations, onBack }) {
  const [rec, setRec] = useState(null);
  const [tab, setTab] = useState("profile");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    let live = true;
    API.get(`/users/hris/staff/${id}/`)
      .then((r) => live && setRec(r.data))
      .catch((err) => live && setError(errText(err, "Could not open this record.")));
    return () => { live = false; };
  }, [id]);

  const done = (data, message) => { setRec(data); setError(""); setNote(message); };
  const fail = (err, fallback) => { setNote(""); setError(errText(err, fallback)); };

  if (!rec) return error ? <div className="rg-msg bad">{error}</div> : <div className="card"><p className="rg-muted">Loading…</p></div>;
  const tabs = RECORD_TABS.filter(([k]) => (k !== "leave" || rec.leave) && (k !== "teaching" || rec.teaching));
  return (
    <>
      <section className="card hr-head">
        <div>
          {onBack && <button type="button" className="hr-link hr-small" onClick={onBack}>← All staff</button>}
          <h2>{rec.name}</h2>
          <p className="rg-muted">
            {[rec.designation_label || "Designation not set", rec.department_name, rec.employee_id].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="hr-row">
          {rec.employment_label && <span className="kb-pill info">{rec.employment_label}</span>}
          {rec.is_active ? <span className="kb-pill ok">Active</span> : <span className="kb-pill">Relieved {fmt(rec.relieved_on)}</span>}
        </div>
      </section>
      <div className="ems-seg crg-tabs hr-tabs" role="tablist">
        {tabs.map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""}
            onClick={() => { setTab(k); setNote(""); setError(""); }}>{l}</button>
        ))}
      </div>
      {error && <div className="rg-msg bad">{error}</div>}
      {note && <div className="rg-msg ok">{note}</div>}
      {tab === "profile" && <ProfileTab rec={rec} designations={designations} done={done} fail={fail} />}
      {tab === "teaching" && <TeachingTab rec={rec} />}
      {tab === "service" && <ServiceTab rec={rec} designations={designations} done={done} fail={fail} />}
      {tab === "leave" && <LeaveTab rec={rec} done={done} fail={fail} />}
      {tab === "documents" && <DocumentsTab rec={rec} done={done} fail={fail} />}
    </>
  );
}

// Teaching: the classes this teacher has now (replaces the HOD's old "Faculty" tab).
// Teaching assignments hold only the current allocation, so there is no history.
function TeachingTab({ rec }) {
  const t = rec.teaching;
  if (!t.rows.length) {
    return (
      <section className="card">
        <p><span className="kb-pill warn">No classes</span></p>
        <p className="rg-muted">No subjects are assigned to this teacher this semester. The HOD assigns them on Faculty Allocation.</p>
      </section>
    );
  }
  return (
    <>
      <div className="hr-tiles">
        <div className="card"><span>Classes</span><b>{t.classes}</b></div>
        <div className="card"><span>Subjects</span><b>{t.subjects}</b></div>
        <div className="card"><span>Students</span><b>{t.students}</b></div>
        {t.hours != null && <div className="card"><span>Hours a week</span><b>{t.hours}</b></div>}
      </div>
      <section className="card">
        <h3>This semester</h3>
        <div className="rg-table-wrap">
          <table className="rg-table">
            <thead><tr><th>Subject</th><th>Class</th><th>Type</th><th>Students</th>{t.hours != null && <th>Hours a week</th>}</tr></thead>
            <tbody>
              {t.rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.subject_code && <b>{r.subject_code} </b>}{r.subject_name}</td>
                  <td>{r.course} · Year {r.year} · Sem {r.semester}</td>
                  <td><span className={`kb-pill ${r.type === "elective" ? "info" : ""}`}>{r.type === "elective" ? "Elective" : "Core"}</span></td>
                  <td>{r.students}</td>
                  {t.hours != null && <td>{r.hours ?? "—"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function Field({ label, children }) {
  return <div><div className="hr-label">{label}</div><div>{children || <span className="rg-muted">—</span>}</div></div>;
}

function ProfileTab({ rec, designations, done, fail }) {
  const [edit, setEdit] = useState(null);
  const [busy, setBusy] = useState(false);
  const options = designations.filter((d) => (rec.role === "teacher") === TEACHING.includes(d.value));

  const start = () => setEdit({
    designation: rec.designation, employment_type: rec.employment_type, aicte_id: rec.aicte_id,
    date_of_joining: rec.date_of_joining || "", experience_years: rec.experience_years ?? "",
    qualification: rec.qualification, specialization: rec.specialization,
  });
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await API.patch(`/users/hris/staff/${rec.id}/`, edit);
      setEdit(null);
      done(r.data, "Job details saved.");
    } catch (err) { fail(err, "Could not save."); } finally { setBusy(false); }
  };
  const set = (k) => (e) => setEdit((o) => ({ ...o, [k]: e.target.value }));

  return (
    <div className="crg-cols">
      <section className="card crg-main">
        <div className="ems-head">
          <h3>Job details</h3>
          {rec.can_edit && !edit && <button type="button" className="btn-edit" onClick={start}>Edit</button>}
        </div>
        {rec.missing.length > 0 && rec.is_active && (
          <p className="rg-msg bad">Missing: {rec.missing.join(", ")}.</p>
        )}
        {edit ? (
          <form className="ems-form hr-form" onSubmit={submit}>
            {rec.role !== "admin" && (
              <label>Designation
                <select value={edit.designation} onChange={set("designation")}>
                  <option value="">Not set</option>
                  {options.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </label>
            )}
            <label>Employment
              <select value={edit.employment_type} onChange={set("employment_type")}>
                <option value="">Not set</option>
                {EMPLOYMENT.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label>Date of joining<input type="date" value={edit.date_of_joining} onChange={set("date_of_joining")} /></label>
            <label>Total experience (years)<input type="number" min="0" max="60" value={edit.experience_years} onChange={set("experience_years")} /></label>
            <label>Qualification<input value={edit.qualification} onChange={set("qualification")} placeholder="M.E, Ph.D" /></label>
            <label>Specialization<input value={edit.specialization} onChange={set("specialization")} /></label>
            {rec.role === "teacher" && <label>AICTE faculty ID<input value={edit.aicte_id} onChange={set("aicte_id")} /></label>}
            <div className="ems-actions ems-wide">
              <button type="button" className="btn-edit" onClick={() => setEdit(null)}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={busy}>Save</button>
            </div>
          </form>
        ) : (
          <div className="hr-grid">
            <Field label="Designation">{rec.designation_label}</Field>
            <Field label="Department">{rec.department_name}</Field>
            <Field label="Employment">{rec.employment_label}</Field>
            <Field label="Date of joining">{rec.date_of_joining && fmt(rec.date_of_joining)}</Field>
            <Field label="Years here">{rec.years_here != null && `${rec.years_here}`}</Field>
            <Field label="Total experience">{rec.experience_years != null && `${rec.experience_years} years`}</Field>
            <Field label="Qualification">{rec.qualification}</Field>
            <Field label="Specialization">{rec.specialization}</Field>
            {rec.role === "teacher" && <Field label="AICTE faculty ID">{rec.aicte_id}</Field>}
          </div>
        )}
      </section>
      <section className="card crg-side">
        <h3>Personal</h3>
        <div className="hr-grid one">
          <Field label="Email">{rec.email}</Field>
          <Field label="Date of birth">{rec.date_of_birth && fmt(rec.date_of_birth)}</Field>
          <Field label="Gender">{rec.gender}</Field>
          <Field label="Blood group">{rec.blood_group}</Field>
          <Field label="Address">{rec.address}</Field>
        </div>
        <p className="rg-muted">The staff member changes these on their own Profile page.</p>
      </section>
    </div>
  );
}

function ServiceTab({ rec, designations, done, fail }) {
  const blank = { kind: "promotion", date: "", details: "", order_no: "", new_designation: "", new_department: "" };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [departments, setDepartments] = useState([]);
  const options = designations.filter((d) => (rec.role === "teacher") === TEACHING.includes(d.value));

  useEffect(() => {
    if (!rec.can_edit) return;
    API.get("/users/departments/").then((r) => setDepartments(r.data.results || r.data)).catch(() => setDepartments([]));
  }, [rec.can_edit]);

  const set = (k) => (e) => setForm((o) => ({ ...o, [k]: e.target.value }));
  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await API.post(`/users/hris/staff/${rec.id}/service/`, form);
      setForm(blank);
      done(r.data.record, "Added to the service record.");
    } catch (err) { fail(err, "Could not add it."); } finally { setBusy(false); }
  };
  const remove = async (s) => {
    if (!window.confirm(`Remove "${s.details}"? What it changed on the account stays; correct that on the Profile tab if needed.`)) return;
    try {
      await API.delete(`/users/hris/service/${s.id}/`);
      const r = await API.get(`/users/hris/staff/${rec.id}/`);
      done(r.data, "Removed.");
    } catch (err) { fail(err, "Could not remove it."); }
  };

  return (
    <div className="crg-cols">
      <section className="card crg-main">
        <h3>Service record</h3>
        {rec.service.length === 0 ? <p className="rg-muted">Nothing recorded yet.</p> : (
          <ol className="hr-timeline">
            {rec.service.map((s) => (
              <li key={s.id}>
                <span className="hr-date">{fmt(s.date)}</span>
                <div>
                  <b>{s.kind_label}</b> · {s.details}
                  {s.order_no && <div className="rg-muted hr-small">Order {s.order_no}</div>}
                </div>
                {rec.can_edit && <button type="button" className="btn-delete" onClick={() => remove(s)}>Remove</button>}
              </li>
            ))}
          </ol>
        )}
      </section>
      {rec.can_edit && (
        <section className="card crg-side">
          <h3>Add an entry</h3>
          <form className="ems-form hr-form one" onSubmit={add}>
            <label>What happened
              <select value={form.kind} onChange={set("kind")}>
                {SERVICE_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label>Date<input type="date" value={form.date} onChange={set("date")} required /></label>
            {form.kind === "promotion" && (
              <label>New designation <small>changes it on the account</small>
                <select value={form.new_designation} onChange={set("new_designation")}>
                  <option value="">Keep as it is</option>
                  {options.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </label>
            )}
            {form.kind === "transfer" && (
              <label>New department <small>moves the account</small>
                <select value={form.new_department} onChange={set("new_department")} required>
                  <option value="">Choose</option>
                  {departments.filter((d) => d.id !== rec.department).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </label>
            )}
            {form.kind === "relieved" && <p className="rg-msg bad">This deactivates the account: they can no longer sign in.</p>}
            <label>Details <small>{["promotion", "transfer", "relieved"].includes(form.kind) ? "optional" : ""}</small>
              <input value={form.details} onChange={set("details")} maxLength={300} />
            </label>
            <label>Order number <small>optional</small><input value={form.order_no} onChange={set("order_no")} maxLength={60} /></label>
            <div className="ems-actions"><button type="submit" className="btn-primary" disabled={busy}>Add</button></div>
          </form>
        </section>
      )}
    </div>
  );
}

function LeaveTab({ rec, done, fail }) {
  const blank = { leave_type: "compensatory", days: "", reason: "" };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((o) => ({ ...o, [k]: e.target.value }));
  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await API.post(`/users/hris/staff/${rec.id}/leave-adjust/`, { ...form, year: rec.leave.year });
      setForm(blank);
      done(r.data, "Leave adjusted.");
    } catch (err) { fail(err, "Could not adjust."); } finally { setBusy(false); }
  };
  const limited = rec.leave.rows.filter((r) => r.limited);
  return (
    <div className="crg-cols">
      <section className="card crg-main">
        <h3>Leave in {rec.leave.year}</h3>
        <div className="rg-table-wrap">
          <table className="rg-table">
            <thead><tr><th>Type</th><th>Allowed</th><th>Used</th><th>Waiting</th><th>Left</th></tr></thead>
            <tbody>
              {rec.leave.rows.map((r) => (
                <tr key={r.leave_type}>
                  <td>{r.label}</td>
                  <td>{r.limited ? r.allowed : <span className="rg-muted">No limit</span>}</td>
                  <td>{r.used}</td>
                  <td>{r.waiting || "—"}</td>
                  <td><b>{r.limited ? r.left : "—"}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="rg-muted">Used counts approved leave. Waiting leave is held back from what can be applied for.</p>
      </section>
      {rec.can_edit && (
        <section className="card crg-side">
          <h3>Adjust leave</h3>
          <p className="rg-muted">Add days (e.g. a compensatory off for weekend work) or take them away, with the reason.</p>
          <form className="ems-form hr-form one" onSubmit={add}>
            <label>Leave type
              <select value={form.leave_type} onChange={set("leave_type")}>
                {limited.map((r) => <option key={r.leave_type} value={r.leave_type}>{r.label}</option>)}
              </select>
            </label>
            <label>Days <small>use a minus sign to take away</small>
              <input type="number" step="0.5" value={form.days} onChange={set("days")} required />
            </label>
            <label>Reason<input value={form.reason} onChange={set("reason")} placeholder="Worked on Saturday 14 Nov" required /></label>
            <div className="ems-actions"><button type="submit" className="btn-primary" disabled={busy}>Save</button></div>
          </form>
        </section>
      )}
    </div>
  );
}

function DocumentsTab({ rec, done, fail }) {
  const [form, setForm] = useState({ kind: "qualification", title: "" });
  const [file, setFile] = useState(null);
  const [inputKey, setInputKey] = useState(0);
  const [busy, setBusy] = useState(false);

  const upload = async (e) => {
    e.preventDefault();
    if (!file) { fail(null, "Choose a file."); return; }
    setBusy(true);
    const body = new FormData();
    body.append("kind", form.kind);
    body.append("title", form.title);
    body.append("file", file);
    try {
      const r = await API.post(`/users/hris/staff/${rec.id}/documents/`, body);
      setForm({ kind: "qualification", title: "" });
      setFile(null);
      setInputKey((k) => k + 1);
      done(r.data, "Document uploaded.");
    } catch (err) { fail(err, "Could not upload."); } finally { setBusy(false); }
  };
  const open = async (d) => {
    try {
      // the file lives on the API's address; the protected file server checks who asks
      const r = await API.get(new URL(d.url, API_BASE_URL).href, { responseType: "blob" });
      window.open(URL.createObjectURL(r.data), "_blank", "noopener");
    } catch (err) { fail(err, "Could not open the file."); }
  };
  const remove = async (d) => {
    if (!window.confirm(`Remove "${d.title}"?`)) return;
    try {
      await API.delete(`/users/hris/documents/${d.id}/`);
      const r = await API.get(`/users/hris/staff/${rec.id}/`);
      done(r.data, "Removed.");
    } catch (err) { fail(err, "Could not remove it."); }
  };

  return (
    <div className="crg-cols">
      <section className="card crg-main">
        <h3>Documents</h3>
        {rec.documents_list.length === 0 ? <p className="rg-muted">No documents yet.</p> : (
          <ul className="hr-docs">
            {rec.documents_list.map((d) => (
              <li key={d.id}>
                <div>
                  <button type="button" className="hr-link" onClick={() => open(d)}>{d.title}</button>
                  <div className="rg-muted hr-small">{d.kind_label.replace(/ \(.*\)$/, "")} · uploaded {fmt(d.uploaded_at)}</div>
                </div>
                <div className="hr-row">
                  {d.private && <span className="kb-pill warn">Private</span>}
                  {d.can_delete && <button type="button" className="btn-delete" onClick={() => remove(d)}>Remove</button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      {rec.can_upload && (
        <section className="card crg-side">
          <h3>Upload</h3>
          <form className="ems-form hr-form one" onSubmit={upload}>
            <label>Kind
              <select value={form.kind} onChange={(e) => setForm((o) => ({ ...o, kind: e.target.value }))}>
                {DOC_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label>Name<input value={form.title} onChange={(e) => setForm((o) => ({ ...o, title: e.target.value }))}
              placeholder="Ph.D degree certificate" maxLength={150} required /></label>
            <label>File <small>PDF, JPG or PNG, up to 10 MB</small>
              <input key={inputKey} type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files[0] || null)} />
            </label>
            <div className="ems-actions"><button type="submit" className="btn-primary" disabled={busy}>Upload</button></div>
          </form>
          <p className="rg-muted">The HOD can see these, except ID proofs.</p>
        </section>
      )}
    </div>
  );
}

// ============================================================ leave rules
function LeaveRules() {
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    API.get("/users/hris/leave-rules/")
      .then((r) => { setData(r.data); setRows(r.data.rules); })
      .catch((err) => setMsg({ bad: true, text: errText(err, "Could not load the leave rules.") }));
  }, []);

  const set = (i, k, v) => setRows((list) => list.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const submit = async () => {
    setBusy(true);
    try {
      const r = await API.put("/users/hris/leave-rules/", { rules: rows.map((r) => ({ ...r, days_per_year: r.days_per_year === "" ? null : r.days_per_year })) });
      setData(r.data);
      setRows(r.data.rules);
      setMsg({ text: "Leave rules saved. Balances use them straight away." });
    } catch (err) { setMsg({ bad: true, text: errText(err, "Could not save.") }); } finally { setBusy(false); }
  };

  if (!data) return msg ? <div className="rg-msg bad">{msg.text}</div> : <div className="card"><p className="rg-muted">Loading…</p></div>;
  return (
    <section className="card hr-stack">
      <h3>Days a year, per leave type</h3>
      <p className="rg-muted">The leave year is January to December. Leave a box empty for no limit. Compensatory off starts at 0 and grows when you adjust it on a staff record.</p>
      {msg && <div className={`rg-msg ${msg.bad ? "bad" : "ok"}`}>{msg.text}</div>}
      <div className="rg-table-wrap">
        <table className="rg-table">
          <thead><tr><th>Leave type</th><th>Days a year</th><th>Note</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.leave_type}>
                <td>{r.label}</td>
                <td>
                  <input className="hr-num" type="number" min="0" step="0.5" disabled={!data.can_edit} aria-label={`${r.label} days a year`}
                    value={r.days_per_year ?? ""} placeholder="No limit" onChange={(e) => set(i, "days_per_year", e.target.value)} />
                </td>
                <td>
                  <input disabled={!data.can_edit} value={r.note || ""} maxLength={200} aria-label={`${r.label} note`}
                    onChange={(e) => set(i, "note", e.target.value)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.can_edit && <div className="ems-actions"><button type="button" className="btn-primary" disabled={busy} onClick={submit}>Save</button></div>}
    </section>
  );
}

// ============================================================ HRIS PART B: verify achievements
function VerifyAchievements() {
  const [status, setStatus] = useState("pending");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState({});           // id -> text
  const [busy, setBusy] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    API.get(`/users/achievements/review/?status=${status}`)
      .then((r) => live && setData(r.data))
      .catch((err) => live && setError(errText(err, "Could not load the achievements.")));
    return () => { live = false; };
  }, [status, tick]);

  const act = async (it, action) => {
    setBusy(it.id);
    setError("");
    try {
      await API.post(`/users/achievements/${it.id}/review/`, { action, note: note[it.id] || "" });
      setTick((t) => t + 1);
    } catch (err) { setError(errText(err, "Could not save.")); } finally { setBusy(null); }
  };
  const proof = async (it) => {
    try {
      const r = await API.get(new URL(it.proof_url, API_BASE_URL).href, { responseType: "blob" });
      window.open(URL.createObjectURL(r.data), "_blank", "noopener");
    } catch (err) { setError(errText(err, "Could not open the proof.")); }
  };

  if (!data) return error ? <div className="rg-msg bad">{error}</div> : <div className="card"><p className="rg-muted">Loading…</p></div>;
  return (
    <section className="card hr-stack">
      <div className="ems-head">
        <div>
          <h3>Achievements to verify</h3>
          <p className="rg-muted">Check each entry against its proof. Only verified entries count in appraisals and NAAC / NBA reports.</p>
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Show">
          <option value="pending">Waiting ({data.counts.pending})</option>
          <option value="returned">Returned ({data.counts.returned})</option>
          <option value="verified">Verified ({data.counts.verified})</option>
        </select>
      </div>
      {error && <div className="rg-msg bad">{error}</div>}
      {data.rows.length === 0 ? (
        <p className="rg-muted">{status === "pending" ? "Nothing is waiting for you." : "None."}</p>
      ) : (
        <ul className="hr-docs hr-verify">
          {data.rows.map((it) => (
            <li key={it.id}>
              <div className="hr-verify-main">
                <span className="kb-pill info">{it.category_label}</span> <b>{it.title}</b>
                <div className="rg-muted hr-small">
                  {it.faculty_name} · {it.department_name} · {fmt(it.date)}
                  {it.organizer ? ` · ${it.organizer}` : ""}
                </div>
                {(it.details || it.indexing_label || it.amount_lakhs != null) && (
                  <div className="hr-small">
                    {[it.details, it.indexing_label, it.amount_lakhs != null ? `₹${it.amount_lakhs} lakh` : ""].filter(Boolean).join(" · ")}
                  </div>
                )}
                {it.review_note && <div className="hr-small rg-muted">Note: {it.review_note}</div>}
                {it.status === "verified" && <div className="hr-small rg-muted">Verified by {it.verified_by_name} on {fmt(it.verified_at)}</div>}
              </div>
              <div className="hr-verify-act">
                {it.has_proof
                  ? <button type="button" className="hr-link hr-small" onClick={() => proof(it)}>Open proof</button>
                  : <span className="kb-pill warn">No proof</span>}
                {it.can_verify && it.status === "pending" && (
                  <>
                    <input placeholder="Note (needed to return)" aria-label={`Note for ${it.title}`}
                      value={note[it.id] || ""} onChange={(e) => setNote((n) => ({ ...n, [it.id]: e.target.value }))} />
                    <div className="hr-row">
                      <button type="button" className="btn-edit" disabled={busy === it.id} onClick={() => act(it, "return")}>Return</button>
                      <button type="button" className="btn-primary" disabled={busy === it.id} onClick={() => act(it, "verify")}>Verify</button>
                    </div>
                  </>
                )}
                {it.can_verify && it.status === "verified" && (
                  <>
                    <input placeholder="Why it goes back" aria-label={`Note for ${it.title}`}
                      value={note[it.id] || ""} onChange={(e) => setNote((n) => ({ ...n, [it.id]: e.target.value }))} />
                    <button type="button" className="btn-edit" disabled={busy === it.id} onClick={() => act(it, "return")}>Return for correction</button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ============================================================ HRIS PART B: appraisal
const STEP_PILL = { not_started: "", draft: "", with_hod: "warn", with_principal: "warn", done: "ok" };

function Appraisals({ openFirst }) {
  const [cycle, setCycle] = useState("");
  const [data, setData] = useState(null);
  const [openAp, setOpenAp] = useState(openFirst ? Number(openFirst) : null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    API.get(`/users/appraisal/list/${cycle ? `?cycle=${cycle}` : ""}`)
      .then((r) => live && setData(r.data))
      .catch((err) => live && setError(errText(err, "Could not load the appraisals.")));
    return () => { live = false; };
  }, [cycle, tick]);

  if (openAp) return <AppraisalView id={openAp} onBack={() => { setOpenAp(null); setTick((t) => t + 1); }} />;
  if (!data) return error ? <div className="rg-msg bad">{error}</div> : <div className="card"><p className="rg-muted">Loading…</p></div>;
  const waiting = data.rows.filter((r) => r.waiting_for_me);
  return (
    <>
      {data.can_edit && <AppraisalYears onChange={() => setTick((t) => t + 1)} />}
      {!data.cycle ? (
        <section className="card"><p className="rg-muted">No appraisal year yet.{data.can_edit ? " Open one above." : " The admin opens one."}</p></section>
      ) : (
        <section className="card hr-stack">
          <div className="ems-head">
            <div>
              <h3>Appraisal {data.cycle.name}</h3>
              <p className="rg-muted">
                {fmt(data.cycle.start)} to {fmt(data.cycle.end)} · {data.cycle.is_open ? "open" : "closed"}
                {waiting.length ? ` · ${waiting.length} waiting for you` : ""}
              </p>
            </div>
            <div className="hr-row">
              {data.cycles.length > 1 && (
                <select value={cycle || data.cycle.id} onChange={(e) => setCycle(e.target.value)} aria-label="Appraisal year">
                  {data.cycles.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              )}
              <button type="button" className="btn-edit"
                onClick={() => save(`/users/appraisal/export/?cycle=${data.cycle.id}`, `appraisal-${data.cycle.name}.xlsx`)
                  .catch((err) => setError(errText(err, "Could not download.")))}>Excel</button>
            </div>
          </div>
          {error && <div className="rg-msg bad">{error}</div>}
          <div className="rg-table-wrap">
            <table className="rg-table">
              <thead><tr><th>Teacher</th><th>Department</th><th>Where it is</th><th>Self</th><th>HOD</th><th>Grade</th><th /></tr></thead>
              <tbody>
                {data.rows.length === 0 && <tr><td colSpan={7} className="rg-muted">No teachers.</td></tr>}
                {data.rows.map((r) => (
                  <tr key={r.staff}>
                    <td><b>{r.name}</b><div className="rg-muted hr-small">{r.designation || "—"}</div></td>
                    <td>{r.department || "—"}</td>
                    <td><span className={`kb-pill ${r.waiting_for_me ? "info" : STEP_PILL[r.status]}`}>
                      {r.waiting_for_me ? "Waiting for you" : r.status_label}</span></td>
                    <td>{r.self_total ?? "—"}</td>
                    <td>{r.hod_total ?? "—"}</td>
                    <td>{r.grade || "—"}</td>
                    <td>{r.id && r.status !== "draft" && (
                      <button type="button" className={r.waiting_for_me ? "btn-primary" : "btn-edit"} onClick={() => setOpenAp(r.id)}>
                        {r.waiting_for_me ? "Review" : "Open"}
                      </button>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="rg-muted">Scores are out of {data.out_of}. A teacher's appraisal opens here once they send it in.</p>
        </section>
      )}
    </>
  );
}

function AppraisalYears({ onChange }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ name: "", start: "", end: "" });
  const [areasFor, setAreasFor] = useState(null);   // {id, areas}
  const [msg, setMsg] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    API.get("/users/appraisal/cycles/").then((r) => setData(r.data)).catch(() => setData({ cycles: [] }));
  }, [tick]);

  const run = async (fn, ok) => {
    try { await fn(); setMsg({ text: ok }); setTick((t) => t + 1); onChange(); return true; } catch (err) { setMsg({ bad: true, text: errText(err, "Could not save.") }); return false; }
  };
  const create = (e) => {
    e.preventDefault();
    run(() => API.post("/users/appraisal/cycles/", form), "Appraisal year opened. Teachers can fill in theirs now.")
      .then((ok) => ok && setForm({ name: "", start: "", end: "" }));
  };
  const setArea = (i, k, v) => setAreasFor((a) => ({ ...a, areas: a.areas.map((x, j) => (j === i ? { ...x, [k]: v } : x)) }));

  if (!data) return null;
  return (
    <section className="card hr-stack">
      <h3>Appraisal years</h3>
      {msg && <div className={`rg-msg ${msg.bad ? "bad" : "ok"}`}>{msg.text}</div>}
      {data.cycles.length > 0 && (
        <ul className="hr-docs">
          {data.cycles.map((c) => (
            <li key={c.id}>
              <div>
                <b>{c.name}</b> <span className={`kb-pill ${c.is_open ? "ok" : ""}`}>{c.is_open ? "Open" : "Closed"}</span>
                <div className="rg-muted hr-small">
                  {fmt(c.start)} to {fmt(c.end)} · {c.areas.map((a) => `${a.label} ${a.max}`).join(" · ")}
                </div>
              </div>
              <div className="hr-row">
                {!c.areas_locked && <button type="button" className="btn-edit" onClick={() => setAreasFor({ id: c.id, areas: c.areas })}>Areas</button>}
                <button type="button" className="btn-edit"
                  onClick={() => run(() => API.patch(`/users/appraisal/cycles/${c.id}/`, { is_open: !c.is_open }), c.is_open ? "Closed." : "Opened again.")}>
                  {c.is_open ? "Close" : "Open again"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {areasFor && (
        <div className="hr-stack">
          <p className="rg-muted">The areas and their highest scores. They are fixed once the first appraisal is sent in.</p>
          {areasFor.areas.map((a, i) => (
            <div className="hr-row" key={i}>
              <input value={a.label} aria-label={`Area ${i + 1}`} onChange={(e) => setArea(i, "label", e.target.value)} style={{ flex: "1 1 240px" }} />
              <input className="hr-num" type="number" min="1" max="100" value={a.max} aria-label={`Area ${i + 1} highest score`}
                onChange={(e) => setArea(i, "max", e.target.value)} />
              <button type="button" className="btn-delete" disabled={areasFor.areas.length <= 2}
                onClick={() => setAreasFor((x) => ({ ...x, areas: x.areas.filter((_, j) => j !== i) }))}>Remove</button>
            </div>
          ))}
          <div className="hr-row">
            <button type="button" className="btn-edit" disabled={areasFor.areas.length >= 8}
              onClick={() => setAreasFor((x) => ({ ...x, areas: [...x.areas, { key: "", label: "", max: 10 }] }))}>+ Area</button>
            <span className="rg-muted">Total {areasFor.areas.reduce((t, a) => t + (Number(a.max) || 0), 0)}</span>
            <button type="button" className="btn-edit" onClick={() => setAreasFor(null)}>Cancel</button>
            <button type="button" className="btn-primary"
              onClick={() => run(() => API.patch(`/users/appraisal/cycles/${areasFor.id}/`, { areas: areasFor.areas }), "Areas saved.")
                .then((ok) => ok && setAreasFor(null))}>Save areas</button>
          </div>
        </div>
      )}
      <form className="ems-form hr-form" onSubmit={create}>
        <label>Name<input value={form.name} placeholder="2026-27" onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required /></label>
        <label>From<input type="date" value={form.start} onChange={(e) => setForm((f) => ({ ...f, start: e.target.value }))} required /></label>
        <label>To<input type="date" value={form.end} onChange={(e) => setForm((f) => ({ ...f, end: e.target.value }))} required /></label>
        <div className="ems-actions ems-wide"><button type="submit" className="btn-primary">Open a new appraisal year</button></div>
      </form>
    </section>
  );
}

function MyAppraisal() {
  const [cycle, setCycle] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    API.get(`/users/appraisal/mine/${cycle ? `?cycle=${cycle}` : ""}`)
      .then((r) => live && setData(r.data))
      .catch((err) => live && setError(errText(err, "Could not load your appraisal.")));
    return () => { live = false; };
  }, [cycle]);

  if (!data) return error ? <div className="rg-msg bad">{error}</div> : <div className="card"><p className="rg-muted">Loading…</p></div>;
  return (
    <>
      {data.years.length > 1 && (
        <label className="oc-pick hr-year">Appraisal year
          <select value={cycle || data.appraisal?.cycle.id || ""} onChange={(e) => setCycle(e.target.value)}>
            {data.years.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
          </select>
        </label>
      )}
      {data.appraisal ? <AppraisalView key={data.appraisal.id} first={data.appraisal} /> : <section className="card"><p className="rg-muted">{data.message}</p></section>}
    </>
  );
}

function AppraisalView({ id, first, onBack }) {
  const [ap, setAp] = useState(first || null);
  const [selfS, setSelfS] = useState(first?.self_scores || {});
  const [summary, setSummary] = useState(first?.self_summary || "");
  const [hodS, setHodS] = useState({});
  const [remarks, setRemarks] = useState("");
  const [grade, setGrade] = useState("");
  const [note, setNote] = useState("");
  const [reply, setReply] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const fill = (d) => {
    setAp(d);
    setSelfS(d.self_scores || {});
    setSummary(d.self_summary || "");
    setHodS(Object.keys(d.hod_scores || {}).length ? d.hod_scores : d.self_scores || {});
    setRemarks(d.can_principal ? d.principal_remarks : d.hod_remarks || "");
    setGrade(d.grade || d.suggested_grade || "");
  };

  useEffect(() => {
    if (first) { fill(first); return; }
    API.get(`/users/appraisal/${id}/`).then((r) => fill(r.data))
      .catch((err) => setMsg({ bad: true, text: errText(err, "Could not open this appraisal.") }));
  }, [id, first]);

  const send = async (step, body, ok) => {
    setBusy(true);
    try {
      const r = await API.post(`/users/appraisal/${ap.id}/${step}/`, body);
      fill(r.data);
      setNote("");
      setMsg({ text: ok });
    } catch (err) { setMsg({ bad: true, text: errText(err, "Could not save.") }); } finally { setBusy(false); }
  };

  if (!ap) return msg ? <div className="rg-msg bad">{msg.text}</div> : <div className="card"><p className="rg-muted">Loading…</p></div>;
  const sum = (o) => ap.areas.reduce((t, a) => t + (Number(o[a.key]) || 0), 0);
  const steps = [
    ["Teacher fills in", ap.submitted_at ? `Sent in ${fmt(ap.submitted_at)}` : "Not sent in yet", ap.status !== "draft"],
    ...(ap.hod_step ? [["HOD reviews", ap.hod_at ? `Done ${fmt(ap.hod_at)}` : "", ["with_principal", "done"].includes(ap.status)]] : []),
    ["Principal finalises", ap.finalised_at ? `Done ${fmt(ap.finalised_at)}` : "Grade and remarks", ap.status === "done"],
    ["Teacher sees the result", ap.staff_reply ? "Replied" : "Can add a reply", !!ap.staff_reply],
  ];
  const now = steps.findIndex((s) => !s[2]);
  const showHod = ap.can_hod || ap.can_principal || ap.hod_total != null;
  const scoreInput = (vals, set, a, who) => (
    <input className="hr-num hr-score" type="number" min="0" max={a.max} aria-label={`${who} score ${a.label}`}
      value={vals[a.key] ?? ""} onChange={(e) => set((o) => ({ ...o, [a.key]: e.target.value === "" ? "" : Number(e.target.value) }))} />
  );

  return (
    <>
      <section className="card hr-head">
        <div>
          {onBack && <button type="button" className="hr-link hr-small" onClick={onBack}>← All appraisals</button>}
          <h2>{ap.staff.name} · Appraisal {ap.cycle.name}</h2>
          <p className="rg-muted">{[ap.staff.designation, ap.staff.department, `${fmt(ap.cycle.start)} to ${fmt(ap.cycle.end)}`].filter(Boolean).join(" · ")}</p>
        </div>
        <span className={`kb-pill ${STEP_PILL[ap.status]}`}>{ap.status_label}</span>
      </section>
      <ol className="hr-steps">
        {steps.map(([t, sub, done], i) => (
          <li key={t} className={done ? "done" : i === now ? "now" : ""}><b>{i + 1} · {t}</b><span>{i === now && !done && !sub ? "Now" : sub}</span></li>
        ))}
      </ol>
      {msg && <div className={`rg-msg ${msg.bad ? "bad" : "ok"}`}>{msg.text}</div>}
      {ap.returned_note && ap.status !== "done" && <div className="fc-note"><b>Sent back:</b> {ap.returned_note}</div>}

      <section className="card hr-stack">
        <h3>Scores</h3>
        <div className="rg-table-wrap">
          <table className="rg-table hr-scores">
            <thead><tr><th>Area</th><th>From the app</th><th>Max</th><th>Self</th>{showHod && <th>HOD</th>}</tr></thead>
            <tbody>
              {ap.areas.map((a) => (
                <tr key={a.key}>
                  <td><b>{a.label}</b></td>
                  <td className="hr-facts">{(ap.facts[a.key] || []).length ? ap.facts[a.key].map((f) => <div key={f}>{f}</div>) : <span className="rg-muted">—</span>}</td>
                  <td>{a.max}</td>
                  <td>{ap.can_self ? scoreInput(selfS, setSelfS, a, "Self") : (ap.self_scores[a.key] ?? "—")}</td>
                  {showHod && <td>{ap.can_hod ? scoreInput(hodS, setHodS, a, "HOD") : (ap.hod_scores[a.key] ?? "—")}</td>}
                </tr>
              ))}
              <tr className="hr-total">
                <td colSpan={2}><b>Total</b></td><td><b>{ap.out_of}</b></td>
                <td><b>{ap.can_self ? sum(selfS) : (ap.self_total ?? "—")}</b></td>
                {showHod && <td><b>{ap.can_hod ? sum(hodS) : (ap.hod_total ?? "—")}</b></td>}
              </tr>
            </tbody>
          </table>
        </div>
        <p className="rg-muted">"From the app" is read from attendance, teaching plans, results, feedback and verified achievements for these dates.</p>
      </section>

      <div className="crg-cols">
        <section className="card crg-main hr-stack">
          <h3>{ap.can_self ? "Your summary of the year" : "Teacher's summary"}</h3>
          {ap.can_self ? (
            <>
              <textarea rows={5} value={summary} onChange={(e) => setSummary(e.target.value)} aria-label="Your summary"
                placeholder="What went well, what you want to do next year, any support you need." />
              <div className="ems-actions">
                <button type="button" className="btn-edit" disabled={busy}
                  onClick={() => send("self", { scores: selfS, summary, submit: false }, "Saved. You can come back to it.")}>Save</button>
                <button type="button" className="btn-primary" disabled={busy}
                  onClick={() => window.confirm("Send it in? You can't change it afterwards unless it is sent back.") &&
                    send("self", { scores: selfS, summary, submit: true }, "Sent in.")}>
                  Send to {ap.hod_step ? "HOD" : "Principal"}
                </button>
              </div>
            </>
          ) : <p className="hr-pre">{ap.self_summary || <span className="rg-muted">Not written yet.</span>}</p>}
          {ap.staff_reply && (<><h3>Teacher's reply</h3><p className="hr-pre">{ap.staff_reply}</p></>)}
          {ap.can_reply && (
            <>
              <h3>Your reply <span className="rg-muted hr-small">(once, optional)</span></h3>
              <textarea rows={3} value={reply} onChange={(e) => setReply(e.target.value)} aria-label="Your reply" />
              <div className="ems-actions"><button type="button" className="btn-primary" disabled={busy}
                onClick={() => send("reply", { reply }, "Reply saved.")}>Send reply</button></div>
            </>
          )}
        </section>

        <section className="card crg-side hr-stack">
          {ap.can_hod ? (
            <>
              <h3>Your remarks (HOD)</h3>
              <textarea rows={5} value={remarks} onChange={(e) => setRemarks(e.target.value)} aria-label="HOD remarks" />
              <input placeholder="Note for sending back" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Send back note" />
              <div className="hr-row hr-end">
                <button type="button" className="btn-edit" disabled={busy} onClick={() => send("hod", { action: "send_back", note }, "Sent back to the teacher.")}>Send back</button>
                <button type="button" className="btn-edit" disabled={busy} onClick={() => send("hod", { action: "save", scores: hodS, remarks }, "Saved.")}>Save</button>
                <button type="button" className="btn-primary" disabled={busy} onClick={() => send("hod", { action: "forward", scores: hodS, remarks }, "Sent to the Principal.")}>Send to Principal</button>
              </div>
            </>
          ) : (
            <>
              <h3>HOD remarks</h3>
              <p className="hr-pre">{ap.hod_remarks || <span className="rg-muted">{ap.status === "done" || !showHod ? "—" : "Not reviewed yet."}</span>}</p>
              {ap.hod_name && <p className="rg-muted hr-small">{ap.hod_name}</p>}
            </>
          )}
          {ap.can_principal ? (
            <>
              <h3>Final grade</h3>
              <select value={grade} onChange={(e) => setGrade(e.target.value)} aria-label="Grade">
                <option value="">Choose</option>
                {ap.grades.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
              </select>
              {ap.suggested_grade && <p className="rg-muted hr-small">The scores suggest {ap.suggested_grade}.</p>}
              <textarea rows={4} value={remarks} onChange={(e) => setRemarks(e.target.value)} aria-label="Principal remarks" placeholder="Your remarks" />
              <input placeholder="Note for sending back" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Send back note" />
              <div className="hr-row hr-end">
                <button type="button" className="btn-edit" disabled={busy} onClick={() => send("principal", { action: "send_back", note }, "Sent back.")}>Send back</button>
                <button type="button" className="btn-primary" disabled={busy} onClick={() => send("principal", { action: "finalise", grade, remarks }, "Finalised. The teacher can see it now.")}>Finalise</button>
              </div>
            </>
          ) : ap.status === "done" && (
            <>
              <h3>Final grade</h3>
              <p className="hr-grade">{ap.grade} <span>{ap.grade_label}</span></p>
              <p className="hr-pre">{ap.principal_remarks}</p>
              {ap.principal_name && <p className="rg-muted hr-small">{ap.principal_name} · {fmt(ap.finalised_at)}</p>}
            </>
          )}
        </section>
      </div>
    </>
  );
}
