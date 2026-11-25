import { useEffect, useRef, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import ImportExport from "../../components/ImportExport";
import "../../styles/Attendance.css";

// ── date helpers ──────────────────────────────────────────────────────────────
// Everything the user SEES is DD/MM/YYYY. Everything sent to the server is ISO
// (YYYY-MM-DD), which is what Django expects. The two never mix.
//
// NOTE: we do NOT use <input type="date">. That control is drawn by the browser
// using the machine's locale — on a US-locale machine it renders MM/DD/YYYY and
// no CSS or attribute can override it. Hence the custom input + calendar below.

const MONTHS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"];
const DOW = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

// "2026-06-09" -> "09/06/2026"
const toDisplay = (iso) => {
  if (!iso) return "";
  const [y, m, d] = String(iso).split("-");
  if (!y || !m || !d) return "";
  return `${d}/${m}/${y}`;
};

// "09/06/2026" -> "2026-06-09"  ("" if the date isn't real)
const toISO = (display) => {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec((display || "").trim());
  if (!m) return "";
  const [, dd, mm, yyyy] = m;
  const d = new Date(Number(yyyy), Number(mm) - 1, Number(dd));
  // reject 31/02/2026 — JS would silently roll it over to 3 March
  if (d.getFullYear() !== Number(yyyy) ||
      d.getMonth() !== Number(mm) - 1 ||
      d.getDate() !== Number(dd)) return "";
  return `${yyyy}-${mm}-${dd}`;
};

// Date object -> "2026-06-09"
const dateToISO = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

// COLLEGE POLICY: no exams on Saturday or Sunday.
// (The college does TEACH on Saturdays — the class timetable has Saturday periods —
// but exams are weekday-only. Two different rules; don't conflate them.)
const isWeekend = (d) => d.getDay() === 0 || d.getDay() === 6;
const weekendName = (d) => (d.getDay() === 0 ? "Sunday" : "Saturday");

// used by the read-only text elsewhere on the page
const fmt = (iso) => toDisplay(iso) || "—";

const CAL_HEIGHT = 340;   // roughly how tall the popup is, for the flip-up check

// ── calendar popup ────────────────────────────────────────────────────────────
// Monday-first grid. Weekends are DISABLED and struck through — grey alone reads
// as "faint", not "unavailable", which is what confused people.
function Calendar({ value, onPick, onClose }) {
  const start = value ? new Date(value + "T00:00:00") : new Date();
  const [view, setView] = useState({ y: start.getFullYear(), m: start.getMonth() });

  const first = new Date(view.y, view.m, 1);
  const daysInMonth = new Date(view.y, view.m + 1, 0).getDate();
  // JS getDay() is 0=Sun..6=Sat; shift so Monday is column 0
  const lead = (first.getDay() + 6) % 7;

  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(view.y, view.m, d));

  const move = (n) => {
    const m = view.m + n;
    if (m < 0) setView({ y: view.y - 1, m: 11 });
    else if (m > 11) setView({ y: view.y + 1, m: 0 });
    else setView({ y: view.y, m });
  };

  const todayISO = dateToISO(new Date());

  return (
    <div className="cal-pop" onClick={(e) => e.stopPropagation()}>
      <div className="cal-head">
        <button type="button" className="cal-nav" onClick={() => move(-1)} aria-label="Previous month">‹</button>
        <span className="cal-title">{MONTHS[view.m]} {view.y}</span>
        <button type="button" className="cal-nav" onClick={() => move(1)} aria-label="Next month">›</button>
      </div>

      <div className="cal-grid cal-dow">
        {DOW.map((d, i) => (
          <span key={d} className={i >= 5 ? "is-wk" : ""}>{d}</span>
        ))}
      </div>

      <div className="cal-grid">
        {cells.map((d, i) => {
          if (!d) return <span key={`x${i}`} className="cal-blank" />;
          const iso = dateToISO(d);
          const off = isWeekend(d);
          const cls = [
            "cal-day",
            iso === value ? "is-sel" : "",
            iso === todayISO ? "is-today" : "",
            off ? "is-off" : "",
          ].filter(Boolean).join(" ");
          return (
            <button
              key={iso}
              type="button"
              className={cls}
              disabled={off}                                   // grey means grey
              title={off ? `${weekendName(d)} — no exams` : ""}
              onClick={() => { if (!off) { onPick(iso); onClose(); } }}
            >
              {d.getDate()}
            </button>
          );
        })}
      </div>

      <div className="cal-foot">
        <span className="cal-key">Weekends unavailable</span>
        <button type="button" className="cal-clear" onClick={() => { onPick(""); onClose(); }}>Clear</button>
      </div>
    </div>
  );
}

