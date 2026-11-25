import { useState } from "react";
import API from "../../api";

export default function FeedbackStudent({
  teachingId,
}) {

  const [rating, setRating] =
    useState("");

  const [message, setMessage] =
    useState("");

  const [loading, setLoading] =
    useState(false);

  const [success, setSuccess] =
    useState("");

  const submitFeedback = async () => {

    if (!message.trim()) {

      alert(
        "Please enter feedback"
      );

      return;
    }

    try {

      setLoading(true);

      await API.post(
        "/feedback/",
        {
          teaching_assignment:
            teachingId,

          rating:
            rating || null,

          message:
            message,
        }
      );

      setSuccess(
        "Feedback submitted successfully"
      );

      setRating("");
      setMessage("");

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
        Course Feedback
      </h3>

      <div
        style={{
          marginBottom: "15px",
        }}
      >

        <label>
          Rating
        </label>

        <select
          value={rating}
          onChange={(e) =>
            setRating(
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
            Select Rating
          </option>

          <option value="1">
            1 Star
          </option>

          <option value="2">
            2 Stars
          </option>

          <option value="3">
            3 Stars
          </option>

          <option value="4">
            4 Stars
          </option>

          <option value="5">
            5 Stars
          </option>

        </select>

      </div>

      <div>

        <label>
          Comments
        </label>

        <textarea
          rows={5}
          value={message}
          onChange={(e) =>
            setMessage(
              e.target.value
            )
          }
          placeholder="Write your feedback..."
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

    </div>
  );
}