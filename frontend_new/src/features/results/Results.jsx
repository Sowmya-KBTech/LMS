import { useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import IATeacher from "./IATeacher";
import IAStudent from "./IAStudent";
import IAAdmin from "./IAAdmin";
import IAParent from "./IAParent";
import SRAdmin from "./SRAdmin";
import SRStudent from "./SRStudent";
import SRParent from "./SRParent";
import HallTicketAdmin from "./HallTicketAdmin";
import HallTicketStudent from "./HallTicketStudent";
import RevaluationAdmin from "./RevaluationAdmin";
import RevaluationStudent from "./RevaluationStudent";
import { MyExamDuties } from "../examsessions/ExamSeating";   // WAVE 3 PART 2b
import "../../styles/Attendance.css";

export default function Results() {
  const [open, setOpen] = useState(false);

  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const role = user.role;

  // #49: the SAME rule as the server's is_exam_admin() - superuser, the main
  // admin (no sub-role), super admin and the Examination admin. Other admins
  // (placement, accounts, IQAC...) don't manage exams.
  const subRole = (user.sub_role || "").toLowerCase();
  const isExamAdmin =
    user.is_superuser === true ||
    role === "exam_admin" ||
    (role === "admin" && ["", "super_admin", "exam_admin"].includes(subRole));
  const isOtherAdmin = role === "admin" && !isExamAdmin;

  const ALL_TABS = [
    { id: "ia", label: "Internal Assessment" },
    { id: "sr", label: "Semester Result" },
    { id: "ht", label: "Hall Ticket" },
    { id: "reval", label: "Revaluation" },
    { id: "duties", label: "Exam duties" },      // WAVE 3 PART 2b: invigilation duties (staff)
  ];

  // teacher only enters IA; parent sees IA + semester result; student + admin/exam_admin see all
  let TABS;
  if (role === "teacher") {
    TABS = ALL_TABS.filter((t) => t.id === "ia" || t.id === "duties");
  } else if (role === "parent") {
    TABS = ALL_TABS.filter((t) => t.id === "ia" || t.id === "sr");
  } else {
    TABS = ALL_TABS.filter((t) => t.id !== "duties");
  }

  // FIX #11: /results?tab=ia or ?tab=ht (from a notification) opens that tab
  const wanted = new URLSearchParams(window.location.search).get("tab");
  const [tab, setTab] = useState(
    TABS.some((t) => t.id === wanted) ? wanted : TABS[0].id
  );

  const renderTab = () => {
    // ===== Internal Assessment =====
    if (tab === "ia") {
      if (role === "teacher") return <IATeacher embedded />;
      if (role === "student") return <IAStudent embedded />;
      if (isExamAdmin)        return <IAAdmin embedded />;
      if (role === "parent")  return <IAParent embedded />;
    }

    // ===== Semester Result =====
    if (tab === "sr") {
      if (isExamAdmin)        return <SRAdmin embedded />;
      if (role === "student") return <SRStudent embedded />;
      if (role === "parent")  return <SRParent embedded />;
    }

    // ===== Hall Ticket =====
    if (tab === "ht") {
      if (isExamAdmin)        return <HallTicketAdmin embedded />;
      if (role === "student") return <HallTicketStudent embedded />;
    }

    // ===== Exam duties (WAVE 3 PART 2b) =====
    if (tab === "duties" && role === "teacher") return <MyExamDuties />;

    // ===== Revaluation =====
    if (tab === "reval") {
      if (isExamAdmin)        return <RevaluationAdmin embedded />;
      if (role === "student") return <RevaluationStudent embedded />;
    }

    return (
      <div className="att-card">
        <div className="att-state">
          <p>
            {isOtherAdmin
              ? "Exams and results are managed by the Examination admin."
              : "This section is coming soon."}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="att-page">

              <div className="att-header">
                <div>
                  <h1 className="att-title">Results</h1>
                  <p className="att-subtitle">
                    Internal assessment, semester results, hall ticket and revaluation
                  </p>
                </div>
              </div>

              <div className="att-tabs">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    className={`att-tab${tab === t.id ? " active" : ""}`}
                    onClick={() => setTab(t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {renderTab()}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}