// ── DD/MM/YYYY field: the input and the calendar icon share ONE border ────────
// `status` is the row's state ("conflict" | "warn" | "ok" | "none") so the whole
// control carries the colour, rather than the input and the icon disagreeing.
function DateInput({ value, onChange, status }) {
  const [text, setText] = useState(toDisplay(value));
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const wrapRef = useRef(null);

  // keep in step when the parent changes the value (e.g. "Arrange Exams")
  useEffect(() => { setText(toDisplay(value)); }, [value]);

  // click anywhere else -> close the calendar
  useEffect(() => {
    if (!open) return;
    const away = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  // Rows near the bottom of the page have no room below — open the calendar
  // upward instead, or half of it ends up off-screen.
  const toggle = () => {
    if (!open && wrapRef.current) {
      const rect = wrapRef.current.getBoundingClientRect();
      setDropUp(window.innerHeight - rect.bottom < CAL_HEIGHT);
    }
    setOpen((v) => !v);
  };

  const handleType = (e) => {
    const digits = e.target.value.replace(/\D/g, "").slice(0, 8);   // ddmmyyyy
    let out = digits;
    if (digits.length > 4) out = `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
    else if (digits.length > 2) out = `${digits.slice(0, 2)}/${digits.slice(2)}`;
    setText(out);
    onChange(digits.length === 8 ? toISO(out) : "");
  };

  const complete = text.length === 10;
  const bad = complete && !toISO(text);   // e.g. 31/02/2026

  const cls = [
    "dp-wrap",
    bad || status === "conflict" ? "is-bad" : "",
    !bad && status === "warn" ? "is-warn" : "",
    dropUp ? "is-up" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={cls} ref={wrapRef}>
      <input
        className="dp-input"
        type="text"
        inputMode="numeric"
        placeholder="dd/mm/yyyy"
        value={text}
        onChange={handleType}
        maxLength={10}
        title="Type dd/mm/yyyy, or use the calendar"
      />
      <button
        type="button"
        className="dp-btn"
        onClick={toggle}
        aria-label="Open calendar"
      >
        📅
      </button>
      {open && (
        <Calendar
          value={value || ""}
          onPick={(iso) => onChange(iso)}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

export default function HallTicketAdmin({ embedded = false }) {
  const [open, setOpen] = useState(false);

  // ── catalog-driven class picker ──
  const [courses, setCourses] = useState([]);   // [{id, name}]
  const [years, setYears]     = useState([]);   // [{id, year_number, subjects:[...]}]
  const [selectedCourse, setSelectedCourse] = useState(""); // course id
  const [selectedYear, setSelectedYear]     = useState(""); // year_number
  const [selectedSem, setSelectedSem]       = useState(""); // semester number

  const [roster, setRoster]     = useState([]);
  const [loading, setLoading]   = useState(false);
  const [fineAmount, setFineAmount] = useState(500);
  const [generating, setGenerating] = useState(false);

  // ELIGIBILITY RULES (#41): the college's minimum % and fine option
  const [rules, setRules] = useState(null);          // saved values from the server
  const [rulesForm, setRulesForm] = useState({ min_attendance: 75, fine_unlocks: true });
  const [savingRules, setSavingRules] = useState(false);
  const [rulesMsg, setRulesMsg] = useState({ type: "", text: "" });

  // ELIGIBILITY OVERRIDE (#41 Part B): pop-up for Override / Revoke + audit log
  const [action, setAction] = useState(null);          // { type: "override" | "revoke", row }
  const [actionReason, setActionReason] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionErr, setActionErr] = useState("");
  const [overrideLog, setOverrideLog] = useState([]);

  // exam schedule: { [subjectId]: { exam_date, session, id } }   exam_date is ISO
  const [schedule, setSchedule] = useState({});
  const [savingSchedule, setSavingSchedule] = useState(false);

  // controls
  const [gap, setGap] = useState(2);
  const [defaultSession, setDefaultSession] = useState("FN");
  const [pref, setPref] = useState("");
  const [startNote, setStartNote] = useState("");
  const [drafting, setDrafting] = useState(false);

  // overview: classes that already have a schedule
  const [scheduledClasses, setScheduledClasses] = useState([]);

  // WAVE 3 PART 2: the exam session these dates belong to (default = the current one)
  const [examSessions, setExamSessions] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const examSession = examSessions.find((x) => String(x.id) === String(sessionId));
  const locked = !!examSession?.timetable_published;
  useEffect(() => {
    API.get("exam-sessions/").then((r) => {
      const list = r.data || [];
      setExamSessions(list);
      const cur = list.find((x) => x.is_current) || list[0];
      if (cur) setSessionId(String(cur.id));
    }).catch(() => setExamSessions([]));
  }, []);
  const sessionParam = sessionId ? `exam_session=${sessionId}` : "";

  // ── load all courses once ──
  useEffect(() => {
    API.get("courses/")
      .then((r) => setCourses(r.data?.results || r.data || []))
      .catch(() => setCourses([]));
  }, []);

  // ── ELIGIBILITY RULES: load once ──
  const loadRules = () => {
    API.get("/hall-ticket/eligibility-rules/")
      .then((r) => {
        setRules(r.data);
        setRulesForm({ min_attendance: r.data.min_attendance, fine_unlocks: r.data.fine_unlocks });
      })
      .catch(() => setRules(null));
  };
  useEffect(() => { loadRules(); }, []);

  const rulesChanged = !!rules && (
    String(rulesForm.min_attendance) !== String(rules.min_attendance) ||
    rulesForm.fine_unlocks !== rules.fine_unlocks
  );

  const saveRules = async () => {
    const pct = Number(rulesForm.min_attendance);
    if (!Number.isInteger(pct) || pct < 1 || pct > 100) {
      setRulesMsg({ type: "error", text: "Minimum attendance must be a whole number between 1 and 100." });
      return;
    }
    setSavingRules(true);
    setRulesMsg({ type: "", text: "" });
    try {
      const r = await API.put("/hall-ticket/eligibility-rules/", {
        min_attendance: pct,
        fine_unlocks: rulesForm.fine_unlocks,
      });
      setRules(r.data);
      setRulesForm({ min_attendance: r.data.min_attendance, fine_unlocks: r.data.fine_unlocks });
      setRulesMsg({ type: "ok", text: "Saved. Eligibility now uses these rules." });
      loadData();   // the roster below changes straight away
    } catch (err) {
      setRulesMsg({ type: "error", text: err.response?.data?.detail || "Could not save the rules." });
    } finally {
      setSavingRules(false);
    }
  };

  const minPct = rules?.min_attendance ?? 75;
  const finesOn = rules ? rules.fine_unlocks : true;

  // ── ELIGIBILITY OVERRIDE (#41 Part B) ──
  const canOverride = !!rules?.can_edit;     // main admin / Examination admin only
  const MIN_REASON = 10;

  const loadOverrideLog = () => {
    if (!selectedCourse || !selectedYear || !selectedSem) { setOverrideLog([]); return; }
    API.get(`/hall-ticket/overrides/?course=${selectedCourse}&year=${selectedYear}&semester=${selectedSem}`)
      .then((r) => setOverrideLog(r.data || []))
      .catch(() => setOverrideLog([]));
  };
  useEffect(() => {
    loadOverrideLog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCourse, selectedYear, selectedSem]);

  const openAction = (type, row) => {
    setAction({ type, row });
    setActionReason("");
    setActionErr("");
  };
  const closeAction = () => { if (!actionBusy) setAction(null); };

  const submitAction = async () => {
    const reason = actionReason.trim();
    if (reason.length < MIN_REASON) {
      setActionErr(`Please write the reason (at least ${MIN_REASON} characters).`);
      return;
    }
    setActionBusy(true);
    setActionErr("");
    try {
      if (action.type === "override") {
        await API.post("/hall-ticket/override/", { student: action.row.student, reason });
      } else {
        await API.post(`/hall-ticket/override/${action.row.override_id}/revoke/`, { reason });
      }
      setAction(null);
      loadData();
      loadOverrideLog();
    } catch (err) {
      setActionErr(err.response?.data?.detail || "Could not save. Please try again.");
    } finally {
      setActionBusy(false);
    }
  };

  // one line per event: the override, and (if any) its revoke — newest first
  const logEvents = overrideLog
    .flatMap((o) => {
      const ev = [{ key: `o${o.id}`, when: o.created_at, type: "Override", o, by: o.created_by, reason: o.reason }];
      if (o.revoked_at) ev.push({ key: `r${o.id}`, when: o.revoked_at, type: "Revoke", o, by: o.revoked_by, reason: o.revoke_reason });
      return ev;
    })
    .sort((a, b) => new Date(b.when) - new Date(a.when));

  const fmtWhen = (iso) =>
    new Date(iso).toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });

  // ── load the "scheduled classes" overview ──
  const loadScheduledClasses = () => {
    API.get(`scheduled-classes/${sessionParam ? `?${sessionParam}` : ""}`)
      .then((r) => setScheduledClasses(r.data?.results || r.data || []))
      .catch(() => setScheduledClasses([]));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadScheduledClasses(); }, [sessionId]);

  const openClass = (c) => {
    setSelectedCourse(String(c.course_id));
    setSelectedYear(String(c.year));
    setSelectedSem(String(c.semester));
  };

  // ── load that course's years (each with nested subjects) ──
  useEffect(() => {
    if (!selectedCourse) { setYears([]); return; }
    API.get(`years/?course=${selectedCourse}`)
      .then((r) => setYears(r.data?.results || r.data || []))
      .catch(() => setYears([]));
  }, [selectedCourse]);

  const courseId = selectedCourse;

  // year numbers available for this course
  const yearOptions = [...new Set(years.map((y) => y.year_number))].sort((a, b) => a - b);

  // the selected year row (holds the nested subjects)
  const selectedYearObj = years.find((y) => String(y.year_number) === String(selectedYear));

  // semesters that actually have subjects in this year
  const semesters = selectedYearObj
    ? [...new Set((selectedYearObj.subjects || []).map((s) => s.semester))].sort((a, b) => a - b)
    : [];

  // subjects for the chosen year + semester
  const classSubjects = (selectedYearObj && selectedSem)
    ? (selectedYearObj.subjects || [])
        .filter((s) => String(s.semester) === String(selectedSem))
        .map((s) => ({ id: s.id, name: s.name, code: s.code || "" }))
    : [];

  // ── load roster + existing exam schedule when the class changes ──
  const loadData = () => {
    if (!courseId || !selectedYear || !selectedSem) { setRoster([]); setSchedule({}); return; }
    setLoading(true);
    Promise.all([
      API.get(`/hall-ticket/roster/?course=${courseId}&year=${selectedYear}&semester=${selectedSem}`),
      API.get(`/exam-schedules/?semester=${selectedSem}${sessionParam ? `&${sessionParam}` : ""}`),
    ])
      .then(([rosterRes, schedRes]) => {
        setRoster(rosterRes.data?.results || rosterRes.data || []);
        const sched = schedRes.data?.results || schedRes.data || [];
        const map = {};
        sched.forEach((e) => {
          map[e.subject] = { id: e.id, exam_date: e.exam_date, session: e.session };
        });
        setSchedule(map);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCourse, selectedYear, selectedSem, sessionId]);

  const setSchedField = (subjectId, field, value) => {
    setSchedule((prev) => ({
      ...prev,
      [subjectId]: { ...prev[subjectId], [field]: value },
    }));
  };

  // ── Arrange (auto) / Draft with AI — fills the schedule map ──
  const runArrange = async (mode) => {
    if (!courseId || !selectedYear || !selectedSem) { alert("Pick a class first."); return; }
    setDrafting(true);
    try {
      const res = await API.post("/exam-schedules/draft/", {
        course: courseId,
        year: selectedYear,
        semester: Number(selectedSem),
        mode,
        preference: pref,
        gap,
        session: defaultSession,
        exam_session: sessionId || undefined,
      });
      const draft = res.data?.draft || [];
      if (res.data?.ai_note) console.log("Scheduler note:", res.data.ai_note);

      // explain a start-date shift (e.g. asked Aug 8, but Aug 8–9 is a weekend)
      const reqStart = res.data?.requested_start;
      const actStart = res.data?.actual_start;
      const notes = [];
      if (reqStart && actStart && reqStart !== actStart) {
        notes.push(`Requested ${fmt(reqStart)} — first working day is ${fmt(actStart)} (weekend/holiday skipped).`);
      }
      if (res.data?.gap_note) {
        notes.push(res.data.gap_note);
      }
      if (res.data?.clash_note) {
        notes.push(res.data.clash_note);
      }

      // The BACKEND still skips only Sundays and 2nd Saturdays, so auto-arrange can
      // still land an exam on a normal Saturday. Flag it here rather than letting the
      // admin discover a red row with no explanation. (Fix the backend rule to match
      // and this warning simply stops firing.)
      const weekendHits = draft.filter((d) => isWeekend(new Date(d.exam_date + "T00:00:00"))).length;
      if (weekendHits) {
        notes.push(`${weekendHits} exam${weekendHits === 1 ? "" : "s"} landed on a weekend — please move to a weekday.`);
      }

      setStartNote(notes.join(" "));
      setSchedule((prev) => {
        const next = { ...prev };
        draft.forEach((d) => {
          next[d.subject] = { ...next[d.subject], exam_date: d.exam_date, session: d.session };
        });
        return next;
      });
    } catch (err) {
      alert(err.response?.data?.detail || "Could not build the schedule.");
    } finally {
      setDrafting(false);
    }
  };

  // ── status per row (clash / weekend / ok) ──
  const groups = {};
  classSubjects.forEach((s) => {
    const r = schedule[s.id];
    if (r?.exam_date) {
      const k = r.exam_date + "|" + (r.session || "FN");
      (groups[k] = groups[k] || []).push(s.id);
    }
  });
  const clashSet = new Set();
  Object.values(groups).forEach((ids) => { if (ids.length > 1) ids.forEach((id) => clashSet.add(id)); });

  const statusOf = (sub) => {
    const r = schedule[sub.id] || {};
    if (!r.exam_date) return { level: "none" };
    if (clashSet.has(sub.id))
      return { level: "conflict", color: "#ef4444", pill: "Conflict", msg: "Clash — another exam is on this date + session" };
    const d = new Date(r.exam_date + "T00:00:00");
    if (isWeekend(d))
      return { level: "conflict", color: "#ef4444", pill: "Conflict",
               msg: `${weekendName(d)} — no exams, choose a weekday` };
    return { level: "ok", color: "#4B32C3", pill: "OK" };
  };

  const statuses = {};
  classSubjects.forEach((s) => { statuses[s.id] = statusOf(s); });
  const blockingCount = classSubjects.filter((s) => ["conflict", "warn"].includes(statuses[s.id].level)).length;
  const examCount = classSubjects.filter((s) => schedule[s.id]?.exam_date).length;
  const hasAnyDate = examCount > 0;

  // rows sorted by date (earliest first; blanks last)
  const sortedSubjects = [...classSubjects].sort((a, b) => {
    const da = schedule[a.id]?.exam_date || "9999";
    const db = schedule[b.id]?.exam_date || "9999";
    return da.localeCompare(db);
  });

  // scheduling window text
  const datesSet = classSubjects.map((s) => schedule[s.id]?.exam_date).filter(Boolean).sort();
  const windowText = datesSet.length
    ? `Scheduling between ${fmt(datesSet[0])} – ${fmt(datesSet[datesSet.length - 1])} · no exams on weekends`
    : "Exams are weekday-only — Saturdays and Sundays are not available";

  // ── save all exam dates for this class ──
  const saveSchedule = async () => {
    if (blockingCount > 0) {
      alert("Resolve all conflicts (weekend dates, clashes) before saving.");
      return;
    }
    setSavingSchedule(true);
    try {
      await Promise.all(
        classSubjects.map((sub) => {
          const row = schedule[sub.id];
          if (!row || !row.exam_date) return null;
          const payload = {
            subject: sub.id,
            semester: Number(selectedSem),
            exam_date: row.exam_date,     // always ISO
            session: row.session || "FN",
            exam_session: sessionId ? Number(sessionId) : undefined,
          };
          return row.id
            ? API.patch(`/exam-schedules/${row.id}/`, payload)
            : API.post("/exam-schedules/", payload);
        }).filter(Boolean)
      );
      alert("Exam schedule saved.");
      loadData();
      loadScheduledClasses();
    } catch (err) {
      alert(err.response?.data?.detail || "Error saving exam schedule.");
    } finally {
      setSavingSchedule(false);
    }
  };

  const generateFines = async () => {
    if (!courseId || !selectedYear || !selectedSem) return;
    if (!window.confirm(`Generate ₹${fineAmount} attendance fine for all below-${minPct}% students in this class?`)) return;
    setGenerating(true);
    try {
      const res = await API.post("/hall-ticket/generate-fines/", {
        course: courseId, year: selectedYear, semester: selectedSem, amount: fineAmount,
      });
      alert(res.data?.message || "Fines generated.");
      loadData();
    } catch (err) {
      alert(err.response?.data?.detail || "Error generating fines.");
    } finally {
      setGenerating(false);
    }
  };

  const eligibleCount = roster.filter((r) => r.eligible).length;

  const pillStyle = (level) => {
    if (level === "conflict") return { background: "#fef2f2", color: "#B42318", border: "1px solid #fecaca" };
    if (level === "warn")     return { background: "#fffbeb", color: "#8A4B0A", border: "1px solid #fde68a" };
    return { background: "#f0fdf4", color: "#15803d", border: "1px solid #bbf7d0" };
  };

  const body = (
    <>
      <style>{`
        .es-strip{display:flex;align-items:center;gap:18px;flex-wrap:wrap;padding-bottom:14px;border-bottom:1px solid #eef2f7}
        .es-group{display:flex;align-items:center;gap:8px;color:#5D5A6B;font-weight:600;font-size:15px}
        .es-step{display:flex;align-items:center;border:1px solid #cbd5e1;border-radius:8px;overflow:hidden}
        .es-step button{border:none;background:#F6F6F8;width:34px;height:34px;font-size:17px;cursor:pointer;color:#5D5A6B}
        .es-step button:disabled{opacity:.4;cursor:not-allowed}
        .es-step span{min-width:36px;text-align:center;font-weight:700}
        .es-btn-ai{background:#7c3aed;color:#fff;border:none;border-radius:8px;padding:10px 16px;font-weight:600;cursor:pointer}
        .es-btn-arrange{background:#4B32C3;color:#fff;border:none;border-radius:8px;padding:10px 16px;font-weight:600;cursor:pointer}
        .es-btn-ai:disabled,.es-btn-arrange:disabled{opacity:.6;cursor:not-allowed}
        .es-help{font-size:13.5px;color:#5D5A6B;padding:10px 0 2px}
        .es-link{color:#4B32C3;font-weight:700;cursor:pointer;text-decoration:underline}
        .es-dot{width:11px;height:11px;border-radius:50%;display:inline-block;margin-right:10px;vertical-align:middle}
        .es-pill{font-size:13px;font-weight:600;padding:3px 11px;border-radius:20px;display:inline-block}
        .es-warn-text{font-size:13px;margin-top:5px}
        .es-footer{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-top:16px;padding-top:14px;border-top:1px solid #eef2f7}

        /* The table wrapper in Attendance.css clips with overflow:auto, which cut the
           calendar popup in half. The table is only four columns and never needs to
           scroll sideways, so let children escape the box. */
        .att-card .att-table-wrap{overflow:visible !important}

        /* ---- date field: input + calendar icon inside ONE border ---- */
        .dp-wrap{position:relative;display:inline-flex;align-items:center;
                 width:165px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;
                 transition:border-color .12s, box-shadow .12s}
        .dp-wrap:focus-within{border-color:#4B32C3;box-shadow:0 0 0 3px rgba(37,99,235,.12)}
        .dp-wrap.is-bad{border-color:#ef4444}
        .dp-wrap.is-warn{border-color:#f59e0b}
        /* the input carries no border of its own — the wrapper IS the control */
        .dp-input{flex:1;min-width:0;border:none !important;background:transparent !important;
                  box-shadow:none !important;outline:none;height:34px;padding:0 0 0 12px;
                  font-size:14.5px;color:#17151F;font-family:inherit}
        .dp-btn{width:34px;height:34px;border:none;background:transparent;cursor:pointer;
                font-size:15px;line-height:1;flex-shrink:0;border-radius:0 7px 7px 0;opacity:.7}
        .dp-btn:hover{background:#ECECF0;opacity:1}

        /* ---- calendar popup ----
           7 equal columns. Two things break that if you let them:
           (1) plain 1fr will not shrink a grid item below its content's min-width, so
               the day buttons overflow instead of fitting — hence minmax(0,1fr);
           (2) <button> carries default browser padding, which inflates each cell past
               its column — hence padding:0 and min-width:0 on .cal-day. */
        .cal-pop{position:absolute;top:calc(100% + 6px);left:0;z-index:60;
                 width:282px;box-sizing:border-box;
                 background:#fff;border:1px solid #E7E7EC;border-radius:12px;
                 box-shadow:0 10px 30px rgba(15,23,42,.14);padding:14px 16px 12px}
        /* rows near the bottom of the page open upward instead */
        .dp-wrap.is-up .cal-pop{top:auto;bottom:calc(100% + 6px)}

        .cal-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
        .cal-title{font-size:15px;font-weight:600;color:#17151F}
        .cal-nav{width:30px;height:30px;border:1px solid #E7E7EC;border-radius:8px;background:#fff;
                 cursor:pointer;color:#5D5A6B;font-size:16px;line-height:1;padding:0}
        .cal-nav:hover{background:#ECECF0}

        .cal-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px;width:100%}
        .cal-dow{margin-bottom:6px}
        .cal-dow span{text-align:center;font-size:12px;font-weight:600;color:#85839A;padding:4px 0}
        .cal-dow span.is-wk{color:#cbd5e1}
        .cal-blank{display:block;height:34px}

        .cal-day{width:100%;min-width:0;padding:0;height:34px;border:none;border-radius:8px;
                 background:#fff;cursor:pointer;font-size:14px;color:#17151F;
                 box-sizing:border-box;font-family:inherit}
        .cal-day:hover{background:#eff6ff}
        /* Weekends: struck through on a tinted cell. Grey alone reads as "faint",
           not "unavailable" — that ambiguity is what caused the confusion. */
        .cal-day.is-off{color:#cbd5e1;background:#F6F6F8;text-decoration:line-through;cursor:not-allowed}
        .cal-day.is-off:hover{background:#F6F6F8;color:#cbd5e1}
        .cal-day:disabled{cursor:not-allowed}
        .cal-day.is-today{box-shadow:inset 0 0 0 1px #cbd5e1;font-weight:600}
        .cal-day.is-sel{background:#4B32C3;color:#fff;font-weight:600}
        .cal-day.is-sel:hover{background:#4B32C3}

        .cal-foot{display:flex;align-items:center;justify-content:space-between;margin-top:12px;padding-top:10px;border-top:1px solid #ECECF0}
        .cal-key{font-size:12px;color:#85839A}
        .cal-clear{border:none;background:none;color:#4B32C3;font-size:13px;cursor:pointer;padding:0}
      `}</style>

      <div className="att-header">
        <div>
          <h1 className="att-title">Hall Ticket — Exam Setup & Eligibility</h1>
          <p className="att-subtitle">Set exam dates, check attendance eligibility, manage fines</p>
        </div>
      </div>

      {/* ===== ELIGIBILITY RULES (#41) — applies to every class ===== */}
      {rules && (
        <div className="att-card">
          <h2 className="att-card-title">Eligibility rules</h2>
          <p style={{ margin: "0 0 14px", fontSize: 15, color: "#5D5A6B" }}>
            These rules apply to every class when deciding who gets a hall ticket.
          </p>

          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 24 }}>
            <div className="att-field" style={{ minWidth: 220 }}>
              <label className="att-label" htmlFor="elig-min">Minimum attendance</label>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  id="elig-min"
                  className="att-input"
                  type="number"
                  min={1}
                  max={100}
                  step={1}
                  style={{ width: 96 }}
                  value={rulesForm.min_attendance}
                  disabled={!rules.can_edit || savingRules}
                  onChange={(e) => setRulesForm((f) => ({ ...f, min_attendance: e.target.value }))}
                />
                <span style={{ fontSize: 15, fontWeight: 600, color: "#17151F" }}>%</span>
              </div>
            </div>

            <label
              style={{
                display: "flex", alignItems: "center", gap: 10, fontSize: 15, color: "#17151F",
                cursor: rules.can_edit ? "pointer" : "default", paddingBottom: 10,
              }}
            >
              <input
                type="checkbox"
                checked={rulesForm.fine_unlocks}
                disabled={!rules.can_edit || savingRules}
                onChange={(e) => setRulesForm((f) => ({ ...f, fine_unlocks: e.target.checked }))}
                style={{ width: 18, height: 18 }}
              />
              A paid attendance fine unlocks the hall ticket
            </label>

            {rules.can_edit && (
              <button
                className="att-save-btn"
                onClick={saveRules}
                disabled={!rulesChanged || savingRules}
                style={{ marginBottom: 2, opacity: !rulesChanged || savingRules ? 0.5 : 1 }}
              >
                {savingRules ? "Saving…" : "Save rules"}
              </button>
            )}
          </div>

          {!rulesForm.fine_unlocks && (
            <p style={{ margin: "12px 0 0", fontSize: 14.5, color: "#8A4B0A" }}>
              With fines off, a student below the minimum stays blocked even after paying a fine.
            </p>
          )}

          {rulesMsg.text && (
            <p
              role="status"
              style={{
                margin: "12px 0 0", fontSize: 14.5, fontWeight: 600,
                color: rulesMsg.type === "ok" ? "#15803d" : "#dc2626",
              }}
            >
              {rulesMsg.type === "ok" ? "✓ " : ""}{rulesMsg.text}
            </p>
          )}

          <p style={{ margin: "12px 0 0", fontSize: 13.5, color: "#85839A" }}>
            {rules.can_edit
              ? (rules.updated_by
                  ? `Last changed by ${rules.updated_by} on ${new Date(rules.updated_at).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}.`
                  : "Using the default rules.")
              : "Only the main admin or the Examination admin can change these rules."}
          </p>
        </div>
      )}

      {/* ===== SELECT CLASS (from the course catalog) ===== */}
      <div className="att-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h2 className="att-card-title">Select Class</h2>
          {/* whole exam timetable from Excel (meeting point 2) - same rules as the grid:
              no weekends/holidays, no two exams of one class in the same session */}
          <ImportExport
            importer="exam_schedule"
            label="exam schedule"
            matchLabel="course, year, semester and subject"
            align="right"
            exportParams={{ course: selectedCourse, year: selectedYear, semester: selectedSem }}
            note="One row per subject. Weekends, holidays and two exams of the same class in one session are refused. An existing subject's date is updated."
            onDone={() => { loadScheduledClasses(); if (selectedSem) loadData(); }}
          />
        </div>
        <div className="att-filter-grid">
          <div className="att-field">
            <label className="att-label">Course</label>
            <select className="att-input" value={selectedCourse}
              onChange={(e) => { setSelectedCourse(e.target.value); setSelectedYear(""); setSelectedSem(""); }}>
              <option value="">— Select Course —</option>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="att-field">
            <label className="att-label">Year</label>
            <select className="att-input" value={selectedYear}
              onChange={(e) => { setSelectedYear(e.target.value); setSelectedSem(""); }}
              disabled={!selectedCourse}>
              <option value="">— Select Year —</option>
              {yearOptions.map((y) => <option key={y} value={y}>Year {y}</option>)}
            </select>
          </div>
          <div className="att-field">
            <label className="att-label">Semester</label>
            <select className="att-input" value={selectedSem}
              onChange={(e) => setSelectedSem(e.target.value)}
              disabled={!selectedYear}>
              <option value="">— Select Semester —</option>
              {semesters.map((s) => <option key={s} value={s}>Semester {s}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* ===== SCHEDULED CLASSES OVERVIEW ===== */}
      {scheduledClasses.length > 0 && (
        <div className="att-card">
          <h2 className="att-card-title">Scheduled classes ({scheduledClasses.length})</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {scheduledClasses.map((c, i) => {
              const active = String(c.course_id) === String(selectedCourse)
                && String(c.year) === String(selectedYear)
                && String(c.semester) === String(selectedSem);
              return (
                <div
                  key={i}
                  onClick={() => openClass(c)}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "13px 15px", borderRadius: 12, cursor: "pointer",
                    border: active ? "1px solid #4B32C3" : "1px solid #E7E7EC",
                    background: active ? "#eff6ff" : "#fff",
                    transition: "background .15s, border-color .15s",
                  }}
                  onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = "#F6F6F8"; }}
                  onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = "#fff"; }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{
                      width: 38, height: 38, borderRadius: 10, background: "#eff6ff",
                      display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
                    }}>🗓️</span>
                    <div>
                      <div style={{ fontWeight: 600 }}>{c.course_name}</div>
                      <div style={{ fontSize: 13.5, color: "#5D5A6B" }}>Year {c.year} · Semester {c.semester}</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <span style={{
                      background: "#eff6ff", color: "#4B32C3", fontWeight: 600, fontSize: 13,
                      padding: "4px 11px", borderRadius: 20,
                    }}>{c.count} exam{c.count !== 1 ? "s" : ""}</span>
                    {c.first && (
                      <span style={{ fontSize: 13.5, color: "#5D5A6B" }}>{fmt(c.first)} – {fmt(c.last)}</span>
                    )}
                    <span style={{ color: "#85839A", fontSize: 18 }}>›</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ===== EXAM SCHEDULE ===== */}
      {selectedSem && classSubjects.length > 0 && (
        <div className="att-card">
          <h2 className="att-card-title">Exam Schedule</h2>

          {/* WAVE 3 PART 2: which exam session these dates are for */}
          {examSessions.length > 0 && (
            <div className="es-strip" style={{ marginBottom: 12 }}>
              <label className="es-group">
                Exam session
                <select className="att-input" style={{ width: 250 }} value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}>
                  {examSessions.map((x) => (
                    <option key={x.id} value={x.id}>{x.name}{x.is_current ? " (current)" : ""}</option>
                  ))}
                </select>
              </label>
              <span style={{ fontSize: 13.5, color: "#5D5A6B" }}>
                {locked
                  ? "This timetable is published, so dates are locked. Unpublish it in Exam sessions to change them."
                  : "Arrear students are checked too: Arrange moves a paper off any slot where they already write another class's paper."}
                {" "}<a href="/exam-sessions" style={{ color: "#4B32C3", fontWeight: 600 }}>Open exam sessions</a>
              </span>
            </div>
          )}

          {/* controls strip */}
          <div className="es-strip">
            <div className="es-group">
              📅 Gap (days)
              <div className="es-step">
                <button onClick={() => setGap((g) => Math.max(1, g - 1))} disabled={gap <= 1}>−</button>
                <span>{gap}</span>
                <button onClick={() => setGap((g) => g + 1)}>+</button>
              </div>
            </div>
            <div className="es-group">
              🕑 Session
              <select className="att-input" style={{ width: 160 }}
                value={defaultSession} onChange={(e) => setDefaultSession(e.target.value)}>
                <option value="FN">FN — Forenoon</option>
                <option value="AN">AN — Afternoon</option>
              </select>
            </div>
            <input
              value={pref}
              onChange={(e) => setPref(e.target.value)}
              placeholder="e.g. august 3, 2 day gap, 2 exams per day, within 2 weeks"
              className="att-input"
              style={{ flex: 1, minWidth: 220, marginRight: 10 }}
              title="Understands: a month or date, a gap, exams per day, a window, a session. Other instructions are ignored."
            />
            <button className="es-btn-ai" onClick={() => runArrange("ai")} disabled={drafting || locked}>
              {drafting ? "Working…" : "✦ Draft with AI"}
            </button>
            <button className="es-btn-arrange" onClick={() => runArrange("auto")} disabled={drafting || locked}>
              {drafting ? "Working…" : "✳ Arrange Exams"}
            </button>
          </div>

          <div className="es-help">ⓘ {windowText}</div>

          {/* Only these five things are understood. Anything else typed into the box is
              silently ignored — say so plainly, or admins will type rules that do nothing. */}
          <div className="es-help" style={{ color: "#7c3aed" }}>
            💡 The box understands only: a month or date (august / august 3) · a gap ("2 day gap") · exams per day ("2 exams per day") · a window ("within 16 days") · a session ("morning"/"afternoon"). Other instructions are ignored — weekends are already blocked automatically.
          </div>

          {startNote && (
            <div className="es-help" style={{ color: "#8A4B0A" }}>
              ↪ {startNote}
            </div>
          )}

          {!hasAnyDate ? (
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "14px 16px", background: "#F6F6F8",
              border: "1px dashed #cbd5e1", borderRadius: 10,
              color: "#5D5A6B", fontSize: 14.5, marginTop: 6,
            }}>
              <span style={{ fontSize: 18 }}>🗓️</span>
              <span>
                No exams yet — set the gap and session, then click{" "}
                <span className="es-link" onClick={() => runArrange("auto")}>Arrange Exams</span>.
              </span>
            </div>
          ) : (
            <>
              <div className="att-table-wrap">
                <table className="att-table">
                  <thead>
                    <tr>
                      <th>Subject</th>
                      <th className="center">Exam Date (dd/mm/yyyy)</th>
                      <th className="center">Session</th>
                      <th className="center">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedSubjects.map((sub) => {
                      const row = schedule[sub.id] || {};
                      const st = statuses[sub.id];
                      const tint = st.level === "conflict" ? "#fef2f2" : st.level === "warn" ? "#fffbeb" : undefined;
                      return (
                        <tr key={sub.id} style={tint ? { background: tint } : undefined}>
                          <td className="att-td-name" style={{ borderLeft: `4px solid ${st.color || "#E7E7EC"}`, paddingLeft: 12 }}>
                            <span className="es-dot" style={{ background: st.color || "#cbd5e1" }} />
                            {sub.code ? <b>{sub.code} </b> : null}{sub.name}
                          </td>
                          <td className="center">
                            <DateInput
                              value={row.exam_date || ""}
                              onChange={(iso) => setSchedField(sub.id, "exam_date", iso)}
                              status={st.level}
                            />
                            {st.msg && (
                              <div className="es-warn-text" style={{ color: st.color }}>⚠ {st.msg}</div>
                            )}
                          </td>
                          <td className="center">
                            <select
                              className="att-input"
                              style={{ width: 120 }}
                              value={row.session || "FN"}
                              onChange={(e) => setSchedField(sub.id, "session", e.target.value)}
                            >
                              <option value="FN">FN</option>
                              <option value="AN">AN</option>
                            </select>
                          </td>
                          <td className="center">
                            <span className="es-pill" style={pillStyle(st.level)}>{st.pill}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="es-footer">
                <div style={{ fontSize: 14, color: blockingCount ? "#B42318" : "#15803d", fontWeight: 600 }}>
                  {examCount} exam{examCount !== 1 ? "s" : ""} · {blockingCount} conflict{blockingCount !== 1 ? "s" : ""}
                  {blockingCount > 0 && (
                    <span style={{ color: "#5D5A6B", fontWeight: 400, marginLeft: 8 }}>
                      — resolve all conflicts to enable Save
                    </span>
                  )}
                </div>
                <button className="att-save-btn" onClick={saveSchedule} disabled={savingSchedule || blockingCount > 0 || locked}
                  style={locked ? { opacity: 0.5, cursor: "not-allowed" } : undefined}>
                  {savingSchedule ? "Saving…" : "Save Exam Schedule"}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ===== ELIGIBILITY ROSTER ===== */}
      <div className="att-card">
        <h2 className="att-card-title">Eligibility Roster</h2>
        {loading ? (
          <div className="att-state"><div className="att-spinner" /><p>Loading roster…</p></div>
        ) : !selectedSem ? (
          <div className="att-state"><p>Select course, year and semester above.</p></div>
        ) : roster.length === 0 ? (
          <div className="att-state"><p>No students found for this class.</p></div>
        ) : (
          <>
            <div className="att-summary-row" style={{ alignItems: "center" }}>
              <span className="att-chip present">{eligibleCount} eligible</span>
              <span className="att-chip absent">{roster.length - eligibleCount} not eligible</span>
              {!finesOn ? (
                <span style={{ marginLeft: "auto", fontSize: 14, color: "#85839A" }}>
                  Fines are off in the eligibility rules.
                </span>
              ) : (
              <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
                <label className="att-label" style={{ margin: 0 }}>Fine ₹</label>
                <input
                  className="att-input"
                  type="number"
                  min={0}
                  style={{ width: 90 }}
                  value={fineAmount}
                  onChange={(e) => setFineAmount(e.target.value)}
                />
                <button className="att-btn-outline" onClick={generateFines} disabled={generating}>
                  {generating ? "Generating…" : "Generate Fines"}
                </button>
              </span>
              )}
            </div>
            <div className="att-table-wrap">
              <table className="att-table">
                <thead>
                  <tr>
                    <th>Sl.No</th>
                    <th>Student Name</th>
                    <th>Roll No</th>
                    <th className="center">Attendance</th>
                    <th className="center">Status</th>
                    {canOverride && <th className="center">Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {roster.map((r, idx) => (
                    <tr key={r.student} className={!r.eligible ? "att-row-low" : ""}>
                      <td>{idx + 1}</td>
                      <td className="att-td-name">{r.student_name}</td>
                      <td><span className="att-roll">{r.student_roll_no || "—"}</span></td>
                      <td className="center">
                        {r.attendance_percent != null ? `${r.attendance_percent}%` : "—"}
                      </td>
                      <td className="center">
                        {r.reason === "override" ? (
                          <span style={{ color: "#4B32C3", fontSize: 14, fontWeight: 600 }}>Eligible (override)</span>
                        ) : r.eligible ? (
                          <span style={{ color: "#16a34a", fontSize: 14 }}>
                            {r.reason === "fine_paid" ? "Eligible (fine paid)" : "Eligible"}
                          </span>
                        ) : r.has_unpaid_fine ? (
                          <span style={{ color: "#8A4B0A", fontSize: 14 }}>Fine pending</span>
                        ) : (
                          <span style={{ color: "#dc2626", fontSize: 14 }}>Not eligible</span>
                        )}
                      </td>
                      {/* ELIGIBILITY OVERRIDE (#41 Part B) */}
                      {canOverride && (
                        <td className="center">
                          {r.reason === "override" && r.override_id ? (
                            <button
                              className="att-btn-outline"
                              style={{ padding: "5px 12px", fontSize: 13.5, color: "#dc2626", borderColor: "#fecaca" }}
                              onClick={() => openAction("revoke", r)}
                            >
                              Revoke
                            </button>
                          ) : r.reason === "blocked" ? (
                            <button
                              className="att-btn-outline"
                              style={{ padding: "5px 12px", fontSize: 13.5 }}
                              onClick={() => openAction("override", r)}
                            >
                              Override
                            </button>
                          ) : r.reason === "exam_fee_unpaid" ? (
                            <span style={{ fontSize: 13.5, color: "#85839A" }}>Exam fee unpaid</span>
                          ) : (
                            <span style={{ color: "#85839A" }}>—</span>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* ===== OVERRIDE LOG (#41 Part B) — read-only audit history ===== */}
      {selectedSem && (
        <div className="att-card">
          <h2 className="att-card-title">Override log</h2>
          <p style={{ margin: "0 0 12px", fontSize: 14.5, color: "#5D5A6B" }}>
            Every override and revoke for this class. Entries cannot be edited or deleted.
          </p>
          {logEvents.length === 0 ? (
            <div className="att-state"><p>No overrides for this class yet.</p></div>
          ) : (
            <div className="att-table-wrap">
              <table className="att-table">
                <thead>
                  <tr>
                    <th>Date &amp; time</th>
                    <th>Action</th>
                    <th>Student</th>
                    <th className="center">Sem</th>
                    <th>Done by</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {logEvents.map((e) => (
                    <tr key={e.key}>
                      <td style={{ whiteSpace: "nowrap" }}>{fmtWhen(e.when)}</td>
                      <td>
                        <span
                          style={{
                            fontSize: 13.5, fontWeight: 700, padding: "3px 9px", borderRadius: 999,
                            background: e.type === "Override" ? "#f5f2ff" : "#fef2f2",
                            color: e.type === "Override" ? "#4B32C3" : "#dc2626",
                          }}
                        >
                          {e.type}
                        </span>
                      </td>
                      <td className="att-td-name">
                        {e.o.student_name}{" "}
                        <span className="att-roll">{e.o.student_roll_no || "—"}</span>
                      </td>
                      <td className="center">{e.o.semester}</td>
                      <td>{e.by || "—"}</td>
                      <td style={{ maxWidth: 360, whiteSpace: "normal" }}>{e.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ===== OVERRIDE / REVOKE POP-UP (#41 Part B) ===== */}
      {action && (
        <div
          onClick={closeAction}
          style={{
            position: "fixed", inset: 0, zIndex: 1100, background: "rgba(15,23,42,.45)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="ovr-title"
            onClick={(ev) => ev.stopPropagation()}
            style={{
              background: "#fff", borderRadius: 16, maxWidth: 480, width: "100%",
              padding: "22px 24px 20px", boxShadow: "0 20px 60px rgba(0,0,0,.30)",
            }}
          >
            <h3 id="ovr-title" style={{ margin: "0 0 6px", fontSize: 17, color: "#17151F" }}>
              {action.type === "override" ? "Override eligibility" : "Revoke override"}
            </h3>
            <p style={{ margin: "0 0 14px", fontSize: 14.5, color: "#5D5A6B", lineHeight: 1.5 }}>
              {action.type === "override"
                ? "This student will get a hall ticket for this semester despite the attendance shortage."
                : "The student's hall ticket will be blocked again. The original override stays in the log."}
            </p>

            <div style={{ background: "#F7F7F9", border: "1px solid #E7E7EC", borderRadius: 10, padding: "10px 12px", fontSize: 15, marginBottom: 14 }}>
              <b>{action.row.student_name}</b>{" "}
              <span className="att-roll">{action.row.student_roll_no || "—"}</span>
              <div style={{ color: "#5D5A6B", fontSize: 14, marginTop: 4 }}>
                Attendance: {action.row.attendance_percent != null ? `${action.row.attendance_percent}%` : "No records"}
                {" · "}Required: {minPct}%
              </div>
            </div>

            <label className="att-label" htmlFor="ovr-reason">
              Reason (required)
            </label>
            <textarea
              id="ovr-reason"
              className="att-input"
              rows={3}
              autoFocus
              value={actionReason}
              onChange={(e) => setActionReason(e.target.value)}
              placeholder={action.type === "override"
                ? "e.g. Medical leave – certificate verified"
                : "e.g. Certificate found to be invalid"}
              style={{ width: "100%", resize: "vertical", fontFamily: "inherit" }}
            />
            <div style={{ fontSize: 13, color: "#85839A", marginTop: 4 }}>
              At least {MIN_REASON} characters. Saved with your name and the date and time.
            </div>

            {actionErr && (
              <p role="alert" style={{ margin: "10px 0 0", fontSize: 14.5, fontWeight: 600, color: "#dc2626" }}>
                {actionErr}
              </p>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
              <button className="att-btn-outline" onClick={closeAction} disabled={actionBusy}>
                Cancel
              </button>
              <button
                className="att-save-btn"
                onClick={submitAction}
                disabled={actionBusy || actionReason.trim().length < MIN_REASON}
                style={{
                  opacity: actionBusy || actionReason.trim().length < MIN_REASON ? 0.5 : 1,
                  ...(action.type === "revoke" ? { background: "#dc2626" } : {}),
                }}
              >
                {actionBusy ? "Saving…" : action.type === "override" ? "Override" : "Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );

  if (embedded) return body;
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="att-page">{body}</div>
          </div>
        </div>
      </div>
    </div>
  );
}