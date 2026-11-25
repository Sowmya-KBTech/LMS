import { useEffect, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";

import API from "../../api";

import "../../App.css";

export default function HodAllocation() {

  const [open, setOpen] = useState(false);

  const [department, setDepartment] = useState("");
  const [courses, setCourses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);

  const [course, setCourse] = useState("");
  const [semester, setSemester] = useState("1");

  const [picked, setPicked] = useState({});

  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);

  const load = (courseId, sem) => {
    setLoading(true);

    const q = new URLSearchParams();
    if (courseId) q.set("course", courseId);
    if (sem) q.set("semester", sem);

    API.get(`/users/hod/allocation/?${q.toString()}`)
      .then((res) => {
        const data = res.data || {};
        setDepartment(data.department || "");
        setCourses(data.courses || []);
        setSubjects(data.subjects || []);
        setTeachers(data.teachers || []);

        if (!courseId && data.selected_course) {
          setCourse(String(data.selected_course));
        }

        const seed = {};
        (data.subjects || []).forEach((s) => {
          seed[s.subject_id] = s.assigned_teacher_id || "";
        });
        setPicked(seed);
      })
      .catch((err) => {
        console.log("allocation load error:", err);
        alert("Could not load allocation. Are you an HOD?");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(course, semester);
    // eslint-disable-next-line
  }, [course, semester]);

  const assign = async (subjectId) => {
    const teacherId = picked[subjectId];

    if (!teacherId) {
      alert("Please pick a teacher first.");
      return;
    }

    setSavingId(subjectId);
    try {
      const res = await API.post("/users/hod/allocate/", {
        subject_id: subjectId,
        teacher_id: teacherId,
      });

      alert(res.data?.detail || "Assigned.");

      setSubjects((prev) =>
        prev.map((s) =>
          s.subject_id === subjectId
            ? {
                ...s,
                assigned_teacher_id: res.data?.assigned_teacher_id ?? s.assigned_teacher_id,
                assigned_teacher_name: res.data?.assigned_teacher_name ?? s.assigned_teacher_name,
              }
            : s
        )
      );
    } catch (err) {
      console.log("assign error:", err);
      alert(err.response?.data?.detail || "Could not assign.");
    } finally {
      setSavingId(null);
    }
  };

  const assignedCount = subjects.filter((s) => s.assigned_teacher_id).length;
  const missingCount = subjects.length - assignedCount;
  const allAssigned = subjects.length > 0 && missingCount === 0;

  const courseName =
    courses.find((c) => String(c.id) === String(course))?.name || "";

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            <div className="header-box">

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  flexWrap: "wrap",
                }}
              >
                <h2 style={{ margin: 0 }}>Faculty Allocation</h2>

                {department && (
                  <span
                    style={{
                      background: "#E3DCFA",
                      color: "#4338ca",
                      fontSize: "14px",
                      fontWeight: 600,
                      padding: "3px 12px",
                      borderRadius: "999px",
                    }}
                  >
                    {department}
                  </span>
                )}
              </div>

              <p>All subjects in a class — you can assign your own department's; others are shown for oversight</p>

            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                margin: "0 0 16px",
                flexWrap: "wrap",
              }}
            >
              <label style={{ fontSize: "15px", color: "#5D5A6B" }}>Course</label>

              <select
                value={course}
                onChange={(e) => setCourse(e.target.value)}
                style={{ minWidth: "170px" }}
              >
                {courses.length === 0 && <option value="">—</option>}
                {courses.map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.name}
                  </option>
                ))}
              </select>

              <label style={{ fontSize: "15px", color: "#5D5A6B" }}>Semester</label>

              <select
                value={semester}
                onChange={(e) => setSemester(e.target.value)}
                style={{ minWidth: "140px" }}
              >
                {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
                  <option key={n} value={String(n)}>
                    Semester {n}
                  </option>
                ))}
              </select>

              {!loading && (
                <span
                  style={{
                    marginLeft: "auto",
                    fontSize: "14px",
                    color: "#85839A",
                  }}
                >
                  {subjects.length} subjects · {assignedCount} assigned
                </span>
              )}
            </div>

            {!loading && subjects.length > 0 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  margin: "0 0 16px",
                  padding: "10px 14px",
                  borderRadius: "10px",
                  fontSize: "14.5px",
                  fontWeight: 600,
                  background: allAssigned ? "#ecfdf3" : "#fffbeb",
                  color: allAssigned ? "#15803d" : "#8A4B0A",
                  border: `1px solid ${allAssigned ? "#bbf7d0" : "#fde68a"}`,
                }}
              >
                <span style={{ fontSize: "15px" }}>{allAssigned ? "✓" : "⚠"}</span>
                {allAssigned
                  ? `All subjects in ${courseName} Semester ${semester} are assigned.`
                  : `${missingCount} of ${subjects.length} subjects not yet assigned in ${courseName} Semester ${semester}.`}
              </div>
            )}

            {loading ? (

              <div className="card">
                <p style={{ color: "#85839A" }}>Loading…</p>
              </div>

            ) : subjects.length === 0 ? (

              <div className="card">
                <p style={{ color: "#5D5A6B" }}>
                  No subjects for this course in Semester {semester}.
                </p>
              </div>

            ) : (

              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>

                {subjects.map((s) => {

                  const isAssigned = !!s.assigned_teacher_id;

                  return (
                    <div
                      key={s.subject_id}
                      className="card"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "14px",
                        flexWrap: "wrap",
                        padding: "14px 16px",
                        background: s.editable ? "#fff" : "#fafafa",
                      }}
                    >

                      <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                        <div style={{ fontWeight: 600, color: "#17151F" }}>
                          {s.subject_name}
                        </div>
                        <div
                          style={{
                            fontSize: "13.5px",
                            color: "#5D5A6B",
                            marginTop: "2px",
                          }}
                        >
                          {s.code ? `${s.code} · ` : ""}
                          {s.course_name} · Year {s.year_number}
                          {!s.editable && s.owner_department
                            ? ` · Managed by ${s.owner_department}`
                            : ""}
                        </div>
                      </div>

                      {s.editable ? (
                        <>
                          <select
                            value={picked[s.subject_id] || ""}
                            onChange={(e) =>
                              setPicked((prev) => ({
                                ...prev,
                                [s.subject_id]: e.target.value,
                              }))
                            }
                            style={{ flex: "0 1 190px" }}
                          >
                            <option value="">Select teacher</option>
                            {teachers.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name}{t.is_me ? " (You)" : ""}
                              </option>
                            ))}
                          </select>

                          <button
                            className="btn-primary"
                            onClick={() => assign(s.subject_id)}
                            disabled={savingId === s.subject_id}
                          >
                            {savingId === s.subject_id ? "Saving…" : "Assign"}
                          </button>
                        </>
                      ) : (
                        <span
                          style={{
                            flex: "0 1 190px",
                            fontSize: "13px",
                            color: "#85839A",
                            fontStyle: "italic",
                          }}
                        >
                          {s.owner_department
                            ? `Managed by ${s.owner_department}`
                            : "No owner department"}
                        </span>
                      )}

                      <span
                        style={{
                          fontSize: "13px",
                          fontWeight: 600,
                          padding: "4px 10px",
                          borderRadius: "999px",
                          background: isAssigned ? "#ecfdf3" : "#fffbeb",
                          color: isAssigned ? "#15803d" : "#8A4B0A",
                        }}
                      >
                        {isAssigned
                          ? `Assigned: ${s.assigned_teacher_name}`
                          : "Unassigned"}
                      </span>

                    </div>
                  );
                })}

              </div>

            )}

          </div>

        </div>

      </div>

    </div>
  );
}