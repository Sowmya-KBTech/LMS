import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";
import HubHome, { HomePanel, HomeRow } from "../../components/HubHome";
import "../../App.css";

// attendance health color: green ≥75, amber 60–74, red below
const attColor = (p) => (p >= 75 ? "#10b981" : p >= 60 ? "#f59e0b" : "#ef4444");

// SVG donut ring (no library). Shows pct in the center.
function Ring({ pct, size = 116, stroke = 11 }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(pct, 100) / 100) * circ;
  const color = attColor(pct);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#ECECF0" strokeWidth={stroke} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: size * 0.26, fontWeight: 700, fill: "#17151F", fontVariantNumeric: "tabular-nums" }}>
        {pct}%
      </text>
    </svg>
  );
}

// "09:00:00" -> "9:00 AM"  (same formatter the timetable uses)
const fmtTime = (t) => {
  if (!t) return "";
  const [h, m] = String(t).split(":");
  let hour = parseInt(h, 10);
  const ampm = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${hour}:${m} ${ampm}`;
};

// "HH:MM[:SS]" -> minutes since midnight
const toMin = (t) => {
  const [h, m] = String(t).split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
};

// local YYYY-MM-DD (matches the holiday date keys)
const dayKey = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function StudentHome() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const [courses, setCourses] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [lectures, setLectures] = useState([]);
  const [quizzes, setQuizzes] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [quizAttempts, setQuizAttempts] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [attendance, setAttendance] = useState([]);   // per-subject: {subject, pct, present, total}
  const [attLoaded, setAttLoaded] = useState(false);

  // timetable (for "Today's classes")
  const [slots, setSlots] = useState([]);
  const [entries, setEntries] = useState([]);
  const [holidayName, setHolidayName] = useState(null);
  const [ttLoaded, setTtLoaded] = useState(false);

  useEffect(() => { loadData(); loadAttendance(); loadTimetable(); }, []);

  const loadData = async () => {
    try {
      const [enrollRes, assignRes, lectureRes, quizRes, submissionRes, attemptRes, notificationRes] =
        await Promise.all([
          API.get("/enrollments/"),
          API.get("/assignments/"),
          API.get("/lectures/"),
          API.get("/quizzes/"),
          API.get("/submissions/"),
          API.get("/quiz-attempts/"),
          API.get("/notifications/?unread=true"),
        ]);

      const pick = (r) => r.data?.results || r.data || [];
      const enrollments = pick(enrollRes);
      const allAssignments = pick(assignRes);
      const allLectures = pick(lectureRes);
      const allQuizzes = pick(quizRes);
      const allSubmissions = pick(submissionRes);
      const allAttempts = pick(attemptRes);

      const myEnrollments = enrollments.filter((e) => (e.student?.id || e.student) === user.id);
      setCourses(myEnrollments);

      const teachingIds = myEnrollments.map((e) => e.teaching_assignment?.id || e.teaching_assignment);
      const inMine = (x) => teachingIds.includes(x.teaching_assignment?.id || x.teaching_assignment);

      setAssignments(allAssignments.filter(inMine));
      setLectures(allLectures.filter(inMine));
      setQuizzes(allQuizzes.filter(inMine));
      setSubmissions(allSubmissions.filter((s) => (s.student?.id || s.student) === user.id));
      setQuizAttempts(allAttempts.filter((a) => (a.student?.id || a.student) === user.id));
      setNotifications(pick(notificationRes));
    } catch (err) {
      console.log("Student dashboard error:", err);
    }
  };

  // ── Attendance: semester dates → records in range → group by subject ──
  const loadAttendance = async () => {
    try {
      const semRes = await API.get("/semester/");
      const sem = (semRes.data || [])[0];
      if (!sem || !sem.start_date || !sem.end_date) {
        setAttLoaded(true);
        return;
      }

      const res = await API.get(
        `/attendance/?from_date=${sem.start_date}&to_date=${sem.end_date}`
      );
      const data = res.data?.results || res.data || [];

      const map = {};
      data.forEach((a) => {
        const key = a.teaching_assignment;
        if (!map[key]) map[key] = { subject: a.subject_name || "Subject", present: 0, total: 0 };
        map[key].total++;
        if (a.status === "present" || a.status === "duty_leave") map[key].present++;
      });

      const rows = Object.values(map)
        .map((s) => ({ ...s, pct: s.total ? Math.round((s.present / s.total) * 100) : 0 }))
        .sort((a, b) => a.pct - b.pct);

      setAttendance(rows);
      setAttLoaded(true);
    } catch (err) {
      console.log("Attendance load error:", err);
      setAttLoaded(true);
    }
  };

  // ── Timetable: same endpoints the Timetable page uses ──
  // /timeslots/  → [{ id, period_no, start_time, end_time, label, is_break }]
  // /timetable/  → [{ day_of_week, time_slot, subject, teacher_name }]  (student sees own class)
  // /holidays/   → [{ date, name }]
  const loadTimetable = async () => {
    try {
      const [slotRes, ttRes, holRes] = await Promise.all([
        API.get("/timeslots/"),
        API.get("/timetable/"),
        API.get("/holidays/"),
      ]);
      setSlots(slotRes.data || []);
      setEntries(ttRes.data || []);

      const k = dayKey(new Date());
      const hol = (holRes.data || []).find((h) => h.date === k);
      setHolidayName(hol ? hol.name : null);
      setTtLoaded(true);
    } catch (err) {
      console.log("Timetable load error:", err);
      setTtLoaded(true);
    }
  };

  const pendingQuizzes = Math.max(quizzes.length - quizAttempts.length, 0);
  const fmt = (iso) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : "");

  const attTotals = attendance.reduce(
    (acc, s) => ({ present: acc.present + s.present, total: acc.total + s.total }),
    { present: 0, total: 0 }
  );
  const overallAtt = attTotals.total ? Math.round((attTotals.present / attTotals.total) * 100) : 0;

  // ── build today's classes from the weekly pattern ──
  const now = new Date();
  const isSunday = now.getDay() === 0;
  const wdToday = now.getDay() - 1; // Mon=0 .. Sat=5  (Sunday = -1)
  const nowMin = now.getHours() * 60 + now.getMinutes();

  const ttLookup = {};
  entries.forEach((e) => { ttLookup[`${e.day_of_week}_${e.time_slot}`] = e; });

  const allToday = (isSunday || holidayName)
    ? []
    : slots
        .filter((s) => !s.is_break)
        .map((s) => {
          const e = ttLookup[`${wdToday}_${s.id}`];
          if (!e) return null;
          let status = "upcoming";
          if (toMin(s.end_time) <= nowMin) status = "done";
          else if (toMin(s.start_time) <= nowMin) status = "now";
          return {
            id: s.id,
            period_no: s.period_no,
            start: s.start_time,
            end: s.end_time,
            subject: e.subject,
            teacher: e.teacher_name,
            status,
          };
        })
        .filter(Boolean);

  // Show only a 3-class window: the one just finished, the current one, and the next.
  let pivot = allToday.findIndex((c) => c.status === "now");
  if (pivot === -1) pivot = allToday.findIndex((c) => c.status === "upcoming");
  if (pivot === -1) pivot = allToday.length - 1;
  const winStart = Math.min(Math.max(pivot - 1, 0), Math.max(allToday.length - 3, 0));
  const todaysClasses = allToday.slice(winStart, winStart + 3);

  // Real activity timeline: merge submissions + quiz attempts, newest first
  const feed = [
    ...submissions.map((s) => ({
      icon: "file", tint: "#6366f1", t: s.submitted_at,
      title: "Submitted an assignment", sub: s.assignment_title || s.subject_name || "Assignment",
    })),
    ...quizAttempts.map((q) => ({
      icon: "quiz", tint: "#8b5cf6", t: q.submitted_at,
      title: "Completed a quiz", sub: `${q.quiz_title || "Quiz"} · scored ${q.score}`,
    })),
  ].sort((a, b) => new Date(b.t) - new Date(a.t)).slice(0, 6);

  const nowClass = allToday.find((c) => c.status === "now");
  const nextClass = allToday.find((c) => c.status === "upcoming");
  const dayLine = !ttLoaded
    ? "Loading today's classes…"
    : holidayName
    ? `Holiday today — ${holidayName}`
    : isSunday
    ? "No classes today"
    : nowClass
    ? `Now: ${nowClass.subject || "Class"} till ${fmtTime(nowClass.end)}`
    : nextClass
    ? `Next: ${nextClass.subject || "Class"} at ${fmtTime(nextClass.start)}`
    : "No more classes today";

  const attTone = !attLoaded || attendance.length === 0 ? "" : overallAtt >= 75 ? "t-ok" : "t-bad";

  return (
    <HubHome
      title={`Hi ${user?.username || "there"}`}
      sub={dayLine}
      action={{ label: "My attendance", to: "/student/attendance", icon: "userCheck" }}
      stats={[
        {
          label: "Attendance",
          value: !attLoaded ? "…" : attendance.length ? `${overallAtt}%` : "—",
          valueTone: attTone,
          hint: attendance.length ? `${attTotals.present}/${attTotals.total} hours present` : "Nothing recorded yet",
          icon: "userCheck", tone: "men", to: "/student/attendance",
        },
        { label: "My subjects", value: courses.length, hint: "This semester", icon: "book", tone: "dep", to: "/student/courses" },
        { label: "Assignments", value: `${submissions.length}/${assignments.length}`, hint: "Submitted", icon: "clipboard", tone: "exm", module: "learning", to: "/student-progress" },
        {
          label: "Quizzes", value: `${quizAttempts.length}/${quizzes.length}`,
          hint: pendingQuizzes ? `${pendingQuizzes} waiting for you` : "All done",
          icon: "check", tone: "plc", module: "learning", to: "/student-progress",
        },
      ]}
    >
        {/* today's classes from the real timetable */}
        <HomePanel span={2} title="Today's classes" action="Full timetable" onAction={() => navigate("/timetable")}>
          {!ttLoaded ? (
            <div className="kb-empty-line">Loading…</div>
          ) : isSunday || holidayName ? (
            <HomeRow
              pill="Today"
              title={holidayName ? `Holiday — ${holidayName}` : "No classes today"}
              sub={holidayName ? "The college is closed" : "Enjoy your Sunday"}
            />
          ) : todaysClasses.length === 0 ? (
            <HomeRow pill="Today" title="No classes scheduled" sub="Free day on your timetable" />
          ) : (
            todaysClasses.map((c) => {
              const isNow = c.status === "now";
              const isDone = c.status === "done";
              return (
                <HomeRow
                  key={c.id}
                  dim={isDone}
                  pill={fmtTime(c.start)}
                  pillTone={isNow ? "info" : ""}
                  title={c.subject || "Activity"}
                  sub={`${c.teacher ? `${c.teacher} · ` : ""}Period ${c.period_no}${isNow ? " · now" : ""}`}
                >
                  {isNow && <span className="kb-pill info">Now</span>}
                  {isDone && <span className="kb-pill">Done</span>}
                </HomeRow>
              );
            })
          )}
        </HomePanel>

        {/* attendance — overall ring + per-subject */}
        <HomePanel title="Attendance" action="Details" onAction={() => navigate("/student/attendance")}>
          {!attLoaded ? (
            <div className="kb-empty-line">Loading attendance…</div>
          ) : attendance.length === 0 ? (
            <div className="kb-empty-line">No attendance recorded yet this semester.</div>
          ) : (
            <div className="kb-att">
              <div className="kb-att-overall">
                <Ring pct={overallAtt} size={112} stroke={11} />
                <div className="kb-row-s">{attTotals.present}/{attTotals.total} hours present</div>
              </div>
              <div className="kb-att-list">
                {attendance.slice(0, 5).map((s, i) => (
                  <div key={i} className="kb-att-item">
                    <div className="kb-att-top">
                      <span className="kb-att-name">{s.subject}</span>
                      <b style={{ color: attColor(s.pct) }}>{s.pct}%</b>
                    </div>
                    <div className="kb-bar"><i style={{ width: `${s.pct}%`, background: attColor(s.pct) }} /></div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </HomePanel>

        <HomePanel span={2} title="Recent activity" action="My progress" onAction={() => navigate("/student-progress")}>
          {feed.length === 0 ? (
            <div className="kb-empty-line">Nothing yet. Submit an assignment or take a quiz to get started.</div>
          ) : (
            feed.map((a, i) => (
              <HomeRow key={i} title={a.title} sub={a.sub}>
                <span className="kb-row-s">{fmt(a.t)}</span>
              </HomeRow>
            ))
          )}
        </HomePanel>

        <HomePanel title="Recent notifications" action="See all" onAction={() => navigate("/notifications")}>
          {notifications.length === 0 ? (
            <div className="kb-empty-line">You're all caught up.</div>
          ) : (
            notifications.slice(0, 5).map((n) => (
              <HomeRow
                key={n.id}
                title={n.title}
                sub={n.created_at ? new Date(n.created_at).toLocaleString("en-IN") : ""}
              />
            ))
          )}
        </HomePanel>
    </HubHome>
  );
}
