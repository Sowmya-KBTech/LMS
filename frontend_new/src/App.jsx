import {BrowserRouter,Routes,Route,Navigate}
from "react-router-dom";

// ===== PLATFORM CONSOLE (KB Technosoft, platform address only) =====
import PlatformApp from "./features/platform/PlatformApp";
import { isPlatformHost } from "./apiBase";

// ===== PUBLIC =====
import Login from "./pages/Login";
import ModuleGate from "./components/ModuleGate";
import Profile from "./pages/Profile";
import Notifications from "./pages/Notifications";
import ChangePassword from "./pages/ChangePassword";

// ===== COMMON FEATURES =====
import Courses from "./features/courses/Courses";
import CourseDetails from "./features/courses/CourseDetails";
import CourseStructure from "./features/courses/CourseStructure";
import Years from "./features/years/Years";
//import Subjects from "./features/subjects/Subjects";
import TeachingAssignments from "./features/teaching/TeachingAssignments";
import FeedbackHistory from "./features/feedback/FeedbackHistory";

// ===== TIMETABLE =====
import TimetableBuilder from "./features/timetable/TimetableBuilder";
import TimetableView from "./features/timetable/TimetableView";  
import AttendanceTeacher from "./features/attendance/AttendanceTeacher";
import AttendanceStudent from "./features/attendance/AttendanceStudent";
import StudentProgress from "./features/progress/StudentProgress";
import TeacherProgress from "./features/progress/TeacherProgress";
import AdminFees from "./features/fees/AdminFees";
import Results from "./features/results/Results";
import RankList from "./features/reports/RankList";                       // Wave 1
import ProgressReport, { MyProgressReport, ParentProgressReport } from "./features/reports/ProgressReport";
import StudentPlanner, { ParentPlanner } from "./features/planner/StudentPlanner";   // Wave 1
import PrincipalOverview from "./features/principal/PrincipalOverview";        // Wave 2
import SurveysManage from "./features/surveys/SurveysManage";                // Wave 2: surveys
import SurveyBuilder from "./features/surveys/SurveyBuilder";
import SurveyResults from "./features/surveys/SurveyResults";
import MySurveys, { AnswerSurvey } from "./features/surveys/MySurveys";
import AccreditationHome from "./features/accreditation/AccreditationHome";   // Wave 2: NAAC / NBA
import AccreditationReport from "./features/accreditation/AccreditationReport";
import Calendar from "./features/calendar/Calendar";
import Announcements from "./features/announcements/Announcements";
 
// ===== ADMIN =====
import Dashboard from "./pages/Admin/Dashboard";
import UserManagement from "./pages/Admin/UserManagement";
import Enrollments from "./pages/Admin/Enrollments";
import Departments from "./pages/Admin/Departments";
import AutomationAdmin from "./features/automation/AutomationAdmin";   // Point 12, step 8

// ===== TEACHER =====
import TeacherHome from "./pages/Teacher/TeacherHome";
import TeacherCourses from "./pages/Teacher/TeacherCourses";
import SubjectDetails from "./pages/Teacher/SubjectDetails";
import TeacherChat from "./pages/Teacher/TeacherChat";

// ===== ASSIGNMENTS =====
import AssignmentSubmissions from "./features/assignments/AssignmentSubmissions";

// ===== STUDENT =====
import StudentHome from "./pages/Student/StudentHome";
import StudentCourses from "./pages/Student/StudentCourses";
import StudentSubjectDetails from "./pages/Student/StudentSubjectDetails";
import StudentGrades from "./pages/Student/StudentGrades";
import StudentTeachingPlan from "./features/teachingplan/StudentTeachingPlan";
import ElectiveEnroll from "./features/courses/ElectiveEnroll";
import ElectivesManage from "./features/electives/ElectivesManage";   // meeting point 9

