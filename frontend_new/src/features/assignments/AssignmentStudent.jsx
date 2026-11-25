import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";

export default function AssignmentStudent({
  teachingId,
}) {

  const navigate = useNavigate();

  const user = JSON.parse(
    localStorage.getItem("user") || "{}"
  );

  // ================= STATES =================
  const [assignments, setAssignments] =
    useState([]);

  const [submissions, setSubmissions] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  // ✅ SEARCH
  const [search, setSearch] =
    useState("");

  // ✅ FILTER
  const [statusFilter, setStatusFilter] =
    useState("all");

  // ================= FETCH =================
  const fetchData = async () => {

    try {

      setLoading(true);

      // ================= ASSIGNMENTS =================
      const assignmentRes =
        await API.get(
          `/assignments/?teaching_assignment=${teachingId}`
        );

      const assignmentData =
        assignmentRes.data?.results ||
        assignmentRes.data ||
        [];

      setAssignments(
        assignmentData
      );

      // ================= SUBMISSIONS =================
      const submissionRes =
        await API.get(
          "/submissions/"
        );

      const submissionData =
        submissionRes.data?.results ||
        submissionRes.data ||
        [];

      // ONLY CURRENT STUDENT
      const mySubmissions =
        submissionData.filter(
          (s) =>
            (s.student?.id ||
              s.student) ===
            user.id
        );

      setSubmissions(
        mySubmissions
      );

    } catch (err) {

      console.log(
        "Fetch error:",
        err
      );

    } finally {

      setLoading(false);
    }
  };

  useEffect(() => {

    if (teachingId) {

      fetchData();
    }

  }, [teachingId]);

  // ================= FIND SUBMISSION =================
  const getSubmission = (
    assignmentId
  ) => {

    return submissions.find(
      (s) =>
        (s.assignment?.id ||
          s.assignment) ===
        assignmentId
    );
  };

  // ================= FILTERED ASSIGNMENTS =================
  const filteredAssignments =
    assignments.filter((a) => {

      const submission =
        getSubmission(a.id);

      // SEARCH
      const matchesSearch =

        a.title
          ?.toLowerCase()
          .includes(
            search.toLowerCase()
          )

        ||

        a.teacher_name
          ?.toLowerCase()
          .includes(
            search.toLowerCase()
          )

        ||

        a.description
          ?.toLowerCase()
          .includes(
            search.toLowerCase()
          );

      // STATUS
      let status =
        "not_submitted";

      if (submission) {

        status =
          submission.status;
      }

      const matchesStatus =

        statusFilter === "all"

        ||

        status ===
        statusFilter;

      return (
        matchesSearch
        &&
        matchesStatus
      );
    });

  return (
    <div className="card">

      {/* ================= HEADER ================= */}
      <div
        style={{
          display: "flex",
          justifyContent:
            "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >

        <h3>
          Assignments
        </h3>

      </div>

      {/* ================= SEARCH + FILTER ================= */}
      <div
        style={{
          display: "flex",
          gap: "12px",
          marginBottom: "20px",
          flexWrap: "wrap",
        }}
      >

        {/* SEARCH */}
        <input
          type="text"
          placeholder="Search assignment..."
          value={search}
          onChange={(e) =>
            setSearch(
              e.target.value
            )
          }
          style={{
            flex: 1,
            minWidth: "220px",
          }}
        />

        {/* FILTER */}
        <select
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(
              e.target.value
            )
          }
        >

          <option value="all">
            All
          </option>

          <option value="pending">
            Pending
          </option>

          <option value="evaluated">
            Evaluated
          </option>

          <option value="late">
            Late
          </option>

          <option value="not_submitted">
            Not Submitted
          </option>

        </select>

      </div>

      {/* ================= LOADING ================= */}
      {loading ? (

        <p>
          Loading assignments...
        </p>

      ) : filteredAssignments.length === 0 ? (

        <p>
          No assignments found
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

                <th>
                  Title
                </th>

                <th>
                  Description
                </th>

                <th>
                  Due Date
                </th>

                <th>
                  Total Marks
                </th>

                <th>
                  Teacher
                </th>

                <th>
                  File
                </th>

                <th>
                  Status
                </th>

                <th>
                  Obtained Marks
                </th>

                <th>
                  Feedback
                </th>

                <th>
                  Action
                </th>

              </tr>

            </thead>

            <tbody>

              {filteredAssignments.map((a) => {

                const submission =
                  getSubmission(
                    a.id
                  );

                return (

                  <tr key={a.id}>

                    {/* TITLE */}
                    <td>
                      {a.title}
                    </td>

                    {/* DESCRIPTION */}
                    <td>
                      {a.description ||
                        "-"}
                    </td>

                    {/* DUE DATE */}
                    <td>

                      {a.due_date
                        ? new Date(
                            a.due_date
                          ).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: true })
                        : "-"}

                    </td>

                    {/* TOTAL MARKS */}
                    <td>
                      {a.total_marks}
                    </td>

                    {/* TEACHER */}
                    <td>
                      {a.teacher_name}
                    </td>

                    {/* FILE */}
                    <td>

                      {a.file ? (

                        <a
                          href={a.file}
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

                    {/* STATUS */}
                    <td>

                      {submission
                        ? submission.status
                        : "Not Submitted"}

                    </td>

                    {/* MARKS */}
                    <td>

                      {submission?.marks !==
                      null &&
                      submission?.marks !==
                        undefined

                        ? `${submission.marks}/${a.total_marks}`

                        : "-"}

                    </td>

                    {/* FEEDBACK */}
                    <td>

                      {submission?.feedback ||
                        "-"}

                    </td>

                    {/* ACTION */}
                    <td>

                      <button
                        className="btn-primary"
                        onClick={() =>
                          navigate(
                            `/assignments/${a.id}/submissions`
                          )
                        }
                      >

                        {submission
                          ? "View / Resubmit"
                          : "Submit"}

                      </button>

                    </td>

                  </tr>

                );
              })}

            </tbody>

          </table>

        </div>

      )}

    </div>
  );
}