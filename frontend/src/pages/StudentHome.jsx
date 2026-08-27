import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";

const API = "http://127.0.0.1:8000/api";

// ── inline styles matching teacher-dashboard.html design system ──
const S = {
  body: {
    fontFamily: "'Segoe UI', sans-serif",
    background: "#e8edf5",
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
  },
  wrapper: {
    paddingTop: 56, // navbar height
    flex: 1,
    padding: "28px",
    paddingTop: "84px",
    boxSizing: "border-box",
  },
  pageHeader: {
    textAlign: "center",
    marginBottom: 28,
  },
  h1: {
    fontSize: 22,
    color: "#1a1f2e",
    fontWeight: 700,
    margin: 0,
  },
  sub: {
    color: "#7a8499",
    fontSize: 13,
    marginTop: 4,
  },
  card: {
    background: "#fff",
    borderRadius: 14,
    padding: 24,
    marginBottom: 20,
    boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "#1a1f2e",
    marginBottom: 18,
  },
  formRow: {
    display: "flex",
    gap: 12,
    marginBottom: 14,
    flexWrap: "wrap",
  },
  formGroup: {
    display: "flex",
    flexDirection: "column",
    gap: 5,
    flex: 1,
    minWidth: 160,
  },
  label: {
    fontSize: 12,
    color: "#555",
    fontWeight: 500,
  },
  input: {
    background: "#1e2535",
    border: "1px solid #2e3648",
    borderRadius: 8,
    color: "#d4dae8",
    fontSize: 13,
    padding: "9px 12px",
    outline: "none",
    fontFamily: "inherit",
    width: "100%",
    boxSizing: "border-box",
  },
  textarea: {
    background: "#1e2535",
    border: "1px solid #2e3648",
    borderRadius: 8,
    color: "#d4dae8",
    fontSize: 13,
    padding: "9px 12px",
    outline: "none",
    fontFamily: "inherit",
    resize: "vertical",
    minHeight: 70,
    width: "100%",
    boxSizing: "border-box",
  },
  select: {
    background: "#1e2535",
    border: "1px solid #2e3648",
    borderRadius: 8,
    color: "#d4dae8",
    fontSize: 13,
    padding: "9px 12px",
    outline: "none",
    fontFamily: "inherit",
    width: "100%",
  },
  uploadArea: {
    border: "2px dashed #c5d0e8",
    borderRadius: 10,
    padding: 32,
    textAlign: "center",
    cursor: "pointer",
    color: "#8892a4",
    fontSize: 13,
    transition: "border-color 0.2s",
    position: "relative",
  },
  uploadIcon: { fontSize: 28, marginBottom: 8 },
  btn: {
    padding: "9px 20px",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    border: "none",
    fontFamily: "inherit",
    transition: "opacity 0.2s",
  },
  btnPrimary: { background: "#3d6ff5", color: "#fff" },
  btnSuccess: { background: "#22b14c", color: "#fff" },
  btnDanger: { background: "#ef4444", color: "#fff" },
  btnOutline: {
    background: "#fff",
    color: "#3d6ff5",
    border: "1.5px solid #3d6ff5",
  },
  btnSm: { padding: "5px 12px", fontSize: 12 },
  badge: {
    padding: "3px 10px",
    borderRadius: 20,
    fontSize: 11,
    fontWeight: 600,
    display: "inline-block",
  },
  tableWrap: {
    overflowX: "auto",
    borderRadius: 10,
    border: "1px solid #e8edf5",
  },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  th: {
    background: "#f4f7fc",
    color: "#7a8499",
    fontWeight: 600,
    padding: "12px 16px",
    textAlign: "left",
    fontSize: 12,
  },
  td: { padding: "12px 16px", color: "#333", borderTop: "1px solid #f0f2f7" },
  sectionSep: { border: "none", borderTop: "1px solid #f0f2f7", margin: "16px 0" },
  // status colors matching teacher-dashboard
  badgePending:  { background: "#fef3c7", color: "#92400e" },
  badgeEval:     { background: "#d1fae5", color: "#065f46" },
  badgeLate:     { background: "#fee2e2", color: "#991b1b" },
  badgeDraft:    { background: "#fef9c3", color: "#854d0e" },
};

// ── helper badge ──
function StatusBadge({ status }) {
  const map = {
    pending:   S.badgePending,
    evaluated: S.badgeEval,
    late:      S.badgeLate,
    draft:     S.badgeDraft,
  };
  const s = (status || "draft").toLowerCase();
  return (
    <span style={{ ...S.badge, ...(map[s] || S.badgeDraft) }}>
      {status}
    </span>
  );
}

