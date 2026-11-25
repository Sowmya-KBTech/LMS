import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";
import HubHome, { HomePanel, HomeRow, QuickActions } from "../../components/HubHome";
import { greeting } from "../../components/hubs";
import "../../App.css";

// pull an id out of a field that might be a bare id or a nested object
const idOf = (v) => (v && typeof v === "object" ? v.id : v);

export default function TeacherHome() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [stats, setStats] = useState({
    subjects: 0, students: 0, assignments: 0, lectures: 0, quizzes: 0, materials: 0,
  });
  const [rows, setRows] = useState([]);     // [{ id, title, subject, submitted, total }]
  const [quizRows, setQuizRows] = useState([]); // [{ id, title, subject, done, total }]
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    API.get("/teacher-dashboard/")
      .then((res) => setStats((s) => ({ ...s, ...res.data })))
      .catch((err) => console.log("Error fetching dashboard:", err));

    loadSubmissionProgress();
  }, []);

  const loadSubmissionProgress = async () => {
    try {
      const [aRes, sRes, eRes, qRes, qaRes] = await Promise.all([
        API.get("/assignments/"),
        API.get("/submissions/"),
        API.get("/enrollments/"),
        API.get("/quizzes/"),
        API.get("/quiz-attempts/"),
      ]);
      const pick = (r) => r.data?.results || r.data || [];
      const assignments = pick(aRes);
      const submissions = pick(sRes);
      const enrollments = pick(eRes);
      const quizzes = pick(qRes);
      const attempts = pick(qaRes);

      // class size per teaching_assignment (count of enrolled students)
      const classSize = {};
      enrollments.forEach((e) => {
        const taId = idOf(e.teaching_assignment);
        if (taId != null) classSize[taId] = (classSize[taId] || 0) + 1;
      });

      // submissions count per assignment id
      const subCount = {};
      submissions.forEach((s) => {
        const aId = idOf(s.assignment);
        if (aId != null) subCount[aId] = (subCount[aId] || 0) + 1;
      });

      const subjectOf = (x) =>
        x.subject_name ||
        x.teaching_assignment?.subject?.name ||
        x.teaching_assignment?.subject_name ||
        x.course_name ||
        "";

      const built = assignments.map((a) => {
        const taId = idOf(a.teaching_assignment);
        const total = classSize[taId] || 0;
        const submitted = subCount[a.id] || 0;
        return { id: a.id, title: a.title || a.name || "Assignment", subject: subjectOf(a), submitted, total };
      });
      built.sort((x, y) => (y.total - y.submitted) - (x.total - x.submitted));
      setRows(built);

      // quiz attempts count per quiz id
      const attCount = {};
      attempts.forEach((qa) => {
        const qId = idOf(qa.quiz);
        if (qId != null) attCount[qId] = (attCount[qId] || 0) + 1;
      });

      const builtQuizzes = quizzes.map((q) => {
        const taId = idOf(q.teaching_assignment);
        const total = classSize[taId] || 0;
        const done = attCount[q.id] || 0;
        return { id: q.id, title: q.title || q.name || "Quiz", subject: subjectOf(q), done, total };
      });
      builtQuizzes.sort((x, y) => (y.total - y.done) - (x.total - x.done));
      setQuizRows(builtQuizzes);

      setLoaded(true);
    } catch (err) {
      console.log("Submission progress error:", err);
      setLoaded(true);
    }
  };

  // only the ones still needing attention (someone hasn't submitted / attempted)
  const pendingRows = rows.filter((r) => r.total - r.submitted > 0);
  const pendingQuizRows = quizRows.filter((r) => r.total - r.done > 0);
  const tone = (pct) => (pct >= 80 ? "ok" : pct >= 50 ? "warn" : "bad");

  const actions = [
    // /courses is the ADMIN course editor — teachers use their own subject list
    { title: "My subjects", sub: `${stats.subjects} subject${stats.subjects === 1 ? "" : "s"} this term`, to: "/teacher/courses", icon: "book", tone: "dep" },
    { title: "Take attendance", sub: "Mark today's periods", to: "/teacher/attendance", icon: "userCheck", tone: "men" },
    { title: "Class progress", sub: "Attendance, assignments, quizzes", to: "/teacher-progress", icon: "chart", tone: "plc" },
    { title: "Messages", sub: "Reply to parents", to: "/teacher/messages", icon: "chat", tone: "brand" },
  ];

  return (
    <HubHome
      title={`${greeting()}, ${user?.username || "Teacher"}`}
      sub="Your subjects, students and activity at a glance."
      action={{ label: "Take attendance", to: "/teacher/attendance", icon: "userCheck" }}
      stats={[
        { label: "My subjects", value: stats.subjects, hint: "Teaching this term", icon: "book", tone: "dep", to: "/teacher/courses" },
        { label: "My students", value: stats.students, hint: "Across all classes", icon: "people", tone: "men", to: "/teacher-progress" },
        { label: "Assignments", value: stats.assignments, hint: "Created", icon: "clipboard", tone: "exm", module: "learning", to: "/teacher/courses" },
        { label: "Quizzes", value: stats.quizzes, hint: "Created", icon: "check", tone: "plc", module: "learning", to: "/teacher/courses" },
      ]}
    >
      <HomePanel title="Quick actions" span={2}>
        <QuickActions items={actions} />
      </HomePanel>

      <HomePanel title="Waiting on your students" sub="Work not yet handed in" action="Progress" onAction={() => navigate("/teacher-progress")}>
        {!loaded ? (
          <div className="kb-empty-line">Loading…</div>
        ) : pendingRows.length === 0 && pendingQuizRows.length === 0 ? (
          <div className="kb-soft-box">
            <b>Everything is in</b>
            <span>No assignment or quiz is waiting on anyone.</span>
          </div>
        ) : (
          <>
            {pendingRows.slice(0, 4).map((r) => {
              const pct = r.total ? Math.round((r.submitted / r.total) * 100) : 0;
              return (
                <HomeRow key={`a${r.id}`} title={r.title} sub={`${r.subject ? `${r.subject} · ` : ""}${r.total - r.submitted} not submitted`}>
                  <span className={`kb-pill ${tone(pct)}`}>{r.submitted}/{r.total}</span>
                </HomeRow>
              );
            })}
            {pendingQuizRows.slice(0, 4).map((r) => {
              const pct = r.total ? Math.round((r.done / r.total) * 100) : 0;
              return (
                <HomeRow key={`q${r.id}`} title={r.title} sub={`Quiz${r.subject ? ` · ${r.subject}` : ""} · ${r.total - r.done} not attempted`}>
                  <span className={`kb-pill ${tone(pct)}`}>{r.done}/{r.total}</span>
                </HomeRow>
              );
            })}
          </>
        )}
      </HomePanel>
    </HubHome>
  );
}
