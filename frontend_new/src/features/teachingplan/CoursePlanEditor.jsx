// COURSE PLAN (Part A) - every timetable session of one subject as a row:
// unit, topic + notes, teaching mode, method, class activity, beyond-class
// activity. Table and calendar views, counts on top, print.
//
// Sessions come from the timetable (teaching-plans/class_days/). A session with
// a topic is "planned"; one without is "not yet planned" and is NOT sent to the
// server (the server refuses a blank topic). Each row's Save stores the whole
// plan as a draft, so nothing typed is lost.
//
// Part B adds two tabs: "Planned vs delivered" (DeliveryView) and "Course
// outcomes" (OutcomesView), and an Outcomes column linking sessions to COs.
// Part C adds "Copy a plan" (CopyPlanDialog) and Excel template / import /
// export through the shared Import / Export menu (importer "course_plan").
import { useCallback, useEffect, useMemo, useState } from "react";
import API from "../../api";
import DeliveryView from "./DeliveryView";
import OutcomesView from "./OutcomesView";
import CopyPlanDialog from "./CopyPlanDialog";          // Part C
import ImportExport from "../../components/ImportExport";   // Part C: Excel (shared engine)
import "../../styles/CoursePlan.css";

const PAGE = 15;
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const parse = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const dmy = (iso) => { if (!iso) return ""; const [y, m, d] = iso.split("-"); return `${d}-${m}-${y}`; };
const dayLabel = (iso) => (iso ? `${WD[parse(iso).getDay()]} ${dmy(iso)}` : "");
const keyOf = (d) => `${d.date}__${d.period_no ?? ""}`;
const EMPTY = { topic: "", unit_no: "", notes: "", mode: "", method: "", class_activity: "", beyond_activity: "", outcomes: [] };
const MODE_TONE = { lecture: "lecture", tutorial: "tutorial", lab: "lab", online: "online" };

const labelOf = (list, value) => (list || []).find((o) => o.value === value)?.label || "";

