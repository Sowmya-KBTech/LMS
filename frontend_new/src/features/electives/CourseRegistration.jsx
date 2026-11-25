// ============================================================
// CBCS PART A - Course registration (one file, three screens)
// ============================================================
//   MyCourseRegistration  student: rank electives, live credits, submit,
//                         status, comment, what they got after allocation
//                         (shown on the student's Electives page)
//   RegistrationReview    class in-charge / HOD / admin: approve or return
//                         (My Class -> "Course registration" tab, and the
//                         Approvals tab of the admin screen)
//   RegistrationAdmin     admin: windows, settings, progress, allocation
//                         (Electives -> "Course registration")
// The server checks every rule; these screens show what it sends back.
// ============================================================
import { useEffect, useState } from "react";

import API from "../../api";

const errText = (err, fallback) => {
  const d = err?.response?.data;
  if (d?.detail) return d.detail;
  if (d && typeof d === "object") return Object.values(d).flat().join(" ");
  return fallback;
};
const fmt = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" })
    : "";
const toLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
const STATUS_TONE = { draft: "", submitted: "info", with_hod: "info", approved: "ok", returned: "warn" };
const STATE_LABEL = { not_open: "Not open yet", open: "Open", closed: "Closed", allocated: "Seats given" };

// ============================================================
// STUDENT
// ============================================================
function initialPicks(data) {
  const out = {};
  for (const g of data.groups) {
    out[g.id] = g.options.filter((o) => o.rank).sort((a, b) => a.rank - b.rank).map((o) => o.id);
  }
  return out;
}

