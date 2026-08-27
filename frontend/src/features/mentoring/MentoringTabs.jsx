// frontend/src/features/mentoring/MentoringTabs.jsx
import { useLocation, useNavigate } from "react-router-dom";

/**
 * One sidebar entry, four pages. Your Sidebar is a flat list, so adding five
 * mentor items would bury the teacher's own menu. These tabs sit inside the
 * pages instead.
 */
const TABS = [
  { label: "Dashboard", path: "/hod/mentor-dashboard" },
  { label: "Mentor Allocation", path: "/hod/mentor-allocation" },
  { label: "Change Requests", path: "/hod/mentor-change-requests" },
  { label: "Allocation History", path: "/hod/mentor-history" },
  { label: "Settings", path: "/hod/mentor-settings" },
];

export default function MentoringTabs() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="ma-toggle" style={{ marginBottom: 16 }}>
      {TABS.map((t) => (
        <button
          key={t.path}
          className={location.pathname === t.path ? "on" : ""}
          onClick={() => navigate(t.path)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}