// ===== PARENT =====
import ParentDashboard from "./pages/Parent/ParentDashboard";
import ParentAttendance from "./features/attendance/ParentAttendance";
import ParentAssignments from "./features/assignments/ParentAssignments";
import ParentFees from "./features/fees/ParentFees";
import ParentGrades from "./pages/Parent/ParentGrades";
import ParentChat from "./pages/Parent/ParentChat";
import ParentMessage from "./pages/Parent/ParentMessage";

// ===== HOD =====
import HODDepartment from "./features/hod/HODDepartment";
import HodAllocation from "./features/hod/HodAllocation";

// ===== MENTORING =====
import HodMentorAllocation from "./features/mentoring/HodMentorAllocation";
import HodMentorDashboard from "./features/mentoring/HodMentorDashboard";
import HodMentorDetail from "./features/mentoring/HodMentorDetail";
import HodAllocationHistory from "./features/mentoring/HodAllocationHistory";
import HodChangeRequests from "./features/mentoring/HodChangeRequests";
import HodMentoringSettings from "./features/mentoring/HodMentoringSettings";
import HodTeamProposals from "./features/mentoring/HodTeamProposals";
import StaffMyMentees from "./features/mentoring/StaffMyMentees";
import StudentMyMentor from "./features/mentoring/StudentMyMentor";

// ===== CLASS GROUPS =====
import ClassGroups from "./features/classgroups/ClassGroups";

import MyClass from "./features/tutor/MyClass";

// ===== STAFF LEAVE =====
import MyLeave from "./features/leave/MyLeave";

import TeacherTeachingPlan from "./features/teachingplan/TeacherTeachingPlan";
import HODTeachingPlan from "./features/teachingplan/HODTeachingPlan";
import Regulations from "./features/regulations/Regulations";      // WAVE 3 PART 1A (CBCS)
import Curriculum from "./features/regulations/Curriculum";        // WAVE 3 PART 1A (CBCS)
import Outcomes from "./features/outcomes/Outcomes";                // CO-PO PART A
import StaffRecords from "./features/staff/StaffRecords";             // HRIS PART A
import ExamSessions from "./features/examsessions/ExamSessions";        // WAVE 3 PART 2
import MyExamRegistration from "./features/examsessions/MyExamRegistration"; // WAVE 3 PART 2
import MyCredits, { ParentCredits } from "./features/results/MyCredits";   // WAVE 3 PART 1B (CBCS)


// ===== IQAC =====
import FacultyContributions from "./features/iqac/FacultyContributions";
import IqacDashboard from "./features/iqac/IqacDashboard";
import AcademicQuality from "./features/iqac/AcademicQuality";

// ===== PLACEMENT =====
import PlacementCoordinators from "./features/placement/PlacementCoordinators";
import PlacementCompanies from "./features/placement/PlacementCompanies";
import PlacementDrives from "./features/placement/PlacementDrives";
import PlacementApplications from "./features/placement/PlacementApplications";
import CoordinatorPlacement from "./features/placement/CoordinatorPlacement";
import StudentPlacement from "./features/placement/StudentPlacement";
import PlacementAttendance from "./features/placement/PlacementAttendance";
import PlacementOffers from "./features/placement/PlacementOffers";
import PlacementReports from "./features/placement/Placementreports";
import PlacementDashboard from "./features/placement/Placementdashboard";

// ================= USER HELPER =================
const getUser = () => {

  try {

    return JSON.parse(
      localStorage.getItem("user")
    );

  } catch {
    return null;
  }
};


