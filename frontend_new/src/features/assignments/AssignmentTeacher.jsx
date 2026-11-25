import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";

export default function AssignmentTeacher({ teachingId }) {
  const navigate = useNavigate();

  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // ================= ADDED: editingAssignment state =================
  const [editingAssignment, setEditingAssignment] = useState(null);

  const [form, setForm] = useState({
    title: "",
    description: "",
    due_date: "",
    total_marks: 100,
    file: null,
  });

  // ================= FETCH =================
  const fetchAssignments = async () => {
    try {
      const res = await API.get(
        `/assignments/?teaching_assignment=${teachingId}`
      );
      setAssignments(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Fetch error", err);
    }
  };

  useEffect(() => {
    if (teachingId) {
      fetchAssignments();
    }
  }, [teachingId]);

  // ================= SUBMISSION COUNTS + POPUP =================
  const [allSubs, setAllSubs] = useState([]);      // my submissions (all assignments)
  const [classList, setClassList] = useState([]);  // students enrolled in this subject
  const [viewing, setViewing] = useState(null);    // assignment shown in the popup

  const idOf = (x) => (x && typeof x === "object" ? x.id : x);

  const fetchProgress = async () => {
    try {
      const [sRes, eRes] = await Promise.all([
        API.get("/submissions/"),
        API.get(`/enrollments/?teaching_assignment=${teachingId}`),
      ]);
      setAllSubs(sRes.data?.results || sRes.data || []);
      setClassList(eRes.data?.results || eRes.data || []);
    } catch (err) {
      console.log("Progress fetch error", err);
    }
  };

  useEffect(() => {
    if (teachingId) fetchProgress();
  }, [teachingId]);

  // who submitted / who did not, for one assignment
  const progressFor = (a) => {
    const subs = allSubs.filter((s) => Number(idOf(s.assignment)) === Number(a.id));
    const doneIds = new Set(subs.map((s) => Number(idOf(s.student))));
    const pending = classList.filter((e) => !doneIds.has(Number(idOf(e.student))));
    const overdue = !!a.due_date && new Date(a.due_date) < new Date();
    return { subs, pending, total: classList.length, overdue };
  };

  const fmtWhen = (iso) =>
    iso
      ? new Date(iso).toLocaleString("en-IN", {
          day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: true,
        })
      : "";

  // ================= HANDLE INPUT =================
  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  // ================= FILE =================
  const handleFileChange = (e) => {
    setForm({ ...form, file: e.target.files[0] });
  };

  // ================= RESET FORM =================
  const resetForm = () => {
    setForm({
      title: "",
      description: "",
      due_date: "",
      total_marks: 100,
      file: null,
    });
    setEditingAssignment(null);
    setShowForm(false);
  };

  // ================= TIMEZONE HELPER =================
  // Converts UTC date string → IST (UTC+5:30) datetime-local string for input prefill
  const toISTInputValue = (utcStr) => {
    if (!utcStr) return "";
    const utcMs = new Date(utcStr).getTime();
    const istMs = utcMs + 5.5 * 60 * 60 * 1000;
    return new Date(istMs).toISOString().slice(0, 16);
  };

  // Formats UTC date string → readable IST time for table display
  const formatISTDisplay = (utcStr) => {
    if (!utcStr) return "-";
    return new Date(utcStr).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  };

  // ================= HANDLE EDIT CLICK =================
  const handleEdit = (a) => {
    setEditingAssignment(a);
    setForm({
      title: a.title || "",
      description: a.description || "",
      // FIX: convert UTC → IST offset before slicing for datetime-local input
      due_date: toISTInputValue(a.due_date),
      total_marks: a.total_marks || 100,
      file: null, // can't prefill file input
    });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ================= CREATE =================
  const addAssignment = async () => {
    if (!form.title.trim()) {
      return alert("Enter assignment title");
    }

    try {
      setLoading(true);

      const fd = new FormData();
      fd.append("title", form.title);
      fd.append("description", form.description);
      fd.append("teaching_assignment", teachingId);
      fd.append("total_marks", form.total_marks);

      if (form.due_date) fd.append("due_date", form.due_date);
      if (form.file) fd.append("file", form.file);

      await API.post("/assignments/", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      alert("Assignment created successfully");
      resetForm();
      fetchAssignments();
    } catch (err) {
      console.log(err.response?.data);
      alert(JSON.stringify(err.response?.data || "Failed to create assignment"));
    } finally {
      setLoading(false);
    }
  };

  // ================= ADDED: UPDATE =================
  const updateAssignment = async () => {
    if (!form.title.trim()) {
      return alert("Enter assignment title");
    }

    try {
      setLoading(true);

      const fd = new FormData();
      fd.append("title", form.title);
      fd.append("description", form.description);
      fd.append("teaching_assignment", teachingId);
      fd.append("total_marks", form.total_marks);

      if (form.due_date) fd.append("due_date", form.due_date);
      // Only append file if a new one was selected
      if (form.file) fd.append("file", form.file);

      await API.patch(`/assignments/${editingAssignment.id}/`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      alert("Assignment updated successfully");
      resetForm();
      fetchAssignments();
    } catch (err) {
      console.log(err.response?.data);
      alert(JSON.stringify(err.response?.data || "Failed to update assignment"));
    } finally {
      setLoading(false);
    }
  };

  // ================= DELETE =================
  const deleteAssignment = async (id) => {
    if (!window.confirm("Delete this assignment?")) return;

    try {
      await API.delete(`/assignments/${id}/`);
      fetchAssignments();
      alert("Assignment deleted");
    } catch (err) {
      console.log(err);
      alert("Delete failed");
    }
  };

  return (
    <div className="card">

      {/* HEADER */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >
        <h3>Assignments</h3>

        <button
          className="btn-primary"
          onClick={() => {
            if (showForm) {
              resetForm();
            } else {
              setShowForm(true);
            }
          }}
        >
          {showForm ? "Cancel" : "+ Add Assignment"}
        </button>
      </div>

      {/* ================= FORM ================= */}
      {showForm && (
        <div
          style={{
            marginBottom: "20px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          {/* FORM HEADING */}
          <h4 style={{ margin: 0, color: "#555" }}>
            {editingAssignment ? "✏️ Edit Assignment" : "➕ New Assignment"}
          </h4>

          {/* TITLE */}
          <input
            type="text"
            name="title"
            placeholder="Assignment Title"
            value={form.title}
            onChange={handleChange}
          />

          {/* DUE DATE */}
          <input
            type="datetime-local"
            name="due_date"
            value={form.due_date}
            onChange={handleChange}
          />

          {/* MARKS */}
          <input
            type="number"
            name="total_marks"
            placeholder="Total Marks"
            value={form.total_marks}
            onChange={handleChange}
          />

          {/* DESCRIPTION */}
          <textarea
            rows="4"
            name="description"
            placeholder="Instructions / Description"
            value={form.description}
            onChange={handleChange}
          />

          {/* FILE */}
          <div>
            <input type="file" onChange={handleFileChange} />
            {/* Show existing file hint when editing */}
            {editingAssignment?.file && !form.file && (
              <p style={{ fontSize: "13px", color: "#888", margin: "4px 0 0" }}>
                Current file:{" "}
                <a href={editingAssignment.file} target="_blank" rel="noreferrer">
                  View existing file
                </a>{" "}
                — upload a new one to replace it
              </p>
            )}
          </div>

          {/* BUTTONS */}
          <div style={{ display: "flex", gap: "10px" }}>
            <button
              className="btn-primary"
              onClick={editingAssignment ? updateAssignment : addAssignment}
              disabled={loading}
            >
              {loading
                ? editingAssignment ? "Updating..." : "Creating..."
                : editingAssignment ? "Update Assignment" : "Create Assignment"}
            </button>

            {/* CANCEL EDIT */}
            {editingAssignment && (
              <button
                className="btn-delete"
                onClick={resetForm}
                disabled={loading}
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}

      {/* ================= LIST ================= */}
      {assignments.length === 0 ? (
        <p>No assignments added</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Due Date</th>
                <th>Marks</th>
                <th>Submitted</th>
                <th>Teacher</th>
                <th>File</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {assignments.map((a) => (
                <tr key={a.id}>

                  {/* TITLE */}
                  <td>{a.title}</td>

                  {/* DUE DATE — FIX: display in IST */}
                  <td>{formatISTDisplay(a.due_date)}</td>

                  {/* MARKS */}
                  <td>{a.total_marks}</td>

                  {/* SUBMITTED COUNT: click to open the popup */}
                  <td>
                    {(() => {
                      const { subs, total, overdue } = progressFor(a);
                      const all = total > 0 && subs.length >= total;
                      const tone = all
                        ? { bg: "#ecfdf3", fg: "#15803d", bd: "#bbf7d0" }
                        : overdue
                        ? { bg: "#fef2f2", fg: "#b91c1c", bd: "#fecaca" }
                        : { bg: "#fff7ed", fg: "#9a3412", bd: "#fed7aa" };
                      return (
                        <button
                          onClick={() => setViewing(a)}
                          title="View who has submitted"
                          style={{
                            background: tone.bg, color: tone.fg, border: `1px solid ${tone.bd}`,
                            borderRadius: 999, padding: "4px 12px", fontWeight: 700,
                            fontSize: 14, cursor: "pointer",
                          }}
                        >
                          {subs.length}/{total}
                        </button>
                      );
                    })()}
                  </td>

                  {/* TEACHER */}
                  <td>{a.teacher_name}</td>

                  {/* FILE */}
                  <td>
                    {a.file ? (
                      <a href={a.file} target="_blank" rel="noreferrer">
                        <button>Open</button>
                      </a>
                    ) : (
                      "-"
                    )}
                  </td>

                  {/* ACTIONS */}
                  <td>
                    <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>

                      {/* SUBMISSIONS */}
                      <button
                        onClick={() => setViewing(a)}
                      >
                        Submissions
                      </button>

                      {/* ADDED: EDIT BUTTON */}
                      <button
                        className="btn-edit"
                        onClick={() => handleEdit(a)}
                      >
                        Edit
                      </button>

                      {/* DELETE */}
                      <button
                        onClick={() => deleteAssignment(a.id)}
                        style={{
                          background: "red",
                          color: "white",
                          border: "none",
                          padding: "8px 12px",
                          borderRadius: "5px",
                          cursor: "pointer",
                        }}
                      >
                        Delete
                      </button>

                    </div>
                  </td>

                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ================= VIEW SUBMISSIONS POPUP ================= */}
      {viewing && (() => {
        const { subs, pending, overdue } = progressFor(viewing);
        const secRow = { fontSize: 12, fontWeight: 700, letterSpacing: 0.5, color: "#5D5A6B", background: "#f7f6fb", padding: "10px 8px 8px" };
        const cell = { padding: "10px 8px", borderBottom: "1px solid #f0eff5", fontSize: 14.5 };
        return (
          <div
            onClick={() => setViewing(null)}
            style={{
              position: "fixed", inset: 0, zIndex: 1000, display: "flex",
              alignItems: "center", justifyContent: "center",
              background: "rgba(23,21,31,0.45)", padding: 20,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: "#fff", borderRadius: 14, width: "100%", maxWidth: 560,
                maxHeight: "80vh", overflow: "auto", padding: "18px 20px",
                boxShadow: "0 20px 50px rgba(0,0,0,0.2)",
              }}
            >
              {/* header */}
              <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 12 }}>
                <div style={{ flex: 1 }}>
                  <b style={{ display: "block", fontSize: 16 }}>View submissions</b>
                  <span style={{ display: "block", fontSize: 13.5, color: "#5D5A6B", marginTop: 2 }}>
                    {viewing.title}
                  </span>
                </div>
                <button onClick={() => setViewing(null)}>Close</button>
              </div>

              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <tbody>
                  <tr><td colSpan={3} style={secRow}>SUBMITTED · {subs.length}</td></tr>
                  {subs.length === 0 && (
                    <tr><td colSpan={3} style={{ ...cell, color: "#85839A" }}>No one has submitted yet</td></tr>
                  )}
                  {subs.map((s) => (
                    <tr key={`s${s.id}`}>
                      <td style={cell}>{s.student_name}</td>
                      <td style={{ ...cell, color: "#5D5A6B", fontSize: 13.5 }}>
                        {s.student_roll_no || ""}
                        <div style={{ fontSize: 12.5, color: "#85839A" }}>{fmtWhen(s.submitted_at)}</div>
                      </td>
                      <td style={{ ...cell, textAlign: "right", fontWeight: 600 }}>
                        {s.marks != null ? `${s.marks}/${viewing.total_marks}` : (
                          <span style={{ color: "#b45309", fontWeight: 500 }}>Not graded</span>
                        )}
                      </td>
                    </tr>
                  ))}

                  <tr><td colSpan={3} style={secRow}>NOT SUBMITTED · {pending.length}</td></tr>
                  {pending.length === 0 && (
                    <tr><td colSpan={3} style={{ ...cell, color: "#15803d" }}>Everyone has submitted</td></tr>
                  )}
                  {pending.map((e) => (
                    <tr key={`p${e.id}`}>
                      <td style={{ ...cell, color: "#85839A" }}>{e.student_name}</td>
                      <td style={{ ...cell, color: "#85839A", fontSize: 13.5 }}>{e.student_roll_no || ""}</td>
                      <td style={{ ...cell, textAlign: "right", color: overdue ? "#b91c1c" : "#b45309" }}>
                        {overdue ? "Overdue" : "Pending"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* footer */}
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 14 }}>
                <span style={{ flex: 1, fontSize: 12.5, color: "#85839A" }}>
                  Open the full page to see files and give marks.
                </span>
                <button
                  className="btn-primary"
                  onClick={() => navigate(`/assignments/${viewing.id}/submissions`)}
                >
                  Grade submissions →
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}