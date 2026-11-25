import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";
import HubHome, { HomePanel, HomeRow } from "../../components/HubHome";
import "../../App.css";

export default function ParentDashboard() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const [data, setData] = useState(null);
  const [children, setChildren] = useState([]);
  const [grades, setGrades] = useState([]);
  const [quizGrades, setQuizGrades] = useState([]);
  const [activeChild, setActiveChild] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = async () => {
    try {
      setLoading(true);
      const dashRes = await API.get("/parent/dashboard/");
      setData(dashRes.data);
      setChildren(dashRes.data?.children || []);

      const subRes = await API.get("/submissions/");
      setGrades(subRes.data?.results || subRes.data || []);

      const quizRes = await API.get("/quiz-attempts/");
      setQuizGrades(quizRes.data?.results || quizRes.data || []);
    } catch (err) {
      console.log("Parent dashboard fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 15000);
    return () => clearInterval(t);
  }, []);

  const matchChild = (record) => {
    if (activeChild === null) return true;
    const child = children.find((c) => c.id === activeChild);
    if (!child) return true;
    return (
      (record.student?.id || record.student) === activeChild ||
      record.student_name === child.username
    );
  };

  const attendanceEntries = Object.entries(data?.attendance_per_child || {});
  const visibleAttendance = activeChild === null
    ? attendanceEntries
    : attendanceEntries.filter(([name]) => {
        const child = children.find((c) => c.id === activeChild);
        return child && name === child.username;
      });

  const recentGrades = grades.filter(matchChild).slice(0, 6);
  const recentQuizzes = quizGrades.filter(matchChild).slice(0, 6);

  const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString() : "");
  const statusChip = (s = "") => {
    const v = s.toLowerCase();
    if (v === "evaluated" || v === "graded") return "ok";
    if (v === "pending" || v === "late") return "warn";
    return "muted";
  };

  const fees = Number(data?.pending_fees || 0);
  const att = Number(data?.avg_attendance || 0);
  const pendAssign = data?.pending_assignments ?? 0;

  const pillFor = (s = "") => {
    const t = statusChip(s);
    return t === "muted" ? "" : t;
  };

  return (
    <HubHome
      title={`Welcome back, ${user?.username || "Parent"}`}
      sub="How your child is doing, at a glance."
      action={{ label: "Pay fees", to: "/parent/fees", icon: "rupee" }}
      stats={data ? [
        { label: "Attendance", value: `${att}%`, valueTone: att >= 75 ? "t-ok" : "t-bad", hint: "Average across subjects", icon: "userCheck", tone: "men", to: "/parent/attendance" },
        { label: "Assignments", value: pendAssign, hint: pendAssign ? "Still to submit" : "Nothing pending", icon: "clipboard", tone: "exm", to: "/parent/assignments" },
        { label: "Fees pending", value: `₹${fees.toLocaleString("en-IN")}`, valueTone: fees > 0 ? "t-bad" : "t-ok", hint: fees > 0 ? "Pay online any time" : "All paid", icon: "rupee", tone: "dep", to: "/parent/fees" },
        { label: "Recent grades", module: "learning", value: recentGrades.length, hint: "Published marks", icon: "star", tone: "plc", to: "/parent/grades" },
      ] : []}
    >
      {children.length > 1 && (
        <div className="kb-seg-row span-3">
          <div className="kb-seg" role="radiogroup" aria-label="Show child">
            <button type="button" role="radio" aria-checked={activeChild === null} onClick={() => setActiveChild(null)}>
              All children
            </button>
            {children.map((c) => (
              <button
                type="button"
                role="radio"
                key={c.id}
                aria-checked={activeChild === c.id}
                onClick={() => setActiveChild(c.id)}
              >
                {c.username}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && !data ? (
        <div className="kb-card kb-empty-line span-3">Loading dashboard…</div>
      ) : (
        <>
            <HomePanel span={2} title="Recent grades" action="All grades" onAction={() => navigate("/parent/grades")}>
              {recentGrades.length === 0 ? (
                <div className="kb-empty-line">No grades published yet.</div>
              ) : (
                recentGrades.map((s) => (
                  <HomeRow
                    key={s.id}
                    title={s.subject_name}
                    sub={s.student_name}
                  >
                    <b className="kb-num">
                      {s.marks !== null && s.marks !== undefined ? `${s.marks}/${s.total_marks}` : "—"}
                    </b>
                    <span className={`kb-pill ${pillFor(s.status)}`}>{s.status}</span>
                  </HomeRow>
                ))
              )}
            </HomePanel>

            <HomePanel title="Attendance" action="Details" onAction={() => navigate("/parent/attendance")}>
              {visibleAttendance.length === 0 ? (
                <div className="kb-empty-line">No attendance recorded.</div>
              ) : (
                <div className="kb-att-list">
                  {visibleAttendance.map(([name, a]) => {
                    const pct = a.percentage || 0;
                    const color = pct >= 85 ? "#1F7A4D" : pct >= 75 ? "#8A4B0A" : "#B42318";
                    return (
                      <div className="kb-att-item" key={name}>
                        <div className="kb-att-top">
                          <span className="kb-att-name">{name}</span>
                          <b style={{ color }}>{pct}%</b>
                        </div>
                        <div className="kb-bar"><i style={{ width: `${pct}%`, background: color }} /></div>
                      </div>
                    );
                  })}
                </div>
              )}
            </HomePanel>

            <HomePanel span={2} title="Recent quiz results">
              {recentQuizzes.length === 0 ? (
                <div className="kb-empty-line">No quiz attempts yet.</div>
              ) : (
                recentQuizzes.map((q) => (
                  <HomeRow key={q.id} title={q.quiz_title} sub={`${q.student_name} · ${fmtTime(q.submitted_at)}`}>
                    <b className="kb-num">{q.score}</b>
                  </HomeRow>
                ))
              )}
            </HomePanel>

            <HomePanel title="Recent notifications" action="See all" onAction={() => navigate("/notifications")}>
              {(data?.recent_notifications || []).length === 0 ? (
                <div className="kb-empty-line">You're all caught up.</div>
              ) : (
                data.recent_notifications.map((n) => (
                  <HomeRow key={n.id} title={n.title} sub={fmtTime(n.created_at)} dim={n.is_read} />
                ))
              )}
            </HomePanel>
        </>
      )}
    </HubHome>
  );
}
