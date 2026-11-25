import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";
import "../../styles/TimetableView.css";

// 7-day week: Monday .. Sunday. (offset = days from Monday)
//
// The weekend columns stay on the grid on purpose. A student looking at their
// week should see the whole week, with Saturday and Sunday marked as days the
// college does not teach - not silently cropped, which reads as "the timetable
// is missing something".
const DAY_OFFSETS = [0, 1, 2, 3, 4, 5, 6];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Indexed by JavaScript's getDay(), where 0 is Sunday. This array must keep all
// seven entries and their order - dropping "Sat" would shift every index and
// mislabel the whole week.
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const fmt = (t) => {
  if (!t) return "";
  const [h, m] = String(t).split(":");
  let hour = parseInt(h, 10);
  const ampm = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${hour}:${m} ${ampm}`;
};

const toDate = (s) => {
  const [y, m, d] = String(s).split("-").map(Number);
  return new Date(y, m - 1, d);
};
const key = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d, n) => {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
};
const mondayOf = (d) => {
  const x = new Date(d);
  const day = x.getDay(); // 0=Sun..6=Sat
  const diff = day === 0 ? -6 : 1 - day;
  x.setDate(x.getDate() + diff);
  x.setHours(0, 0, 0, 0);
  return x;
};
const sameDay = (a, b) => key(a) === key(b);
const fmtDate = (d) => `${MONTHS[d.getMonth()]} ${d.getDate()}`;

// what the popup says when there is no topic to show
const NO_TOPIC_MESSAGE = {
  no_plan: "Your teacher hasn't written the plan for this subject yet.",
  not_approved: "The plan is written but still waiting for HOD approval.",
  no_topic: "No topic planned for this class.",
  no_class: "No class scheduled here.",
  error: "Couldn't load the topic. Please try again.",
};

export default function TimetableView() {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const isTeacher = (user.role || "").toLowerCase() === "teacher";

  const [open, setOpen] = useState(false);
  const [slots, setSlots] = useState([]);
  const [entries, setEntries] = useState([]);
  const [holidays, setHolidays] = useState({}); // { 'YYYY-MM-DD': name }
  const [semester, setSemester] = useState(null); // { start, end, name }
  const [loading, setLoading] = useState(true);

  // the topic popup: null = closed
  const [topic, setTopic] = useState(null);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const [weekStart, setWeekStart] = useState(mondayOf(today));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = async () => {
    try {
      const [slotRes, semRes, holRes] = await Promise.all([
        API.get("/timeslots/"),
        API.get("/semester/"),
        API.get("/holidays/"),
      ]);

      setSlots(slotRes.data || []);

      const active = (semRes.data || [])[0];
      if (active) {
        const sem = {
          start: toDate(active.start_date),
          end: toDate(active.end_date),
          name: active.name,
        };
        setSemester(sem);
        let ws = mondayOf(today);
        if (ws < mondayOf(sem.start)) ws = mondayOf(sem.start);
        if (ws > sem.end) ws = mondayOf(sem.end);
        setWeekStart(ws);
      }

      const hmap = {};
      (holRes.data || []).forEach((h) => {
        hmap[h.date] = h.name;
      });
      setHolidays(hmap);

      const url = isTeacher ? "/timetable/?scope=teacher" : "/timetable/";
      const res = await API.get(url);
      setEntries(res.data || []);
    } catch (err) {
      console.error("Timetable load error:", err);
    } finally {
      setLoading(false);
    }
  };

  // ---------- topic popup (students only) ----------
  // The cell already knows its exact DATE (the grid is week-based) and its PERIOD.
  // That pair is all the backend needs: it derives the subject from the student's
  // own enrolments, so the browser can't ask about a class it isn't in.
  const openTopic = async (d, slot, entry) => {
    if (isTeacher) return;

    setTopic({
      loading: true,
      subject: entry.subject,
      teacher: entry.teacher_name,
      period_no: slot.period_no,
      date: key(d),
    });

    try {
      const res = await API.get(
        `teaching-plans/student_topic/?date=${key(d)}&period=${slot.period_no}`
      );
      setTopic(res.data);
    } catch {
      setTopic({
        found: false,
        reason: "error",
        subject: entry.subject,
        teacher: entry.teacher_name,
        period_no: slot.period_no,
      });
    }
  };

  // weekly pattern lookup: "weekday_timeslot" -> entry  (weekday 0=Mon..4=Fri)
  const lookup = {};
  entries.forEach((e) => {
    lookup[`${e.day_of_week}_${e.time_slot}`] = e;
  });

  // 7 dated columns (Mon..Sun) for the current week
  const cols = DAY_OFFSETS.map((off) => addDays(weekStart, off));

  // is a date within the semester window?
  const inSemester = (d) =>
    !semester || (d >= semester.start && d <= semester.end);

  const prevDisabled =
    semester && addDays(weekStart, -7) < mondayOf(semester.start);
  const nextDisabled = semester && addDays(weekStart, 7) > semester.end;

  const moveWeek = (n) => {
    if (n < 0 && prevDisabled) return;
    if (n > 0 && nextDisabled) return;
    setWeekStart(addDays(weekStart, n * 7));
  };

  const goToday = () => {
    let ws = mondayOf(today);
    if (semester) {
      if (ws < mondayOf(semester.start)) ws = mondayOf(semester.start);
      if (ws > semester.end) ws = mondayOf(semester.end);
    }
    setWeekStart(ws);
  };

  // decide what a given date is: weekend | holiday | outside | normal
  //
  // Saturday joins Sunday here. The college teaches Monday to Friday, and
  // TimetableEntry.day_of_week no longer accepts a sixth day, so a Saturday
  // column of empty dashes told students "nothing scheduled yet" when the
  // truth is "there are never classes then".
  const dayKind = (d) => {
    const wd = d.getDay();                         // 0=Sun .. 6=Sat
    if (wd === 0 || wd === 6) return "weekend";    // no teaching at the weekend
    if (!inSemester(d)) return "outside";          // before start / after end
    if (holidays[key(d)]) return "holiday";        // admin-added holiday
    return "normal";
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="tv">
            <header className="tv-head">
              <div>
                <h1>{isTeacher ? "My Schedule" : "My Timetable"}</h1>
                <p>
                  {semester
                    ? `${semester.name} · ${fmtDate(semester.start)} – ${fmtDate(
                        semester.end
                      )}, ${semester.end.getFullYear()}`
                    : isTeacher
                    ? "Your weekly classes across all departments."
                    : "Your weekly class timetable."}
                </p>
              </div>
            </header>

            {loading ? (
              <div className="tv-empty">Loading…</div>
            ) : entries.length === 0 ? (
              <div className="tv-empty">No timetable has been published yet.</div>
            ) : (
              <>
                <div className="tv-wknav">
                  <button onClick={() => moveWeek(-1)} disabled={prevDisabled}>‹</button>
                  <span className="tv-wklabel">
                    Week of {fmtDate(cols[0])} – {fmtDate(cols[6])}
                  </span>
                  <button onClick={() => moveWeek(1)} disabled={nextDisabled}>›</button>
                  <button className="tv-today" onClick={goToday}>Today</button>
                </div>

                {!isTeacher && (
                  <p className="tv-tip">Tap any class to see what your teacher is covering that day.</p>
                )}

                <div className="tv-wrap">
                  <table className="tv-table">
                    <thead>
                      <tr>
                        <th className="tv-corner">Period</th>
                        {cols.map((d) => {
                          const kind = dayKind(d);
                          const cls =
                            "tv-col" +
                            (sameDay(d, today) ? " is-today" : "") +
                            (kind !== "normal" ? " is-off" : "");
                          const label =
                            kind === "weekend"
                              ? "No classes"
                              : kind === "holiday"
                              ? holidays[key(d)]
                              : kind === "outside"
                              ? ""
                              : "";
                          return (
                            <th key={key(d)} className={cls}>
                              <div className="tv-dow">{DOW[d.getDay()]}</div>
                              <div className="tv-date">{fmtDate(d)}</div>
                              {label && <span className="tv-holname">{label}</span>}
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {slots.map((slot) =>
                        slot.is_break ? (
                          <tr key={slot.id} className="tv-brkrow">
                            <td className="tv-per">
                              {slot.label || "Break"}
                              <span>{fmt(slot.start_time)}–{fmt(slot.end_time)}</span>
                            </td>
                            <td colSpan={cols.length}>{slot.label || "Break"}</td>
                          </tr>
                        ) : (
                          <tr key={slot.id}>
                            <td className="tv-per">
                              P{slot.period_no}
                              <span>{fmt(slot.start_time)}–{fmt(slot.end_time)}</span>
                            </td>
                            {cols.map((d) => {
                              const isToday = sameDay(d, today);
                              const kind = dayKind(d);
                              const cellCls =
                                "tv-cell" +
                                (isToday ? " today-col" : "") +
                                (kind !== "normal" ? " off-col" : "");

                              // Weekend or admin holiday -> a labelled band, so
                              // the reason the cell is empty is on the screen.
                              if (kind === "weekend" || kind === "holiday") {
                                return (
                                  <td key={key(d)} className={cellCls}>
                                    <span className="tv-hol">
                                      {kind === "weekend" ? "No classes" : "Holiday"}
                                    </span>
                                  </td>
                                );
                              }

                              // outside the semester window -> blank
                              if (kind === "outside") {
                                return <td key={key(d)} className={cellCls}></td>;
                              }

                              // normal teaching day -> project the weekly pattern
                              const wd = d.getDay() - 1; // Mon=0 .. Fri=4
                              const e = lookup[`${wd}_${slot.id}`];
                              return (
                                <td key={key(d)} className={cellCls}>
                                  {e ? (
                                    <div
                                      className={
                                        "tv-blk" +
                                        (isTeacher ? " teacher" : " tv-blk--click")
                                      }
                                      onClick={() => openTopic(d, slot, e)}
                                      role={isTeacher ? undefined : "button"}
                                      tabIndex={isTeacher ? undefined : 0}
                                      onKeyDown={(ev) => {
                                        if (!isTeacher && (ev.key === "Enter" || ev.key === " ")) {
                                          ev.preventDefault();
                                          openTopic(d, slot, e);
                                        }
                                      }}
                                    >
                                      {isTeacher ? (
                                        <>
                                          <span className="tv-cls">
                                            {e.course} · Year {e.year_number}
                                          </span>
                                          <span className="tv-sub">{e.subject}</span>
                                        </>
                                      ) : (
                                        <>
                                          <strong>{e.subject}</strong>
                                          <span>{e.teacher_name}</span>
                                        </>
                                      )}
                                    </div>
                                  ) : (
                                    <span className="tv-free">—</span>
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ========== TOPIC POPUP (students only) ========== */}
      {topic && (
        <div className="tv-modal-overlay" onClick={() => setTopic(null)}>
          <div className="tv-modal" onClick={(ev) => ev.stopPropagation()}>
            <div className="tv-modal-head">
              <div className="tv-modal-head-info">
                <div className="tv-modal-subject">{topic.subject}</div>
                <div className="tv-modal-meta">
                  {topic.teacher}
                  {topic.period_no ? ` · Period ${topic.period_no}` : ""}
                  {topic.date ? ` · ${fmtDate(toDate(topic.date))}` : ""}
                </div>
              </div>
              {topic.is_today && <span className="tv-modal-today">Today</span>}
            </div>

            <div className="tv-modal-body">
              {topic.loading ? (
                <div className="tv-modal-note">Loading…</div>
              ) : topic.found ? (
                <>
                  <div className="tv-modal-label">Topic for this class</div>
                  <div className="tv-modal-topic">{topic.topic}</div>
                  <div className="tv-modal-foot">
                    From the teaching plan approved by your HOD.
                  </div>
                </>
              ) : (
                <div className="tv-modal-note">
                  {NO_TOPIC_MESSAGE[topic.reason] || NO_TOPIC_MESSAGE.error}
                </div>
              )}
            </div>

            <div className="tv-modal-actions">
              <button className="tv-modal-close" onClick={() => setTopic(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}