export default function StudentSubmission() {
  const user     = JSON.parse(localStorage.getItem("user") || "{}");
  const token    = user?.token;
  const navigate = useNavigate();

  const [assignments,   setAssignments]   = useState([]);
  const [mySubmissions, setMySubmissions] = useState([]);
  const [selectedAsgn,  setSelectedAsgn]  = useState(null);
  const [file,          setFile]          = useState(null);
  const [textEntry,     setTextEntry]     = useState("");
  const [urlEntry,      setUrlEntry]      = useState("");
  const [loading,       setLoading]       = useState(false);
  const [msg,           setMsg]           = useState("");
  const [msgType,       setMsgType]       = useState("success"); // success | error
  const fileRef = useRef();

  const headers = {
    Authorization: `Token ${token}`,
  };

  // ── fetch all assignments for enrolled courses ──
  useEffect(() => {
    fetch(`${API}/learning/assignments/`, { headers })
      .then((r) => r.json())
      .then(setAssignments)
      .catch(console.error);

    fetch(`${API}/learning/submissions/?student=${user.id}`, { headers })
      .then((r) => r.json())
      .then(setMySubmissions)
      .catch(console.error);
  }, []);

  const alreadySubmitted = (asgnId) =>
    mySubmissions.find((s) => s.assignment === asgnId);

  const showMsg = (text, type = "success") => {
    setMsg(text);
    setMsgType(type);
    setTimeout(() => setMsg(""), 4000);
  };

  // ── submit handler ──
  const handleSubmit = async () => {
    if (!selectedAsgn) return showMsg("Please select an assignment.", "error");
    if (!file && !textEntry.trim() && !urlEntry.trim())
      return showMsg("Please upload a file or enter text/URL.", "error");

    setLoading(true);
    const formData = new FormData();
    formData.append("assignment", selectedAsgn.id);
    formData.append("student", user.id);
    if (file) formData.append("file", file);
    if (textEntry) formData.append("text_entry", textEntry);
    if (urlEntry)  formData.append("url_entry", urlEntry);

    try {
      const res = await fetch(`${API}/learning/submissions/`, {
        method: "POST",
        headers: { Authorization: `Token ${token}` },
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setMySubmissions((prev) => [...prev, data]);
        setFile(null);
        setTextEntry("");
        setUrlEntry("");
        setSelectedAsgn(null);
        showMsg("✅ Assignment submitted successfully! A receipt has been sent to your email.");
      } else {
        const err = await res.json();
        showMsg(JSON.stringify(err), "error");
      }
    } catch {
      showMsg("Network error. Please try again.", "error");
    } finally {
      setLoading(false);
    }
  };

  const isLate = (dueDate) => dueDate && new Date() > new Date(dueDate);

  const getStatus = (asgn) => {
    const sub = alreadySubmitted(asgn.id);
    if (!sub) return isLate(asgn.due_date) ? "late" : "pending";
    if (sub.marks !== undefined && sub.marks !== null) return "evaluated";
    return "submitted";
  };

  const countdown = (due) => {
    if (!due) return "No deadline";
    const diff = new Date(due) - new Date();
    if (diff <= 0) return "Deadline passed";
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    return `${d}d ${h}h remaining`;
  };

  return (
    <div style={S.body}>
      <Navbar />
      <div style={S.wrapper}>
        {/* ── Page header ── */}
        <div style={S.pageHeader}>
          <h1 style={S.h1}>LMS Student</h1>
          <p style={S.sub}>My Assignments &amp; Submissions</p>
        </div>

        {/* ── Alert message ── */}
        {msg && (
          <div
            style={{
              padding: "12px 18px",
              borderRadius: 10,
              marginBottom: 18,
              background: msgType === "success" ? "#d1fae5" : "#fee2e2",
              color:      msgType === "success" ? "#065f46" : "#991b1b",
              fontSize: 13,
              fontWeight: 500,
            }}
          >
            {msg}
          </div>
        )}

        {/* ── CARD 1: Assignments list + selection ── */}
        <div style={S.card}>
          <div style={S.cardTitle}>📋 Available Assignments</div>
          {assignments.length === 0 ? (
            <div style={{ color: "#8892a4", fontSize: 13 }}>
              No assignments available yet.
            </div>
          ) : (
            <div style={S.tableWrap}>
              <table style={S.table}>
                <thead>
                  <tr>
                    <th style={S.th}>Assignment</th>
                    <th style={S.th}>Course</th>
                    <th style={S.th}>Max Marks</th>
                    <th style={S.th}>Due Date</th>
                    <th style={S.th}>Time Left</th>
                    <th style={S.th}>Status</th>
                    <th style={S.th}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {assignments.map((asgn) => {
                    const status = getStatus(asgn);
                    const sub    = alreadySubmitted(asgn.id);
                    return (
                      <tr key={asgn.id}>
                        <td style={S.td}>
                          <strong>{asgn.title}</strong>
                          {asgn.description && (
                            <div style={{ fontSize: 11, color: "#8892a4", marginTop: 2 }}>
                              {asgn.description.slice(0, 60)}…
                            </div>
                          )}
                        </td>
                        <td style={S.td}>{asgn.course_title || asgn.course || "—"}</td>
                        <td style={S.td}>{asgn.max_marks}</td>
                        <td style={S.td}>
                          {asgn.due_date
                            ? new Date(asgn.due_date).toLocaleDateString()
                            : "—"}
                        </td>
                        <td style={{ ...S.td, color: isLate(asgn.due_date) ? "#991b1b" : "#166534", fontWeight: 500 }}>
                          {countdown(asgn.due_date)}
                        </td>
                        <td style={S.td}>
                          <StatusBadge status={status} />
                          {sub?.marks !== undefined && sub?.marks !== null && (
                            <span style={{ marginLeft: 6, fontSize: 12, color: "#166534", fontWeight: 600 }}>
                              {sub.marks}/{asgn.max_marks}
                            </span>
                          )}
                        </td>
                        <td style={S.td}>
                          {!sub ? (
                            <button
                              style={{ ...S.btn, ...S.btnPrimary, ...S.btnSm }}
                              onClick={() => setSelectedAsgn(asgn)}
                            >
                              Submit
                            </button>
                          ) : (
                            <button
                              style={{ ...S.btn, ...S.btnOutline, ...S.btnSm }}
                              onClick={() => setSelectedAsgn(asgn)}
                            >
                              View
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── CARD 2: Submit form (shown when assignment selected) ── */}
        {selectedAsgn && !alreadySubmitted(selectedAsgn.id) && (
          <div style={S.card}>
            <div style={S.cardTitle}>
              📤 Submit: {selectedAsgn.title}
            </div>

            {/* Assignment brief */}
            <div
              style={{
                background: "#f8faff",
                border: "1px solid #e0e8f8",
                borderRadius: 10,
                padding: 16,
                marginBottom: 18,
              }}
            >
              <div style={{ fontSize: 13, color: "#1a1f2e", marginBottom: 6 }}>
                <strong>Instructions:</strong>{" "}
                {selectedAsgn.description || "No instructions provided."}
              </div>
              <div style={{ fontSize: 12, color: "#7a8499", display: "flex", gap: 20, marginTop: 8, flexWrap: "wrap" }}>
                <span>📅 Due: <strong>{selectedAsgn.due_date ? new Date(selectedAsgn.due_date).toLocaleString() : "—"}</strong></span>
                <span>🏆 Max Marks: <strong>{selectedAsgn.max_marks}</strong></span>
                <span>📁 Allowed: <strong>{selectedAsgn.allowed_types || "PDF, DOCX"}</strong></span>
              </div>
            </div>

            {isLate(selectedAsgn.due_date) && (
              <div
                style={{
                  background: "#fee2e2",
                  borderRadius: 8,
                  padding: "10px 14px",
                  fontSize: 12,
                  color: "#991b1b",
                  fontWeight: 600,
                  marginBottom: 14,
                }}
              >
                ⚠️ Late submission — penalty may apply as per course policy.
              </div>
            )}

            {/* File Upload */}
            <div style={S.formRow}>
              <div style={{ ...S.formGroup, flex: 2 }}>
                <label style={S.label}>Upload File</label>
                <div
                  style={{
                    ...S.uploadArea,
                    borderColor: file ? "#22b14c" : "#c5d0e8",
                  }}
                  onClick={() => fileRef.current.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    setFile(e.dataTransfer.files[0]);
                  }}
                >
                  <div style={S.uploadIcon}>📁</div>
                  {file ? (
                    <div style={{ color: "#22b14c", fontWeight: 600 }}>
                      ✅ {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                    </div>
                  ) : (
                    <>
                      <div>Drag &amp; drop your file here, or click to browse</div>
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        {selectedAsgn.allowed_types || "PDF, DOCX, ZIP"} – Max 20MB
                      </div>
                    </>
                  )}
                  <input
                    ref={fileRef}
                    type="file"
                    style={{ display: "none" }}
                    onChange={(e) => setFile(e.target.files[0])}
                  />
                </div>
                {file && (
                  <button
                    style={{ ...S.btn, ...S.btnDanger, ...S.btnSm, marginTop: 6, alignSelf: "flex-start" }}
                    onClick={() => setFile(null)}
                  >
                    Remove File
                  </button>
                )}
              </div>
            </div>

            <hr style={S.sectionSep} />

            {/* Text Entry */}
            <div style={S.formGroup}>
              <label style={S.label}>Or Enter Text (Rich Text Entry)</label>
              <textarea
                style={{ ...S.textarea, minHeight: 100 }}
                placeholder="Paste your submission text here…"
                value={textEntry}
                onChange={(e) => setTextEntry(e.target.value)}
              />
            </div>

            <hr style={S.sectionSep} />

            {/* URL Entry */}
            <div style={S.formRow}>
              <div style={S.formGroup}>
                <label style={S.label}>Or Paste a URL (GitHub / Drive / External Link)</label>
                <input
                  style={S.input}
                  type="url"
                  placeholder="https://github.com/your-repo"
                  value={urlEntry}
                  onChange={(e) => setUrlEntry(e.target.value)}
                />
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
              <button
                style={{ ...S.btn, ...S.btnSuccess }}
                onClick={handleSubmit}
                disabled={loading}
              >
                {loading ? "Submitting…" : "✅ Submit Assignment"}
              </button>
              <button
                style={{ ...S.btn, ...S.btnOutline }}
                onClick={() => setSelectedAsgn(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ── CARD 3: My Submissions / Grades ── */}
        <div style={S.card}>
          <div style={S.cardTitle}>📊 My Submissions &amp; Grades</div>
          {mySubmissions.length === 0 ? (
            <div style={{ color: "#8892a4", fontSize: 13 }}>
              You have not submitted any assignments yet.
            </div>
          ) : (
            <div style={S.tableWrap}>
              <table style={S.table}>
                <thead>
                  <tr>
                    <th style={S.th}>Assignment</th>
                    <th style={S.th}>Submitted At</th>
                    <th style={S.th}>File</th>
                    <th style={S.th}>Status</th>
                    <th style={S.th}>Marks</th>
                    <th style={S.th}>Feedback</th>
                  </tr>
                </thead>
                <tbody>
                  {mySubmissions.map((sub) => (
                    <tr key={sub.id}>
                      <td style={S.td}>{sub.assignment_title || `Assignment #${sub.assignment}`}</td>
                      <td style={S.td}>
                        {sub.submitted_at
                          ? new Date(sub.submitted_at).toLocaleString()
                          : "—"}
                      </td>
                      <td style={S.td}>
                        {sub.file ? (
                          <a
                            href={`http://127.0.0.1:8000${sub.file}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ color: "#3d6ff5", fontSize: 12 }}
                          >
                            ⬇ Download
                          </a>
                        ) : sub.url_entry ? (
                          <a href={sub.url_entry} target="_blank" rel="noreferrer" style={{ color: "#3d6ff5", fontSize: 12 }}>
                            🔗 Link
                          </a>
                        ) : "Text Entry"}
                      </td>
                      <td style={S.td}>
                        <StatusBadge
                          status={
                            sub.marks !== undefined && sub.marks !== null
                              ? "evaluated"
                              : "pending"
                          }
                        />
                      </td>
                      <td style={S.td}>
                        {sub.marks !== undefined && sub.marks !== null ? (
                          <strong style={{ color: "#166534", fontSize: 15 }}>
                            {sub.marks} / {sub.max_marks || "—"}
                          </strong>
                        ) : (
                          <span style={{ color: "#8892a4" }}>Not graded</span>
                        )}
                      </td>
                      <td style={S.td}>
                        {sub.feedback ? (
                          <div
                            style={{
                              background: "#f8faff",
                              border: "1px solid #e0e8f8",
                              borderRadius: 8,
                              padding: "8px 12px",
                              fontSize: 12,
                              color: "#333",
                              maxWidth: 260,
                            }}
                          >
                            {sub.feedback}
                          </div>
                        ) : (
                          <span style={{ color: "#8892a4", fontSize: 12 }}>
                            Awaiting feedback
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
