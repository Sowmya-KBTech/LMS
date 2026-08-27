import { useNavigate, useLocation } from "react-router-dom";

import { useState, useEffect } from "react";
import API from "../api";

export default function Sidebar({ open, setOpen }) {

  const navigate = useNavigate();
  const location = useLocation();

  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const [usersOpen, setUsersOpen] = useState(true);
  const [isHod, setIsHod] = useState(false);
  const [isTutor, setIsTutor] = useState(false);

  // ================= PLACEMENT COORDINATOR =================
  // Coordinator is an ASSIGNMENT, not a role, so it cannot be read from
  // localStorage like user.role can -- it has to be asked for. Same reason
  // isHod and isTutor are fetched above.
  const [isPlacementCoordinator, setIsPlacementCoordinator] = useState(false);

  useEffect(() => {
    if (user.role === "teacher") {
      API.get("users/my-department/")
        .then((res) => setIsHod(res.data?.is_hod || false))
        .catch(() => setIsHod(false));

      API.get("users/my-class/")
        .then((res) => setIsTutor(res.data?.is_tutor || false))
        .catch(() => setIsTutor(false));

      // the backend is the single source of truth for who is a coordinator;
      // the sidebar never decides this for itself
      API.get("placement/me/")
        .then((res) =>
          setIsPlacementCoordinator(res.data?.is_placement_coordinator || false)
        )
        .catch(() => setIsPlacementCoordinator(false));
    }
  }, [user.role]);

  let menu = [];

  const subRole = user.sub_role;
  // the "main" admin = superuser, or an admin with no sub_role
  const isMainAdmin =
    user.is_superuser === true || (user.role === "admin" && !subRole);

  // ================= FULL ADMIN (SUPER ADMIN) =================
  if (isMainAdmin) {
    menu = [
      { name: "Dashboard", path: "/dashboard" },
      { name: "Departments", path: "/departments" },
      { name: "User Management", path: "/users" },
      { name: "Courses", path: "/courses" },
    //  { name: "Enrollments", path: "/enrollments" },
      // Faculty Allocation moved to HODs (Step 5) — admin link removed
      { name: "Timetable Builder", path: "/timetable-builder" },
      { name: "Results", path: "/results" },
      { name: "Fee Management", path: "/admin/fees" },
      { name: "Placement", path: "/placement" },
      { name: "Calendar", path: "/calendar" },
      { name: "Announcements", path: "/announcements" },
      { name: "Profile", path: "/profile" },
    ];
  }

  // ================= ACCOUNTS ADMIN =================
  else if (user.role === "admin" && subRole === "accounts_admin") {
    menu = [
      { name: "Fee Management", path: "/admin/fees" },
      { name: "Announcements", path: "/announcements" },
      { name: "Profile", path: "/profile" },
    ];
  }

  // ================= EXAMINATION ADMIN =================
  else if (user.role === "admin" && subRole === "exam_admin") {
    menu = [
      { name: "Results", path: "/results" },
      { name: "Announcements", path: "/announcements" },
      { name: "Profile", path: "/profile" },
    ];
  }

  // ================= ACADEMIC ADMIN =================
  else if (user.role === "admin" && subRole === "academic_admin") {
    menu = [
      { name: "Departments", path: "/departments" },
      { name: "Courses", path: "/courses" },
      // Faculty Allocation moved to HODs (Step 5) — admin link removed
      //{ name: "Enrollments", path: "/enrollments" },
      { name: "Profile", path: "/profile" },
    ];
  }

  // ================= IQAC ADMIN =================
  else if (user.role === "admin" && subRole === "iqac_admin") {
    menu = [
      { name: "Faculty Participation", path: "/iqac" },
      { name: "Academic Quality", path: "/iqac/academic-quality" },
      { name: "Profile", path: "/profile" },
    ];
  }

  // ================= PLACEMENT OFFICER =================
  // role='admin' + sub_role='placement_officer'. Runs placement for the whole
  // college; every department, every drive.
  else if (user.role === "admin" && subRole === "placement_officer") {
    menu = [
      { name: "Dashboard", path: "/placement" },
      { name: "Coordinators", path: "/placement/coordinators" },
      { name: "Companies", path: "/placement/companies" },
      { name: "Drives", path: "/placement/drives" },
      { name: "Applications", path: "/placement/applications" },
      { name: "Drive attendance", path: "/placement/interviews" },
      { name: "Offers", path: "/placement/offers" },
      { name: "Reports", path: "/placement/reports" },
      { name: "Announcements", path: "/announcements" },
      { name: "Notifications", path: "/notifications" },
      { name: "Profile", path: "/profile" },
    ];
  }

  // ================= TEACHER =================
  else if (user.role === "teacher") {
    menu = [
      { name: "Dashboard", path: "/teacher" },
      ...(isHod ? [
        { name: "My Department", path: "/my-department" },
        { name: "Plan Approvals", path: "/my-department/teaching-plans" },
        { name: "Faculty Allocation", path: "/hod/allocation" },
      ] : []),
      ...(isTutor ? [{ name: "My Class", path: "/my-class" }] : []),
      // teachers get their OWN subjects page — /courses is the admin course editor
      { name: "My Subjects", path: "/teacher/courses" },
      { name: "Timetable", path: "/timetable" },
      { name: "My Teaching Plan", path: "/teacher/teaching-plan" },
      { name: "Attendance", path: "/teacher/attendance" },
      // shown only to a teacher who ALSO holds a coordinator assignment;
      // they keep every teaching menu above it
      ...(isPlacementCoordinator
        ? [{ name: "Placement", path: "/placement/coordinator" }]
        : []),
      { name: "Calendar", path: "/calendar" },
      { name: "Results", path: "/results" },
      { name: "Student Progress", path: "/teacher-progress" },
      { name: "My Contributions", path: "/my-contributions" },
      { name: "Announcements", path: "/announcements" },
      { name: "Messages", path: "/teacher/messages" },
      { name: "Feedback History", path: "/feedback" },
      { name: "Notifications", path: "/notifications" },
      { name: "Profile", path: "/profile" },
    ];
  } else if (user.role === "student") {
    menu = [
      { name: "Dashboard", path: "/student" },
      { name: "My Subjects", path: "/student/courses" },
      { name: "Electives", path: "/student/electives" },
      { name: "Timetable", path: "/timetable" },
      { name: "Attendance", path: "/student/attendance" },
      { name: "Grades", path: "/student/grades" },
      { name: "Results", path: "/results" },
      { name: "My Progress", path: "/student-progress" },
      { name: "Placement", path: "/student/placement" },
      { name: "Calendar", path: "/calendar" },
      { name: "Announcements", path: "/announcements" },
      { name: "Feedback History", path: "/feedback" },
      { name: "Notifications", path: "/notifications" },
      { name: "Profile", path: "/profile" },
    ];
  } else if (user.role === "parent") {
    menu = [
      { name: "Dashboard", path: "/parent" },
      { name: "Grades", path: "/parent/grades" },
      { name: "Attendance", path: "/parent/attendance" },
      { name: "Assignments", path: "/parent/assignments" },
      { name: "Results", path: "/results" },
      { name: "Fees", path: "/parent/fees" },
      { name: "Messages", path: "/parent/chat" },
      { name: "Notifications", path: "/notifications" },
      { name: "Profile", path: "/profile" },
    ];
  }

  // active check — keeps the "Courses" / "My Subjects" item highlighted while
  // on a detail page belonging to it
  const isActive = (itemPath) => {

    if (location.pathname === itemPath) {
      return true;
    }

    // admin / academic admin: /courses/:id and /courses/:id/structure
    if (location.pathname.startsWith("/courses/")) {
      if (itemPath === "/courses") {
        return true;
      }
    }

    // teacher: /teacher/subject/:id belongs to "My Subjects"
    if (location.pathname.startsWith("/teacher/subject/")) {
      if (itemPath === "/teacher/courses") {
        return true;
      }
    }

    // student: /student/subject/:id belongs to "My Subjects"
    if (location.pathname.startsWith("/student/subject/")) {
      if (itemPath === "/student/courses") {
        return true;
      }
    }

    // ================= PLACEMENT =================
    // Placement paths can nest (/placement/drives, /placement/offers), so an
    // exact match alone would drop the highlight on a detail page.
    if (location.pathname.startsWith("/student/placement")) {
      if (itemPath === "/student/placement") {
        return true;
      }
    }

    if (location.pathname.startsWith("/placement/coordinator")) {
      if (itemPath === "/placement/coordinator") {
        return true;
      }
    }

    if (
      location.pathname.startsWith("/placement/") &&
      !location.pathname.startsWith("/placement/coordinator")
    ) {
      // highlight the deepest matching section item, not the dashboard
      if (itemPath !== "/placement" && location.pathname.startsWith(itemPath)) {
        return true;
      }
    }

    return false;
  };

  return (
    <>
      {open && (
        <div className="sidebar-overlay" onClick={() => setOpen(false)} />
      )}

      <div className={`sidebar ${open ? "open" : ""}`}>
        <h2 className="logo">LMS</h2>

        <div className="user-info">
          <div className="avatar">
            {user?.username?.slice(0, 2).toUpperCase() || "US"}
          </div>
          <div>
            <p>{user?.username}</p>
            <span>{user?.role}</span>
          </div>
        </div>

        <div className="menu">
          {menu.map((item) => (
            <div key={item.name}>
              {!item.children && (
                <p
                  onClick={() => {
                    navigate(item.path);
                    setOpen(false);
                  }}
                  className={isActive(item.path) ? "active" : ""}
                >
                  {item.name}
                </p>
              )}

              {item.children && (
                <div>
                  <p onClick={() => setUsersOpen(!usersOpen)}>{item.name}</p>
                  {usersOpen && (
                    <div style={{ marginLeft: "20px" }}>
                      {item.children.map((sub) => (
                        <p
                          key={sub.name}
                          onClick={() => {
                            navigate(sub.path);
                            setOpen(false);
                          }}
                          className={isActive(sub.path) ? "active" : ""}
                        >
                          {sub.name}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}