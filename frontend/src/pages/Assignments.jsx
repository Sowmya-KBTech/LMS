// ===================== REACT IMPORTS =====================
import React, { useEffect, useState } from "react";

// ===================== API =====================
import API from "../api";


// ===================== STYLES =====================
const labelStyle = {
  display: "block",
  marginBottom: 6,
  fontSize: 12,
  fontWeight: 600,
  color: "#475569",
  letterSpacing: "0.3px",
};

const inputStyle = {
  width: "100%",
  padding: "10px 14px",
  borderRadius: 9,
  border: "1.5px solid #e2e8f0",
  fontSize: 13.5,
  color: "#1e293b",
  background: "#f8fafc",
  outline: "none",
  fontFamily: "inherit",
  boxSizing: "border-box",
  transition: "border-color 0.15s",
};


// ===================== HELPERS =====================
function formatDate(raw) {
  if (!raw) return "—";
  return new Date(raw).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function isOverdue(due_date) {
  return due_date && new Date(due_date) < new Date();
}


// ===================== SUB COMPONENTS =====================
function StatusBadge({ due_date }) {
  const overdue = isOverdue(due_date);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 10px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.5px",
        background: overdue ? "#fff1f2" : "#f0fdf4",
        color: overdue ? "#e11d48" : "#16a34a",
        border: `1px solid ${overdue ? "#fecdd3" : "#bbf7d0"}`,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: overdue ? "#e11d48" : "#16a34a",
        }}
      />
      {overdue ? "Overdue" : "Active"}
    </span>
  );
}

function AssignmentCard({ a, user, file, setFile, submitAssignment }) {
  const [expanded, setExpanded] = useState(false);
  const [hover, setHover] = useState(false);

  return (
    <div
      style={{
        background: "#ffffff",
        borderRadius: 16,
        border: `1.5px solid ${hover ? "#c7d2fe" : "#e2e8f0"}`,
        overflow: "hidden",
        transition: "all 0.2s ease",
        boxShadow: hover
          ? "0 8px 32px rgba(79,70,229,0.08)"
          : "0 1px 4px rgba(0,0,0,0.04)",
        transform: hover ? "translateY(-2px)" : "none",
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {/* ── top stripe ── */}
      <div
        style={{
          height: 4,
          background: isOverdue(a.due_date)
            ? "linear-gradient(90deg,#e11d48,#fb7185)"
            : "linear-gradient(90deg,#4f46e5,#818cf8)",
        }}
      />

      <div style={{ padding: "20px 24px" }}>

        {/* ── header row ── */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: 10,
          }}
        >
          <div>
            <h3
              style={{
                margin: 0,
                fontSize: 16,
                fontWeight: 700,
                color: "#1e293b",
                lineHeight: 1.3,
              }}
            >
              {a.title}
            </h3>
            <p style={{ margin: "5px 0 0", fontSize: 12.5, color: "#94a3b8" }}>
              Due&nbsp;
              <span
                style={{
                  color: isOverdue(a.due_date) ? "#e11d48" : "#64748b",
                  fontWeight: 500,
                }}
              >
                {formatDate(a.due_date)}
              </span>
            </p>
          </div>
          <StatusBadge due_date={a.due_date} />
        </div>

        {/* ── description ── */}
        {a.description && (
          <p
            style={{
              margin: "10px 0 0",
              fontSize: 13.5,
              color: "#64748b",
              lineHeight: 1.6,
              display: "-webkit-box",
              WebkitLineClamp: expanded ? "unset" : 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {a.description}
          </p>
        )}
        {a.description && a.description.length > 120 && (
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              marginTop: 6,
              background: "none",
              border: "none",
              color: "#4f46e5",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              padding: 0,
            }}
          >
            {expanded ? "Show less ↑" : "Read more ↓"}
          </button>
        )}

        {/* ── student submit ── */}
        {user.role === "student" && (
          <div
            style={{
              marginTop: 16,
              paddingTop: 16,
              borderTop: "1px solid #f1f5f9",
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
            }}
          >
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                padding: "8px 14px",
                borderRadius: 8,
                border: "1.5px dashed #c7d2fe",
                background: "#eef2ff",
                color: "#4f46e5",
                fontSize: 12.5,
                fontWeight: 600,
                cursor: "pointer",
                transition: "background 0.15s",
              }}
            >
              📎 {file ? file.name : "Attach file"}
              <input
                type="file"
                style={{ display: "none" }}
                onChange={(e) => setFile(e.target.files[0])}
              />
            </label>

            <button
              onClick={() => submitAssignment(a.id)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 18px",
                borderRadius: 8,
                background: "linear-gradient(135deg,#4f46e5,#6366f1)",
                color: "#fff",
                fontSize: 13,
                fontWeight: 600,
                border: "none",
                cursor: "pointer",
                boxShadow: "0 2px 8px rgba(79,70,229,0.25)",
                transition: "opacity 0.15s",
              }}
              onMouseEnter={(e) => (e.target.style.opacity = 0.88)}
              onMouseLeave={(e) => (e.target.style.opacity = 1)}
            >
              Submit ↗
            </button>
          </div>
        )}

      </div>
    </div>
  );
}


