// WAVE 1 - mentoring & guidance records, by category.
//   <MentoringRecords studentId=... />  mentor / HOD: one student's records, add and edit
//   <MyGuidance />                      student: their own history (no private notes)
//   <HodRecordsSummary academicYear />  HOD: counts by category and mentor, students not met
import { useCallback, useEffect, useState } from "react";

import {
  CATEGORY_TONE, addRecord, deleteRecord, getMyGuidance, getRecordsSummary,
  getStudentRecords, recordError, showDate, updateRecord,
} from "./recordsApi";
import "../../styles/MentorAllocation.css";
import "../../styles/MentoringRecords.css";

const today = () => new Date().toISOString().slice(0, 10);
const EMPTY = { date: "", category: "", mode: "one_to_one", summary: "", action_points: "", follow_up_date: "", private_note: "" };

function RecordItem({ rec, onEdit, onDelete }) {
  return (
    <div className="mr-item">
      <div className="mr-item-head">
        <span className="mr-date">{showDate(rec.date)}</span>
        <span className={`ma-pill ${CATEGORY_TONE[rec.category] || "ma-grey"}`}>{rec.category_label}</span>
        <span className="mr-meta">{rec.mode_label} · {rec.mentor_name}</span>
        <span className="mr-grow" />
        {rec.can_edit && onEdit && (
          <>
            <button className="ma-btn small" onClick={() => onEdit(rec)}>Edit</button>
            <button className="ma-btn small" onClick={() => onDelete(rec)}>Delete</button>
          </>
        )}
      </div>
      <p className="mr-summary">{rec.summary}</p>
      {rec.action_points && <div className="mr-sub"><b>Action points</b>{rec.action_points}</div>}
      {rec.follow_up_date && <div className="mr-sub"><b>Follow-up</b>{showDate(rec.follow_up_date)}</div>}
      {rec.private_note && (
        <div className="mr-private">
          <b>Private note · only you and the HOD can see this</b>
          {rec.private_note}
        </div>
      )}
    </div>
  );
}

function RecordForm({ modes, categories, initial, onSave, onCancel, saving, error }) {
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSave(f); }}
      className="ma-panel-body"
      style={{ borderBottom: "1px solid #ECECF0" }}
    >
      <div className="mr-form">
        <label>Date
          <input className="ma-input" type="date" max={today()} value={f.date} onChange={set("date")} required />
        </label>
        <label>Category
          <select className="ma-input" value={f.category} onChange={set("category")} required>
            <option value="">Choose…</option>
            {categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </label>
        <label>How
          <select className="ma-input" value={f.mode} onChange={set("mode")}>
            {modes.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </label>
        <label>Follow-up date
          <input className="ma-input" type="date" value={f.follow_up_date || ""} onChange={set("follow_up_date")} />
        </label>
        <label className="mr-wide">Summary
          <textarea value={f.summary} onChange={set("summary")} required
            placeholder="What was discussed. The student can read this." />
        </label>
        <label className="mr-wide">Action points
          <textarea value={f.action_points} onChange={set("action_points")}
            placeholder="What the student will do next (optional)" />
        </label>
        <label className="mr-wide">Private note
          <span className="mr-hint">Only you and the HOD can see this. Never shown to the student or parents.</span>
          <textarea value={f.private_note} onChange={set("private_note")} placeholder="Optional" />
        </label>
      </div>
      {error && <div className="mr-error">{error}</div>}
      <div className="mr-actions">
        <button type="button" className="ma-btn" onClick={onCancel} disabled={saving}>Cancel</button>
        <button type="submit" className="ma-btn primary" disabled={saving}>{saving ? "Saving…" : "Save record"}</button>
      </div>
    </form>
  );
}