export default function CoursePlanEditor({
  subjectId, classForSubject, semSel, locked, onSaved, savedUnits, allDays, allotted, planId, onReload,
}) {
  const [opts, setOpts] = useState(null);
  const [content, setContent] = useState({});          // key -> session fields
  const [view, setView] = useState("table");
  const [unitFilter, setUnitFilter] = useState("");
  const [show, setShow] = useState("all");
  const [page, setPage] = useState(0);
  const [editKey, setEditKey] = useState(null);
  const [draft, setDraft] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);                 // { tone, text }
  const [month, setMonth] = useState(null);             // "YYYY-MM"
  const [syllabus, setSyllabus] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);       // Part C
  const [notice, setNotice] = useState("");              // Part C: result of a copy / import, shown under the toolbar

  useEffect(() => {
    API.get("teaching-plans/field_options/").then((r) => setOpts(r.data)).catch(() => setOpts(null));
  }, []);

  // COURSE PLAN (Part B): the subject's course outcomes
  const [coInfo, setCoInfo] = useState(null);
  const loadOutcomes = useCallback(() => {
    if (!subjectId) return;
    API.get(`course-outcomes/?subject=${subjectId}`).then((r) => setCoInfo(r.data)).catch(() => setCoInfo(null));
  }, [subjectId]);
  useEffect(() => { loadOutcomes(); }, [loadOutcomes]);
  const cos = useMemo(() => coInfo?.outcomes || [], [coInfo]);
  const coIds = useMemo(() => new Set(cos.map((o) => o.id)), [cos]);
  const coCodes = (ids) => cos.filter((o) => (ids || []).includes(o.id)).map((o) => o.code);

  const classDays = useMemo(() => (allDays || []).filter((d) => !d.holiday), [allDays]);
  const holidays = useMemo(() => (allDays || []).filter((d) => d.holiday), [allDays]);

  // saved sessions -> content map; a saved session whose slot left the timetable is kept as an "orphan"
  const orphans = useMemo(() => {
    const known = new Set(classDays.map(keyOf));
    return (savedUnits || []).filter((u) => u.due && !known.has(`${u.due}__${u.period_no ?? ""}`))
      .map((u) => ({ date: u.due, period_no: u.period_no, hours: u.hours || 1, period_label: `Period ${u.period_no ?? "?"}`,
        time_label: "", orphan: true }));
  }, [savedUnits, classDays]);

  useEffect(() => {
    const map = {};
    (savedUnits || []).forEach((u) => {
      if (!u.due) return;
      map[`${u.due}__${u.period_no ?? ""}`] = {
        topic: u.topic || "", unit_no: u.unit_no ?? "", notes: u.notes || "", mode: u.mode || "",
        method: u.method || "", class_activity: u.class_activity || "", beyond_activity: u.beyond_activity || "",
        outcomes: u.outcomes || [],
      };
    });
    setContent(map);
    setEditKey(null);
    setPage(0);
    const first = classDays[0]?.date;
    setMonth(first ? first.slice(0, 7) : null);
  }, [savedUnits, classDays]);

  const sessions = useMemo(
    () => [...classDays, ...orphans]
      .sort((a, b) => (a.date === b.date ? (a.period_no || 0) - (b.period_no || 0) : a.date < b.date ? -1 : 1))
      .map((d, i) => ({ ...d, no: i + 1, key: keyOf(d), ...(content[keyOf(d)] || EMPTY) })),
    [classDays, orphans, content],
  );

  const planned = sessions.filter((s) => s.topic.trim());
  const timetableCount = classDays.length;
  const notPlanned = Math.max(0, timetableCount - planned.filter((s) => !s.orphan).length);
  const coverage = timetableCount ? Math.round((planned.filter((s) => !s.orphan).length * 100) / timetableCount) : 0;
  const unitCount = opts?.default_units || 5;
  const unitChoices = useMemo(() => {
    const used = planned.map((s) => Number(s.unit_no)).filter(Boolean);
    return Array.from({ length: Math.max(unitCount, ...used, 0) }, (_, i) => i + 1);
  }, [planned, unitCount]);

  // the table: filters, holidays in date order (only when nothing is filtered), pages
  const filtered = sessions.filter((s) => {
    if (unitFilter && String(s.unit_no) !== unitFilter) return false;
    if (show === "planned" && !s.topic.trim()) return false;
    if (show === "unplanned" && s.topic.trim()) return false;
    return true;
  });
  const withHolidays = (unitFilter || show !== "all") ? filtered
    : [...filtered, ...holidays.map((h) => ({ ...h, key: `h-${h.date}` }))]
      .sort((a, b) => (a.date === b.date ? (a.holiday ? -1 : 1) : a.date < b.date ? -1 : 1));
  const pages = Math.max(1, Math.ceil(withHolidays.length / PAGE));
  const shown = withHolidays.slice(page * PAGE, page * PAGE + PAGE);

  // ---------------------------------------------------------------- saving
  const payload = (status, map) => ({
    subject: subjectId,
    class_section: classForSubject,
    semester: semSel,
    allotted_hours: allotted,
    status,
    units: sessions
      .map((s) => ({ ...s, ...(map[s.key] || EMPTY) }))
      .filter((s) => s.topic.trim())
      .map((s, i) => ({
        topic: s.topic.trim(), hours: s.hours || 1, due: s.date, period_no: s.period_no, sequence_no: i + 1,
        unit_no: s.unit_no ? Number(s.unit_no) : null, notes: s.notes, mode: s.mode, method: s.method,
        class_activity: s.class_activity, beyond_activity: s.beyond_activity,
        outcomes: (s.outcomes || []).filter((id) => coIds.has(id)),     // a deleted CO is dropped
      })),
  });

  const errorText = (err, fallback) => {
    const d = err?.response?.data;
    if (typeof d?.detail === "string") return d.detail;
    if (typeof d?.units === "string") return d.units;
    if (Array.isArray(d?.units) && typeof d.units[0] === "string") return d.units[0];
    if (Array.isArray(d?.subject)) return d.subject[0];
    return fallback;
  };

  const save = async (status, map = content) => {
    setBusy(true);
    setMsg(null);
    try {
      await API.post("teaching-plans/", payload(status, map));
      setMsg({ tone: "ok", text: status === "submitted" ? "Sent to your HOD for review." : "Saved as a draft." });
      onSaved?.(status);
      return true;
    } catch (err) {
      setMsg({ tone: "bad", text: errorText(err, "The plan wasn't saved. Try again.") });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const openEditor = (s) => {
    if (locked) return;
    setEditKey(s.key);
    setDraft({ ...EMPTY, ...(content[s.key] || {}) });
    setMsg(null);
  };

  const saveRow = async () => {
    const next = { ...content, [editKey]: { ...draft, topic: draft.topic.trim() } };
    setContent(next);
    setEditKey(null);
    await save("draft", next);
  };

  const sendToHod = async () => {
    const missing = planned.find((s) => !s.unit_no || !s.mode);
    if (missing) {
      setView("table"); setUnitFilter(""); setShow("all");
      const idx = [...sessions, ...holidays.map((h) => ({ ...h, key: `h-${h.date}` }))]
        .sort((a, b) => (a.date === b.date ? (a.holiday ? -1 : 1) : a.date < b.date ? -1 : 1))
        .findIndex((x) => x.key === missing.key);
      setPage(Math.max(0, Math.floor(idx / PAGE)));
      openEditor(missing);
      setMsg({ tone: "bad", text: `Session ${missing.no} (${dayLabel(missing.date)}) needs a unit and a teaching mode before the plan can go to the HOD.` });
      return;
    }
    if (!planned.length) {
      setMsg({ tone: "bad", text: "Plan at least one session before sending it to the HOD." });
      return;
    }
    if (notPlanned && !window.confirm(`${notPlanned} timetable session${notPlanned === 1 ? " is" : "s are"} not planned yet. Send the plan to your HOD anyway?`)) return;
    await save("submitted");
  };

  // ---------------------------------------------------------------- AI topics (kept from the old page)
  const suggestTopics = async () => {
    if (!classDays.length) return;
    const filled = planned.length;
    if (filled && !window.confirm(`This will replace the ${filled} topic${filled === 1 ? "" : "s"} already written. Continue?`)) return;
    setAiLoading(true);
    setMsg(null);
    try {
      const res = await API.post("teaching-plans/suggest_topics/", {
        subject: subjectId, count: classDays.length, syllabus: syllabus.trim(),
      });
      const topics = res.data?.topics || [];
      const next = { ...content };
      classDays.forEach((d, i) => {
        if (topics[i]) next[keyOf(d)] = { ...EMPTY, ...(next[keyOf(d)] || {}), topic: topics[i] };
      });
      setContent(next);
      setMsg({ tone: "ok", text: "Topics suggested by AI. Review them, add units and teaching modes, then Save draft." });
    } catch (err) {
      setMsg({ tone: "bad", text: errorText(err, "Could not generate topics. Please try again.") });
    } finally {
      setAiLoading(false);
    }
  };

  // ---------------------------------------------------------------- calendar
  const monthCells = useMemo(() => {
    if (!month) return [];
    const [y, m] = month.split("-").map(Number);
    const first = new Date(y, m - 1, 1);
    const start = new Date(first);
    start.setDate(1 - ((first.getDay() + 6) % 7));       // Monday on or before the 1st
    const byDate = {};
    sessions.forEach((s) => { (byDate[s.date] = byDate[s.date] || []).push(s); });
    const hol = Object.fromEntries(holidays.map((h) => [h.date, h.holiday_name]));
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      return { iso, day: d.getDate(), inMonth: d.getMonth() === m - 1, items: byDate[iso] || [], holiday: hol[iso] || "" };
    });
  }, [month, sessions, holidays]);
  const moveMonth = (n) => {
    const [y, m] = month.split("-").map(Number);
    const d = new Date(y, m - 1 + n, 1);
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  };
  const monthTitle = month ? `${["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][Number(month.slice(5)) - 1]} ${month.slice(0, 4)}` : "";
  const openFromCalendar = (s) => {
    setView("table"); setUnitFilter(""); setShow("all");
    const all = [...sessions, ...holidays.map((h) => ({ ...h, key: `h-${h.date}` }))]
      .sort((a, b) => (a.date === b.date ? (a.holiday ? -1 : 1) : a.date < b.date ? -1 : 1));
    setPage(Math.max(0, Math.floor(all.findIndex((x) => x.key === s.key) / PAGE)));
    openEditor(s);
  };

  if (!classDays.length && !orphans.length) {
    return <div className="tp-note">No timetable found for this subject yet. Ask the admin to add it to the timetable.</div>;
  }

  const sel = (field, list, label, required) => (
    <label className="cp-cell-field">
      <span className="cp-sr">{label}</span>
      <select value={draft[field]} onChange={(e) => setDraft({ ...draft, [field]: e.target.value })}
        className={required && !draft[field] ? "cp-need" : ""}>
        <option value="">{required ? "Choose…" : "—"}</option>
        {(list || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );

  return (
    <div className="cp">
      {/* ---------- counts ---------- */}
      {(view === "table" || view === "calendar") && <div className="cp-counts">
        <div><span>Timetable sessions</span><b>{timetableCount}</b><small>from the approved timetable</small></div>
        <div><span>Planned</span><b>{planned.length}</b><small>sessions with a topic</small></div>
        <div><span>Not yet planned</span><b className={notPlanned ? "cp-warn" : ""}>{notPlanned}</b><small>sessions without a topic</small></div>
        <div><span>Plan coverage</span><b>{coverage}%</b><span className="cp-bar"><span style={{ width: `${coverage}%` }} /></span></div>
      </div>}

      {/* ---------- AI (kept) ---------- */}
      {!locked && (view === "table" || view === "calendar") && (
        <details className="cp-ai no-print">
          <summary>Suggest topics with AI</summary>
          <textarea value={syllabus} onChange={(e) => setSyllabus(e.target.value)}
            placeholder="Paste your syllabus here: units, topics, or the university outline (optional)." />
          <div className="cp-ai-foot">
            <span>Only the subject and this text are sent. You review every topic before saving.</span>
            <button type="button" className="tp-btn-primary tp-btn-sm" onClick={suggestTopics} disabled={aiLoading}>
              {aiLoading ? "Generating…" : `Suggest topics for ${classDays.length} sessions`}
            </button>
          </div>
        </details>
      )}

      {/* ---------- toolbar ---------- */}
      <div className="cp-toolbar no-print">
        <div className="cp-seg" role="tablist" aria-label="View">
          <button type="button" role="tab" aria-selected={view === "table"} className={view === "table" ? "on" : ""} onClick={() => setView("table")}>Table</button>
          <button type="button" role="tab" aria-selected={view === "calendar"} className={view === "calendar" ? "on" : ""} onClick={() => setView("calendar")}>Calendar</button>
          <button type="button" role="tab" aria-selected={view === "delivered"} className={view === "delivered" ? "on" : ""} onClick={() => setView("delivered")}>Planned vs delivered</button>
          <button type="button" role="tab" aria-selected={view === "outcomes"} className={view === "outcomes" ? "on" : ""} onClick={() => setView("outcomes")}>Course outcomes</button>
        </div>
        <div className="cp-tools">
          {(view === "table" || view === "calendar") && (
            <>
              {!locked && <button type="button" className="cp-btn" onClick={() => setCopyOpen(true)}>Copy a plan</button>}
              <ImportExport
                importer="course_plan"
                label="course plan"
                matchLabel="date and period"
                modes={["upsert"]}
                align="right"
                options={{ subject: subjectId }}
                canImport={!locked}
                note="One row per timetable session. Download the template: it already lists every session with what you have planned. Empty cells never erase what is saved."
                onDone={() => { setNotice("Imported. Review the plan, then send it to your HOD."); onSaved?.(); onReload?.(); }}
              />
              <button type="button" className="cp-btn" onClick={() => window.print()}>Print</button>
            </>
          )}
        </div>
      </div>

      {notice && (view === "table" || view === "calendar") && (
        <div className="cp-msg ok cp-notice no-print" role="status">
          <span>{notice}</span>
          <button type="button" className="cp-btn" aria-label="Dismiss" onClick={() => setNotice("")}>×</button>
        </div>
      )}

      {view === "table" && (
        <>
          <div className="cp-filters no-print">
            <label>Unit
              <select value={unitFilter} onChange={(e) => { setUnitFilter(e.target.value); setPage(0); }}>
                <option value="">All units</option>
                {unitChoices.map((u) => <option key={u} value={u}>Unit {u}</option>)}
              </select>
            </label>
            <label>Show
              <select value={show} onChange={(e) => { setShow(e.target.value); setPage(0); }}>
                <option value="all">All sessions</option>
                <option value="unplanned">Not yet planned</option>
                <option value="planned">Planned</option>
              </select>
            </label>
            <span className="cp-key"><i className="cp-key-hol" />Holiday</span>
            <span className="cp-key"><i className="cp-key-un" />Not yet planned</span>
            {!locked && <span className="cp-key"><b className="cp-star">*</b> needed before sending to the HOD</span>}
          </div>

          <div className="cp-table-wrap">
            <table className="cp-table">
              <thead>
                <tr>
                  <th>#</th><th>Date · period</th><th>Unit{!locked && <b className="cp-star">*</b>}</th>
                  <th className="cp-topic-col">Topic</th><th>Outcomes</th><th>Teaching mode{!locked && <b className="cp-star">*</b>}</th>
                  <th>Teaching method</th><th>Class activity</th><th>Beyond-class activity</th>
                  {!locked && <th className="no-print"><span className="cp-sr">Actions</span></th>}
                </tr>
              </thead>
              <tbody>
                {shown.length === 0 && (
                  <tr><td colSpan={10} className="cp-empty">No sessions match these filters.</td></tr>
                )}
                {shown.map((s) => {
                  if (s.holiday) {
                    return (
                      <tr key={s.key} className="cp-row-hol">
                        <td>—</td><td className="cp-nowrap"><b>{dayLabel(s.date)}</b></td>
                        <td colSpan={locked ? 7 : 8}>Holiday · {s.holiday_name} (no classes)</td>
                      </tr>
                    );
                  }
                  if (editKey === s.key) {
                    return (
                      <tr key={s.key} className="cp-row-edit">
                        <td>{s.no}</td>
                        <td className="cp-nowrap"><b>{dayLabel(s.date)}</b><small>{s.period_label}{s.time_label ? ` · ${s.time_label}` : ""}</small></td>
                        <td>
                          <label className="cp-cell-field"><span className="cp-sr">Unit</span>
                            <select value={draft.unit_no} className={!draft.unit_no ? "cp-need" : ""}
                              onChange={(e) => setDraft({ ...draft, unit_no: e.target.value })}>
                              <option value="">Choose…</option>
                              {(opts?.units || unitChoices).map((u) => <option key={u} value={u}>Unit {u}</option>)}
                            </select>
                          </label>
                        </td>
                        <td>
                          <label className="cp-cell-field"><span className="cp-sr">Topic</span>
                            <input value={draft.topic} placeholder="What will you teach?" maxLength={200}
                              onChange={(e) => setDraft({ ...draft, topic: e.target.value })} /></label>
                          <label className="cp-cell-field"><span className="cp-sr">Notes</span>
                            <textarea rows={2} value={draft.notes} placeholder="Notes (optional)"
                              onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></label>
                        </td>
                        <td>
                          {cos.length === 0 ? <small className="cp-muted">Add outcomes in the Course outcomes tab</small> : (
                            <fieldset className="cp-co-pick">
                              <legend className="cp-sr">Course outcomes taught</legend>
                              {cos.map((o) => {
                                const on = (draft.outcomes || []).includes(o.id);
                                return (
                                  <label key={o.id} className={on ? "on" : ""} title={o.text}>
                                    <input type="checkbox" checked={on} onChange={() => setDraft({
                                      ...draft,
                                      outcomes: on ? draft.outcomes.filter((x) => x !== o.id) : [...(draft.outcomes || []), o.id],
                                    })} />{o.code}
                                  </label>
                                );
                              })}
                            </fieldset>
                          )}
                        </td>
                        <td>{sel("mode", opts?.modes, "Teaching mode", true)}</td>
                        <td>{sel("method", opts?.methods, "Teaching method")}</td>
                        <td>{sel("class_activity", opts?.class_activities, "Class activity")}</td>
                        <td>{sel("beyond_activity", opts?.beyond_activities, "Beyond-class activity")}</td>
                        <td className="no-print">
                          <div className="cp-row-actions">
                            <button type="button" className="tp-btn-primary tp-btn-sm" onClick={saveRow} disabled={busy}>Save</button>
                            <button type="button" className="tp-btn-outline tp-btn-sm" onClick={() => setEditKey(null)}>Cancel</button>
                          </div>
                          {draft.topic.trim() === "" && content[s.key]?.topic && (
                            <small className="cp-clear-note">An empty topic marks the session “not yet planned”.</small>
                          )}
                        </td>
                      </tr>
                    );
                  }
                  if (!s.topic.trim()) {
                    return (
                      <tr key={s.key} className="cp-row-un">
                        <td>{s.no}</td>
                        <td className="cp-nowrap"><b>{dayLabel(s.date)}</b><small>{s.period_label}{s.time_label ? ` · ${s.time_label}` : ""}</small></td>
                        <td colSpan={7} className="cp-un-text">Not yet planned</td>
                        {!locked && <td className="no-print"><button type="button" className="cp-btn cp-btn-accent" onClick={() => openEditor(s)}>Plan</button></td>}
                      </tr>
                    );
                  }
                  return (
                    <tr key={s.key}>
                      <td>{s.no}</td>
                      <td className="cp-nowrap"><b>{dayLabel(s.date)}</b><small>{s.period_label}{s.time_label ? ` · ${s.time_label}` : ""}{s.orphan ? " · no longer in timetable" : ""}</small></td>
                      <td>{s.unit_no ? `Unit ${s.unit_no}` : <span className="cp-missing">—</span>}</td>
                      <td><b className="cp-topic">{s.topic}</b>{s.notes && <small>{s.notes}</small>}</td>
                      <td className="cp-nowrap">{coCodes(s.outcomes).join(", ") || "—"}</td>
                      <td>{labelOf(opts?.modes, s.mode) || <span className="cp-missing">—</span>}</td>
                      <td>{labelOf(opts?.methods, s.method) || "—"}</td>
                      <td>{labelOf(opts?.class_activities, s.class_activity) || "—"}</td>
                      <td>{labelOf(opts?.beyond_activities, s.beyond_activity) || "—"}</td>
                      {!locked && <td className="no-print"><button type="button" className="cp-btn" onClick={() => openEditor(s)} aria-label={`Edit session ${s.no}`}>Edit</button></td>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="cp-pager no-print">
            <span>Showing {shown.length ? page * PAGE + 1 : 0}–{page * PAGE + shown.length} of {withHolidays.length}
              {" "}· dates and periods come from the approved timetable</span>
            <div>
              <button type="button" className="cp-btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
              <button type="button" className="cp-btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </div>
        </>
      )}

      {view === "calendar" && month && (
        <div className="cp-cal">
          <div className="cp-cal-head">
            <button type="button" className="cp-btn" aria-label="Previous month" onClick={() => moveMonth(-1)}>‹</button>
            <b>{monthTitle}</b>
            <button type="button" className="cp-btn" aria-label="Next month" onClick={() => moveMonth(1)}>›</button>
          </div>
          <div className="cp-cal-key">
            <span><i className="cp-tone-lecture" />Lecture</span><span><i className="cp-tone-lab" />Lab</span>
            <span><i className="cp-tone-tutorial" />Tutorial</span><span><i className="cp-tone-other" />Other modes</span>
            <span><i className="cp-tone-un" />Not yet planned</span><span><i className="cp-key-hol" />Holiday</span>
          </div>
          <div className="cp-cal-grid">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((w) => <div key={w} className="cp-cal-wd">{w}</div>)}
            {monthCells.map((c) => (
              <div key={c.iso} className={`cp-cal-cell${c.inMonth ? "" : " out"}${c.holiday ? " hol" : ""}`}>
                <div className="cp-cal-day"><b>{c.day}</b>{c.holiday && <small>{c.holiday}</small>}</div>
                {c.items.map((s) => {
                  const tone = s.topic.trim() ? (MODE_TONE[s.mode] || "other") : "un";
                  return (
                    <button type="button" key={s.key} className={`cp-cal-item cp-tone-${tone}`}
                      onClick={() => openFromCalendar(s)} disabled={locked && !s.topic.trim()}
                      title={s.topic || "Not yet planned"}>
                      <b>P{s.period_no}</b> {s.topic.trim() || "Not yet planned"}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="cp-muted">Click a session to open it in the table.</p>
        </div>
      )}

      {view === "delivered" && <DeliveryView planId={planId} onChanged={() => { onSaved?.(); onReload?.(); }} />}
      {view === "outcomes" && (
        <OutcomesView subjectId={subjectId} info={coInfo} sessions={sessions} onChanged={loadOutcomes} />
      )}

      {copyOpen && (
        <CopyPlanDialog
          subjectId={subjectId}
          sessionKeys={classDays.map(keyOf)}
          plannedKeys={new Set(planned.filter((x) => !x.orphan).map((x) => x.key))}
          onClose={() => setCopyOpen(false)}
          onCopied={(text) => { setCopyOpen(false); setNotice(text); onSaved?.(); onReload?.(); }}
        />
      )}

      {/* ---------- print: every planned session, nothing else ---------- */}
      <table className="cp-print">
        <thead><tr><th>#</th><th>Date · period</th><th>Unit</th><th>Topic</th><th>Outcomes</th><th>Mode</th><th>Method</th><th>Class activity</th><th>Beyond class</th></tr></thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.key}>
              <td>{s.no}</td><td>{dmy(s.date)} · P{s.period_no}</td><td>{s.unit_no || ""}</td>
              <td>{s.topic || "(not yet planned)"}{s.notes ? ` — ${s.notes}` : ""}</td><td>{coCodes(s.outcomes).join(", ")}</td>
              <td>{labelOf(opts?.modes, s.mode)}</td><td>{labelOf(opts?.methods, s.method)}</td>
              <td>{labelOf(opts?.class_activities, s.class_activity)}</td><td>{labelOf(opts?.beyond_activities, s.beyond_activity)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ---------- footer ---------- */}
      {(view === "table" || view === "calendar") && <div className="cp-foot no-print">
        <span>{planned.length} of {timetableCount} sessions planned{holidays.length ? ` · ${holidays.length} holiday${holidays.length === 1 ? "" : "s"} skipped` : ""}</span>
        {locked ? (
          <span>This plan is locked while it is with the HOD or approved.</span>
        ) : (
          <div className="cp-foot-actions">
            <button type="button" className="tp-btn-outline tp-btn-sm" onClick={() => save("draft")} disabled={busy}>Save draft</button>
            <button type="button" className="tp-btn-primary tp-btn-sm" onClick={sendToHod} disabled={busy}>Send to HOD</button>
          </div>
        )}
      </div>}
      {msg && (view === "table" || view === "calendar") && <div className={msg.tone === "ok" ? "cp-msg ok" : "cp-msg bad"} role={msg.tone === "ok" ? "status" : "alert"}>{msg.text}</div>}
    </div>
  );
}

