import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

// ================= FEATURES =================
import Lecture from "../../features/lectures/LectureTeacher";
import Assignments from "../../features/assignments/AssignmentTeacher";
import Quiz from "../../features/quiz/QuizTeacher";
import StudyMaterialTeacher from "../../features/materials/StudyMaterialTeacher";
import DiscussionTeacher from "../../features/discussion/DiscussionTeacher";
import FeedbackTeacher from "../../features/feedback/FeedbackTeacher";
import { CoAttainmentTab } from "../../features/outcomes/CoMarks";   // CO-PO PART B


export default function SubjectDetails() {

  const { id } = useParams();

  const [open, setOpen] =
    useState(false);

  const [ta, setTA] =
    useState(null);

  const [students, setStudents] =
    useState([]);

  // FIX #23: a notification can open a tab directly, e.g. ?tab=assignments
  const [activeTab, setActiveTab] =
    useState(
      new URLSearchParams(window.location.search).get("tab") || "students"
    );

  const [loading, setLoading] =
    useState(true);

  // ================= FETCH =================
  useEffect(() => {

    if (id) {

      fetchData();
    }

  }, [id]);

  const fetchData = async () => {

    try {

      setLoading(true);

      // ================= SUBJECT DETAILS =================
      const res = await API.get(
        `/teaching-assignments/${id}/`
      );

      setTA(res.data);

      // ================= ENROLLMENTS =================
      const s = await API.get(
        "/enrollments/"
      );

      const allStudents =
        s.data?.results ||
        s.data ||
        [];

      // ================= FILTER =================
      const filteredStudents =
        allStudents.filter(
          (e) =>
            (e.teaching_assignment?.id ||
              e.teaching_assignment) ===
            Number(id)
        );

      setStudents(filteredStudents);

    } catch (err) {

      console.error(
        "Error loading subject:",
        err
      );

    } finally {

      setLoading(false);
    }
  };

  // ================= LOADING =================
  if (loading) {

    return (
      <p style={{ padding: "20px" }}>
        Loading...
      </p>
    );
  }

  // ================= NO DATA =================
  if (!ta) {

    return (
      <p style={{ padding: "20px" }}>
        No subject data found
      </p>
    );
  }

  return (
    <div className="app">

      {/* NAVBAR */}
      <Navbar setOpen={setOpen} />

      <div className="layout">

        {/* SIDEBAR */}
        <Sidebar
          open={open}
          setOpen={setOpen}
        />

        {/* MAIN */}
        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">

              <h2>
                {ta.course_name || "Course"}{" "}
                - Year{" "}
                {ta.year_number || ""}
              </h2>

              <h3>
                {ta.subject_name || "Subject"}
              </h3>

            </div>

            {/* ================= TABS ================= */}
            <div className="tabs">

              {/* STUDENTS */}
              <button
                className={
                  activeTab === "students"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab("students")
                }
              >
                Students
              </button>

              {/* LECTURES */}
              <button
                className={
                  activeTab === "lectures"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab("lectures")
                }
              >
                Lectures
              </button>

              {/* ASSIGNMENTS */}
              <button
                className={
                  activeTab === "assignments"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab("assignments")
                }
              >
                Assignments
              </button>

              {/* QUIZ */}
              <button
                className={
                  activeTab === "quiz"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab("quiz")
                }
              >
                Online tests
              </button>

              {/* CO-PO PART B: CO ATTAINMENT */}
              <button
                className={activeTab === "co" ? "btn-primary" : ""}
                onClick={() => setActiveTab("co")}
              >
                CO attainment
              </button>

              {/* STUDY MATERIALS */}
              <button
                className={
                  activeTab === "materials"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab("materials")
                }
              >
                Study Materials
              </button>

              {/* DISCUSSION FORUM */}
              <button
              className={
               activeTab === "discussion"
               ? "btn-primary"
                : ""
              }
              onClick={() =>
               setActiveTab("discussion")
              }>
               Discussion Forum
              </button>

              <button
              className={
              activeTab === "feedback"
              ? "btn-primary"
              : ""
              }
              onClick={() =>
              setActiveTab("feedback")
              }>
              Feedback
              </button>

            </div>

            {/* ================= STUDENTS TAB ================= */}
            {activeTab === "students" && (

              <div className="card">

                <h3>
                  Students
                </h3>

                {students.length === 0 ? (

                  <p>
                    No students enrolled
                  </p>

                ) : (

                  <div
                    style={{
                      overflowX: "auto",
                    }}
                  >

                    <table>

                      <thead>

                        <tr>

                          <th> Student Name </th>
                          <th>  Roll No  </th>
                          <th>  Course  </th>
                          <th> Subject </th>
                          <th> Year </th> 
                        </tr>   
                       </thead>
                       <tbody> 

                        {students.map((s) => (

                          <tr key={s.id}>

                            <td> {s.student_name} </td>
                            <td> {s.student_roll_no || "-"} </td>
                            <td>  {s.course_name} </td>
                            <td>  {s.subject_name} </td>
                            <td> Year {s.year_number} </td>

                          </tr>

                        ))}

                      </tbody>

                    </table>

                  </div>

                )}

              </div>

            )}

            {/* ================= LECTURES TAB ================= */}
            {activeTab === "lectures" && (

              <Lecture teachingId={id} />

            )}

            {/* ================= ASSIGNMENTS TAB ================= */}
            {activeTab === "assignments" && (

              <Assignments teachingId={id} />

            )}

            {/* ================= QUIZ TAB ================= */}
            {activeTab === "quiz" && (

              <Quiz teachingId={id} />
            )}

            {/* ================= STUDY MATERIALS TAB ================= */}
            {activeTab === "co" && <CoAttainmentTab ta={id} />}

            {activeTab === "materials" && (

              <StudyMaterialTeacher teachingId={id}/> )}
              
            {/* DISCUSSION TAB */}
            {activeTab === "discussion" && (<DiscussionTeacher teachingId={id} /> )}

            {/* FEEDBACK TAB */}
            {activeTab === "feedback" && ( <FeedbackTeacher teachingId={id} students={students} /> )}

          </div>

        </div>

      </div>

    </div>
  );
}