// ============================================================
// AttendanceStudent — a student's own attendance + on-duty requests
// ============================================================
// Opens on what a student needs to know: am I above 75% in every
// subject, and how many classes can I miss / must I attend?
//
//   /student/attendance              → By subject (default) / Day by day
//   /student/attendance?tab=onduty   → On-duty requests (own sidebar link)
//   /student/attendance?tab=leave    → Leave requests (WAVE 1, StudentLeave.jsx)
//
// One fetch of the semester's records feeds the summary, the subject
// list and the day grid, so the three can never disagree. Picking a
// custom date range refetches for that range; the summary at the top
// always stays "semester so far".
// ============================================================

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import Icon from "../../components/Icon";
import API from "../../api";
import StudentLeave from "./StudentLeave";     // WAVE 1: student leave
import "../../App.css";

const DOT_LABEL = { present: "P", absent: "A", duty_leave: "OD" };

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};
const niceDate = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

// local YYYY-MM-DD (toISOString is UTC and is a day behind in IST before 5:30 am)
const toKey = (d) => {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().split("T")[0];
};
const todayLocal = () => toKey(new Date());

const pick = (res) => res?.data?.results || res?.data || [];

// ── On Duty: form categories (must match backend ODRequest.Category) ──
const OD_CATEGORIES = [
  { value: "paper_presentation", label: "Paper presentation" },
  { value: "seminar", label: "Seminar / conference" },
  { value: "placement", label: "Placement drive" },
  { value: "sports", label: "Sports" },
  { value: "nss_ncc", label: "NSS / NCC" },
  { value: "other", label: "Other" },
];

// ── On Duty: status pill from status + stage ──
const odStatusBadge = (r) => {
  if (r.status === "approved") return { tone: "ok", text: "Approved" };
  if (r.status === "rejected") return { tone: "bad", text: "Rejected" };
  if (r.status === "cancelled") return { tone: "", text: "Cancelled" };
  if (r.stage === "awaiting_hod") return { tone: "warn", text: "Awaiting HOD" };
  return { tone: "warn", text: "Awaiting class in-charge" };
};

// ── the 75% rule, in plain numbers ──
// official % counts approved on-duty as present.
// above 75%: how many more classes can be missed and still stay at 75%
// below 75%: how many classes in a row must be attended to get back to 75%
const RULE = 0.75;
const guidance = (attended, total) => {
  if (!total) return null;
  if (attended / total >= RULE) {
    const canMiss = Math.floor(attended / RULE - total);
    return { ok: true, n: canMiss };
  }
  const need = Math.ceil((RULE * total - attended) / (1 - RULE));
  return { ok: false, n: need };
};
const guidanceText = (g, short = false) => {
  if (!g) return "";
  if (g.ok) {
    if (g.n === 0) return short ? "On the line" : "You're exactly at the limit — don't miss the next class";
    return short ? `Can miss ${g.n}` : `You can miss ${g.n} more class${g.n === 1 ? "" : "es"} and stay above 75%`;
  }
  return short ? `Attend next ${g.n}` : `Attend the next ${g.n} class${g.n === 1 ? "" : "es"} in a row to get back to 75%`;
};

const tally = (records) => {
  let present = 0, absent = 0, duty = 0;
  records.forEach((a) => {
    if (a.status === "present") present++;
    else if (a.status === "duty_leave") duty++;
    else if (a.status === "absent") absent++;
  });
  const total = present + absent + duty;
  return { present, absent, duty, total, pct: total ? ((present + duty) / total) * 100 : 0 };
};

