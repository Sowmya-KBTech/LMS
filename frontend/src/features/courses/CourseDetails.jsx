import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function CourseDetails() {

  const { id } = useParams();

  const navigate = useNavigate();

  const user = JSON.parse(
    localStorage.getItem("user") || "{}"
  );

  const [open, setOpen] = useState(false);
  const [course, setCourse] = useState(null);
  const [years, setYears] = useState([]);
  const [year, setYear] = useState("");
  const [yearId, setYearId] = useState("");
  const [subject, setSubject] = useState("");
  const [code, setCode] = useState("");
  const [semester, setSemester] = useState("");
  const [credits, setCredits] = useState("");
  const [weeklyHours, setWeeklyHours] = useState("");
  const [isElective, setIsElective] = useState(false);
  const [department, setDepartment] = useState("");
  const [departments, setDepartments] = useState([]);

  // ================= EDIT SUBJECT =================
  const [editingSubjectId, setEditingSubjectId] = useState(null);

  // full-page loader: first load only
  const [loading, setLoading] = useState(true);

  // button-level busy flag (no page-wide spinner)
  const [saving, setSaving] = useState(false);

  // ================= INIT (course + years only) =================
  useEffect(() => {

    if (id) { loadCourseAndYears(); }
  }, [id]);

  // ================= LOAD DEPARTMENTS (for the subject dropdown) =================
  useEffect(() => {
    API.get("/users/departments/")
      .then((res) => setDepartments(res.data?.results || res.data || []))
      .catch((err) => console.log("departments error:", err));
  }, []);

  // ================= LOAD COURSE + YEARS =================
  const loadCourseAndYears = async () => {

    try {

      setLoading(true);

      const c = await API.get(
        `/courses/${id}/`
      );

      setCourse(c.data);

      const y = await API.get(
        `/years/?course=${id}`
      );

      setYears(
        y.data?.results ||
        y.data ||
        []
      );

    } catch (err) {

      console.error(
        "Course details error:",
        err
      );

    } finally {

      setLoading(false);
    }
  };

  // ================= SEMESTER -> YEAR DERIVATION =================
  // A semester fully determines the year: Sem 1-2 -> Year 1, 3-4 -> Year 2,
  // 5-6 -> Year 3, 7-8 -> Year 4. So the user picks the SEMESTER and the year
  // is computed automatically. This makes an impossible combo (e.g. Year 2 +
  // Semester 2) impossible to enter - which is what caused mis-filed subjects.
  const yearNumberForSemester = (sem) =>
    sem ? Math.ceil(Number(sem) / 2) : null;

  // when semester changes, set it AND resolve the matching Year row -> yearId
  const handleSemesterChange = (value) => {
    setSemester(value);

    const yearNum = yearNumberForSemester(value);
    if (!yearNum) {
      setYearId("");
      return;
    }

    const match = years.find(
      (y) => Number(y.year_number) === yearNum
    );
    setYearId(match ? String(match.id) : "");
  };

  // for the label + validation
  const derivedYearNumber = yearNumberForSemester(semester);
  const derivedYearExists = derivedYearNumber
    ? years.some((y) => Number(y.year_number) === derivedYearNumber)
    : false;

  // ================= LOCAL: upsert a subject into years =================
  const upsertSubjectInYears = (subj) => {

    setYears((prev) => {

      // remove any existing copy (edit / moved year)
      let next = prev.map((y) => ({
        ...y,
        subjects: (y.subjects || []).filter(
          (s) => s.id !== subj.id
        ),
      }));

      // insert into its target year, keep name order (matches backend)
      next = next.map((y) => {

        if (y.id === subj.year) {

          const list = [
            ...(y.subjects || []),
            subj,
          ].sort((a, b) =>
            (a.name || "").localeCompare(
              b.name || ""
            )
          );

          return { ...y, subjects: list };
        }

        return y;
      });

      return next;
    });
  };

  // ================= ADD YEAR =================
  const handleAddYear = async () => {

    if (!year) {

      return alert("Select year");
    }

    const yearNum = Number(year);

    const exists = years.find(
      (y) => Number(y.year_number) === yearNum
    );

    if (exists) {

      return alert("Year already exists");
    }

    try {

      setSaving(true);

      const res = await API.post(
        "/years/",
        {
          course: Number(id),
          year_number: yearNum,
        }
      );

      // instant: append new year locally, keep order
      setYears((prev) =>
        [
          ...prev,
          {
            ...res.data,
            subjects: res.data.subjects || [],
          },
        ].sort(
          (a, b) => a.year_number - b.year_number
        )
      );

      setYear("");

    } catch (err) {

      console.error(err.response?.data);

      alert("Failed to add year");

    } finally {

      setSaving(false);
    }
  };

  // ================= ADD / UPDATE SUBJECT =================
  const handleAddSubject = async () => {

    if (!semester || !subject) {

      return alert(
        "Select semester and enter subject name"
      );
    }

    // the year is derived from the semester - make sure it exists
    if (!derivedYearExists || !yearId) {

      return alert(
        `Year ${derivedYearNumber} has not been added for this course yet. Add it above first.`
      );
    }

    const payload = {
      name: subject,
      code: code,
      year: Number(yearId),
      semester: Number(semester),
      credits: Number(credits) || 0,
      weekly_hours: Number(weeklyHours) || 0,
      is_elective: isElective,
      department: department ? Number(department) : null,
    };

    try {

      setSaving(true);

      let res;

      if (editingSubjectId) {

        res = await API.put(
          `/subjects/${editingSubjectId}/`,
          payload
        );

      } else {

        res = await API.post(
          "/subjects/",
          payload
        );
      }

      // instant: update the list from server response
      upsertSubjectInYears(res.data);

      // ================= RESET =================
      setSubject("");
      setCode("");
      setYearId("");
      setSemester("");
      setCredits("");
      setWeeklyHours("");
      setIsElective(false);
      setDepartment("");

      setEditingSubjectId(null);

    } catch (err) {

      console.error(err.response?.data);

      alert("Failed to save subject");

    } finally {

      setSaving(false);
    }
  };

  // ================= DELETE SUBJECT =================
  const handleDeleteSubject = async (subjectId) => {

    if (!window.confirm("Delete this subject?")) {
      return;
    }

    try {

      setSaving(true);

      await API.delete(
        `/subjects/${subjectId}/`
      );

      // instant: drop it from local state
      setYears((prev) =>
        prev.map((y) => ({
          ...y,
          subjects: (y.subjects || []).filter(
            (s) => s.id !== subjectId
          ),
        }))
      );

      // if we were editing this one, clear the form
      if (editingSubjectId === subjectId) {

        setSubject("");
        setCode("");
        setYearId("");
        setSemester("");
        setCredits("");
        setWeeklyHours("");
        setIsElective(false);
        setDepartment("");
        setEditingSubjectId(null);
      }

    } catch (err) {

      console.error(err);

      alert("Delete failed");

    } finally {

      setSaving(false);
    }
  };

  // ================= LOADING (first load only) =================
  if (loading) {

    return (
      <p style={{ padding: "20px" }}>
        Loading...
      </p>
    );
  }

  // ================= NO DATA =================
  if (!course) {

    return (
      <p style={{ padding: "20px" }}>
        Course not found
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

              {/* top row: subtle back link (left) + primary action (right) */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "18px",
                }}
              >

                <button
                  onClick={() => navigate("/courses")}
                  style={{
                    background: "transparent",
                    color: "#64748b",
                    padding: "6px 2px",
                    fontWeight: 600,
                  }}
                >
                  &larr; Back to Courses
                </button>

                <button
                  className="btn-primary"
                  onClick={() =>
                    navigate(
                      `/courses/${id}/structure`
                    )
                  }
                >
                  Course Structure
                </button>

              </div>

              <h2>
                {course.name}
              </h2>

              <p>
                Manage course structure
              </p>

            </div>

            {/* ================= STRUCTURE (admin only) ================= */}
            {user.role === "admin" && (

              <>

                {/* ================= ADD YEAR ================= */}
                <div className="card">

                  <h3>Add Year </h3>

                  <div className="form-grid form-grid--row">

                    <select
                      value={year}
                      onChange={(e) =>
                        setYear(e.target.value)
                      }
                    >

                      <option value="">
                        Select Year
                      </option>

                      {[1, 2, 3, 4].map((y) => (
                        <option
                          key={y}
                          value={y}
                          disabled={years.some(
                            (yr) =>
                              yr.year_number === y
                          )}
                        >
                          Year {y}
                        </option>
                      ))}

                    </select>

                    <button
                      className="btn-primary"
                      onClick={handleAddYear}
                      disabled={saving}
                    >
                      {saving
                        ? "Saving..."
                        : "Add Year"}
                    </button>

                  </div>

                </div>

                {/* ================= ADD SUBJECT ================= */}
                <div className="card">

                  <h3>
                    {editingSubjectId
                      ? "Edit Subject"
                      : "Add Subject"}
                  </h3>

                  <div className="form-grid form-grid--row">

                    {/* SEMESTER (the year is derived from this) */}
                    <select
                      value={semester}
                      onChange={(e) =>
                        handleSemesterChange(e.target.value)
                      }
                    >

                      <option value="">
                        Select Semester
                      </option>

                      {[1,2,3,4,5,6,7,8].map((s) => (
                        <option
                          key={s}
                          value={s}
                        >
                          Semester {s}
                        </option>
                      ))}

                    </select>

                    {/* DERIVED YEAR (read-only, auto from semester) */}
                    <span
                      className={`sem-year-badge ${
                        !semester
                          ? "is-empty"
                          : derivedYearExists
                          ? "is-ok"
                          : "is-warn"
                      }`}
                    >
                      {!semester
                        ? "Year -"
                        : derivedYearExists
                        ? `Year ${derivedYearNumber}`
                        : `Year ${derivedYearNumber} not added yet`}
                    </span>

                    {/* DEPARTMENT (owner) */}
                    <select
                      value={department}
                      onChange={(e) =>
                        setDepartment(e.target.value)
                      }
                    >

                      <option value="">
                        Select Department
                      </option>

                      {departments.map((d) => (
                        <option
                          key={d.id}
                          value={d.id}
                        >
                          {d.name}
                        </option>
                      ))}

                    </select>

                    {/* CODE */}
                    <input
                      placeholder="Subject Code (e.g. HS3152)"
                      value={code}
                      onChange={(e) =>
                        setCode(e.target.value)
                      }
                    />

                    {/* SUBJECT */}
                    <input
                      placeholder="Subject Name"
                      value={subject}
                      onChange={(e) =>
                        setSubject(e.target.value)
                      }
                    />

                    {/* CREDITS */}
                    <input
                      type="number"
                      min="0"
                      placeholder="Credits"
                      value={credits}
                      onChange={(e) =>
                        setCredits(e.target.value)
                      }
                    />

                    {/* WEEKLY PERIODS (timetable target) */}
                    <input
                      type="number"
                      min="0"
                      placeholder="Weekly periods"
                      value={weeklyHours}
                      onChange={(e) =>
                        setWeeklyHours(e.target.value)
                      }
                    />

                    {/* ELECTIVE (students self-enrol; not auto-enrolled) */}
                    <label
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        fontSize: "14px",
                        color: "#334155",
                        whiteSpace: "nowrap",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isElective}
                        onChange={(e) =>
                          setIsElective(e.target.checked)
                        }
                      />
                      Elective
                    </label>

                    {/* BUTTON */}
                    <button
                      className="btn-primary"
                      onClick={handleAddSubject}
                      disabled={saving}
                    >
                      {saving
                        ? "Saving..."
                        : editingSubjectId
                        ? "Update Subject"
                        : "Add Subject"}
                    </button>

                  </div>

                </div>

                {/* ================= SUBJECTS BY YEAR ================= */}
                <div className="card">

                  <h3>
                    Subjects by Year
                  </h3>

                  {years.length === 0 ? (

                    <p>
                      No years added
                    </p>

                  ) : (

                    years.map((y) => (

                      <div
                        key={y.id}
                        style={{ marginBottom: "25px" }}
                      >

                        <h4>
                          Year {y.year_number}
                        </h4>

                        <table>

                          <thead>

                            <tr>
                              <th>Code</th>
                              <th>Subject</th>
                              <th>Department</th>
                              <th>Semester</th>
                              <th>Credits</th>
                              <th>Weekly periods</th>
                              <th>Type</th>
                              <th>Action</th>
                            </tr>

                          </thead>

                          <tbody>

                            {y.subjects?.length > 0 ? (

                              y.subjects.map((s) => (

                                <tr key={s.id}>

                                  <td>
                                    {s.code || "-"}
                                  </td>

                                  <td>
                                    {s.name}
                                  </td>

                                  <td>
                                    {s.department_name || "-"}
                                  </td>

                                  <td>
                                    Semester {s.semester}
                                  </td>

                                  <td>
                                    {s.credits ?? 0}
                                  </td>

                                  <td>
                                    {s.weekly_hours ?? 0}
                                  </td>

                                  <td>
                                    {s.is_elective ? "Elective" : "Core"}
                                  </td>

                                  <td>

                                    <div className="action-buttons">

                                      <button
                                        className="btn-edit"
                                        onClick={() => {
                                          setSubject(s.name);
                                          setCode(s.code || "");
                                          setSemester(String(s.semester));
                                          // derive yearId from the semester so
                                          // edit stays consistent with the rule
                                          setYearId(String(s.year));
                                          setCredits(s.credits ?? "");
                                          setWeeklyHours(s.weekly_hours ?? "");
                                          setIsElective(!!s.is_elective);
                                          setDepartment(s.department || "");
                                          setEditingSubjectId(s.id);
                                        }}
                                      >
                                        Edit
                                      </button>

                                      <button
                                        className="btn-delete"
                                        onClick={() =>
                                          handleDeleteSubject(s.id)
                                        }
                                      >
                                        Delete
                                      </button>

                                    </div>

                                  </td>

                                </tr>

                              ))

                            ) : (

                              <tr>
                                <td colSpan="8">
                                  No subjects
                                </td>
                              </tr>

                            )}

                          </tbody>

                        </table>

                      </div>

                    ))

                  )}

                </div>

              </>
            )}

          </div>

        </div>

      </div>

    </div>
  );
}