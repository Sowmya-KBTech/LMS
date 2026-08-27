import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import Navbar from "../components/Navbar";
import API from "../api";

// =============================================================
//  Dashboard Page — Admin Overview
// =============================================================

export default function Dashboard() {

  // ─────────────────────────────────────────────────────────
  //  STATE
  // ─────────────────────────────────────────────────────────

  const [stats, setStats] = useState({
    total_users:       0,
    total_students:    0,
    total_teachers:    0,
    total_courses:     0,
    total_enrollments: 0,
  });


  // ─────────────────────────────────────────────────────────
  //  HELPERS
  // ─────────────────────────────────────────────────────────

  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good Morning";
    if (hour < 18) return "Good Afternoon";
    return "Good Evening";
  };


  // ─────────────────────────────────────────────────────────
  //  LIFECYCLE
  // ─────────────────────────────────────────────────────────

  useEffect(() => {
    fetchStats();
  }, []);


  // ─────────────────────────────────────────────────────────
  //  API CALLS
  // ─────────────────────────────────────────────────────────

  const fetchStats = async () => {
    try {
      const res = await API.get("admin-dashboard/");
      setStats(res.data);
    } catch (err) {
      console.error("Dashboard fetch error:", err);
    }
  };


  // ─────────────────────────────────────────────────────────
  //  RENDER
  // ─────────────────────────────────────────────────────────

  return (
    <div className="layout">
      <Sidebar />

      <div className="main">
        <Navbar />

        <div className="content">

          {/* ── Page Header ───────────────────────────────── */}
          <div className="header-box">
            <h2>{getGreeting()}, {user?.username || "User"} 👋</h2>
            <p>Welcome to your LMS dashboard</p>
          </div>

          {/* ── Stats Cards ───────────────────────────────── */}
          <div className="cards">

            <div className="dashboard-card blue">
              <h4>Total Users</h4>
              <h2>{stats?.total_users || 0}</h2>
            </div>

            <div className="dashboard-card green">
              <h4>Students</h4>
              <h2>{stats?.total_students || 0}</h2>
            </div>

            <div className="dashboard-card purple">
              <h4>Teachers</h4>
              <h2>{stats?.total_teachers || 0}</h2>
            </div>

            <div className="dashboard-card orange">
              <h4>Courses</h4>
              <h2>{stats?.total_courses || 0}</h2>
            </div>

            <div className="dashboard-card red">
              <h4>Enrollments</h4>
              <h2>{stats?.total_enrollments || 0}</h2>
            </div>

          </div>

        </div>
      </div>
    </div>
  );
}