export default function AttendanceStudent() {
  const [open, setOpen] = useState(false);
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const section = tabParam === "onduty" ? "onduty" : tabParam === "leave" ? "leave" : "attendance";

  // WAVE 1: dates of approved leave -> an absence on those days shows "L" (excused)
  const [leaveDates, setLeaveDates] = useState(() => new Set());
  useEffect(() => {
    API.get("users/leave/").then((res) => {
      const dates = new Set();
      (res.data?.results || res.data || []).filter((r) => r.status === "approved").forEach((r) => {
        for (let d = new Date(r.from_date); d <= new Date(r.to_date); d.setDate(d.getDate() + 1)) {
          dates.add(d.toISOString().slice(0, 10));
        }
      });
      setLeaveDates(dates);
    }).catch(() => {});
  }, []);
  const [view, setView] = useState("subjects"); // subjects | days

  // class period numbers from admin's timetable (e.g. [1,2,3,4,5,6,7,8])
  const [hours, setHours] = useState([]);

  // semester so far — feeds the summary
  const [semStart, setSemStart] = useState("");
  const [semRecords, setSemRecords] = useState([]);
  const [semLoaded, setSemLoaded] = useState(false);

  // current range — feeds By subject and Day by day
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [dailyRaw, setDailyRaw] = useState([]);
  const [rangeLoading, setRangeLoading] = useState(true);
  const [rangeError, setRangeError] = useState("");
  const [showRange, setShowRange] = useState(false);
  const [rf, setRf] = useState(""); // dates being typed in "Change dates"
  const [rt, setRt] = useState("");

  // ── On Duty state ──
  const [odCategory, setOdCategory] = useState("paper_presentation");
  const [odFrom, setOdFrom] = useState("");
  const [odTo, setOdTo] = useState("");
  const [odReason, setOdReason] = useState("");
  const [odProof, setOdProof] = useState(null);
  const [odList, setOdList] = useState([]);
  const [odLoading, setOdLoading] = useState(false);
  const [odSubmitting, setOdSubmitting] = useState(false);
  const [odNotice, setOdNotice] = useState(null); // { tone, text }

  // ── periods admin created (class periods only) ──
  useEffect(() => {
    API.get("/timeslots/")
      .then((res) => {
        const classHours = pick(res)
          .filter((s) => !s.is_break) // breaks aren't marked for attendance
          .map((s) => Number(s.period_no))
          .filter((n) => !Number.isNaN(n))
          .sort((a, b) => a - b);
        setHours([...new Set(classHours)]);
      })
      .catch(() => setHours([])); // fall back below, derived from the data
  }, []);

  // ── one load: semester start → today ──
  useEffect(() => {
    const load = async () => {
      let start = "";
      try {
        const d = pick(await API.get("/semester/"));
        const sem = Array.isArray(d) ? d[0] : d;
        if (sem?.start_date) start = sem.start_date;
      } catch { /* no semester → all of the student's records */ }

      const today = todayLocal();
      const url = start ? `/attendance/?from_date=${start}&to_date=${today}` : "/attendance/";
      try {
        const data = pick(await API.get(url));
        setSemStart(start);
        setSemRecords(data);
        setFromDate(start);
        setToDate(today);
        setDailyRaw(data);
      } catch {
        setRangeError("Couldn't load your attendance. Check your connection and refresh the page.");
      } finally {
        setSemLoaded(true);
        setRangeLoading(false);
      }
    };
    load();
  }, []);

  const loadRange = async (f, t) => {
    setRangeError("");
    if (!f || !t) return setRangeError("Choose both dates.");
    if (f > t) return setRangeError("The From date is after the To date.");
    setRangeLoading(true);
    try {
      setDailyRaw(pick(await API.get(`/attendance/?from_date=${f}&to_date=${t}`)));
      setFromDate(f);
      setToDate(t);
    } catch {
      setRangeError("Couldn't load that range. Try again.");
    } finally {
      setRangeLoading(false);
    }
  };

  const resetRange = () => {
    setRangeError("");
    setShowRange(false);
    setFromDate(semStart);
    setToDate(todayLocal());
    setDailyRaw(semRecords);
  };

  const quickRange = (kind) => {
    const today = todayLocal();
    const d = new Date(`${today}T00:00:00`);
    if (kind === "week") {
      const mon = new Date(d);
      mon.setDate(d.getDate() - ((d.getDay() + 6) % 7));
      loadRange(toKey(mon), today);
    } else if (kind === "month") {
      loadRange(toKey(new Date(d.getFullYear(), d.getMonth(), 1)), today);
    }
  };

  const isSemesterRange = fromDate === semStart && toDate === todayLocal() && dailyRaw === semRecords;

  // ── derived views (all from the same records) ──
  const summary = useMemo(() => tally(semRecords), [semRecords]);
  const summaryG = guidance(summary.present + summary.duty, summary.total);

  const courseReport = useMemo(() => {
    const m = {};
    dailyRaw.forEach((a) => {
      const key = a.teaching_assignment;
      if (!m[key]) m[key] = { subject: a.subject_name, course: a.course_name, total: 0, present: 0, duty: 0 };
      m[key].total++;
      if (a.status === "present") m[key].present++;
      else if (a.status === "duty_leave") m[key].duty++;
    });
    // lowest attendance first — those are the ones that need attention
    return Object.values(m).sort(
      (x, y) => (x.present + x.duty) / (x.total || 1) - (y.present + y.duty) / (y.total || 1)
    );
  }, [dailyRaw]);

  const dailyData = useMemo(() => {
    const grouped = {};
    dailyRaw.forEach((a) => {
      if (!grouped[a.date]) grouped[a.date] = {};
      grouped[a.date][a.hour] = a.status;
    });
    return Object.keys(grouped).sort().map((date) => ({ date, hours: grouped[date] }));
  }, [dailyRaw]);

  // If periods haven't loaded (or none exist), fall back to the hours
  // actually present in the fetched attendance so the table still shows.
  const hoursFor = (records) => {
    if (hours.length) return hours;
    const found = [...new Set(records.map((a) => Number(a.hour)).filter((n) => !Number.isNaN(n)))]
      .sort((a, b) => a - b);
    return found.length ? found : [1, 2, 3, 4, 5, 6, 7, 8];
  };
  const dailyHours = hoursFor(dailyRaw);
  const lowSubjects = courseReport.filter((c) => (c.present + c.duty) / (c.total || 1) < RULE);

  // the print layouts read these names
  const cwFrom = fromDate;
  const cwTo = toDate;

  // ── On Duty ──
  const loadOd = async () => {
    setOdLoading(true);
    try {
      setOdList(pick(await API.get("users/od/")));
    } catch {
      setOdNotice({ tone: "bad", text: "Couldn't load your requests. Refresh the page to try again." });
    } finally {
      setOdLoading(false);
    }
  };
  useEffect(() => { loadOd(); }, []);

  const submitOd = async () => {
    setOdNotice(null);
    if (!odFrom || !odTo) return setOdNotice({ tone: "bad", text: "Choose both the From and To dates." });
    if (odTo < odFrom) return setOdNotice({ tone: "bad", text: "The To date can't be before the From date." });
    if (!odReason.trim()) return setOdNotice({ tone: "bad", text: "Write a short reason for the request." });
    setOdSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("from_date", odFrom);
      fd.append("to_date", odTo);
      fd.append("category", odCategory);
      fd.append("reason", odReason.trim());
      if (odProof) fd.append("proof", odProof);
      // no Content-Type header — axios sets multipart boundary from FormData
      await API.post("users/od/create/", fd);
      setOdFrom(""); setOdTo(""); setOdReason("");
      setOdProof(null); setOdCategory("paper_presentation");
      const fileEl = document.getElementById("od-proof-input");
      if (fileEl) fileEl.value = "";
      await loadOd();
      setOdNotice({ tone: "ok", text: "Request sent to your class in-charge. You'll see its status below." });
    } catch (err) {
      const d = err?.response?.data;
      setOdNotice({ tone: "bad", text: d?.detail || d?.non_field_errors?.[0] || "The request wasn't sent. Try again." });
    } finally {
      setOdSubmitting(false);
    }
  };

  const cancelOd = async (id) => {
    if (!window.confirm("Cancel this on-duty request?")) return;
    setOdNotice(null);
    try {
      await API.post(`users/od/${id}/cancel/`);
      await loadOd();
      setOdNotice({ tone: "ok", text: "Request cancelled." });
    } catch (err) {
      setOdNotice({ tone: "bad", text: err?.response?.data?.detail || "Couldn't cancel the request." });
    }
  };

  const handlePrintDaily = () => {
    const user = JSON.parse(localStorage.getItem("user") || "{}");
    const printHours = hoursFor(dailyRaw);
    const hourHeaders = printHours.map(h => `<th>Hour ${h}</th>`).join("");
    const rows = dailyData.map((row) => {
      const hasAny = Object.keys(row.hours).length > 0;
      if (!hasAny) return `<tr><td class="date-col" style="color:#dc2626">${fmtDate(row.date)}</td><td colspan="${printHours.length}" style="text-align:center;color:#dc2626;font-style:italic">Holiday / No Classes</td></tr>`;
      const cells = printHours.map(h => {
        const s = row.hours[h];
        if (s === "present")    return `<td class="p">P</td>`;
        if (s === "absent")     return `<td class="a">A</td>`;
        if (s === "duty_leave") return `<td class="dl">DL</td>`;
        return `<td class="dash">—</td>`;
      }).join("");
      return `<tr><td class="date-col">${fmtDate(row.date)}</td>${cells}</tr>`;
    }).join("");
    const html = `<html><head><title>Daily Attendance</title>
    <style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:Arial,sans-serif;font-size:14px;padding:30px}
    .title{text-align:center;font-size:16px;font-weight:bold;border:2px solid #000;padding:8px;border-bottom:none}
    .info-table{width:100%;border-collapse:collapse;border:2px solid #000;border-top:none}
    .info-table td{border:1px solid #000;padding:7px 10px}
    .rule{text-align:center;border:1px solid #000;border-top:none;padding:7px;margin-bottom:12px}
    table.att{width:100%;border-collapse:collapse}
    table.att th{border:1px solid #ccc;padding:7px 5px;background:#f5f5f5;text-align:center;font-weight:bold}
    table.att td{border:1px solid #ccc;padding:6px 5px;text-align:center}
    .date-col{text-align:left!important;padding-left:10px!important;font-weight:600}
    .p{color:#16a34a;font-weight:bold}.a{color:#dc2626;font-weight:bold}.dl{color:#d97706;font-weight:bold}.dash{color:#ccc}
    @media print{@page{size:A4 landscape;margin:15mm}}</style></head>
    <body>
      <div class="title">Daily Attendance</div>
      <table class="info-table"><tr>
        <td><b>Student Name:</b> ${user.username || "-"}</td>
        <td><b>Roll No:</b> ${user.roll_number || "-"}</td>
        <td><b>Course:</b> ${dailyRaw[0]?.course_name || "-"}</td>
        <td><b>Year:</b> ${dailyRaw[0]?.year_number || "-"}</td>
        <td><b>Semester:</b> ${dailyRaw[0]?.semester || "-"}</td>
      </tr></table>
      <div class="rule">Using attendance rule from <b>${fmtDate(fromDate)}</b> to <b>${fmtDate(toDate)}</b></div>
      <table class="att"><thead><tr><th class="date-col">Dates</th>${hourHeaders}</tr></thead><tbody>${rows}</tbody></table>
      <p style="font-size:13px;color:#555;margin-top:10px">P = Present &nbsp; A = Absent &nbsp; DL = Duty Leave</p>
    </body></html>`;
    const win = window.open("", "_blank"); win.document.write(html); win.document.close(); win.print();
  };

  const handlePrintCourseWise = () => {
    const user = JSON.parse(localStorage.getItem("user") || "{}");
    const rows = courseReport.map((c, idx) => {
      const ahPct = c.total > 0 ? ((c.present / c.total) * 100).toFixed(2) : "0.00";
      const dlPct = c.total > 0 ? (((c.present + c.duty) / c.total) * 100).toFixed(2) : "0.00";
      const isLow = parseFloat(dlPct) < 75;
      return `<tr style="color:${isLow ? "#dc2626" : "#000"}">
        <td style="border:1px solid #ccc;padding:6px;text-align:center">${idx + 1}</td>
        <td style="border:1px solid #ccc;padding:8px 6px"><b>${c.subject}</b>${c.course ? ` (${c.course})` : ""}</td>
        <td style="border:1px solid #ccc;padding:6px;text-align:center">${c.total}</td>
        <td style="border:1px solid #ccc;padding:6px;text-align:center">${c.present}</td>
        <td style="border:1px solid #ccc;padding:6px;text-align:center">${c.duty}</td>
        <td style="border:1px solid #ccc;padding:6px;text-align:center">${c.present + c.duty}</td>
        <td style="border:1px solid #ccc;padding:6px;text-align:center;${parseFloat(ahPct) < 75 ? "color:#dc2626;font-weight:700" : "color:#16a34a;font-weight:700"}">${ahPct}%</td>
        <td style="border:1px solid #ccc;padding:6px;text-align:center;${isLow ? "color:#dc2626;font-weight:700" : "color:#16a34a;font-weight:700"}">${dlPct}%</td>
      </tr>`;
    }).join("");
    const html = `<html><head><title>Course Wise Attendance</title>
    <style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:Arial,sans-serif;font-size:14px;padding:24px}
    .college{text-align:center;font-size:18px;font-weight:bold;margin-bottom:6px}
    .rtitle{text-align:center;font-size:15px;font-weight:bold;border:2px solid #000;padding:8px;margin-bottom:12px}
    table{width:100%;border-collapse:collapse}th{background:#ECECF0;border:1px solid #ccc;padding:7px;text-align:center;font-weight:bold}
    @media print{@page{size:A4 landscape;margin:12mm}}</style></head>
    <body>
      <div class="college">KB Tech Campus</div>
      <div class="rtitle">Course Wise Attendance Report</div>
      <p style="font-size:14px;margin-bottom:10px"><b>Student:</b> ${user.username || "-"} &nbsp; <b>Roll No:</b> ${user.roll_number || "-"} &nbsp; <b>Date Range:</b> ${fmtDate(cwFrom)} to ${fmtDate(cwTo)}</p>
      <table><thead><tr><th>Sl.No</th><th>Course Name</th><th>TH</th><th>AH</th><th>DL</th><th>AH+DL</th><th>AH%</th><th>AH+DL%</th></tr></thead><tbody>${rows}</tbody></table>
      <p style="font-size:12px;color:#888;margin-top:8px">* Red = below 75% (with duty leave) | TH: Total Hours | AH: Attended | DL: Duty Leave</p>
    </body></html>`;
    const win = window.open("", "_blank"); win.document.write(html); win.document.close(); win.print();
  };

  // ================= RENDER =================
  const pctTone = summary.pct >= 75 ? "t-ok" : summary.pct >= 65 ? "t-warn" : "t-bad";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="kb-at">

              {section === "leave" ? (
                <StudentLeave />
              ) : section === "attendance" ? (
                <>
                  <div className="header-box">
                    <h1>My attendance</h1>
                    <p>Your attendance this semester, and what you need to stay above 75%.</p>
                  </div>

                  {/* ---------- summary ---------- */}
                  {!semLoaded ? (
                    <section className="kb-card"><div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading your attendance…</b></div></section>
                  ) : summary.total === 0 ? (
                    <section className="kb-card">
                      <div className="kb-at-empty">
                        <span className="kb-at-empty-ico"><Icon name="calendar" /></span>
                        <b>No attendance recorded yet</b>
                        <span>Once your teachers start marking classes this semester, your attendance appears here.</span>
                      </div>
                    </section>
                  ) : (
                    <section className="kb-card kb-sa-hero">
                      <div className="kb-sa-big">
                        <span>Overall attendance</span>
                        <b className={pctTone}>{summary.pct.toFixed(1)}%</b>
                        <em>{semStart ? `Since ${fmtDate(semStart)}` : "All recorded classes"}</em>
                      </div>
                      <div className="kb-sa-mid">
                        <div className={`kb-sa-verdict ${summaryG?.ok ? "ok" : "bad"}`}>
                          <Icon name={summaryG?.ok ? "check" : "alert"} />
                          <span>{guidanceText(summaryG)}</span>
                        </div>
                        {lowSubjects.length > 0 && isSemesterRange && (
                          <p className="kb-sa-note">
                            {lowSubjects.length} subject{lowSubjects.length === 1 ? " is" : "s are"} below 75% — see the list below.
                          </p>
                        )}
                        <div className="kb-bar kb-sa-bar">
                          <i style={{ width: `${Math.min(summary.pct, 100)}%`, background: summary.pct >= 75 ? "var(--ok)" : "var(--bad)" }} />
                          <span className="kb-sa-mark" title="75%" />
                        </div>
                      </div>
                      <div className="kb-sa-stats">
                        <div><b>{summary.present}</b><span>Present</span></div>
                        <div><b className="t-bad">{summary.absent}</b><span>Absent</span></div>
                        <div><b>{summary.duty}</b><span>On duty</span></div>
                        <div><b>{summary.total}</b><span>Classes</span></div>
                      </div>
                    </section>
                  )}

                  {summary.total > 0 && (
                    <section className="kb-card">
                      <div className="kb-sa-head">
                        <div className="tabs" role="tablist" aria-label="View">
                          <button role="tab" aria-selected={view === "subjects"} onClick={() => setView("subjects")}>By subject</button>
                          <button role="tab" aria-selected={view === "days"} onClick={() => setView("days")}>Day by day</button>
                        </div>
                        <div className="kb-sa-range">
                          <span className="kb-muted">
                            {isSemesterRange ? "Whole semester" : `${fmtDate(fromDate)} – ${fmtDate(toDate)}`}
                          </span>
                          <button type="button" className="kb-btn kb-btn--sm" onClick={() => { setRf(fromDate); setRt(toDate); setShowRange((s) => !s); }}>
                            <Icon name="calendar" /> Change dates
                          </button>
                          {!isSemesterRange && (
                            <button type="button" className="kb-btn kb-btn--sm" onClick={resetRange}>Whole semester</button>
                          )}
                          <button
                            type="button"
                            className="kb-btn kb-btn--sm"
                            onClick={view === "subjects" ? handlePrintCourseWise : handlePrintDaily}
                          >
                            Print
                          </button>
                        </div>
                      </div>

                      {showRange && (
                        <div className="kb-sa-rangebox">
                          <label className="kb-at-field">
                            <span>From</span>
                            <input type="date" value={rf} onChange={(e) => setRf(e.target.value)} />
                          </label>
                          <label className="kb-at-field">
                            <span>To</span>
                            <input type="date" value={rt} onChange={(e) => setRt(e.target.value)} />
                          </label>
                          <button
                            type="button"
                            className="kb-btn kb-btn--primary"
                            onClick={() => loadRange(rf, rt)}
                          >
                            Show
                          </button>
                          <div className="kb-at-ranges">
                            <button type="button" className="kb-chip" onClick={() => quickRange("week")}>This week</button>
                            <button type="button" className="kb-chip" onClick={() => quickRange("month")}>This month</button>
                          </div>
                        </div>
                      )}

                      {rangeError && <div className="kb-at-error" role="alert">{rangeError}</div>}

                      {rangeLoading ? (
                        <div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading…</b></div>
                      ) : dailyRaw.length === 0 ? (
                        <div className="kb-at-empty">
                          <span className="kb-at-empty-ico"><Icon name="calendar" /></span>
                          <b>No classes recorded in these dates</b>
                          <span>Pick a wider range, or go back to the whole semester.</span>
                        </div>
                      ) : view === "subjects" ? (
                        /* ---------- by subject ---------- */
                        <div className="kb-sa-subjects">
                          {courseReport.map((c, i) => {
                            const attended = c.present + c.duty;
                            const pct = c.total ? (attended / c.total) * 100 : 0;
                            const g = guidance(attended, c.total);
                            const low = pct < 75;
                            return (
                              <div key={i} className={`kb-sa-subj${low ? " is-low" : ""}`}>
                                <div className="kb-sa-subj-main">
                                  <div className="kb-sa-subj-name">{c.subject}</div>
                                  <div className="kb-sa-subj-meta">
                                    Attended {c.present} of {c.total}{c.duty ? ` · ${c.duty} on duty` : ""}
                                  </div>
                                </div>
                                <div className="kb-sa-subj-bar">
                                  <span className="kb-at-bar">
                                    <i className={low ? "bad" : "ok"} style={{ width: `${Math.min(pct, 100)}%` }} />
                                  </span>
                                  <b className={low ? "t-bad" : "t-ok"}>{pct.toFixed(1)}%</b>
                                </div>
                                <span className={`kb-pill ${g?.ok ? (g.n === 0 ? "warn" : "ok") : "bad"}`}>{guidanceText(g, true)}</span>
                              </div>
                            );
                          })}
                          <p className="kb-at-foot">
                            Percentages count approved on-duty as present — the same figure used for the 75% rule.
                            Subjects with the lowest attendance are listed first.
                          </p>
                        </div>
                      ) : (
                        /* ---------- day by day ---------- */
                        <>
                          <div className="table-container">
                            <table className="kb-at-table kb-sa-days">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  {dailyHours.map((h) => <th key={h} className="c">P{h}</th>)}
                                </tr>
                              </thead>
                              <tbody>
                                {[...dailyData].reverse().map((row) => {
                                  const hasAny = Object.keys(row.hours).length > 0;
                                  return (
                                    <tr key={row.date}>
                                      <td className="kb-sa-date">{niceDate(row.date)}</td>
                                      {!hasAny ? (
                                        <td colSpan={dailyHours.length} className="c kb-muted">Holiday / no classes</td>
                                      ) : dailyHours.map((h) => {
                                        const st = row.hours[h];
                                        return (
                                          <td key={h} className="c">
                                            {st && st === "absent" && leaveDates.has(row.date) ? (
                                              <span className="kb-sa-dot d-leave" title="On leave (approved) - still counts as absent">L</span>
                                            ) : st ? <span className={`kb-sa-dot d-${st}`} title={st === "duty_leave" ? "On duty" : st}>{DOT_LABEL[st]}</span>
                                              : <span className="kb-muted">—</span>}
                                          </td>
                                        );
                                      })}
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                          <div className="kb-sa-legend">
                            <span><span className="kb-sa-dot d-present">P</span> Present</span>
                            <span><span className="kb-sa-dot d-absent">A</span> Absent</span>
                            <span><span className="kb-sa-dot d-duty_leave">OD</span> On duty</span>
                            <span className="kb-muted">Newest first · P1, P2… are periods</span>
                          </div>
                        </>
                      )}
                    </section>
                  )}
                </>
              ) : (
                /* ════════════════ ON DUTY ════════════════ */
                <>
                  <div className="header-box">
                    <h1>On-duty requests</h1>
                    <p>Ask for on-duty when you're away for college work. Once approved, those classes count as present.</p>
                  </div>

                  <section className="kb-card">
                    <h2 className="kb-at-h2">New request</h2>
                    <div className="kb-sa-odgrid">
                      <label className="kb-at-field">
                        <span>From</span>
                        <input type="date" value={odFrom} onChange={(e) => setOdFrom(e.target.value)} />
                      </label>
                      <label className="kb-at-field">
                        <span>To</span>
                        <input type="date" value={odTo} onChange={(e) => setOdTo(e.target.value)} />
                      </label>
                      <label className="kb-at-field">
                        <span>What for</span>
                        <select value={odCategory} onChange={(e) => setOdCategory(e.target.value)}>
                          {OD_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                        </select>
                      </label>
                    </div>
                    <label className="kb-at-field kb-sa-full">
                      <span>Reason</span>
                      <textarea
                        value={odReason}
                        onChange={(e) => setOdReason(e.target.value)}
                        rows={3}
                        placeholder="Presenting a paper at the national symposium, SSN College"
                      />
                    </label>
                    <label className="kb-at-field kb-sa-full">
                      <span>Proof (optional)</span>
                      <input id="od-proof-input" type="file" onChange={(e) => setOdProof(e.target.files?.[0] || null)} />
                    </label>

                    {odNotice && (
                      <div className={odNotice.tone === "ok" ? "kb-sa-ok" : "kb-at-error"} role={odNotice.tone === "ok" ? "status" : "alert"}>
                        {odNotice.text}
                      </div>
                    )}

                    <div className="kb-sa-actions">
                      <span className="kb-muted">Your class in-charge reviews it first, then your HOD.</span>
                      <button type="button" className="kb-btn kb-btn--primary" onClick={submitOd} disabled={odSubmitting}>
                        {odSubmitting ? "Sending…" : "Send request"}
                      </button>
                    </div>
                  </section>

                  <section className="kb-card">
                    <h2 className="kb-at-h2">Your requests</h2>
                    {odLoading ? (
                      <div className="kb-at-empty"><div className="kb-at-spinner" /><b>Loading…</b></div>
                    ) : odList.length === 0 ? (
                      <div className="kb-at-empty">
                        <span className="kb-at-empty-ico"><Icon name="briefcase" /></span>
                        <b>No requests yet</b>
                        <span>Requests you send appear here with their status.</span>
                      </div>
                    ) : (
                      <div className="kb-sa-odlist">
                        {odList.map((r) => {
                          const badge = odStatusBadge(r);
                          return (
                            <div key={r.id} className="kb-sa-od">
                              <div className="kb-sa-od-top">
                                <div className="kb-grow">
                                  <div className="kb-sa-subj-name">{r.category_label}</div>
                                  <div className="kb-sa-subj-meta">{fmtDate(r.from_date)} → {fmtDate(r.to_date)}</div>
                                </div>
                                <span className={`kb-pill ${badge.tone}`}>{badge.text}</span>
                                {r.status === "pending" && (
                                  <button type="button" className="kb-btn kb-btn--sm" onClick={() => cancelOd(r.id)}>Cancel</button>
                                )}
                              </div>
                              {r.reason && <p className="kb-sa-od-reason">{r.reason}</p>}
                              {r.tutor_remark && <p className="kb-sa-od-remark"><b>Class in-charge:</b> {r.tutor_remark}</p>}
                              {r.hod_remark && <p className="kb-sa-od-remark"><b>HOD:</b> {r.hod_remark}</p>}
                              {r.status === "approved" && <p className="kb-sa-od-ok">Counted as on duty in your attendance.</p>}
                              {r.proof && <a href={r.proof} target="_blank" rel="noreferrer" className="kb-sa-od-proof">View proof</a>}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </section>
                </>
              )}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
