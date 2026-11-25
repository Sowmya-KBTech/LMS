import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

// ================= STUDENT FEATURES =================
import TeachingPlanStudent from "../../features/teachingplan/StudentTeachingPlan";
import LectureStudent from "../../features/lectures/LectureStudent";
import AssignmentStudent from "../../features/assignments/AssignmentStudent";
import QuizStudent from "../../features/quiz/QuizStudent";
import StudyMaterialStudent from "../../features/materials/StudyMaterialStudent";
import DiscussionStudent from "../../features/discussion/DiscussionStudent";
import FeedbackStudent from "../../features/feedback/FeedbackStudent";

export default function StudentSubjectDetails() {

  const { id } = useParams();

  const [open, setOpen] =
    useState(false);

  const [ta, setTA] =
    useState(null);

  // FIX #23: a notification can open a tab directly, e.g. ?tab=assignments
  const [activeTab, setActiveTab] =
    useState(
      new URLSearchParams(window.location.search).get("tab") || "teachingplan"
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

      const res = await API.get(
        `/teaching-assignments/${id}/`
      );

      setTA(res.data);

    } catch (err) {

      console.log(
        "Subject fetch error:",
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
        No subject found
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
                {ta.course_name} -
                Year {ta.year_number}
              </h2>

              <h3>
                {ta.subject_name}
              </h3>

            </div>

            {/* ================= TABS ================= */}
            <div className="tabs">

              {/* TEACHING PLAN */}
              <button
                className={
                  activeTab === "teachingplan"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab(
                    "teachingplan"
                  )
                }
              >
                Teaching Plan
              </button>

              {/* LECTURES */}
              <button
                className={
                  activeTab === "lectures"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab(
                    "lectures"
                  )
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
                  setActiveTab(
                    "assignments"
                  )
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
                  setActiveTab(
                    "quiz"
                  )
                }
              >
                Online tests
              </button>

              {/* STUDY MATERIALS */}
              <button
                className={
                  activeTab === "materials"
                    ? "btn-primary"
                    : ""
                }
                onClick={() =>
                  setActiveTab(
                    "materials"
                  )
                }
              >
                Study Materials
              </button>
            
            {/* DISCUSSION */}
            <button
             className={
               activeTab === "discussion"
              ? "btn-primary"
               : ""
              }
           onClick={() => setActiveTab( "discussion" ) }> Discussion Forum  </button>

           <button
            className={ activeTab === "feedback" ? "btn-primary" : "" }
            onClick={() => setActiveTab("feedback")} >  Feedback </button>
            </div>

            {/* ================= CONTENT ================= */}

            {/* TEACHING PLAN */}
            {activeTab === "teachingplan" && (

              <TeachingPlanStudent
                ta={ta}
              />

            )}

            {/* LECTURES */}
            {activeTab === "lectures" && (

              <LectureStudent
                teachingId={id}
              />

            )}

            {/* ASSIGNMENTS */}
            {activeTab === "assignments" && (

              <AssignmentStudent
                teachingId={id}
              />

            )}

            {/* QUIZ */}
            {activeTab === "quiz" && (

              <QuizStudent
                teachingId={id}
              />

            )}

            {/* STUDY MATERIALS */}
            {activeTab === "materials" && (

              <StudyMaterialStudent
                teachingId={id}
              />

            )}

            {/* DISCUSSION */}
            {activeTab === "discussion" && (

            <DiscussionStudent
             teachingId={id}
              />)}
             
             {/* FEEDBACK */}
            {activeTab === "feedback" && ( <FeedbackStudent teachingId={id} /> )}
          </div>

        </div>

      </div>

    </div>
  );
}