// ================= PROTECTED ROUTE =================
function ProtectedRoute({ children, role, roles, adminOnly = false }) {

  const user = getUser();

  if (!user)
    return (<Navigate to="/" replace />);

  const userRole = user.role?.toLowerCase();
  const subRole = user.sub_role?.toLowerCase();

  // the "main" admin = superuser, or an admin with no sub_role
  const isMainAdmin =
    user.is_superuser === true ||
    (userRole === "admin" && !subRole);

  // does the user satisfy a single required role string?
  //  - "admin"                    -> only the main admin
  //  - teacher / student / parent -> match the main role
  //  - anything else (exam_admin, iqac_admin, ...) -> match the sub_role
  const matches = (r) => {
    r = (r || "").toLowerCase();
    if (r === "admin") return isMainAdmin;
    if (["teacher", "student", "parent"].includes(r)) return userRole === r;
    return subRole === r;
  };

  // admin-only routes
  if (adminOnly && !isMainAdmin) {
    return (<Navigate to="/" replace />);
  }

  // single allowed role
  if (role && !matches(role)) {
    return (<Navigate to="/" replace />);
  }

  // multiple allowed roles
  if (roles && !roles.some(matches)) {
    return (<Navigate to="/" replace />);
  }

  // page belongs to a module this college has switched off -> friendly message
  return <ModuleGate>{children}</ModuleGate>;
}


// ================= ROLE REDIRECT =================
function RoleRedirect() {

  const user = getUser();

  if (!user)
    return (<Navigate to="/" replace />);

  const role = user.role?.toLowerCase();
  const subRole = user.sub_role?.toLowerCase();

  // superuser -> main dashboard
  if (user.is_superuser === true)
    return (<Navigate to="/dashboard" replace />);

  // admins: decide by sub_role
  if (role === "admin") {
    if (subRole === "accounts_admin")
      return (<Navigate to="/admin/fees" replace />);
    if (subRole === "exam_admin")
      return (<Navigate to="/results" replace />);
    if (subRole === "academic_admin")
      return (<Navigate to="/courses" replace />);
    if (subRole === "iqac_admin")
      return (<Navigate to="/iqac" replace />);
    if (subRole === "placement_officer")
      return (<Navigate to="/placement" replace />);
    return (<Navigate to="/dashboard" replace />);   // plain admin
  }

  if (role === "teacher")
    return (<Navigate to="/teacher" replace />);

  if (role === "student")
    return (<Navigate to="/student" replace />);

  if (role === "parent")
    return (<Navigate to="/parent" replace />);

  return (<Navigate to="/" replace />);
}


