import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import Navbar from "../components/Navbar";
import API from "../api";

export default function Enrollments() {
  const [enrollments, setEnrollments] = useState([]);
  const [students, setStudents] = useState([]);
  const [courses, setCourses] = useState([]);

  const [form, setForm] = useState({
    student: "",
    course: ""
  });

  // ✅ LOAD ONLY ONCE
  useEffect(() => {
    fetchEnrollments();
    fetchStudents();
    fetchCourses();
  }, []);

  // ================= FETCH =================
  const fetchEnrollments = async () => {
    try {
      const res = await API.get("enrollments/");
      setEnrollments(res.data);
    } catch (err) {
      console.error("Enrollment fetch error:", err);
    }
  };

  const fetchStudents = async () => {
    try {
      const res = await API.get("users/");
      const studentList = res.data.filter(u => u.role === "student");
      setStudents(studentList);
    } catch (err) {
      console.error("Student fetch error:", err);
    }
  };

  const fetchCourses = async () => {
    try {
      const res = await API.get("courses/");
      setCourses(res.data);
    } catch (err) {
      console.error("Course fetch error:", err);
    }
  };

  // ================= HANDLE =================
  const handleChange = (e) => {
    setForm({
      ...form,
      [e.target.name]: e.target.value
    });
  };

  // ================= SUBMIT =================
  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      await API.post("enrollments/", {
        student: Number(form.student),
        course: Number(form.course)
      });

      setForm({ student: "", course: "" });

      // ✅ refresh only enrollments (not all)
      fetchEnrollments();

      alert("Enrollment successful ✅");
    } catch (err) {
      console.error(err);

      if (err.response?.data) {
        alert("⚠️ Student already enrolled in this course");
      } else {
        alert("❌ Server error");
      }
    }
  };

  // ================= DELETE =================
  const handleDelete = async (id) => {
    try {
      await API.delete(`enrollments/${id}/`);
      fetchEnrollments();
    } catch (err) {
      console.error(err);
    }
  };

  // ================= SELECTED =================
  const selectedStudent = students.find(
    s => s.id === Number(form.student)
  );

  const selectedCourse = courses.find(
    c => c.id === Number(form.course)
  );

  return (
  <div className="layout">
    <Sidebar />

    <div className="main">
      <Navbar />

      <div className="content">

        {/* HEADER */}
        <div className="header-box">
          <h2>Enrollment Management</h2>
          <p>Enroll students into courses</p>
        </div>

        {/* ================= FORM CARD ================= */}
        <div className="card">
          <form onSubmit={handleSubmit} className="form-grid">

            <select
              name="student"
              value={form.student}
              onChange={handleChange}
              required
            >
              <option value="">Select Student</option>
              {students.map(s => (
                <option key={s.id} value={s.id}>
                  {s.username} ({s.roll_number || "No Roll"})
                </option>
              ))}
            </select>

            <select
              name="course"
              value={form.course}
              onChange={handleChange}
              required
            >
              <option value="">Select Course</option>
              {courses.map(c => (
                <option key={c.id} value={c.id}>
                  {c.title} ({c.teacher_name})
                </option>
              ))}
            </select>

            <button className="btn-primary" type="submit">
              Enroll
            </button>
          </form>

          {/* LIVE INFO */}
          <div className="info-text">
            {selectedStudent && (
              <p>Dept: <strong>{selectedStudent.department}</strong></p>
            )}

            {selectedCourse && (
              <p>Teacher: <strong>{selectedCourse.teacher_name}</strong></p>
            )}
          </div>
        </div>

        {/* ================= TABLE CARD ================= */}
        <div className="card">
          <table className="styled-table">
            <thead>
              <tr>
                <th>Roll No</th>
                <th>Student</th>
                <th>Department</th>
                <th>Course</th>
                <th>Teacher</th>
                <th>Action</th>
              </tr>
            </thead>

            <tbody>
              {enrollments.length === 0 ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: "center" }}>
                    No enrollments found
                  </td>
                </tr>
              ) : (
                enrollments.map(e => (
                  <tr key={e.id}>
                    <td>{e.student_roll || "N/A"}</td>
                    <td>{e.student_name}</td>
                    <td>{e.student_dept}</td>
                    <td>{e.course_title}</td>
                    <td>{e.course_teacher}</td>

                    
                      <td>
                       <button className="btn-danger" onClick={() => handleDelete(e.id)} >
                               Delete
                         </button>
                        </td>
                  
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

      </div>
    </div>
  </div>
);
}