export default function MentoringRecords({ studentId }) {
  const [data, setData] = useState(null);
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState(null);          // null | {mode:"add"} | {mode:"edit", rec}
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(() => {
    setError("");
    getStudentRecords(studentId, category)
      .then(setData)
      .catch((err) => setError(recordError(err, "Could not load the mentoring records.")));
  }, [studentId, category]);

  useEffect(() => { setForm(null); load(); }, [load]);

  const save = async (values) => {
    setSaving(true);
    setFormError("");
    const body = { ...values, follow_up_date: values.follow_up_date || null };
    try {
      if (form?.mode === "edit") await updateRecord(form.rec.id, body);
      else await addRecord({ ...body, student: studentId });
      setForm(null);
      load();
    } catch (err) {
      setFormError(recordError(err, "Could not save the record."));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (rec) => {
    if (!window.confirm(`Delete the ${rec.category_label.toLowerCase()} record of ${showDate(rec.date)}?`)) return;
    try { await deleteRecord(rec.id); load(); } catch (err) { setError(recordError(err, "Could not delete it.")); }
  };

  const total = data ? data.categories.reduce((n, c) => n + c.count, 0) : 0;

  return (
    <div className="ma-panel" style={{ marginTop: 16 }}>
      <div className="ma-panel-head">
        <div>
          <h3>Mentoring &amp; guidance</h3>
          <p>{total} session{total === 1 ? "" : "s"} recorded</p>
        </div>
        {data?.can_add && !form && (
          <button className="ma-btn primary" onClick={() => { setFormError(""); setForm({ mode: "add" }); }}>
            + Record a session
          </button>
        )}
      </div>

      {data && (
        <div className="ma-panel-body" style={{ borderBottom: "1px solid #ECECF0" }}>
          <div className="mr-cats">
            <button className={`mr-cat${category === "" ? " on" : ""}`} onClick={() => setCategory("")}>
              All <b>{total}</b>
            </button>
            {data.categories.map((c) => (
              <button key={c.key} className={`mr-cat${category === c.key ? " on" : ""}`} onClick={() => setCategory(c.key)}>
                {c.label} <b>{c.count}</b>
              </button>
            ))}
          </div>
        </div>
      )}

      {form && data && (
        <RecordForm
          key={form.rec?.id || "new"}
          modes={data.modes}
          categories={data.categories}
          initial={form.mode === "edit"
            ? { ...EMPTY, ...form.rec, follow_up_date: form.rec.follow_up_date || "", private_note: form.rec.private_note || "" }
            : { ...EMPTY, date: today(), category: category || "" }}
          onSave={save}
          onCancel={() => setForm(null)}
          saving={saving}
          error={formError}
        />
      )}

      {error && <div className="ma-empty">{error}</div>}
      {!error && !data && <div className="ma-empty">Loading…</div>}
      {data && data.records.length === 0 && (
        <div className="ma-empty">
          {category ? "No sessions in this category yet." : "No mentoring sessions recorded yet."}
        </div>
      )}
      {data && data.records.length > 0 && (
        <div className="mr-list">
          {data.records.map((r) => (
            <RecordItem key={r.id} rec={r} onEdit={(rec) => { setFormError(""); setForm({ mode: "edit", rec }); }} onDelete={remove} />
          ))}
        </div>
      )}
    </div>
  );
}

export function MyGuidance() {
  const [data, setData] = useState(null);
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getMyGuidance().then(setData).catch((err) => setError(recordError(err, "Could not load your guidance history.")));
  }, []);

  const rows = data ? data.records.filter((r) => !category || r.category === category) : [];

  return (
    <div className="ma-panel">
      <div className="ma-panel-head">
        <div>
          <h3>Guidance history</h3>
          <p>Sessions your mentor recorded with you</p>
        </div>
      </div>
      {data && data.records.length > 0 && (
        <div className="ma-panel-body" style={{ borderBottom: "1px solid #ECECF0" }}>
          <div className="mr-cats">
            <button className={`mr-cat${category === "" ? " on" : ""}`} onClick={() => setCategory("")}>All</button>
            {data.categories.map((c) => (
              <button key={c.key} className={`mr-cat${category === c.key ? " on" : ""}`} onClick={() => setCategory(c.key)}>
                {c.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {error && <div className="ma-empty">{error}</div>}
      {!error && !data && <div className="ma-empty">Loading…</div>}
      {data && rows.length === 0 && <div className="ma-empty">No guidance sessions recorded yet.</div>}
      {rows.length > 0 && <div className="mr-list">{rows.map((r) => <RecordItem key={r.id} rec={r} />)}</div>}
    </div>
  );
}

export function HodRecordsSummary({ academicYear }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    getRecordsSummary(academicYear ? { academic_year: academicYear } : {})
      .then(setData)
      .catch((err) => setError(recordError(err, "Could not load the mentoring sessions.")));
  }, [academicYear]);

  if (error) return <div className="ma-panel" style={{ marginTop: 16 }}><div className="ma-empty">{error}</div></div>;
  if (!data) return null;

  return (
    <div className="ma-panel" style={{ marginTop: 16 }}>
      <div className="ma-panel-head">
        <div>
          <h3>Mentoring sessions</h3>
          <p>{data.total} recorded this academic year</p>
        </div>
      </div>
      <div className="mr-stats">
        {data.by_category.map((c) => (
          <div className="mr-stat" key={c.key}><span>{c.label}</span><b>{c.count}</b></div>
        ))}
      </div>
      <div className="ma-scroll">
        <table className="ma-table">
          <thead>
            <tr><th>Mentor</th><th className="num">Mentees</th><th className="num">Sessions</th>
              <th className="num">Not met in {data.not_met_days} days</th></tr>
          </thead>
          <tbody>
            {data.mentors.length === 0 && (
              <tr><td colSpan={4} className="ma-empty">No mentors allocated this year.</td></tr>
            )}
            {data.mentors.map((m) => (
              <tr key={m.mentor_id}>
                <td><b>{m.mentor_name}</b></td>
                <td className="num">{m.mentees}</td>
                <td className="num">{m.records}</td>
                <td className="num">{m.not_met ? <span className="ma-pill ma-amber">{m.not_met}</span> : 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.not_met.length > 0 && (
        <>
          <div className="ma-panel-head" style={{ borderTop: "1px solid #ECECF0" }}>
            <div>
              <h3>Students not met in {data.not_met_days} days</h3>
              <p>{data.not_met.length} student{data.not_met.length === 1 ? "" : "s"}</p>
            </div>
          </div>
          <div className="ma-scroll">
            <table className="ma-table">
              <thead><tr><th>Student</th><th>Roll no.</th><th>Mentor</th><th>Last session</th></tr></thead>
              <tbody>
                {data.not_met.map((s) => (
                  <tr key={s.student_id}>
                    <td><b>{s.student_name}</b></td>
                    <td>{s.roll_number || "—"}</td>
                    <td>{s.mentor_name}</td>
                    <td>{s.last_met ? showDate(s.last_met) : "Never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <div className="ma-panel-foot">Private notes are never shown here. Open a mentor to see their students.</div>
    </div>
  );
}