// ================= APP =================
function App() {

  // PLATFORM CONSOLE: at the platform address (localhost:5173, later
  // admin.kbtechcampus.in) show KB Technosoft's console, not a college app
  if (isPlatformHost()) return <PlatformApp />;

  return (

    <BrowserRouter>

      <Routes>

        {/* ===== PUBLIC ===== */}
        <Route path="/" element={<Login />}/>

        {/* ===== AFTER LOGIN ===== */}
        <Route path="/home" element={<RoleRedirect />} />

        {/* ================= COURSES (admin + academic admin only) ================= */}
        {/* Teachers use /teacher/courses (their own subjects), NOT this admin
            course editor. Students use /student/courses. */}

        <Route path="/courses" element={ <ProtectedRoute roles={["admin", "academic_admin"]}> <Courses /> </ProtectedRoute> }/>
        {/* WAVE 3 PART 1A (CBCS): regulations, credits and categories */}
        <Route path="/regulations" element={<ProtectedRoute roles={["admin", "academic_admin", "exam_admin"]}><Regulations /></ProtectedRoute>} />
        {/* CO-PO PART A: POs / PSOs, CO-PO mapping, attainment rules */}
        <Route path="/outcomes" element={<ProtectedRoute roles={["teacher", "admin", "academic_admin", "iqac_admin"]}><Outcomes /></ProtectedRoute>} />
        {/* HRIS PART A: staff directory and records (own record for other staff) */}
        <Route path="/staff" element={<ProtectedRoute roles={["teacher", "admin", "non_teaching"]}><StaffRecords /></ProtectedRoute>} />
        {/* WAVE 3 PART 2: exam sessions and registration */}
        <Route path="/exam-sessions" element={<ProtectedRoute roles={["admin", "exam_admin"]}><ExamSessions /></ProtectedRoute>} />
        <Route path="/exam-registration" element={<ProtectedRoute role="student"><MyExamRegistration /></ProtectedRoute>} />
        <Route path="/curriculum" element={<ProtectedRoute roles={["admin", "academic_admin", "exam_admin"]}><Curriculum /></ProtectedRoute>} />
        <Route path="/courses/:id" element={ <ProtectedRoute roles={["admin", "academic_admin"]}> <CourseDetails /> </ProtectedRoute> }/>
        <Route path="/courses/:id/structure" element={ <ProtectedRoute roles={["admin", "academic_admin"]}> <CourseStructure /> </ProtectedRoute> }/>

        {/* ================= ADMIN ================= */}

        <Route path="/dashboard" element={ <ProtectedRoute adminOnly={true}> <Dashboard /></ProtectedRoute> }/>
        <Route path="/users" element={ <ProtectedRoute adminOnly={true}> <UserManagement /> </ProtectedRoute> } />
        {/* Point 12, step 8: Automation (nightly reminder jobs) - main admin only */}
        <Route path="/admin/automation" element={ <ProtectedRoute adminOnly={true}> <AutomationAdmin /> </ProtectedRoute> } />


        {/* ================= ENROLLMENTS ================= */}
    
        <Route path="/enrollments" element={ <ProtectedRoute adminOnly={true}> <Enrollments /></ProtectedRoute> }/>

        {/* ================= YEARS ================= */}
        <Route path="/years" element={ <ProtectedRoute adminOnly={true} > <Years /> </ProtectedRoute>} />

        {/* ================= SUBJECTS ================= 
        <Route path="/subjects" element={ <ProtectedRoute adminOnly={true}> <Subjects /> </ProtectedRoute>}/> */}

        {/* ================= TEACHING ASSIGNMENTS ================= */}
        {/* Faculty allocation moved to HODs (Step 5). Kept reachable by the main
            admin only, as a fallback for departments with no HOD assigned yet.
            No sidebar link — reachable by direct URL only. */}
        <Route path="/teaching-assignments" element={ <ProtectedRoute adminOnly={true}><TeachingAssignments /></ProtectedRoute> }/>
        <Route path="/teacher/attendance" element={<ProtectedRoute role="teacher"><AttendanceTeacher /></ProtectedRoute>} />
        <Route path="/teacher/leave" element={<ProtectedRoute role="teacher"><MyLeave /></ProtectedRoute>} />
        <Route path="/student/attendance" element={<ProtectedRoute role="student"><AttendanceStudent /></ProtectedRoute>} />
        <Route path="/results" element={<ProtectedRoute><Results /></ProtectedRoute>} />
        {/* Wave 1: rank lists and progress reports (the server checks who may see which class / student) */}
        <Route path="/rank-list" element={<ProtectedRoute roles={["teacher", "admin", "exam_admin", "academic_admin"]}><RankList /></ProtectedRoute>} />
        <Route path="/progress-report/:studentId" element={<ProtectedRoute roles={["teacher", "admin", "exam_admin", "academic_admin", "parent"]}><ProgressReport /></ProtectedRoute>} />
        <Route path="/my-progress-report" element={<ProtectedRoute role="student"><MyProgressReport /></ProtectedRoute>} />
        {/* WAVE 3 PART 1B (CBCS): credits earned, CGPA, arrears */}
        <Route path="/my-credits" element={<ProtectedRoute role="student"><MyCredits /></ProtectedRoute>} />
        <Route path="/parent/credits" element={<ProtectedRoute role="parent"><ParentCredits /></ProtectedRoute>} />
        <Route path="/credits/:studentId" element={<ProtectedRoute roles={["teacher", "admin", "exam_admin", "academic_admin"]}><MyCredits /></ProtectedRoute>} />
        <Route path="/parent/progress-report" element={<ProtectedRoute role="parent"><ParentProgressReport /></ProtectedRoute>} />
        {/* Wave 1: student planner */}
        <Route path="/planner" element={<ProtectedRoute role="student"><StudentPlanner /></ProtectedRoute>} />
        <Route path="/parent/planner" element={<ProtectedRoute role="parent"><ParentPlanner /></ProtectedRoute>} />
        {/* Wave 2: Principal's college overview (the server decides who sees it) */}
        <Route path="/principal" element={<ProtectedRoute roles={["teacher", "admin"]}><PrincipalOverview /></ProtectedRoute>} />
        {/* Wave 2: surveys - building (HOD, Principal, admins) and answering (students, staff) */}
        <Route path="/surveys/manage" element={<ProtectedRoute roles={["teacher", "admin", "iqac_admin", "academic_admin"]}><SurveysManage /></ProtectedRoute>} />
        <Route path="/surveys/manage/new" element={<ProtectedRoute roles={["teacher", "admin", "iqac_admin", "academic_admin"]}><SurveyBuilder /></ProtectedRoute>} />
        <Route path="/surveys/manage/:id/edit" element={<ProtectedRoute roles={["teacher", "admin", "iqac_admin", "academic_admin"]}><SurveyBuilder /></ProtectedRoute>} />
        <Route path="/surveys/manage/:id/results" element={<ProtectedRoute roles={["teacher", "admin", "iqac_admin", "academic_admin"]}><SurveyResults /></ProtectedRoute>} />
        <Route path="/surveys" element={<ProtectedRoute roles={["student", "teacher"]}><MySurveys /></ProtectedRoute>} />
        <Route path="/surveys/:id" element={<ProtectedRoute roles={["student", "teacher"]}><AnswerSurvey /></ProtectedRoute>} />
        {/* Wave 2: NAAC / NBA reports (IQAC, Principal, main admin; HODs see their own department) */}
        <Route path="/accreditation" element={<ProtectedRoute roles={["teacher", "admin", "iqac_admin"]}><AccreditationHome /></ProtectedRoute>} />
        <Route path="/accreditation/:key" element={<ProtectedRoute roles={["teacher", "admin", "iqac_admin"]}><AccreditationReport /></ProtectedRoute>} />
        <Route path="/student/electives" element={ <ProtectedRoute role="student"> <ElectiveEnroll /> </ProtectedRoute> }/>
        {/* Electives (meeting point 9): admin, academic admin, super admin and HODs.
            Teachers who are not a HOD get an empty list - the server decides. */}
        <Route path="/electives/manage" element={ <ProtectedRoute roles={["admin", "academic_admin", "super_admin", "teacher"]}> <ElectivesManage /> </ProtectedRoute> }/>

        {/* ================= DEPARTMENTS ================= */}
        <Route path="/departments" element={ <ProtectedRoute roles={["admin", "academic_admin"]} ><Departments /></ProtectedRoute> }/>

        {/* ================= TEACHER ================= */}

        <Route path="/teacher" element={ <ProtectedRoute role="teacher"> <TeacherHome /></ProtectedRoute> }/>
        <Route path="/teacher/courses" element={ <ProtectedRoute role="teacher"> <TeacherCourses /> </ProtectedRoute> }/>
        <Route path="/teacher/subject/:id" element={ <ProtectedRoute role="teacher"><SubjectDetails /></ProtectedRoute>}/>
        <Route path="/teacher-progress" element={ <ProtectedRoute role="teacher"> <TeacherProgress /></ProtectedRoute>}/>
        <Route path="/teacher/messages" element={ <ProtectedRoute role="teacher"> <TeacherChat /> </ProtectedRoute> }/>

        {/* ================= TEACHING PLANS ================= */}
        <Route path="/teacher/teaching-plan" element={ <ProtectedRoute role="teacher"> <TeacherTeachingPlan /> </ProtectedRoute> }/>
        <Route path="/my-department/teaching-plans" element={ <ProtectedRoute role="teacher"> <HODTeachingPlan /> </ProtectedRoute> }/>
        <Route path="/student/teaching-plan" element={ <ProtectedRoute role="student"> <StudentTeachingPlan /> </ProtectedRoute> }/>

        {/* ================= MY CONTRIBUTIONS (IQAC) ================= */}
        <Route path="/my-contributions" element={ <ProtectedRoute role="teacher"> <FacultyContributions /> </ProtectedRoute> }/>


        {/* ================= ASSIGNMENT SUBMISSIONS ================= */}

        <Route path="/assignments/:id/submissions" element={ <ProtectedRoute> <AssignmentSubmissions /> </ProtectedRoute> }/>

        {/* ================= STUDENT ================= */}

        <Route path="/student" element={ <ProtectedRoute role="student" > <StudentHome /> </ProtectedRoute> } />
        <Route path="/student/courses" element={ <ProtectedRoute role="student"> <StudentCourses /> </ProtectedRoute>  }/> 

        <Route path="/student/subject/:id" element={<ProtectedRoute role="student"> <StudentSubjectDetails /> </ProtectedRoute>}/>

        <Route path="/student/grades" element={<ProtectedRoute role="student" > <StudentGrades /> </ProtectedRoute> }/>

        <Route path="/student-progress" element={ <ProtectedRoute role="student"> <StudentProgress /> </ProtectedRoute>}/>
        <Route path="/calendar" element={<ProtectedRoute><Calendar /></ProtectedRoute>} />
       
        <Route path="/announcements" element={<ProtectedRoute><Announcements /></ProtectedRoute>} />

        {/* ================= PROFILE ================= */}

        <Route
          path="/profile"
          element={
            <ProtectedRoute>

              <Profile />

            </ProtectedRoute>
          }
        />

        {/* ================= FEEDBACK ================= */}

        <Route
           path="/feedback"
           element={
             <ProtectedRoute>
               <FeedbackHistory />
             </ProtectedRoute>
            }
         />     

        {/* ================= NOTIFICATIONS ================= */}

        <Route path="/notifications" element={ <ProtectedRoute> <Notifications /> </ProtectedRoute>  }/>
        <Route path="/change-password" element={ <ProtectedRoute> <ChangePassword /> </ProtectedRoute> } />

        {/* ================= TIMETABLE ================= */}
        <Route
          path="/timetable-builder"
          element={
          <ProtectedRoute adminOnly={true}>
              <TimetableBuilder />
          </ProtectedRoute>
           }
        />

         <Route
          path="/timetable"
          element={
          <ProtectedRoute>
            <TimetableView />
          </ProtectedRoute>
          }
        /> 
         {/* ================= PARENT ================= */}

        <Route path="/parent" element={<ProtectedRoute role="parent"> <ParentDashboard /> </ProtectedRoute>}/>
        <Route path="/parent/attendance" element={ <ProtectedRoute role="parent"> <ParentAttendance /> </ProtectedRoute>}/>
        <Route path="/parent/assignments" element={<ProtectedRoute role="parent"> <ParentAssignments /> </ProtectedRoute>}/>
        <Route path="/parent/fees" element={ <ProtectedRoute role="parent"> <ParentFees /> </ProtectedRoute>}/>
        <Route path="/parent/grades" element={  <ProtectedRoute role="parent"> <ParentGrades /> </ProtectedRoute>}/>
        <Route path="/parent/chat" element={ <ProtectedRoute role="parent"> <ParentChat /> </ProtectedRoute>}/>
        <Route path="/parent/messages" element={ <ProtectedRoute role="parent"> <ParentMessage /> </ProtectedRoute>}/>
        <Route path="/admin/fees" element={<ProtectedRoute roles={["admin", "accounts_admin"]}> <AdminFees /> </ProtectedRoute>} />
        <Route path="/my-department" element={<ProtectedRoute role="teacher">  <HODDepartment /> </ProtectedRoute> }/>
        <Route
          path="/my-class"
          element={
            <ProtectedRoute role="teacher">
              <MyClass />
            </ProtectedRoute>
          }
        />
        <Route
          path="/hod/allocation"
          element={
            <ProtectedRoute role="teacher">
              <HodAllocation />
            </ProtectedRoute>
          }
        />

        {/* ================= MENTOR ALLOCATION ================= */}
        <Route
          path="/hod/mentor-allocation"
          element={
            <ProtectedRoute role="teacher">
              <HodMentorAllocation />
            </ProtectedRoute>
          }
        />

        <Route path="/hod/mentor-dashboard" element={
          <ProtectedRoute role="teacher"><HodMentorDashboard /></ProtectedRoute>} />
        <Route path="/hod/mentor-change-requests" element={
          <ProtectedRoute role="teacher"><HodChangeRequests /></ProtectedRoute>} />
        <Route path="/hod/mentor-history" element={
          <ProtectedRoute role="teacher"><HodAllocationHistory /></ProtectedRoute>} />
        <Route path="/hod/mentor-settings" element={
          <ProtectedRoute role="teacher"><HodMentoringSettings /></ProtectedRoute>} />
        <Route path="/hod/mentors/:mentorId" element={
          <ProtectedRoute role="teacher"><HodMentorDetail /></ProtectedRoute>} />
        <Route path="/hod/team-proposals" element={
          <ProtectedRoute role="teacher"><HodTeamProposals /></ProtectedRoute>} />

        {/* ================= MY MENTEES (STAFF) ================= */}
        <Route path="/my-mentees" element={
          <ProtectedRoute role="teacher"><StaffMyMentees /></ProtectedRoute>} />

        {/* ================= MY MENTOR (STUDENT) ================= */}
        <Route path="/my-mentor" element={
          <ProtectedRoute role="student"><StudentMyMentor /></ProtectedRoute>} />

        {/* ================= CLASS GROUPS ================= */}
        <Route path="/my-groups" element={
          <ProtectedRoute roles={["teacher", "student"]}><ClassGroups /></ProtectedRoute>} />

        {/* ================= IQAC DASHBOARD ================= */}
        <Route path="/iqac" element={<ProtectedRoute role="iqac_admin"> <IqacDashboard /> </ProtectedRoute>} />
        <Route path="/iqac/academic-quality" element={<ProtectedRoute role="iqac_admin"> <AcademicQuality /> </ProtectedRoute>} />

        {/* ================= PLACEMENT — OFFICER ================= */}
        {/* "admin" matches the main admin / superuser; "placement_officer"
            matches the sub_role. Both are readable from localStorage.

            ONE route per path. As each screen is built, edit the COMPONENT on
            its existing line -- never add a second <Route> for the same path.
            React Router uses the FIRST match, so a leftover placeholder wins
            silently and the new page never renders. */}

        <Route path="/placement" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementDashboard /> </ProtectedRoute> }/>
        <Route path="/placement/coordinators" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementCoordinators /> </ProtectedRoute> }/>
        <Route path="/placement/companies" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementCompanies /> </ProtectedRoute> }/>
        <Route path="/placement/drives" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementDrives /> </ProtectedRoute> }/>
        <Route path="/placement/applications" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementApplications /> </ProtectedRoute> }/>
        <Route path="/placement/rounds" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementAttendance /> </ProtectedRoute> }/>
        <Route path="/placement/interviews" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementAttendance /> </ProtectedRoute> }/>  {/* old address, kept for bookmarks */}
        <Route path="/placement/offers" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementOffers /> </ProtectedRoute> }/>
        <Route path="/placement/reports" element={ <ProtectedRoute roles={["admin", "placement_officer"]}> <PlacementReports /> </ProtectedRoute> }/>

        {/* ================= PLACEMENT — COORDINATOR ================= */}
        {/* Coordinator is an assignment row, not a role, so localStorage cannot
            prove it — this route only checks "is a teacher". The sidebar hides
            the link from non-coordinators, and the API refuses their data. */}

        <Route path="/placement/coordinator" element={ <ProtectedRoute role="teacher"> <CoordinatorPlacement /> </ProtectedRoute> }/>

        {/* ================= PLACEMENT — STUDENT ================= */}

        <Route path="/student/placement" element={ <ProtectedRoute role="student"> <StudentPlacement /> </ProtectedRoute> }/>

        {/* ===== FALLBACK ===== */}
        <Route path="*" element={ <Navigate to="/" replace/>}/>

      </Routes>

    </BrowserRouter>
  );
}

export default App;