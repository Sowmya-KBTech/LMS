import { useState } from "react";
import API from "../../api";

export default function FeedbackTeacher({
  teachingId,
  students,
}) {
  const [selectedStudent, setSelectedStudent] =
    useState("");

  const [message, setMessage] =
    useState("");

  const [loading, setLoading] =
    useState(false);

  const [success, setSuccess] =
    useState("");

  const submitFeedback = async () => {

    if (!selectedStudent) {
      alert("Please select a student");
      return;
    }

    if (!message.trim()) {
      alert("Please enter feedback");
      return;
    }

    try {

      setLoading(true);

      await API.post(
        "/feedback/",
        {
          teaching_assignment:
            teachingId,

          student:
            selectedStudent,

          message:
            message,
        }
      );

      setSuccess(
        "Feedback submitted successfully"
      );

      setMessage("");
      setSelectedStudent("");

      setTimeout(() => {
        setSuccess("");
      }, 3000);

    } catch (err) {

      console.error(err);

      alert(
        "Failed to submit feedback"
      );

    } finally {

      setLoading(false);
    }
  };

  return (

    <div className="card">

      <h3>
        Student Feedback
      </h3>

      {students.length === 0 ? (

        <p>
          No students enrolled.
        </p>

      ) : (

        <>
          <div
            style={{
              marginBottom: "15px",
            }}
          >

            <label>
              Student
            </label>

            <select
              value={selectedStudent}
              onChange={(e) =>
                setSelectedStudent(
                  e.target.value
                )
              }
              style={{
                width: "100%",
                padding: "10px",
                marginTop: "5px",
              }}
            >

              <option value="">
                Select Student
              </option>

              {students.map((s) => (

                <option
                  key={s.id}
                  value={s.student}
                >

                  {s.student_name}

                </option>

              ))}

            </select>

          </div>

          <div>

            <label>
              Feedback
            </label>

            <textarea
              rows={5}
              value={message}
              onChange={(e) =>
                setMessage(
                  e.target.value
                )
              }
              placeholder="Enter feedback for the student..."
              style={{
                width: "100%",
                padding: "10px",
                marginTop: "5px",
              }}
            />

          </div>

          {success && (

            <p
              style={{
                color: "green",
                marginTop: "10px",
              }}
            >

              {success}

            </p>

          )}

          <button
            className="btn-primary"
            onClick={submitFeedback}
            disabled={loading}
            style={{
              marginTop: "15px",
            }}
          >

            {loading
              ? "Submitting..."
              : "Submit Feedback"}

          </button>
        </>
      )}

    </div>
  );
}