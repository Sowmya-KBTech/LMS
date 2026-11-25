import { useEffect, useState } from "react";

import Icon from "../../components/Icon";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";
import "../../styles/FeedbackHistory.css";

export default function FeedbackHistory() {
  const [open, setOpen] = useState(false);
  const [feedbacks, setFeedbacks] = useState([]);
  const [loading, setLoading] = useState(true); 

  // FIX #35: a teacher needs to see WHO she sent feedback to
  const isTeacher =
    (JSON.parse(localStorage.getItem("user") || "{}").role || "").toLowerCase() === "teacher";

  useEffect(() => {
    fetchFeedbacks();
  }, []);

  const fetchFeedbacks = async () => {
    try {
      const res = await API.get("/feedback/");
      setFeedbacks(res.data?.results || res.data || []);
    } catch (err) {
      console.error("Feedback fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      {/* NAVBAR */}
      <Navbar setOpen={setOpen} />

      <div className="layout">
        {/* SIDEBAR */}
        <Sidebar open={open} setOpen={setOpen} />

        {/* MAIN */}
        <div className="main">
          {/* .content is the page's scroll container — without it a long
              list was cut off with no way to scroll */}
          <div className="content">
            <div className="header-box">
              <h1>Feedback history</h1>
              <p>All feedback across your subjects</p>
            </div>

            <div className="feedback-history">
              {loading ? (
                <div className="kb-card kb-at-empty" style={{ marginTop: 0 }}><div className="kb-at-spinner" /><b>Loading feedback…</b></div>
              ) : feedbacks.length === 0 ? (
                <div className="kb-card kb-at-empty" style={{ marginTop: 0 }}>
                  <span className="kb-at-empty-ico"><Icon name="chat" /></span>
                  <b>No feedback yet</b>
                  <span>Feedback shared between you and your teachers or students will appear here.</span>
                </div>
              ) : (
              <div className="fh-card">
                {feedbacks.map((f) => (
                  <div key={f.id} className={`fh-item ${f.direction}`}>
                    {/* direction tag */}
                    <span className="fh-chip">
                      {f.direction === "t2s"
                        ? "Teacher → Student"
                        : "Student → Teacher"}
                    </span>

                    {/* subject */}
                    <h4 className="fh-subject">{f.subject}</h4>

                    {/* meta row: who + rating */}
                    <div className="fh-meta">
                      {f.direction === "t2s" && (
                        <span className="fh-meta-item">
                          {isTeacher ? (
                            <><strong>To:</strong> {f.student_name || "Student not recorded"}</>
                          ) : (
                            <><strong>Teacher:</strong> {f.teacher_name}</>
                          )}
                        </span>
                      )}

                      {f.direction === "s2t" && (
                        <span className="fh-meta-item">
                          <strong>Student:</strong> {f.student_name}
                        </span>
                      )}

                      {f.rating && (
                        <span className="fh-rating">{f.rating}/5</span>
                      )}
                    </div>

                    {/* message */}
                    <p className="fh-message">{f.message}</p>

                    {/* date */}
                    <small className="fh-date">
                      {new Date(f.created_at).toLocaleString()}
                    </small>
                  </div>
                ))}
              </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}