export function MyCourseRegistration({ data, onChange }) {
  const [picks, setPicks] = useState(() => initialPicks(data));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const w = data.window;
  const editable = data.can_edit;
  const maxRanks = (g) => Math.max(w.max_ranks, g.picks);
  const allocated = w.state === "allocated";

  const toggle = (g, o) => {
    if (!editable || o.blocked) return;
    const cur = picks[g.id] || [];
    const next = cur.includes(o.id) ? cur.filter((x) => x !== o.id) : cur.length >= maxRanks(g) ? cur : [...cur, o.id];
    setPicks({ ...picks, [g.id]: next });
    setNotice("");
  };

  const coreCredits = data.core.reduce((s, c) => s + Number(c.credits || 0), 0);
  const credits =
    coreCredits +
    data.groups.reduce((s, g) => {
      const ids = (picks[g.id] || []).slice(0, g.picks);
      return s + g.options.filter((o) => ids.includes(o.id)).reduce((t, o) => t + Number(o.credits || 0), 0);
    }, 0);
  const missing = data.groups.filter((g) => (picks[g.id] || []).length < g.picks);
  const under = credits < Number(data.min_credits || 0);
  const over = data.limit != null && credits > Number(data.limit);
  const changed = JSON.stringify(picks) !== JSON.stringify(initialPicks(data));

  const choicesBody = () => ({
    choices: data.groups.flatMap((g) => (picks[g.id] || []).map((id, i) => ({ group: g.id, option: id, rank: i + 1 }))),
  });

  const send = async (submitting) => {
    setBusy(true);
    setError("");
    try {
      const r = submitting
        ? await API.post("/course-registration/me/submit/", choicesBody())
        : await API.put("/course-registration/me/", choicesBody());
      setNotice(submitting ? "Submitted. Your class in-charge will review it." : "Saved. Submit it before the window closes.");
      onChange(r.data);
    } catch (err) {
      setError(errText(err, "Could not save. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const meterMax = Math.max(Number(data.limit || 0), credits, 1);

  // CBCS PART B: this semester's credits per category (core + the options that count)
  const thisSem = {};
  for (const c of data.core) if (c.category) thisSem[c.category] = (thisSem[c.category] || 0) + Number(c.credits || 0);
  for (const g of data.groups) {
    const ids = (picks[g.id] || []).slice(0, g.picks);
    for (const o of g.options) {
      if (ids.includes(o.id) && o.category) thisSem[o.category] = (thisSem[o.category] || 0) + Number(o.credits || 0);
    }
  }
  const tone = STATUS_TONE[data.status] || "";

  return (
    <div className="crg">
      <div className="card crg-banner">
        <div>
          <b>{w.name} · Semester {w.semester}</b>
          <span className="el-muted">
            {w.state === "open" && `Open until ${fmt(w.closes_at)}. Rank up to ${w.max_ranks} choices in each elective.`}
            {w.state === "not_open" && `Opens ${fmt(w.opens_at)}.`}
            {w.state === "closed" && "The window has closed. Seats will be given soon."}
            {allocated && "Seats have been given. Your electives are below."}
            {w.state !== "not_open" && !allocated &&
              (w.allocation === "cgpa"
                ? " Seats are given after the window closes, by CGPA; your rank decides which one you get."
                : " Seats are given in the order students submit; your rank decides which one you get.")}
          </span>
        </div>
        <span className={`kb-pill ${tone}`}>{data.status_label}</span>
      </div>

      {error && <div className="tb-error">{error}</div>}
      {notice && <div className="card ems-notice" role="status">{notice}</div>}

      {data.comment && (
        <div className="card crg-comment">
          <b>Comment from {data.returned_by || "your class in-charge"}</b>
          <p>{data.comment}</p>
        </div>
      )}

      <div className="crg-cols">
        <div className="crg-main">
          <div className="card">
            <div className="ems-head">
              <h3>Core subjects</h3>
              <span className="el-muted">Added for you · {coreCredits} credits</span>
            </div>
            {data.core.length === 0 ? (
              <p className="el-muted">No core subjects are set up for your class yet.</p>
            ) : (
              <div className="table-container">
                <table className="sd-tbl">
                  <thead><tr><th>Subject</th><th>L-T-P</th><th>Credits</th></tr></thead>
                  <tbody>
                    {data.core.map((c) => (
                      <tr key={c.code + c.name}><td><b>{c.code}</b> {c.name}</td><td>{c.ltp}</td><td>{c.credits}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {data.groups.map((g) => {
            const mine = picks[g.id] || [];
            return (
              <div className="card" key={g.id}>
                <div className="ems-head">
                  <h3>{g.name}</h3>
                  <span className="el-muted">
                    {g.open_elective ? "Open elective · from other departments · " : ""}
                    Take {g.picks}{editable ? ` · click in your order of choice (up to ${maxRanks(g)})` : ""}
                  </span>
                </div>
                <div className="crg-opts">
                  {g.options.map((o) => {
                    const r = mine.indexOf(o.id);
                    const full = o.seats_left === 0;
                    return (
                      <button
                        type="button"
                        key={o.id}
                        className={`crg-opt${r >= 0 ? " on" : ""}${o.blocked && r < 0 ? " off" : ""}`}
                        onClick={() => toggle(g, o)}
                        disabled={!editable || (Boolean(o.blocked) && r < 0)}
                        aria-pressed={r >= 0}
                      >
                        <span className={`crg-rank${r >= 0 ? " on" : ""}`} aria-hidden="true">{r >= 0 ? r + 1 : ""}</span>
                        <span className="crg-opt-text">
                          <b>{o.code} {o.subject}</b>
                          <span className="el-muted">
                            {[g.open_elective ? o.course_name : "", o.teacher_name, `${o.credits} credits`,
                              o.first_choice ? `${o.first_choice} asked as 1st` : ""].filter(Boolean).join(" · ")}
                          </span>
                          {o.blocked && <span className="crg-why">{o.blocked}</span>}
                        </span>
                        {o.blocked && !(allocated && o.result) ? (
                          <span className="kb-pill bad">Not available</span>
                        ) : allocated && o.result ? (
                          <span className={`kb-pill ${o.result === "allotted" ? "ok" : o.result === "waitlist" ? "warn" : ""}`}>
                            {o.result === "allotted" ? "You got this" : o.result === "waitlist" ? `Waitlist #${o.waitlist_no}` : "Not given"}
                          </span>
                        ) : (
                          <span className={`kb-pill ${full ? "warn" : ""}`}>
                            {o.seats_left == null ? "Open seats" : full ? "Full · waitlist" : `${plural(o.seats_left, "seat")} left`}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        <aside className="crg-side">
          <div className="card">
            <h3>Credits this semester</h3>
            <div className="crg-big">
              {credits}
              <span className="el-muted">
                {data.limit != null ? ` credits · allowed ${data.min_credits} to ${data.limit}` : ` credits · at least ${data.min_credits}`}
              </span>
            </div>
            <div className="crg-meter" role="img" aria-label={`${credits} credits`}>
              <span className={over ? "over" : ""} style={{ width: `${Math.min(100, (credits * 100) / meterMax)}%` }} />
            </div>
            {missing.length > 0 && <p className="kb-pill warn crg-wrap">Choose in {missing.map((g) => g.name).join(", ")}.</p>}
            {missing.length === 0 && under && <p className="kb-pill warn crg-wrap">Below the minimum of {data.min_credits}.</p>}
            {over && <p className="kb-pill bad crg-wrap">Above the limit of {data.limit}.</p>}
            {missing.length === 0 && !under && !over && <p className="kb-pill ok crg-wrap">Within the limit.</p>}
            {(data.issues || []).filter((i) => i.code === "first_full").map((i) => (
              <p key={i.text} className="el-muted">{i.text}</p>
            ))}
          </div>

          {data.degree && (
            <div className="card">
              <h3>Towards your degree</h3>
              {data.degree.categories.filter((c) => c.required || thisSem[c.code]).map((c) => (
                <div key={c.code} className="crg-line">
                  <span>{c.name} <span className="el-muted">({c.code})</span></span>
                  <b>{c.earned}{thisSem[c.code] ? ` + ${thisSem[c.code]}` : ""} / {c.required}</b>
                </div>
              ))}
              <div className="crg-line">
                <span>Total credits</span>
                <b>{data.degree.earned} + {credits} / {data.degree.required}</b>
              </div>
              <p className="el-muted">Earned so far + this semester, against {data.degree.regulation}.</p>
            </div>
          )}

          {editable && (
            <div className="card crg-actions">
              <button className="btn-primary" type="button" disabled={busy || missing.length > 0 || under || over}
                onClick={() => send(true)}>
                {busy ? "Saving…" : data.status === "returned" && !changed ? "Submit again" : "Submit for approval"}
              </button>
              <button className="btn-secondary" type="button" disabled={busy || !changed} onClick={() => send(false)}>
                Save without submitting
              </button>
              <p className="el-muted">
                Your class in-charge approves it{w.hod_approval ? ", then the HOD" : ""}. Changing a submitted
                registration takes it back: you submit again.
              </p>
            </div>
          )}
          {data.submitted_at && <p className="el-muted">Submitted {fmt(data.submitted_at)}</p>}
        </aside>
      </div>
    </div>
  );
}

// ============================================================
// CLASS IN-CHARGE / HOD / ADMIN: APPROVALS
// ============================================================
const REVIEW_TABS = [
  ["waiting", "Waiting"],
  ["returned", "Returned"],
  ["approved", "Approved"],
  ["not_submitted", "Not submitted"],
];

export function RegistrationReview({ windowId }) {
  const [tab, setTab] = useState("waiting");
  const [data, setData] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    const q = new URLSearchParams({ tab });
    if (windowId) q.set("window", windowId);
    API.get(`/course-registration/review/?${q}`)
      .then((r) => live && setData(r.data))
      .catch((err) => live && setError(errText(err, "Could not load registrations.")));
    return () => { live = false; };
  }, [tab, windowId, tick]);

  const act = async (fn, msg) => {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      setNotice(typeof msg === "function" ? msg(r.data) : msg);
      setOpenId(null);
      setComment("");
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  if (!data) return error ? <div className="tb-error">{error}</div> : <div className="card"><p className="el-muted">Loading…</p></div>;
  if (!data.window) return <div className="card"><p className="el-muted">No course registration is open now.</p></div>;

  const rows = data.rows || [];
  const okIds = rows.filter((r) => r.ok && r.can_act).map((r) => r.id);

  return (
    <div className="crg">
      <div className="ems-head">
        <p className="el-muted">
          {data.window.name} · Semester {data.window.semester} · closes {fmt(data.window.closes_at)}
          {data.window.hod_approval ? " · class in-charge, then HOD" : ""}
        </p>
        <button type="button" className="btn-secondary"
          onClick={() => downloadStudents(data.window.id).catch((err) => setError(errText(err, "Could not download.")))}>
          Download student list
        </button>
      </div>
      <div className="ems-seg crg-tabs" role="tablist">
        {REVIEW_TABS.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""}
            onClick={() => { setTab(k); setOpenId(null); setNotice(""); }}>
            {label} ({data.counts?.[k] ?? 0})
          </button>
        ))}
      </div>

      {error && <div className="tb-error">{error}</div>}
      {notice && <div className="card ems-notice" role="status">{notice}</div>}

      <div className="card">
        {tab === "waiting" && okIds.length > 0 && (
          <div className="ems-head">
            <span className="el-muted">{plural(okIds.length, "registration")} with no problems.</span>
            <button className="btn-primary" type="button" disabled={busy}
              onClick={() => act(() => API.post("/course-registration/review/approve-ok/", { ids: okIds }),
                (d) => `Approved ${d.approved}.${d.skipped ? ` ${d.skipped} need a look.` : ""}`)}>
              Approve the {okIds.length} with no problems
            </button>
          </div>
        )}
        {rows.length === 0 ? (
          <p className="el-muted">Nobody here.</p>
        ) : tab === "not_submitted" ? (
          <div className="table-container">
            <table className="sd-tbl">
              <thead><tr><th>Student</th><th>Class</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.student}><td><b>{r.name}</b> <span className="el-muted">{r.roll_number}</span></td><td>{r.course_name}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="table-container">
            <table className="sd-tbl">
              <thead><tr><th>Student</th><th>Credits</th><th>Choices</th><th>Checks</th><th></th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <RegistrationRow key={r.id} r={r} open={openId === r.id} busy={busy} comment={comment}
                    setComment={setComment}
                    onOpen={() => { setOpenId(openId === r.id ? null : r.id); setComment(r.comment || ""); }}
                    onApprove={() => act(() => API.post(`/course-registration/${r.id}/approve/`),
                      (d) => `${r.name}: ${d.status_label}.`)}
                    onReturn={() => act(() => API.post(`/course-registration/${r.id}/return/`, { comment }),
                      `${r.name}'s registration was returned.`)} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function RegistrationRow({ r, open, busy, comment, setComment, onOpen, onApprove, onReturn }) {
  const blocking = r.issues.filter((i) => i.blocking);
  const warnings = r.issues.filter((i) => !i.blocking);
  return (
    <>
      <tr>
        <td>
          <b>{r.name}</b>
          <div className="el-muted">{[r.roll_number, r.cgpa != null ? `CGPA ${r.cgpa}` : ""].filter(Boolean).join(" · ")}</div>
        </td>
        <td>{r.credits}</td>
        <td>
          {r.choices.map((c) => (
            <div key={c.group}><span className="el-muted">{c.group}:</span> {c.options.join(", ") || "—"}</div>
          ))}
        </td>
        <td>
          {blocking.map((i) => <span key={i.text} className="kb-pill bad crg-wrap">{i.text}</span>)}
          {warnings.map((i) => <span key={i.text} className="kb-pill warn crg-wrap">{i.text}</span>)}
          {r.issues.length === 0 && <span className="kb-pill ok">All fine</span>}
        </td>
        <td>
          {(r.can_act || r.can_return) && (
            <button type="button" className="btn-secondary" onClick={onOpen}>{open ? "Close" : "Open"}</button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="crg-open-row">
          <td colSpan={5}>
            <label className="crg-field">
              Comment to the student (needed when returning)
              <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
            </label>
            <div className="ems-actions">
              {r.can_act && (
                <button type="button" className="btn-primary" disabled={busy || blocking.length > 0} onClick={onApprove}
                  title={blocking.length ? "Fix the problems first, or return it" : undefined}>
                  Approve
                </button>
              )}
              <button type="button" className="btn-secondary" disabled={busy} onClick={onReturn}>Return to student</button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ============================================================
// ADMIN: WINDOWS, SETTINGS, ALLOCATION
// ============================================================
const EMPTY_WINDOW = {
  name: "", semester: "", courses: [], opens_at: "", closes_at: "", min_credits: "", max_credits: "",
  extra_cgpa: "", extra_credits: 0, allocation: "cgpa", max_ranks: 3, hod_approval: false, min_strength: 15,
};

export function RegistrationAdmin({ isAdmin }) {
  const [windows, setWindows] = useState(null);
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState("settings");
  const [tick, setTick] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    API.get("/course-registration/windows/")
      .then((r) => live && setWindows(r.data))
      .catch((err) => live && setError(errText(err, "Could not load registration windows.")));
    return () => { live = false; };
  }, [tick]);

  const reload = (id) => { setTick((t) => t + 1); if (id !== undefined) setSelected(id); };

  if (error) return <div className="tb-error">{error}</div>;
  if (!windows) return <div className="card"><p className="el-muted">Loading…</p></div>;

  const current = windows.find((w) => w.id === selected);
  return (
    <div className="crg">
      <div className="card">
        <div className="ems-head">
          <h3>Registration windows</h3>
          {isAdmin && (
            <button className="btn-primary" type="button" onClick={() => { setSelected("new"); setView("settings"); }}>
              + New window
            </button>
          )}
        </div>
        {windows.length === 0 && selected !== "new" && <p className="el-muted">No registration window yet.</p>}
        <ul className="ems-groups">
          {windows.map((w) => (
            <li key={w.id}>
              <button type="button" className={`crg-win${selected === w.id ? " on" : ""}`}
                onClick={() => { setSelected(w.id); setView("settings"); }}>
                <b>{w.name}</b>
                <span className="el-muted">
                  Semester {w.semester} · {w.course_names.length ? w.course_names.join(", ") : "all courses"} · {fmt(w.opens_at)} to {fmt(w.closes_at)}
                </span>
                <span className={`kb-pill ${w.state === "open" ? "ok" : w.state === "allocated" ? "info" : ""}`}>{STATE_LABEL[w.state]}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {selected === "new" && <WindowSettings key="new" isAdmin={isAdmin} onSaved={(w) => reload(w.id)} onDeleted={() => reload(null)} />}

      {current && (
        <>
          <div className="ems-seg crg-tabs" role="tablist">
            {[["settings", "Settings"], ["approvals", "Approvals"], ["allocation", "Allocation"]].map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={view === k} className={view === k ? "on" : ""}
                onClick={() => setView(k)}>{label}</button>
            ))}
          </div>
          {view === "settings" && (
            <WindowSettings key={current.id} id={current.id} isAdmin={isAdmin}
              onSaved={() => reload()} onDeleted={() => reload(null)} />
          )}
          {view === "approvals" && <RegistrationReview windowId={current.id} />}
          {view === "allocation" && <Allocation key={current.id} id={current.id} isAdmin={isAdmin} state={current.state} />}
        </>
      )}
    </div>
  );
}

function WindowSettings({ id, isAdmin, onSaved, onDeleted }) {
  const [form, setForm] = useState(id ? null : EMPTY_WINDOW);
  const [info, setInfo] = useState(null);
  const [courses, setCourses] = useState([]);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let live = true;
    API.get("/courses/").then((r) => live && setCourses(r.data.results || r.data)).catch(() => {});
    if (id) {
      API.get(`/course-registration/windows/${id}/`).then((r) => {
        if (!live) return;
        const w = r.data;
        setInfo(w);
        setForm({
          ...EMPTY_WINDOW, ...w,
          opens_at: toLocalInput(w.opens_at), closes_at: toLocalInput(w.closes_at),
          max_credits: w.max_credits ?? "", extra_cgpa: w.extra_cgpa ?? "",
        });
      });
    }
    return () => { live = false; };
  }, [id]);

  if (!form) return <div className="card"><p className="el-muted">Loading…</p></div>;
  const locked = !isAdmin || info?.state === "allocated";
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const toggleCourse = (cid) =>
    setForm({ ...form, courses: form.courses.includes(cid) ? form.courses.filter((c) => c !== cid) : [...form.courses, cid] });

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    setNotice("");
    const body = { ...form, opens_at: fromLocalInput(form.opens_at), closes_at: fromLocalInput(form.closes_at) };
    for (const k of ["state", "progress", "groups", "course_names", "allocated_at", "id"]) delete body[k];
    try {
      const r = id
        ? await API.patch(`/course-registration/windows/${id}/`, body)
        : await API.post("/course-registration/windows/", body);
      setInfo(r.data);
      setNotice("Saved.");
      onSaved(r.data);
    } catch (err) {
      const d = err?.response?.data || {};
      setErrors(d.detail ? { detail: d.detail } : d);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete this registration window?")) return;
    try {
      await API.delete(`/course-registration/windows/${id}/`);
      onDeleted();
    } catch (err) {
      setErrors({ detail: errText(err, "Could not delete.") });
    }
  };

  const err = (k) => errors[k] && <small className="crg-err">{[].concat(errors[k]).join(" ")}</small>;
  const p = info?.progress;

  return (
    <div className="crg-cols">
      <form className="card crg-main" onSubmit={save}>
        <h3>{id ? "Settings" : "New registration window"}</h3>
        {errors.detail && <div className="tb-error">{errors.detail}</div>}
        {notice && <div className="ems-notice" role="status">{notice}</div>}
        <fieldset disabled={locked} className="crg-fieldset">
          <div className="ems-form">
            <label>Name<input value={form.name} onChange={set("name")} placeholder="Odd semester 2026-27" />{err("name")}</label>
            <label>Semester
              <select value={form.semester} onChange={set("semester")}>
                <option value="">Choose…</option>
                {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => <option key={s} value={s}>Semester {s}</option>)}
              </select>{err("semester")}
            </label>
            <label>Opens<input type="datetime-local" value={form.opens_at} onChange={set("opens_at")} />{err("opens_at")}</label>
            <label>Closes<input type="datetime-local" value={form.closes_at} onChange={set("closes_at")} />{err("closes_at")}</label>
            <label>How seats are given
              <select value={form.allocation} onChange={set("allocation")}>
                <option value="cgpa">By CGPA after the window closes</option>
                <option value="fcfs">By who submitted first</option>
              </select>
            </label>
            <label>Choices a student may rank<input type="number" min="1" max="10" value={form.max_ranks} onChange={set("max_ranks")} />{err("max_ranks")}</label>
            <div className="ems-wide">
              <span className="crg-label">Courses <small>(none ticked = every course with this semester)</small></span>
              <div className="crg-checks">
                {courses.map((c) => (
                  <label key={c.id} className="crg-check">
                    <input type="checkbox" checked={form.courses.includes(c.id)} onChange={() => toggleCourse(c.id)} /> {c.name}
                  </label>
                ))}
              </div>
              {err("courses")}
            </div>
          </div>
          <h3>Credit limits</h3>
          <div className="ems-form">
            <label>Minimum<input type="number" step="0.5" min="0" value={form.min_credits} onChange={set("min_credits")} />{err("min_credits")}</label>
            <label>Maximum<input type="number" step="0.5" min="0" value={form.max_credits} onChange={set("max_credits")} />{err("max_credits")}</label>
            <label>Extra allowed when CGPA is at least<input type="number" step="0.01" min="0" max="10" value={form.extra_cgpa} onChange={set("extra_cgpa")} placeholder="e.g. 8.5" />{err("extra_cgpa")}</label>
            <label>Extra credits<input type="number" step="0.5" min="0" value={form.extra_credits} onChange={set("extra_credits")} />{err("extra_credits")}</label>
          </div>
          <h3>Approval and options</h3>
          <div className="ems-form">
            <label className="crg-check ems-wide">
              <input type="checkbox" checked={form.hod_approval} onChange={set("hod_approval")} />
              HOD approves after the class in-charge
            </label>
            <label>Flag an option with fewer students than<input type="number" min="0" value={form.min_strength} onChange={set("min_strength")} />{err("min_strength")}</label>
          </div>
        </fieldset>
        <p className="el-muted">
          When the window closes, registrations still waiting for approval are approved automatically if they pass every check.
        </p>
        {!locked && (
          <div className="ems-actions">
            {id && <button type="button" className="btn-delete" onClick={remove}>Delete</button>}
            <button type="submit" className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          </div>
        )}
      </form>

      {info && (
        <aside className="crg-side">
          <div className="card">
            <h3>Progress</h3>
            <dl className="crg-dl">
              <dt>Students</dt><dd>{p.students}</dd>
              <dt>Not started</dt><dd>{p.not_started}</dd>
              <dt>Saved, not submitted</dt><dd>{p.draft}</dd>
              <dt>With class in-charge</dt><dd>{p.submitted}</dd>
              {info.hod_approval && <><dt>With HOD</dt><dd>{p.with_hod}</dd></>}
              <dt>Returned</dt><dd>{p.returned}</dd>
              <dt>Approved</dt><dd>{p.approved}</dd>
            </dl>
          </div>
          <div className="card">
            <h3>Elective groups in this window</h3>
            {info.groups.length === 0 && <p className="el-muted">No elective groups for Semester {info.semester} yet. Add them under Elective groups.</p>}
            {info.groups.map((g) => (
              <div key={g.id} className="crg-line">
                <span><b>{g.name}</b> · {g.course_name} · take {g.picks}</span>
                <span className="kb-pill">{plural(g.options, "option")}</span>
              </div>
            ))}
          </div>
        </aside>
      )}
    </div>
  );
}

function Allocation({ id, isAdmin, state }) {
  const [report, setReport] = useState(null);
  const [skip, setSkip] = useState([]);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [manual, setManual] = useState({});

  useEffect(() => {
    let live = true;
    API.get(`/course-registration/windows/${id}/allocation/?skip=${skip.join(",")}`)
      .then((r) => live && setReport(r.data))
      .catch((err) => live && setError(errText(err, "Could not run the allocation.")));
    return () => { live = false; };
  }, [id, skip, tick]);

  if (!isAdmin) return <div className="card"><p className="el-muted">Only the academic admin gives seats.</p></div>;
  if (!report) return error ? <div className="tb-error">{error}</div> : <div className="card"><p className="el-muted">Working it out…</p></div>;

  const run = async (fn, msg) => {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      setNotice(typeof msg === "function" ? msg(r.data) : msg);
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  const confirm = () => {
    if (!window.confirm("Give seats now? Students are enrolled and told. This can't be run again.")) return;
    run(() => API.post(`/course-registration/windows/${id}/allocation/`, { skip }), "Seats given. Students have been enrolled and told.");
  };

  const toggleSkip = (oid) => setSkip(skip.includes(oid) ? skip.filter((x) => x !== oid) : [...skip, oid]);

  const download = () => {
    const head = ["Group", "Code", "Subject", "Teacher", "Seats", "Filled", "Asked as 1st", "Waitlist"];
    const lines = [head, ...report.options.map((o) => [o.group_name, o.code, o.subject, o.teacher_name,
      o.seat_limit ?? "", o.filled, o.first_choice, o.waitlist])];
    saveCsv(lines, "allocation.csv");
  };

  const freeIn = (groupId) =>
    report.options.filter((o) => o.group === groupId && (o.seat_limit == null || o.filled < o.seat_limit));

  return (
    <div className="crg">
      {error && <div className="tb-error">{error}</div>}
      {notice && <div className="card ems-notice" role="status">{notice}</div>}

      <div className="crg-stats">
        <div className="card"><span className="el-muted">Submitted</span><b>{report.submitted} / {report.students}</b></div>
        <div className="card"><span className="el-muted">Approved</span><b>{report.approved}{report.auto_approved ? ` + ${report.auto_approved} auto` : ""}</b></div>
        <div className="card"><span className="el-muted">Got their 1st choice</span><b>{report.first_choice_pct}%</b></div>
        <div className="card"><span className="el-muted">Without a seat</span><b className={report.unplaced.length ? "crg-bad" : ""}>{report.unplaced.length}</b></div>
      </div>

      <div className="card">
        <div className="ems-head">
          <div>
            <h3>{report.saved ? `Seats given ${fmt(report.allocated_at)}` : "Trial run · not saved yet"}</h3>
            <span className="el-muted">
              {report.saved
                ? "Students are enrolled. When seats free up, move waitlisted students in."
                : `Each student gets the highest-ranked option with a free seat. Untick an option to cancel it; its students move to their next choice.${state === "open" ? " The window is still open, so this can change; you can confirm after it closes." : ""}`}
            </span>
          </div>
          <div className="ems-actions">
            <button type="button" className="btn-secondary" onClick={download}>Download options (Excel CSV)</button>
            <button type="button" className="btn-secondary" onClick={() => downloadStudents(id).catch((err) => setError(errText(err, "Could not download.")))}>
              Download student list
            </button>
            {report.saved ? (
              <button type="button" className="btn-primary" disabled={busy}
                onClick={() => run(() => API.post(`/course-registration/windows/${id}/fill-waitlist/`),
                  (d) => (d.moved ? `${plural(d.moved, "student")} moved up from the waitlist.` : "No free seats for waitlisted students."))}>
                Fill free seats from the waitlist
              </button>
            ) : (
              <>
                <button type="button" className="btn-secondary" disabled={busy} onClick={() => setTick((t) => t + 1)}>Run again</button>
                <button type="button" className="btn-primary" disabled={busy || state !== "closed"} onClick={confirm}
                  title={state !== "closed" ? "You can confirm after the window closes" : undefined}>
                  Confirm and enrol students
                </button>
              </>
            )}
          </div>
        </div>
        <div className="table-container">
          <table className="sd-tbl">
            <thead>
              <tr>{!report.saved && <th>Runs</th>}<th>Option</th><th>Group</th><th>Seats filled</th><th>Asked as 1st</th><th>Waitlist</th><th></th></tr>
            </thead>
            <tbody>
              {report.options.map((o) => {
                const pct = o.seat_limit ? Math.min(100, (o.filled * 100) / o.seat_limit) : 0;
                return (
                  <tr key={o.option} className={o.note === "cancelled" ? "crg-dim" : ""}>
                    {!report.saved && (
                      <td><input type="checkbox" aria-label={`Run ${o.subject}`} checked={!skip.includes(o.option)}
                        onChange={() => toggleSkip(o.option)} /></td>
                    )}
                    <td><b>{o.code}</b> {o.subject}<div className="el-muted">{o.teacher_name}</div></td>
                    <td>{o.group_name}<div className="el-muted">{o.course_name}</div></td>
                    <td>
                      <div className="crg-fill-cell">
                        {o.seat_limit != null && (
                          <span className="crg-fill"><span className={o.filled >= o.seat_limit ? "over" : ""} style={{ width: `${pct}%` }} /></span>
                        )}
                        {o.filled}{o.seat_limit != null ? ` / ${o.seat_limit}` : ""}
                      </div>
                    </td>
                    <td>{o.first_choice}</td>
                    <td>{o.waitlist || ""}</td>
                    <td>
                      {o.note === "popular" && <span className="kb-pill warn">Popular</span>}
                      {o.note === "low" && <span className="kb-pill bad">Few students</span>}
                      {o.note === "cancelled" && <span className="kb-pill">Cancelled</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {report.unplaced.length > 0 && (
        <div className="card">
          <h3>Students without a seat ({report.unplaced.length})</h3>
          <p className="el-muted">
            {report.saved
              ? "All their choices were full. Give them a seat here."
              : "All their choices are full in this trial. After confirming you can give them a seat here."}
          </p>
          <div className="table-container">
            <table className="sd-tbl">
              <tbody>
                {report.unplaced.map((u) => {
                  const key = `${u.student}-${u.group}`;
                  return (
                    <tr key={key}>
                      <td><b>{u.name}</b> <span className="el-muted">{u.roll_number} · {u.group_name}</span></td>
                      {report.saved && (
                        <td>
                          <div className="crg-inline">
                            <select value={manual[key] || ""} onChange={(e) => setManual({ ...manual, [key]: e.target.value })}>
                              <option value="">Choose…</option>
                              {freeIn(u.group).map((o) => (
                                <option key={o.option} value={o.option}>
                                  {o.subject}{o.seat_limit != null ? ` (${o.seat_limit - o.filled} free)` : ""}
                                </option>
                              ))}
                            </select>
                            <button type="button" className="btn-primary" disabled={busy || !manual[key]}
                              onClick={() => run(() => API.post("/electives/allocate/", { student: u.student, option: manual[key] }),
                                `${u.name} has a seat now.`)}>
                              Give seat
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// CBCS PART B: student list (Excel CSV) and the prerequisite picker
// ============================================================
function saveCsv(lines, name) {
  const csv = lines.map((l) => l.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv" }));
  a.download = name;
  a.click();
}

async function downloadStudents(windowId) {
  const r = await API.get(`/course-registration/windows/${windowId}/students/`);
  const groups = [...new Set(r.data.rows.flatMap((x) => x.groups.map((g) => g.group)))];
  const head = ["Roll no", "Name", "Class", "Status", "Credits",
    ...groups.flatMap((g) => [`${g}: choices in order`, `${g}: got`])];
  const lines = [head, ...r.data.rows.map((x) => [
    x.roll_number, x.name, x.course_name, x.status, x.credits ?? "",
    ...groups.flatMap((name) => {
      const g = x.groups.find((y) => y.group === name);
      return g ? [g.ranked.join(" > "), g.got.join(", ")] : ["", ""];
    }),
  ])];
  saveCsv(lines, `${r.data.window} - students.csv`);
}

export function PrerequisiteEditor({ option, busy, onSave }) {
  const [choices, setChoices] = useState(null);
  const [picked, setPicked] = useState(() => option.requires.map((r) => r.id));
  useEffect(() => {
    let live = true;
    API.get(`/electives/options/${option.id}/prerequisites/`)
      .then((r) => live && setChoices(r.data))
      .catch(() => live && setChoices([]));
    return () => { live = false; };
  }, [option.id]);
  if (!choices) return <p className="el-muted">Loading…</p>;
  return (
    <div className="crg-prereq">
      <span className="crg-label">
        Students must have passed these to take {option.subject} <small>(earlier semesters of {option.course_name || "the course"})</small>
      </span>
      {choices.length === 0 ? (
        <p className="el-muted">No subjects in earlier semesters.</p>
      ) : (
        <div className="crg-checks">
          {choices.map((c) => (
            <label key={c.id} className="crg-check">
              <input type="checkbox" checked={picked.includes(c.id)}
                onChange={() => setPicked(picked.includes(c.id) ? picked.filter((x) => x !== c.id) : [...picked, c.id])} />
              {c.code} {c.name} <span className="el-muted">· Sem {c.semester}</span>
            </label>
          ))}
        </div>
      )}
      <div className="ems-actions">
        <button type="button" className="btn-primary" disabled={busy} onClick={() => onSave(picked)}>Save prerequisite</button>
      </div>
    </div>
  );
}
