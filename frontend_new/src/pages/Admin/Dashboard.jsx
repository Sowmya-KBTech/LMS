import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";
import HubHome, { HomePanel, HomeRow, QuickActions } from "../../components/HubHome";
import { greeting } from "../../components/hubs";
import "../../App.css";

export default function Dashboard() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    total_users: 0, total_students: 0, total_teachers: 0,
    total_parents: 0, total_courses: 0, total_enrollments: 0,
  });

  useEffect(() => {
    API.get("admin-dashboard/")
      .then((res) => setStats((s) => ({ ...s, ...(res.data || {}) })))
      .catch((err) => console.error("Dashboard error:", err))
      .finally(() => setLoading(false));
  }, []);

  const v = (n) => (loading ? "…" : n);

  // every path here is a real <Route> in App.jsx
  const actions = [
    { title: "Add a user", sub: "Student, teacher, parent or staff", to: "/users", icon: "people", tone: "dep" },
    { title: "Collect a fee", sub: "Take a payment at the counter", to: "/admin/fees", icon: "rupee", tone: "men" },
    { title: "Post an announcement", sub: "To everyone or one group", to: "/announcements", icon: "megaphone", tone: "brand" },
    { title: "Build a timetable", sub: "Periods, rooms and class grids", to: "/timetable-builder", icon: "table", tone: "plc" },
  ];

  return (
    <HubHome
      title={`${greeting()}, ${user?.username || "Admin"}`}
      sub="Your campus at a glance."
      action={{ label: "Add a user", to: "/users", icon: "plus" }}
      stats={[
        { label: "Students", value: v(stats.total_students), hint: "Enrolled", icon: "cap", tone: "dep", to: "/users" },
        { label: "Teachers", value: v(stats.total_teachers), hint: "Faculty accounts", icon: "faculty", tone: "men", to: "/users" },
        { label: "Parents", value: v(stats.total_parents), hint: "Linked to students", icon: "group", tone: "exm", to: "/users" },
        { label: "Courses", value: v(stats.total_courses), hint: "On the books", icon: "layers", tone: "plc", to: "/courses" },
      ]}
    >
      <HomePanel title="Quick actions" span={2}>
        <QuickActions items={actions} />
      </HomePanel>

      <HomePanel title="All accounts" sub="Everyone who can sign in" action="Manage" onAction={() => navigate("/users")}>
        <HomeRow title="Total users" sub="Students, faculty, parents and staff">
          <b className="kb-num kb-big">{v(stats.total_users)}</b>
        </HomeRow>
        <HomeRow title="Enrollments" sub="Students in subjects this term">
          <b className="kb-num kb-big">{v(stats.total_enrollments)}</b>
        </HomeRow>
      </HomePanel>
    </HubHome>
  );
}
