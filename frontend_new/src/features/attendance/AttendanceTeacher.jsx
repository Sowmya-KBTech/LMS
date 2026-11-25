import { useEffect, useMemo, useRef, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import Icon from "../../components/Icon";
import ImportExport from "../../components/ImportExport";
import API from "../../api";
import "../../App.css";

// ---------------- helpers ----------------
const fmtTime = (t) => {
  if (!t) return "";
  const [h, m] = String(t).split(":");
  let hr = parseInt(h, 10);
  const ap = hr >= 12 ? "PM" : "AM";
  hr = hr % 12 || 12;
  return `${hr}:${m} ${ap}`;
};

// local YYYY-MM-DD (avoids UTC off-by-one in IST)
const toKey = (d) => {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().split("T")[0];
};
const todayLocal = () => toKey(new Date());
const shiftDay = (key, n) => {
  const d = new Date(`${key}T00:00:00`);
  d.setDate(d.getDate() + n);
  return toKey(d);
};
const dayLabel = (key) =>
  new Date(`${key}T00:00:00`).toLocaleDateString("en-IN", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

// normalize a FK that may come back as an id (5) or an object ({id:5})
const idOf = (v) => {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return String(v.id ?? v.pk ?? "");
  return String(v);
};

const pick = (res) => res?.data?.results || res?.data || [];

// "2026-11-09" -> "09-11-2026"
const fmtD = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("-") : "");

const STATUS = [
  { key: "present", label: "Present", short: "P" },
  { key: "absent", label: "Absent", short: "A" },
  { key: "duty_leave", label: "On duty", short: "OD" },
];

// QUICK ENTRY (meeting point 7): "3 7 12" or "25ME003, 25ME007" -> students.
// A token matches a full roll number, or the END of one ("7" -> 25ME007) when
// that is unique in this class. Returns { matched: [student ids], problems: [] }.
const matchRolls = (text, roster) => {
  const tokens = String(text || "").split(/[\s,;]+/).map((t) => t.trim().toLowerCase()).filter(Boolean);
  const matched = new Set();
  const problems = [];
  tokens.forEach((t) => {
    const exact = roster.filter((e) => String(e.student_roll_no || "").toLowerCase() === t);
    let hits = exact;
    // "7" means roll number 7 (25ME007), not every roll ending in 7 (25ME017)
    if (!hits.length && /^\d+$/.test(t)) {
      const n = Number(t);
      hits = roster.filter((e) => {
        const digits = (String(e.student_roll_no || "").match(/(\d+)$/) || [])[1];
        return digits !== undefined && Number(digits) === n;
      });
    }
    if (!hits.length) {
      hits = roster.filter((e) => String(e.student_roll_no || "").toLowerCase().endsWith(t));
    }
    if (hits.length === 1) matched.add(hits[0].student);
    else if (hits.length === 0) problems.push(`"${t}" - no student`);
    else problems.push(`"${t}" - matches ${hits.length} students, type more of the roll number`);
  });
  return { matched: [...matched], problems };
};

const classLabel = (s) =>
  s ? `${s.course_name} · Year ${s.year_number}, Sem ${s.semester}` : "";

export default function AttendanceTeacher() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("mark");

  // ---------------- reference data ----------------
  const [subjects, setSubjects] = useState([]);
  const [timeSlots, setTimeSlots] = useState([]);
  const [semester, setSemester] = useState(null);
  const [ttEntries, setTtEntries] = useState([]);
  const [ttLoaded, setTtLoaded] = useState(false);

  // ---------------- mark: selection ----------------
  const [selectedDate, setSelectedDate] = useState(todayLocal());
  const [sel, setSel] = useState(null); // { ta, hour }
  const [markedMap, setMarkedMap] = useState({}); // "ta|hour" → true, for selectedDate

  // ---------------- mark: register ----------------
  const [students, setStudents] = useState([]);
  const [attendance, setAttendance] = useState({});
  const [savedMarks, setSavedMarks] = useState({}); // what the server holds for this register
  const [wasMarked, setWasMarked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null); // { tone: "ok" | "bad", text }
  const [odStudentIds, setOdStudentIds] = useState([]); 
  const [leaveStudentIds, setLeaveStudentIds] = useState([]);   // WAVE 1: approved student leave
    const [holidays, setHolidays] = useState({}); // FIX #27: "YYYY-MM-DD" → holiday name
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  // ATTENDANCE WINDOW (#46, replaces the #43 Change 1 past-day lock): the
  // server says whether this register is open, in its correction window,
  // locked, or past the late-entry deadline. The server also enforces it.
  const [win, setWin] = useState(null); // { state, late_entry_deadline, first_saved, edit_until }
  // #46 Part 2: reason pop-up for changes inside the correction window
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reasonText, setReasonText] = useState("");
  const [locking, setLocking] = useState(false);   // #46 Part 3: manual lock
  const lockedPast = win ? ["locked", "late_closed"].includes(win.state) : false;

  // ---------------- report ----------------
  const [reportTA, setReportTA] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [reportData, setReportData] = useState([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportRan, setReportRan] = useState(false);
  const [reportError, setReportError] = useState("");
  const [onlyLow, setOnlyLow] = useState(false);

  // ================= LOAD REFERENCE DATA =================
  useEffect(() => {
    API.get("/teaching-assignments/?my=true").then((res) => setSubjects(pick(res)));
    API.get("/timeslots/").then((res) => setTimeSlots(pick(res)));
    API.get("/semester/").then((res) => {
      const data = pick(res);
      setSemester(Array.isArray(data) ? data[0] : data);
    });

        // FIX #27: holidays from the Calendar (and the old timetable list)
    API.get("/holidays/")
      .then((res) => {
        const m = {};
        pick(res).forEach((h) => { if (h.date) m[String(h.date).slice(0, 10)] = h.name || "Holiday"; });
        setHolidays(m);
      })
      .catch(() => setHolidays({}));

    API.get("/timetable/?scope=teacher")
      .then((res) => setTtEntries(pick(res)))
      .catch(() => setTtEntries([]))
      .finally(() => setTtLoaded(true));
  }, []);

  // approved-OD students for the selected date
  useEffect(() => {
    if (!selectedDate) { setOdStudentIds([]); setLeaveStudentIds([]); return; }
    API.get(`/attendance/od_students/?date=${selectedDate}`)
      .then((res) => {
        setOdStudentIds((res.data?.student_ids || []).map(Number));
        setLeaveStudentIds((res.data?.leave_ids || []).map(Number));
      })
      .catch(() => { setOdStudentIds([]); setLeaveStudentIds([]); });
  }, [selectedDate]);

  const subjectById = useMemo(() => {
    const m = {};
    subjects.forEach((s) => { m[String(s.id)] = s; });
    return m;
  }, [subjects]);

  // ================= CLASSES ON THE SELECTED DATE =================
  // Why a date has no classes — checked in the same order the list is built.
  const blockedReason = useMemo(() => {
    if (semester?.start_date && selectedDate < semester.start_date)
      return { title: "Semester hasn't started", text: `Classes begin on ${semester.start_date}.` };
    if (semester?.end_date && selectedDate > semester.end_date)
      return { title: "Semester has ended", text: `The semester ended on ${semester.end_date}.` };
    if (new Date(`${selectedDate}T00:00:00`).getDay() === 0)
      return { title: "It's a Sunday", text: "There are no classes on Sundays." };
    if (holidays[selectedDate])
      return { title: `Holiday — ${holidays[selectedDate]}`, text: "No classes and no attendance on a holiday." };
    // FIX #28: attendance only for today or earlier
    if (selectedDate > todayLocal())
      return { title: "This date is in the future", text: "Attendance can only be marked for today or earlier days." };
    return null;
  }, [semester, selectedDate, holidays]);

  const dayClasses = useMemo(() => {
    if (blockedReason) return [];
    const weekday = new Date(`${selectedDate}T00:00:00`).getDay() - 1; // Mon=0 .. Sat=5
    const slotMap = {};
    timeSlots.forEach((s) => { slotMap[s.period_no] = s; });
    const seen = new Set();
    return ttEntries
      .filter((e) => e.day_of_week === weekday)
      .map((e) => {
        const ta = idOf(e.assignment);
        const slot = slotMap[e.period_no];
        return {
          ta,
          hour: e.period_no,
          start: slot?.start_time,
          end: slot?.end_time,
          subject: subjectById[ta],
        };
      })
      .filter((c) => {
        const k = `${c.ta}|${c.hour}`;
        if (!c.ta || seen.has(k)) return false;
        seen.add(k);
        return true;
      })
      .sort((a, b) => a.hour - b.hour);
  }, [ttEntries, timeSlots, subjectById, selectedDate, blockedReason]);

  const dayKey = dayClasses.map((c) => `${c.ta}|${c.hour}`).join(",");

  // Which of the day's classes already have attendance saved.
  useEffect(() => {
    const tas = [...new Set(dayClasses.map((c) => c.ta))];
    if (tas.length === 0) { setMarkedMap({}); return undefined; }
    let alive = true;
    Promise.all(
      tas.map((ta) =>
        API.get(`/attendance/?teaching_assignment=${ta}&from_date=${selectedDate}&to_date=${selectedDate}`)
          .then((res) => pick(res).map((a) => `${ta}|${a.hour}`))
          .catch(() => [])
      )
    ).then((lists) => {
      if (!alive) return;
      const m = {};
      lists.flat().forEach((k) => { m[k] = true; });
      setMarkedMap(m);
    });
    return () => { alive = false; };
  }, [dayKey, selectedDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // With exactly one class that day, open it straight away.
  useEffect(() => {
    if (!sel && dayClasses.length === 1) setSel({ ta: dayClasses[0].ta, hour: dayClasses[0].hour });
  }, [dayKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // ================= LOAD THE REGISTER =================
  // Roster and saved marks load TOGETHER for one (class, date, period), and
  // the register is only shown once both have arrived. Responses for a
  // register the teacher has already left are ignored, so a slow request
  // can never overwrite marks — and marks from one period can never leak
  // into another.
  useEffect(() => {
    setNotice(null);
    setQuery("");
    setFilter("all");
    if (!sel) { setStudents([]); setAttendance({}); setSavedMarks({}); setWasMarked(false); return undefined; }

    let alive = true;
    setLoading(true);
    Promise.all([
      API.get(`/enrollments/?teaching_assignment=${sel.ta}`),
      API.get(`/attendance/?teaching_assignment=${sel.ta}&from_date=${selectedDate}&to_date=${selectedDate}`),
    ])
      .then(([enrRes, attRes]) => {
        if (!alive) return;
        const roster = pick(enrRes);
        const saved = {};
        pick(attRes)
          .filter((a) => a.hour === Number(sel.hour))
          .forEach((a) => { saved[a.student] = a.status; });

        const next = {};
        roster.forEach((e) => {
          // Present by default: the teacher marks the absentees.
          next[e.student] = saved[e.student] ?? "present";
        });
        setStudents(roster);
        setSavedMarks(saved);
        setWasMarked(Object.keys(saved).length > 0);
        setAttendance(next);
      })
      .catch(() => {
        if (alive) setNotice({ tone: "bad", text: "Couldn't load this class. Check your connection and pick the class again." });
      })
      .finally(() => { if (alive) setLoading(false); });

    return () => { alive = false; };
  }, [sel?.ta, sel?.hour, selectedDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // Approved-OD students are forced to On duty (added on top, never rebuilt).
  useEffect(() => {
    if (odStudentIds.length === 0) return;
    setAttendance((prev) => {
      const next = { ...prev };
      odStudentIds.forEach((id) => { if (id in next) next[id] = "duty_leave"; });
      return next;
    });
  }, [odStudentIds, students]);

  const isOd = (studentId) => odStudentIds.includes(Number(studentId));
  const isOnLeave = (studentId) => leaveStudentIds.includes(Number(studentId));

  // WAVE 1: a student on approved leave starts as Absent (leave is an excused
  // absence). The teacher can still mark Present if they turn up.
  useEffect(() => {
    if (leaveStudentIds.length === 0) return;
    setAttendance((prev) => {
      const next = { ...prev };
      leaveStudentIds.forEach((id) => { if (id in next && savedMarks[id] === undefined) next[id] = "absent"; });
      return next;
    });
  }, [leaveStudentIds, students, savedMarks]);

  // ATTENDANCE WINDOW (#46): load the register's state from the server
  const loadWin = () => {
    if (!sel) { setWin(null); return; }
    API.get(`/attendance/session_status/?teaching_assignment=${sel.ta}&date=${selectedDate}&hour=${Number(sel.hour)}`)
      .then((r) => setWin(r.data))
      .catch(() => setWin(null));
  };
  useEffect(() => {
    loadWin();
  }, [sel?.ta, sel?.hour, selectedDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // what the register looked like when it was opened
  const baseline = (id) => (isOd(id) ? "duty_leave" : savedMarks[id] ?? "present");
  const dirty = students.some((e) => attendance[e.student] && attendance[e.student] !== baseline(e.student));

  // warn before leaving the page with unsaved changes
  useEffect(() => {
    if (!dirty) return undefined;
    const onUnload = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [dirty]);

  const confirmLeave = () =>
    !dirty || window.confirm("You have unsaved attendance changes. Leave without saving?");

  const chooseClass = (c) => {
    if (sel && sel.ta === c.ta && sel.hour === c.hour) return;
    if (!confirmLeave()) return;
    setSel({ ta: c.ta, hour: c.hour });
  };

  const changeDate = (key) => {
    if (!key || key === selectedDate) return;
    if (!confirmLeave()) return;
    setSel(null);
    setSelectedDate(key);
  };

  // ================= MARKING =================
  const setStatus = (studentId, status) => {
    if (isOd(studentId)) return; // locked — approved OD
    if (lockedPast) return;      // locked — past day already marked
    setNotice(null);
    setAttendance((prev) => ({ ...prev, [studentId]: status }));
  };

  const markAll = (status) => {
    if (lockedPast) return;      // locked — past day already marked
    setNotice(null);
    setAttendance(() => {
      const all = {};
      // never override an approved-OD student
      students.forEach((e) => { all[e.student] = isOd(e.student) ? "duty_leave" : status; });
      return all;
    });
  };

  // #46 Part 2: statuses that were saved earlier and are being changed now
  const changedSaved = students.filter(
    (e) => savedMarks[e.student] !== undefined && !isOd(e.student) && attendance[e.student] !== savedMarks[e.student]
  );

  const saveAttendance = () => {
    if (!sel) return;
    // Inside the correction window (after the first-save day) a change needs a reason.
    if (win?.state === "open_reason" && changedSaved.length > 0) {
      setReasonText("");
      setNotice(null);
      setReasonOpen(true);
      return;
    }
    doSave("");
  };

  // #46 Part 3: the teacher closes this period early. There is no unlock.
  const lockSession = async () => {
    if (!sel) return;
    if (!window.confirm(
      "Lock this period's attendance?\n\nYou won't be able to change it yourself after locking. " +
      "Only the class in-charge can correct it, with a reason."
    )) return;
    setLocking(true);
    setNotice(null);
    try {
      await API.post("/attendance/lock_session/", {
        teaching_assignment: sel.ta, date: selectedDate, hour: Number(sel.hour),
      });
      setNotice({ tone: "ok", text: "Attendance locked." });
      loadWin();
    } catch (err) {
      setNotice({ tone: "bad", text: err?.response?.data?.error || "Couldn't lock this period." });
    } finally {
      setLocking(false);
    }
  };

  const doSave = async (reason) => {
    if (!sel) return;
    // A student with no status is a bug, not an absence — refuse the save
    // rather than record anyone absent by accident.
    const missing = students.filter((e) => !isOd(e.student) && !attendance[e.student]);
    if (missing.length > 0) {
      setNotice({
        tone: "bad",
        text: `${missing.length} student(s) have no status. Pick the class again to reload the list, then save.`,
      });
      return;
    }

    const records = students.map((e) => ({
      student: e.student,
      // force duty_leave for approved-OD students regardless of UI state
      status: isOd(e.student) ? "duty_leave" : attendance[e.student],
    }));

    setSaving(true);
    setNotice(null);
    try {
      await API.post("/attendance/bulk_mark/", {
        teaching_assignment: sel.ta,
        date: selectedDate,
        hour: Number(sel.hour),
        records,
        reason,   // #46 Part 2: only needed for changes inside the window
      });
      setReasonOpen(false);
      const snap = {};
      records.forEach((r) => { snap[r.student] = r.status; });
      setSavedMarks(snap);
      setWasMarked(true);
      setMarkedMap((m) => ({ ...m, [`${sel.ta}|${sel.hour}`]: true }));
      loadWin(); // the correction window starts at the first save
      const t = new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
      setNotice({ tone: "ok", text: `Attendance saved at ${t}.` });
    } catch (err) {
      const why = err?.response?.data?.error || err?.response?.data?.detail;
      setNotice({ tone: "bad", text: why || "Attendance wasn't saved. Check your connection and press Save again." });
    } finally {
      setSaving(false);
    }
  };

  // ================= REGISTER VIEW DATA =================
  const counts = { present: 0, absent: 0, duty_leave: 0 };
  students.forEach((e) => {
    const st = isOd(e.student) ? "duty_leave" : attendance[e.student];
    if (st in counts) counts[st]++;
  });
  const odCount = students.filter((e) => isOd(e.student)).length;

  const q = query.trim().toLowerCase();
  const visible = students
    .map((e, i) => ({ e, n: i + 1 }))
    .filter(({ e }) => {
      const st = isOd(e.student) ? "duty_leave" : attendance[e.student];
      if (filter !== "all" && st !== filter) return false;
      if (!q) return true;
      return `${e.student_name || ""} ${e.student_roll_no || ""}`.toLowerCase().includes(q);
    });

  const current = sel ? dayClasses.find((c) => c.ta === sel.ta && c.hour === sel.hour) : null;
  const currentSubject = sel ? subjectById[sel.ta] : null;
  const isToday = selectedDate === todayLocal();

  // ---- QUICK ENTRY: type the absentees, everyone else is present ----
  const [quick, setQuick] = useState("");
  const [quickMsg, setQuickMsg] = useState(null);   // { tone, text }
  useEffect(() => { setQuick(""); setQuickMsg(null); }, [sel?.ta, sel?.hour, selectedDate]);

  const applyAbsentees = () => {
    if (lockedPast) return;
    const { matched, problems } = matchRolls(quick, students);
    if (!matched.length && problems.length) {
      setQuickMsg({ tone: "bad", text: problems.join(" · ") });
      return;
    }
    const absent = new Set(matched.map(String));
    const skippedOd = students.filter((e) => absent.has(String(e.student)) && isOd(e.student)).length;
    setNotice(null);
    setAttendance(() => {
      const all = {};
      students.forEach((e) => {
        all[e.student] = isOd(e.student) ? "duty_leave" : absent.has(String(e.student)) ? "absent" : "present";
      });
      return all;
    });
    const parts = [`${matched.length - skippedOd} marked absent, everyone else present. Check the list, then save.`];
    if (skippedOd) parts.push(`${skippedOd} on approved OD stay On duty.`);
    if (problems.length) parts.push(`Not matched: ${problems.join(" · ")}`);
    setQuickMsg({ tone: problems.length ? "bad" : "ok", text: parts.join(" ") });
  };

  // ---- the class happening NOW opens by itself (once per day) ----
  const autoPicked = useRef("");
  useEffect(() => {
    if (!isToday || sel || !dayClasses.length || autoPicked.current === selectedDate) return;
    const now = new Date();
    const mins = now.getHours() * 60 + now.getMinutes();
    const toMin = (t) => {
      if (!t) return null;
      const [h, m] = String(t).split(":").map(Number);
      return h * 60 + (m || 0);
    };
    // the running period, or one that starts within 10 minutes
    const live = dayClasses.find((c) => {
      const a = toMin(c.start), b = toMin(c.end);
      return a !== null && b !== null && mins >= a - 10 && mins <= b;
    });
    autoPicked.current = selectedDate;
    if (live) setSel({ ta: live.ta, hour: live.hour });
  }, [isToday, sel, dayClasses, selectedDate]);

  // ================= REPORT =================
  // sensible default range: semester start (or last 30 days) → today
  const applyDefaultRange = () => {
    const today = todayLocal();
    const start = semester?.start_date && semester.start_date <= today ? semester.start_date : shiftDay(today, -30);
    setFromDate(start);
    setToDate(semester?.end_date && semester.end_date < today ? semester.end_date : today);
  };

  useEffect(() => {
    if (view === "report" && !fromDate && !toDate) applyDefaultRange();
  }, [view, semester]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRange = (kind) => {
    const today = todayLocal();
    const d = new Date(`${today}T00:00:00`);
    if (kind === "week") {
      const mon = new Date(d);
      mon.setDate(d.getDate() - ((d.getDay() + 6) % 7));
      setFromDate(toKey(mon));
      setToDate(today);
    } else if (kind === "month") {
      setFromDate(toKey(new Date(d.getFullYear(), d.getMonth(), 1)));
      setToDate(today);
    } else if (kind === "semester" && semester?.start_date) {
      setFromDate(semester.start_date);
      setToDate(semester.end_date && semester.end_date < today ? semester.end_date : today);
    }
  };

  const fetchReport = async () => {
    setReportError("");
    if (!reportTA) return setReportError("Choose a subject first.");
    if (!fromDate || !toDate) return setReportError("Choose both dates.");
    if (fromDate > toDate) return setReportError("The From date is after the To date.");
    setReportLoading(true);
    try {
      const res = await API.get(
        `/attendance/?teaching_assignment=${reportTA}&from_date=${fromDate}&to_date=${toDate}`
      );
      const studentMap = {};
      pick(res).forEach((a) => {
        if (!studentMap[a.student]) {
          studentMap[a.student] = { name: a.student_name, roll: a.student_roll_no || "-", present: 0, absent: 0, duty: 0, total: 0 };
        }
        const s = studentMap[a.student];
        s.total++;
        if (a.status === "present") s.present++;
        else if (a.status === "absent") s.absent++;
        else if (a.status === "duty_leave") s.duty++;
      });
      setReportData(Object.values(studentMap));
      setReportRan(true);
    } catch {
      setReportError("Couldn't load the report. Check your connection and try again.");
    } finally {
      setReportLoading(false);
    }
  };

  const resetReport = () => {
    setReportTA(""); setReportData([]); setReportRan(false); setReportError(""); setOnlyLow(false);
    applyDefaultRange();
  };

  const pctOf = (s) => ({
    actual: s.total > 0 ? (s.present / s.total) * 100 : 0,
    official: s.total > 0 ? ((s.present + s.duty) / s.total) * 100 : 0,
  });

  const rows = reportData.map((s) => ({ ...s, ...pctOf(s) }));
  const lowRows = rows.filter((r) => r.official < 75);
  const avgOfficial = rows.length ? rows.reduce((n, r) => n + r.official, 0) / rows.length : 0;
  const shownRows = onlyLow ? lowRows : rows;

  const handlePrint = () => {
    const subject = subjects.find((s) => String(s.id) === String(reportTA));
    const subjectName = subject ? `${subject.subject_name} — ${classLabel(subject)}` : "";
    const body = rows.map((s, idx) => {
      // Red-flag uses the OFFICIAL percentage (incl. duty leave), so students
      // protected by approved OD are not wrongly flagged.
      const isLow = s.official < 75;
      return `<tr style="color:${isLow ? "#B42318" : "#000"}">
        <td class="c">${idx + 1}</td><td>${s.name}</td><td class="c">${s.roll}</td>
        <td class="c">${s.total}</td><td class="c">${s.present}</td><td class="c">${s.duty}</td>
        <td class="c">${s.present + s.duty}</td><td class="c b">${s.actual.toFixed(2)}%</td>
        <td class="c b" style="color:${isLow ? "#B42318" : "#1F7A4D"}">${s.official.toFixed(2)}%</td>
      </tr>`;
    }).join("");
    const html = `<html><head><title>Attendance Report</title>
    <style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:Arial,sans-serif;font-size:14px;padding:20px}
    .title{text-align:center;font-size:17px;font-weight:700;margin-bottom:4px}
    .sub{text-align:center;font-size:14px;font-weight:600;border:2px solid #000;padding:6px;margin-bottom:10px}
    .info{font-size:13px;margin-bottom:8px}table{width:100%;border-collapse:collapse;font-size:13px}
    th{background:#ECECF0;border:1px solid #ccc;padding:7px;text-align:center;font-weight:700}
    td{border:1px solid #ccc;padding:6px}.c{text-align:center}.b{font-weight:700}
    @media print{@page{size:A4 landscape;margin:10mm}}</style></head>
    <body>
      <div class="title">KB Tech Campus</div>
      <div class="sub">Course-wise Attendance Report</div>
      <p class="info"><b>Subject:</b> ${subjectName} &nbsp;&nbsp; <b>Period:</b> ${fromDate} to ${toDate}</p>
      <table><thead><tr>
        <th>Sl.No</th><th>Student name</th><th>Roll no</th>
        <th>Classes<br>held</th><th>Attended</th><th>On duty</th><th>Attended<br>+ on duty</th>
        <th>Attendance %<br>(actual)</th><th>Official %<br>(incl. OD)</th>
      </tr></thead><tbody>${body}</tbody></table>
      <p style="font-size:12px;color:#666;margin-top:8px">* Red = official attendance below 75% (approved on duty counts as present)</p>
    </body></html>`;
    const win = window.open("", "_blank");
    win.document.write(html);
    win.document.close();
    win.print();
  };

  // ================= RENDER =================
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="kb-at">

              <div className="header-box">
                <h1>Attendance</h1>
                <p>Mark your classes and see who is falling below 75%.</p>
              </div>

              <div className="tabs" role="tablist" aria-label="Attendance">
                <button role="tab" aria-selected={view === "mark"} onClick={() => setView("mark")}>
                  Mark attendance
                </button>
                <button
                  role="tab"
                  aria-selected={view === "report"}
                  onClick={() => { if (view === "mark" && !confirmLeave()) return; setView("report"); }}
                >
                  Attendance report
                </button>
              </div>

              {/* ════════════════ MARK ════════════════ */}
              {view === "mark" && (
                <>
                  {/* ---------- step 1 + 2: date and the day's classes ---------- */}
                  <section className="kb-card kb-at-day">
                    <div className="kb-at-dayhead">
                      <div>
                        <h2>{isToday ? "Today" : dayLabel(selectedDate).split(",")[0]}</h2>
                        <p>{dayLabel(selectedDate)}</p>
                      </div>

                      <div className="kb-at-datenav">
                        <button type="button" className="kb-icon-btn" aria-label="Previous day" onClick={() => changeDate(shiftDay(selectedDate, -1))}>
                          <Icon name="arrowLeft" />
                        </button>
                        <label className="kb-sr" htmlFor="kb-at-date">Date</label>
                        <input
                          id="kb-at-date"
                          type="date"
                          className="kb-at-date"
                          value={selectedDate}
                          max={todayLocal()}
                          onChange={(e) => changeDate(e.target.value)}
                        />
                        <button type="button" className="kb-icon-btn" aria-label="Next day" disabled={selectedDate >= todayLocal()} onClick={() => changeDate(shiftDay(selectedDate, 1))}>
                          <Icon name="arrowRight" />
                        </button>
                        {!isToday && (
                          <button type="button" className="kb-btn kb-btn--sm" onClick={() => changeDate(todayLocal())}>
                            Today
                          </button>
                        )}
                      </div>
                    </div>

                    {!ttLoaded ? (
                      <div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading your timetable…</b></div>
                    ) : blockedReason ? (
                      <div className="kb-at-empty">
                        <span className="kb-at-empty-ico"><Icon name="calendar" /></span>
                        <b>{blockedReason.title}</b>
                        <span>{blockedReason.text} Pick another date.</span>
                      </div>
                    ) : dayClasses.length === 0 ? (
                      <div className="kb-at-empty">
                        <span className="kb-at-empty-ico"><Icon name="calendar" /></span>
                        <b>No classes on your timetable this day</b>
                        <span>It's a free day or a holiday. Use the arrows to pick another date.</span>
                      </div>
                    ) : (
                      <>
                        <p className="kb-at-step">
                          {dayClasses.length} class{dayClasses.length === 1 ? "" : "es"} on your timetable — pick one to take attendance.
                        </p>
                        <div className="kb-at-classes" role="list">
                          {dayClasses.map((c) => {
                            const k = `${c.ta}|${c.hour}`;
                            const active = sel && sel.ta === c.ta && sel.hour === c.hour;
                            const done = !!markedMap[k];
                            return (
                              <button
                                type="button"
                                role="listitem"
                                key={k}
                                className={`kb-at-class${active ? " is-active" : ""}`}
                                aria-pressed={!!active}
                                onClick={() => chooseClass(c)}
                              >
                                <span className="kb-at-class-top">
                                  <span className="kb-at-period">
                                    Period {c.hour}
                                    {c.start && <em>{fmtTime(c.start)} – {fmtTime(c.end)}</em>}
                                  </span>
                                  <span className={`kb-pill ${done ? "ok" : "warn"}`}>{done ? "Marked" : "Not marked"}</span>
                                </span>
                                <span className="kb-at-class-subj">{c.subject?.subject_name || "Class"}</span>
                                <span className="kb-at-class-meta">{classLabel(c.subject)}</span>
                              </button>
                            );
                          })}
                        </div>
                      </>
                    )}
                  </section>

                  {/* ---------- step 3: the register ---------- */}
                  {sel && (
                    <section className="kb-card kb-at-reg">
                      <div className="kb-at-reghead">
                        <div className="kb-grow">
                          <h2>{currentSubject?.subject_name || "Class"}</h2>
                          <p>
                            {classLabel(currentSubject)}
                            {current ? ` · Period ${current.hour}` : ""}
                            {current?.start ? `, ${fmtTime(current.start)}–${fmtTime(current.end)}` : ""}
                          </p>
                        </div>
                        {!loading && (
                          <div className="kb-at-regactions">
                            <span className={`kb-pill ${lockedPast ? "warn" : wasMarked ? "ok" : "warn"}`}>
                              {win?.state === "late_closed"
                                ? "🔒 Late entry closed"
                                : win?.lock?.kind === "tutor_late_entry"
                                  ? "🔒 Entered by class in-charge"
                                  : win?.lock
                                    ? `🔒 Locked by ${win.lock.by}`
                                    : win?.state === "locked"
                                      ? "🔒 Locked"
                                  : win?.state === "open_reason"
                                    ? `Can change until ${fmtD(win.edit_until)}`
                                    : wasMarked
                                      ? "Already marked — you can edit"
                                      : win?.late_entry_deadline && selectedDate < todayLocal()
                                        ? `Not marked yet · mark by ${fmtD(win.late_entry_deadline)}`
                                        : "Not marked yet"}
                            </span>
                            {/* #46 Part 3: close this period early (only when saved, no unsaved changes) */}
                            {wasMarked && !lockedPast && !dirty && students.length > 0 && (
                              <button
                                type="button"
                                className="kb-btn kb-btn--sm"
                                onClick={lockSession}
                                disabled={locking || saving}
                                title="Lock now. Only the class in-charge can change it after this."
                              >
                                <Icon name="lock" />
                                {locking ? "Locking…" : "Lock attendance"}
                              </button>
                            )}
                            {students.length > 0 && !lockedPast && (
                              <button
                                type="button"
                                className="kb-btn kb-btn--primary kb-btn--sm"
                                onClick={saveAttendance}
                                disabled={saving}
                              >
                                <Icon name="check" />
                                {saving ? "Saving…" : "Save"}
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      {loading ? (
                        <div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading students…</b></div>
                      ) : students.length === 0 ? (
                        <div className="kb-at-empty">
                          <span className="kb-at-empty-ico"><Icon name="people" /></span>
                          <b>No students enrolled</b>
                          <span>Nobody is enrolled in this subject yet, so there is nothing to mark.</span>
                        </div>
                      ) : (
                        <>
                          <p className="kb-at-help">
                            {win?.state === "late_closed" ? (
                              <>
                                <b>Late entry is closed.</b> This class had to be marked by {fmtD(win.late_entry_deadline)}.
                                Ask the class in-charge to enter it.
                              </>
                            ) : win?.lock ? (
                              <>
                                <b>This period is locked</b>
                                {win.lock.kind === "tutor_late_entry" ? " — it was entered late by the class in-charge" : ` by ${win.lock.by}`}.
                                Only the class in-charge can correct it now.
                              </>
                            ) : lockedPast ? (
                              <>
                                <b>This period is locked.</b> The correction window ended on {fmtD(win?.edit_until)}.
                                Only the class in-charge can correct it now.
                              </>
                            ) : win?.state === "open_reason" ? (
                              <>
                                You can still change this period until <b>{fmtD(win.edit_until)}</b>. After that it locks
                                and only the class in-charge can correct it.
                              </>
                            ) : (
                              <>Everyone starts as <b>Present</b>. Tap <b>Absent</b> for students who are missing, then save.</>
                            )}
                            {odCount > 0 && <> {odCount} student{odCount === 1 ? " has" : "s have"} approved on-duty and {odCount === 1 ? "is" : "are"} set to <b>On duty</b> automatically.</>}
                          </p>

                          {/* QUICK ENTRY (meeting point 7) */}
                          {!lockedPast && (
                            <div className="kb-at-quick">
                              <label htmlFor="kb-at-quick">Absent today? Type their roll numbers — or just the last digits</label>
                              <div className="kb-at-quick-row">
                                <input
                                  id="kb-at-quick"
                                  inputMode="numeric"
                                  autoComplete="off"
                                  placeholder="e.g. 3 7 12"
                                  value={quick}
                                  onChange={(e) => { setQuick(e.target.value); setQuickMsg(null); }}
                                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); applyAbsentees(); } }}
                                />
                                <button type="button" className="kb-btn kb-btn--primary" onClick={applyAbsentees} disabled={!quick.trim()}>
                                  Mark absent
                                </button>
                              </div>
                              {quickMsg && (
                                <span className={quickMsg.tone === "ok" ? "t-ok" : "t-bad"} role="status">{quickMsg.text}</span>
                              )}
                            </div>
                          )}

                          <div className="kb-at-toolbar">
                            <div className="kb-at-search">
                              <Icon name="search" />
                              <label className="kb-sr" htmlFor="kb-at-q">Find a student</label>
                              <input
                                id="kb-at-q"
                                type="search"
                                placeholder="Find by name or roll no"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                              />
                            </div>

                            <div className="kb-at-filters" role="radiogroup" aria-label="Show">
                              {[
                                ["all", `All ${students.length}`],
                                ["present", `Present ${counts.present}`],
                                ["absent", `Absent ${counts.absent}`],
                                ["duty_leave", `On duty ${counts.duty_leave}`],
                              ].map(([k, label]) => (
                                <button
                                  type="button"
                                  key={k}
                                  role="radio"
                                  aria-checked={filter === k}
                                  className={`kb-at-filter f-${k}`}
                                  onClick={() => setFilter(k)}
                                >
                                  {label}
                                </button>
                              ))}
                            </div>

                            <div className="kb-at-bulk">
                              <button type="button" className="kb-btn kb-btn--sm" onClick={() => markAll("present")} disabled={lockedPast}>All present</button>
                              <button type="button" className="kb-btn kb-btn--sm" onClick={() => markAll("absent")} disabled={lockedPast}>All absent</button>
                            </div>
                          </div>

                          <div className="table-container">
                            <table className="kb-at-table">
                              <thead>
                                <tr>
                                  <th className="c">#</th>
                                  <th>Roll no</th>
                                  <th>Student</th>
                                  <th className="r">Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {visible.length === 0 ? (
                                  <tr><td colSpan={4} className="kb-at-none">No students match. Clear the search or pick “All”.</td></tr>
                                ) : visible.map(({ e, n }) => {
                                  const od = isOd(e.student);
                                  const status = od ? "duty_leave" : attendance[e.student];
                                  return (
                                    <tr
                                      key={e.id}
                                      className={`s-${status || "none"}${!od && !lockedPast ? " is-tap" : ""}`}
                                      onClick={() => { if (!od && !lockedPast) setStatus(e.student, status === "absent" ? "present" : "absent"); }}
                                    >
                                      <td className="c kb-at-n">{n}</td>
                                      <td className="kb-at-roll">{e.student_roll_no || "—"}</td>
                                      <td className="kb-at-name">
                                        {e.student_name}
                                        {!od && isOnLeave(e.student) && (
                                          <span className="kb-pill warn" style={{ marginLeft: 8 }} title="Approved leave - mark Absent unless they attend">
                                            On leave
                                          </span>
                                        )}
                                      </td>
                                      <td className="r">
                                        {od ? (
                                          <span className="kb-at-locked" title="Approved on-duty — can't be changed here">
                                            <Icon name="lock" /> On duty · approved
                                          </span>
                                        ) : (
                                          <div className="kb-at-seg" role="radiogroup" aria-label={`Status for ${e.student_name}`}>
                                            {STATUS.map((st) => (
                                              <button
                                                type="button"
                                                key={st.key}
                                                role="radio"
                                                aria-checked={status === st.key}
                                                className={`st-${st.key}`}
                                                disabled={lockedPast}
                                                onClick={(ev) => { ev.stopPropagation(); setStatus(e.student, st.key); }}
                                              >
                                                <span className="kb-at-long">{st.label}</span>
                                                <span className="kb-at-short">{st.short}</span>
                                              </button>
                                            ))}
                                          </div>
                                        )}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>

                          {/* save bar — end of the list */}
                          <div className="kb-at-savebar">
                            <div className="kb-at-sum">
                              <span className="kb-at-counts">
                                <b>{counts.present}</b> present · <b className="t-bad">{counts.absent}</b> absent · <b>{counts.duty_leave}</b> on duty
                              </span>
                              <span className="kb-at-state">
                                {notice ? (
                                  <span className={notice.tone === "ok" ? "t-ok" : "t-bad"} role={notice.tone === "ok" ? "status" : "alert"}>{notice.text}</span>
                                ) : lockedPast ? (
                                  win?.state === "late_closed"
                                    ? "Late entry closed — ask the class in-charge"
                                    : "Locked — only the class in-charge can correct this period"
                                ) : dirty ? (
                                  "You have unsaved changes"
                                ) : wasMarked ? (
                                  "Saved — no changes"
                                ) : (
                                  "Not saved yet"
                                )}
                              </span>
                            </div>
                            {!lockedPast && (
                            <button
                              type="button"
                              className="kb-btn kb-btn--primary"
                              onClick={saveAttendance}
                              disabled={saving}
                            >
                              <Icon name="check" />
                              {saving ? "Saving…" : wasMarked ? "Save changes" : "Save attendance"}
                            </button>
                            )}
                          </div>
                        </>
                      )}
                    </section>
                  )}
                </>
              )}

              {/* ════════ REASON POP-UP (#46 Part 2) ════════ */}
              {reasonOpen && (
                <div
                  onClick={() => !saving && setReasonOpen(false)}
                  style={{
                    position: "fixed", inset: 0, zIndex: 1100, background: "rgba(15,23,42,.45)",
                    display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
                  }}
                >
                  <div
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="reason-title"
                    onClick={(ev) => ev.stopPropagation()}
                    style={{
                      background: "#fff", borderRadius: 16, maxWidth: 460, width: "100%",
                      padding: "22px 24px 20px", boxShadow: "0 20px 60px rgba(0,0,0,.30)",
                    }}
                  >
                    <h3 id="reason-title" style={{ margin: "0 0 6px", fontSize: 17, color: "#17151F" }}>
                      Reason for the change
                    </h3>
                    <p style={{ margin: "0 0 12px", fontSize: 14.5, color: "#5D5A6B", lineHeight: 1.5 }}>
                      This attendance was saved earlier. You are changing {changedSaved.length} student
                      {changedSaved.length === 1 ? "" : "s"}. The reason is saved in the correction log with your name.
                    </p>
                    <ul style={{ margin: "0 0 12px", paddingLeft: 18, fontSize: 14.5, color: "#17151F", lineHeight: 1.6 }}>
                      {changedSaved.slice(0, 5).map((e) => (
                        <li key={e.student}>
                          {e.student_name}: {STATUS.find((x) => x.key === savedMarks[e.student])?.label} →{" "}
                          <b>{STATUS.find((x) => x.key === attendance[e.student])?.label}</b>
                        </li>
                      ))}
                      {changedSaved.length > 5 && <li>…and {changedSaved.length - 5} more</li>}
                    </ul>
                    <label className="kb-sr" htmlFor="reason-text">Reason</label>
                    <textarea
                      id="reason-text"
                      rows={3}
                      autoFocus
                      value={reasonText}
                      onChange={(e) => setReasonText(e.target.value)}
                      placeholder="e.g. Student came late, was present"
                      style={{
                        width: "100%", resize: "vertical", fontFamily: "inherit", fontSize: 15,
                        border: "1px solid #E7E7EC", borderRadius: 10, padding: "10px 12px", boxSizing: "border-box",
                      }}
                    />
                    <div style={{ fontSize: 13, color: "#85839A", marginTop: 4 }}>At least 10 characters.</div>
                    {notice?.tone === "bad" && (
                      <p role="alert" style={{ margin: "10px 0 0", fontSize: 14.5, fontWeight: 600, color: "#dc2626" }}>{notice.text}</p>
                    )}
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
                      <button type="button" className="kb-btn" onClick={() => setReasonOpen(false)} disabled={saving}>
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="kb-btn kb-btn--primary"
                        onClick={() => doSave(reasonText.trim())}
                        disabled={saving || reasonText.trim().length < 10}
                        style={{ opacity: saving || reasonText.trim().length < 10 ? 0.5 : 1 }}
                      >
                        {saving ? "Saving…" : "Save with reason"}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* ════════════════ REPORT ════════════════ */}
              {view === "report" && (
                <section className="kb-card kb-at-report">
                  <h2 className="kb-at-h2">Course-wise attendance report</h2>

                  <div className="kb-at-rfilters">
                    <label className="kb-at-field kb-at-field--wide">
                      <span>Subject</span>
                      <select value={reportTA} onChange={(e) => { setReportTA(e.target.value); setReportRan(false); }}>
                        <option value="">Choose a subject</option>
                        {subjects.map((s) => (
                          <option key={s.id} value={s.id}>{s.subject_name} — {classLabel(s)}</option>
                        ))}
                      </select>
                    </label>
                    <label className="kb-at-field">
                      <span>From</span>
                      <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
                    </label>
                    <label className="kb-at-field">
                      <span>To</span>
                      <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
                    </label>
                  </div>

                  <div className="kb-at-ractions">
                    <div className="kb-at-ranges">
                      <span>Quick range:</span>
                      <button type="button" className="kb-chip" onClick={() => setRange("week")}>This week</button>
                      <button type="button" className="kb-chip" onClick={() => setRange("month")}>This month</button>
                      {semester?.start_date && (
                        <button type="button" className="kb-chip" onClick={() => setRange("semester")}>Whole semester</button>
                      )}
                    </div>
                    <div className="kb-at-rbtns">
                      {/* Import/Export uses the subject and dates chosen above.
                          Imported rows follow the same window as the register:
                          locked periods and changes that need a reason are refused. */}
                      <ImportExport
                        importer="attendance"
                        label="attendance"
                        matchLabel="roll number"
                        modes={["upsert"]}
                        disabled={!reportTA}
                        options={{ teaching_assignment: reportTA }}
                        exportParams={{ from_date: fromDate, to_date: toDate }}
                        note="One row per student, date and period. Status: P, A or OD. Locked periods can't be changed by import - the class tutor corrects them in My Class."
                        onDone={() => { if (reportRan) fetchReport(); }}
                      />
                      <button type="button" className="kb-btn" onClick={resetReport}>Reset</button>
                      {rows.length > 0 && (
                        <button type="button" className="kb-btn" onClick={handlePrint}>Print</button>
                      )}
                      <button type="button" className="kb-btn kb-btn--primary" onClick={fetchReport} disabled={reportLoading}>
                        <Icon name="search" />
                        {reportLoading ? "Loading…" : "Show report"}
                      </button>
                    </div>
                  </div>

                  {reportError && <div className="kb-at-error" role="alert">{reportError}</div>}

                  <div className="kb-at-legend">
                    <div><b>Attendance %</b><span>Classes the student actually attended.</span></div>
                    <div><b>Official %</b><span>Counts approved on-duty as present — this is the one used for the 75% rule.</span></div>
                  </div>

                  {reportLoading ? (
                    <div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading report…</b></div>
                  ) : !reportRan ? (
                    <div className="kb-at-empty">
                      <span className="kb-at-empty-ico"><Icon name="chart" /></span>
                      <b>Pick a subject and dates</b>
                      <span>Then press Show report to see each student's attendance.</span>
                    </div>
                  ) : rows.length === 0 ? (
                    <div className="kb-at-empty">
                      <span className="kb-at-empty-ico"><Icon name="chart" /></span>
                      <b>No attendance recorded in this range</b>
                      <span>Try a wider date range, or mark attendance for this subject first.</span>
                    </div>
                  ) : (
                    <>
                      <div className="kb-at-kpis">
                        <div className="kb-at-kpi"><span>Students</span><b>{rows.length}</b></div>
                        <div className="kb-at-kpi">
                          <span>Class average (official)</span>
                          <b className={avgOfficial < 75 ? "t-bad" : "t-ok"}>{avgOfficial.toFixed(1)}%</b>
                        </div>
                        <div className="kb-at-kpi">
                          <span>Below 75%</span>
                          <b className={lowRows.length ? "t-bad" : "t-ok"}>{lowRows.length}</b>
                        </div>
                      </div>

                      <label className="kb-at-check">
                        <input type="checkbox" checked={onlyLow} onChange={(e) => setOnlyLow(e.target.checked)} />
                        Show only students below 75%
                      </label>

                      <div className="table-container">
                        <table className="kb-at-table kb-at-rtable">
                          <thead>
                            <tr>
                              <th className="c">#</th>
                              <th>Roll no</th>
                              <th>Student</th>
                              <th className="c">Classes held</th>
                              <th className="c">Attended</th>
                              <th className="c">On duty</th>
                              <th className="c">Attendance %</th>
                              <th>Official %</th>
                            </tr>
                          </thead>
                          <tbody>
                            {shownRows.length === 0 ? (
                              <tr><td colSpan={8} className="kb-at-none">Everyone is at or above 75%.</td></tr>
                            ) : shownRows.map((s, idx) => {
                              const low = s.official < 75;
                              return (
                                <tr key={`${s.roll}-${idx}`} className={low ? "s-low" : ""}>
                                  <td className="c kb-at-n">{idx + 1}</td>
                                  <td className="kb-at-roll">{s.roll}</td>
                                  <td className="kb-at-name">{s.name}</td>
                                  <td className="c">{s.total}</td>
                                  <td className="c">{s.present}</td>
                                  <td className="c">{s.duty}</td>
                                  <td className="c">{s.actual.toFixed(1)}%</td>
                                  <td>
                                    <div className="kb-at-pct">
                                      <b className={low ? "t-bad" : "t-ok"}>{s.official.toFixed(1)}%</b>
                                      <span className="kb-at-bar"><i style={{ width: `${Math.min(s.official, 100)}%` }} className={low ? "bad" : "ok"} /></span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      <p className="kb-at-foot">Rows in red are below 75% official attendance (approved on-duty counts as present).</p>
                    </>
                  )}
                </section>
              )}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
