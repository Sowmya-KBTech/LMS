import { useEffect, useState } from "react";
import {
  useParams,
  useNavigate,
} from "react-router-dom";

import API from "../../api";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import "../../App.css";

export default function AssignmentSubmissions() {

  const { id } = useParams();

  const navigate =
    useNavigate();

  const user = JSON.parse(
    localStorage.getItem("user") || "{}"
  );

  const [open, setOpen] =
    useState(false);

  const [submissions, setSubmissions] =
    useState([]);

  const [assignment, setAssignment] =
    useState(null);

  const [file, setFile] =
    useState(null);

  const [loading, setLoading] =
    useState(false);

  const [grading, setGrading] =
    useState(false);

  // FIX #2: everyone enrolled in this subject (teacher view only)
  const [enrolled, setEnrolled] =
    useState([]);

  // ================= FETCH =================
  const fetchData = async () => {

    try {

      // ASSIGNMENT
      const assignmentRes =
        await API.get(
          `/assignments/${id}/`
        );

      setAssignment(
        assignmentRes.data
      );

      // SUBMISSIONS
      const res = await API.get(
        `/submissions/?assignment=${id}`
      );

      setSubmissions(
        res.data?.results ||
        res.data ||
        []
      );

      // FIX #2: load the class list so we can show who has NOT submitted
      if (user.role === "teacher") {
        const ta = assignmentRes.data?.teaching_assignment;
        const taId = typeof ta === "object" ? ta?.id : ta;
        if (taId) {
          const enr = await API.get(
            `/enrollments/?teaching_assignment=${taId}`
          );
          setEnrolled(enr.data?.results || enr.data || []);
        }
      }

    } catch (err) {

      console.log(
        "Fetch error:",
        err
      );
    }
  };

  useEffect(() => {

    if (id) {

      fetchData();
    }

  }, [id]);

  // ================= SUBMIT =================
  const submitAssignment = async () => {

    if (!file) {

      return alert(
        "Please upload a file"
      );
    }

    try {

      setLoading(true);

      const fd = new FormData();

      fd.append(
        "assignment",
        id
      );

      fd.append(
        "file",
        file
      );

      await API.post(
        "/submissions/",
        fd,
        {
          headers: {
            "Content-Type":
              "multipart/form-data",
          },
        }
      );

      alert(
        "Assignment submitted successfully"
      );

      setFile(null);

      fetchData();

    } catch (err) {

      console.log(
        err.response?.data
      );

      alert(
        JSON.stringify(
          err.response?.data ||
          "Submission failed"
        )
      );

    } finally {

      setLoading(false);
    }
  };

  // ================= GRADE =================
  const updateSubmission = async (
    submissionId,
    marks,
    feedback
  ) => {

    if (
      assignment &&
      Number(marks) >
      Number(
        assignment.total_marks
      )
    ) {

      return alert(
        `Marks cannot exceed ${assignment.total_marks}`
      );
    }

    try {

      setGrading(true);

      await API.patch(
        `/submissions/${submissionId}/`,
        {
          marks,
          feedback,
        }
      );

      alert(
        "Submission graded successfully"
      );

      fetchData();

    } catch (err) {

      console.log(err);

      alert(
        "Failed to update submission"
      );

    } finally {

      setGrading(false);
    }
  };

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

            <div className="card">

              {/* HEADER */}
              <div
                style={{
                  marginBottom:
                    "20px",
                }}
              >

                {/* BACK */}
                <button
                  className="btn-primary"
                  style={{
                    marginBottom:
                      "15px",
                  }}
                  onClick={() =>
                    navigate(-1)
                  }
                >
                  ← Back
                </button>

                <h2>
                  Assignment
                  Submissions
                </h2>

                {assignment && (

                  <div>

                    <p>
                      <strong>
                        Assignment:
                      </strong>{" "}
                      {assignment.title}
                    </p>

                    <p>
                      <strong>
                        Total Marks:
                      </strong>{" "}
                      {
                        assignment.total_marks
                      }
                    </p>

                  </div>

                )}

              </div>

              {/* STUDENT SUBMISSION */}
              {user.role ===
                "student" && (

                <div
                  style={{
                    marginBottom:
                      "20px",
                    display: "flex",
                    gap: "10px",
                    flexWrap:
                      "wrap",
                  }}
                >

                  <input
                    type="file"
                    onChange={(e) =>
                      setFile(
                        e.target
                          .files[0]
                      )
                    }
                  />

                  <button
                    className="btn-primary"
                    onClick={
                      submitAssignment
                    }
                    disabled={
                      loading
                    }
                  >

                    {loading
                      ? "Submitting..."
                      : "Submit / Resubmit"}

                  </button>

                </div>

              )}

              {/* FIX #2: submitted / not submitted summary (teacher) */}
              {user.role === "teacher" && enrolled.length > 0 && (() => {
                const idOf = (x) => (typeof x === "object" ? x?.id : x);
                const done = new Set(submissions.map((s) => Number(idOf(s.student))));
                const pending = enrolled.filter((e) => !done.has(Number(idOf(e.student))));
                const overdue =
                  assignment?.due_date && new Date(assignment.due_date) < new Date();
                return (
                  <div
                    style={{
                      background: "#fff",
                      border: "1px solid #e4e2ec",
                      borderRadius: 12,
                      padding: "14px 16px",
                      margin: "0 0 16px",
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: 15.5 }}>
                      Submitted {enrolled.length - pending.length} of {enrolled.length}
                      <span style={{ fontWeight: 500, color: pending.length ? "#b45309" : "#15803d" }}>
                        {" · "}
                        {pending.length ? `Not submitted ${pending.length}` : "Everyone has submitted"}
                      </span>
                    </div>
                    {pending.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
                        {pending.map((e) => (
                          <span
                            key={e.id}
                            style={{
                              fontSize: 13.5,
                              padding: "5px 10px",
                              borderRadius: 999,
                              background: overdue ? "#fef2f2" : "#fff7ed",
                              color: overdue ? "#b91c1c" : "#9a3412",
                              border: `1px solid ${overdue ? "#fecaca" : "#fed7aa"}`,
                            }}
                          >
                            {e.student_name}
                            {e.student_roll_no ? ` · ${e.student_roll_no}` : ""}
                            {overdue ? " · Overdue" : " · Pending"}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* TABLE */}
              {submissions.length ===
              0 ? (

                <p>
                  No submissions
                  yet
                </p>

              ) : (

                <div
                  style={{
                    overflowX:
                      "auto",
                  }}
                >

                  <table>

                    <thead>

                      <tr>

                        <th>
                          Student
                        </th>

                        <th>
                          Roll No
                        </th>

                        <th>
                          File
                        </th>

                        <th>
                          Submitted
                        </th>

                        <th>
                          Status
                        </th>

                        <th>
                          Marks
                        </th>

                        <th>
                          Feedback
                        </th>

                        {user.role ===
                          "teacher" && (

                          <th>
                            Actions
                          </th>

                        )}

                      </tr>

                    </thead>

                    <tbody>

                      {submissions.map(
                        (s) => (

                          <tr
                            key={s.id}
                          >

                            <td>
                              {
                                s.student_name
                              }
                            </td>

                            <td>
                              {s.student_roll_no ||
                                "-"}
                            </td>

                            <td>

                              {s.file ? (

                                <a
                                  href={
                                    s.file
                                  }
                                  target="_blank"
                                  rel="noreferrer"
                                >

                                  <button>
                                    Open
                                  </button>

                                </a>

                              ) : (

                                "-"
                              )}

                            </td>

                            <td>

                              {s.submitted_at
                                ? new Date(
                                    s.submitted_at
                                  ).toLocaleString()
                                : "-"}

                            </td>

                            <td>
                              {s.status}
                            </td>

                            <td>

                              {s.marks !==
                              null
                                ? `${s.marks}/${assignment?.total_marks}`
                                : "Not graded"}

                            </td>

                            <td>
                              {s.feedback ||
                                "-"}

                            </td>

                            {/* TEACHER */}
                            {user.role ===
                              "teacher" && (

                              <td>

                                <div
                                  style={{
                                    display:
                                      "flex",
                                    flexDirection:
                                      "column",
                                    gap: "8px",
                                    minWidth:
                                      "220px",
                                  }}
                                >

                                  <input
                                    type="number"
                                    placeholder="Marks"
                                    defaultValue={
                                      s.marks ||
                                      ""
                                    }
                                    id={`marks-${s.id}`}
                                  />

                                  <textarea
                                    placeholder="Feedback"
                                    defaultValue={
                                      s.feedback ||
                                      ""
                                    }
                                    id={`feedback-${s.id}`}
                                    rows="3"
                                  />

                                  <button
                                    className="btn-primary"
                                    disabled={
                                      grading
                                    }
                                    onClick={() =>
                                      updateSubmission(
                                        s.id,

                                        document.getElementById(
                                          `marks-${s.id}`
                                        ).value,

                                        document.getElementById(
                                          `feedback-${s.id}`
                                        ).value
                                      )
                                    }
                                  >

                                    Save Evaluation

                                  </button>

                                </div>

                              </td>

                            )}

                          </tr>

                        )
                      )}

                    </tbody>

                  </table>

                </div>

              )}

            </div>

          </div>

        </div>

      </div>

    </div>
  );
}