// ===================== MAIN COMPONENT =====================
function Assignments() {
  const user = JSON.parse(localStorage.getItem("user"));

  const [assignments, setAssignments] = useState([]);
  const [file,        setFile]        = useState(null);
  const [showForm,    setShowForm]    = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [toast,       setToast]       = useState(null);
  const [form,        setForm]        = useState({
    title: "",
    description: "",
    due_date: "",
  });

  // ── notify ──
  const notify = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  // ── fetch ──
  const fetchAssignments = async () => {
    setLoading(true);
    try {
      const res = await API.get("learning/assignments/");
      setAssignments(res.data);
    } catch {
      notify("Failed to load assignments", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAssignments();
  }, []);

  // ── create ──
  const createAssignment = async () => {
    if (!form.title) return;
    try {
      await API.post("learning/assignments/", form);
      setForm({ title: "", description: "", due_date: "" });
      setShowForm(false);
      notify("Assignment created!");
      fetchAssignments();
    } catch {
      notify("Create failed", "error");
    }
  };

  // ── submit ──
  const submitAssignment = async (assignmentId) => {
    if (!file) { notify("Please attach a file first", "error"); return; }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("assignment", assignmentId);
    try {
      await API.post("learning/submissions/", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      notify("Submitted successfully! 🎉");
      setFile(null);
    } catch {
      notify("Submission failed", "error");
    }
  };

  const active  = assignments.filter((a) => !isOverdue(a.due_date));
  const overdue = assignments.filter((a) =>  isOverdue(a.due_date));

  return (
    <div
      style={{
        padding: "80px 36px 60px",
        background: "#f8fafc",
        minHeight: "100vh",
        fontFamily: "'Inter',sans-serif",
      }}
    >

      {/* ── toast ── */}
      {toast && (
        <div
          style={{
            position: "fixed",
            top: 24,
            right: 24,
            zIndex: 999,
            padding: "12px 20px",
            borderRadius: 12,
            background: toast.type === "error" ? "#fff1f2" : "#f0fdf4",
            border: `1px solid ${toast.type === "error" ? "#fecdd3" : "#bbf7d0"}`,
            color: toast.type === "error" ? "#e11d48" : "#16a34a",
            fontSize: 13.5,
            fontWeight: 600,
            boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
            animation: "slideIn 0.25s ease",
          }}
        >
          {toast.msg}
        </div>
      )}

      <style>{`@keyframes slideIn{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}`}</style>

      {/* ── page header ── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: 32,
          maxWidth: 900,
        }}
      >
        <div>
          <p
            style={{
              margin: "0 0 4px",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "1.2px",
              color: "#94a3b8",
              textTransform: "uppercase",
            }}
          >
            Learning Management
          </p>
          <h1
            style={{
              margin: 0,
              fontSize: 28,
              fontWeight: 800,
              color: "#1e293b",
              letterSpacing: "-0.5px",
            }}
          >
            Assignments
          </h1>
          <p style={{ margin: "6px 0 0", fontSize: 13.5, color: "#94a3b8" }}>
            {assignments.length} total · {active.length} active · {overdue.length} overdue
          </p>
        </div>

        {user?.role === "teacher" && (
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 7,
              padding: "10px 20px",
              borderRadius: 10,
              background: showForm
                ? "#f1f5f9"
                : "linear-gradient(135deg,#4f46e5,#6366f1)",
              color: showForm ? "#64748b" : "#fff",
              fontSize: 13.5,
              fontWeight: 700,
              border: showForm ? "1.5px solid #e2e8f0" : "none",
              cursor: "pointer",
              boxShadow: showForm ? "none" : "0 4px 12px rgba(79,70,229,0.3)",
              transition: "all 0.2s",
            }}
          >
            {showForm ? "✕ Cancel" : "+ New Assignment"}
          </button>
        )}
      </div>

      {/* ── create form ── */}
      {user?.role === "teacher" && showForm && (
        <div
          style={{
            maxWidth: 900,
            marginBottom: 28,
            background: "#fff",
            borderRadius: 16,
            border: "1.5px solid #e0e7ff",
            padding: "24px 28px",
            boxShadow: "0 4px 20px rgba(79,70,229,0.07)",
          }}
        >
          <h3
            style={{
              margin: "0 0 20px",
              fontSize: 16,
              fontWeight: 700,
              color: "#4f46e5",
            }}
          >
            Create New Assignment
          </h3>

          <div style={{ display: "grid", gap: 14 }}>
            <div>
              <label style={labelStyle}>Title *</label>
              <input
                placeholder="e.g. Chapter 3 Quiz"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Description</label>
              <textarea
                placeholder="Add instructions or notes for students..."
                value={form.description}
                rows={3}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
                style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6 }}
              />
            </div>

            <div>
              <label style={labelStyle}>Due Date & Time</label>
              <input
                type="datetime-local"
                value={form.due_date}
                onChange={(e) =>
                  setForm({ ...form, due_date: e.target.value })
                }
                style={inputStyle}
              />
            </div>

            <div
              style={{
                display: "flex",
                gap: 10,
                justifyContent: "flex-end",
                paddingTop: 4,
              }}
            >
              <button
                onClick={() => setShowForm(false)}
                style={{
                  padding: "9px 18px",
                  borderRadius: 8,
                  background: "#f8fafc",
                  border: "1.5px solid #e2e8f0",
                  color: "#64748b",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                onClick={createAssignment}
                disabled={!form.title}
                style={{
                  padding: "9px 22px",
                  borderRadius: 8,
                  background: form.title
                    ? "linear-gradient(135deg,#4f46e5,#6366f1)"
                    : "#e2e8f0",
                  color: form.title ? "#fff" : "#94a3b8",
                  fontSize: 13,
                  fontWeight: 700,
                  border: "none",
                  cursor: form.title ? "pointer" : "not-allowed",
                  boxShadow: form.title
                    ? "0 2px 8px rgba(79,70,229,0.25)"
                    : "none",
                  transition: "all 0.2s",
                }}
              >
                Create Assignment
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── loading ── */}
      {loading && (
        <div
          style={{
            textAlign: "center",
            padding: 60,
            color: "#94a3b8",
            fontSize: 14,
          }}
        >
          Loading assignments...
        </div>
      )}

      {/* ── empty state ── */}
      {!loading && assignments.length === 0 && (
        <div
          style={{
            maxWidth: 900,
            textAlign: "center",
            padding: "60px 20px",
            background: "#fff",
            borderRadius: 16,
            border: "1.5px dashed #e2e8f0",
          }}
        >
          <div style={{ fontSize: 40, marginBottom: 12 }}>📝</div>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "#1e293b" }}>
            No assignments yet
          </p>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "#94a3b8" }}>
            {user?.role === "teacher"
              ? "Create your first assignment above."
              : "Check back later."}
          </p>
        </div>
      )}

      {/* ── active section ── */}
      {active.length > 0 && (
        <div style={{ maxWidth: 900, marginBottom: 28 }}>
          <p
            style={{
              margin: "0 0 14px",
              fontSize: 10.5,
              fontWeight: 700,
              color: "#16a34a",
              letterSpacing: "1px",
              textTransform: "uppercase",
            }}
          >
            ● Active ({active.length})
          </p>
          <div style={{ display: "grid", gap: 14 }}>
            {active.map((a) => (
              <AssignmentCard
                key={a.id}
                a={a}
                user={user}
                file={file}
                setFile={setFile}
                submitAssignment={submitAssignment}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── overdue section ── */}
      {overdue.length > 0 && (
        <div style={{ maxWidth: 900 }}>
          <p
            style={{
              margin: "0 0 14px",
              fontSize: 10.5,
              fontWeight: 700,
              color: "#e11d48",
              letterSpacing: "1px",
              textTransform: "uppercase",
            }}
          >
            ● Overdue ({overdue.length})
          </p>
          <div style={{ display: "grid", gap: 14 }}>
            {overdue.map((a) => (
              <AssignmentCard
                key={a.id}
                a={a}
                user={user}
                file={file}
                setFile={setFile}
                submitAssignment={submitAssignment}
              />
            ))}
          </div>
        </div>
      )}

    </div>
  );
}

export default Assignments;