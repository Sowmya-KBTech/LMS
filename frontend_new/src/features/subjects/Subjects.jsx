// import { useEffect, useState } from "react";
// import Sidebar from "../../components/Sidebar";
// import Navbar from "../../components/Navbar";
// import API from "../../api";
// import "../../App.css";

// export default function Subjects() {
//   const [courses, setCourses] = useState([]);
//   const [years, setYears] = useState([]);
//   const [subjects, setSubjects] = useState([]);

//   const [form, setForm] = useState({
//     course: "",
//     year: "",
//     name: "",
//   });

//   useEffect(() => {
//     fetchData();
//   }, []);

//   // ================= FETCH =================
//   const fetchData = async () => {
//     try {
//       const [c, y, s] = await Promise.all([
//         API.get("/courses/"),
//         API.get("/years/"),
//         API.get("/subjects/"),
//       ]);

//       setCourses(c.data?.results || c.data || []);
//       setYears(y.data?.results || y.data || []);
//       setSubjects(s.data?.results || s.data || []);
//     } catch (err) {
//       console.log("Error:", err);
//     }
//   };

//   // ================= FILTER YEARS =================
//   const filteredYears = years.filter(
//     (y) => String(y.course) === String(form.course)
//   );

//   // ================= ADD SUBJECT =================
//   const handleAdd = async () => {
//     if (!form.course || !form.year || !form.name) {
//       alert("Fill all fields");
//       return;
//     }

//     // prevent duplicate subject
//     const exists = subjects.find(
//       (s) =>
//         String(s.year) === String(form.year) &&
//         s.name.toLowerCase() === form.name.toLowerCase()
//     );

//     if (exists) {
//       alert("Subject already exists for this year");
//       return;
//     }

//     try {
//       await API.post("/subjects/", {
//         name: form.name,
//         year: form.year,
//       });

//       setForm({ course: "", year: "", name: "" });
//       fetchData();
//     } catch (err) {
//       alert("Failed to add subject");
//     }
//   };

//   // ================= DELETE =================
//   const handleDelete = async (id) => {
//     if (!window.confirm("Delete this subject?")) return;

//     try {
//       await API.delete(`/subjects/${id}/`);
//       fetchData();
//     } catch (err) {
//       alert("Delete failed");
//     }
//   };

//   return (
//     <div className="layout">
//       <Sidebar />
//       <div className="main">
//         <Navbar />

//         <div className="content">
//           <h2>Subjects Management</h2>

//           {/* ===== ADD FORM ===== */}
//           <div className="card">
//             <div className="form-grid">

//               {/* COURSE */}
//               <select
//                 value={form.course}
//                 onChange={(e) =>
//                   setForm({
//                     ...form,
//                     course: e.target.value,
//                     year: "",
//                   })
//                 }
//               >
//                 <option value="">Select Course</option>
//                 {courses.map((c) => (
//                   <option key={c.id} value={c.id}>
//                     {c.name}
//                   </option>
//                 ))}
//               </select>

//               {/* YEAR */}
//               <select
//                 value={form.year}
//                 onChange={(e) =>
//                   setForm({ ...form, year: e.target.value })
//                 }
//               >
//                 <option value="">Select Year</option>
//                 {filteredYears.map((y) => (
//                   <option key={y.id} value={y.id}>
//                     Year {y.year_number}
//                   </option>
//                 ))}
//               </select>

//               {/* SUBJECT NAME */}
//               <input
//                 type="text"
//                 placeholder="Subject Name"
//                 value={form.name}
//                 onChange={(e) =>
//                   setForm({ ...form, name: e.target.value })
//                 }
//               />

//               <button onClick={handleAdd}>Add Subject</button>
//             </div>
//           </div>

//           {/* ===== TABLE ===== */}
//           <div className="card">
//             <table>
//               <thead>
//                 <tr>
//                   <th>Course</th>
//                   <th>Year</th>
//                   <th>Subject</th>
//                   <th>Action</th>
//                 </tr>
//               </thead>

//               <tbody>
//                 {subjects.map((s) => (
//                   <tr key={s.id}>
//                     <td>{s.year_info?.split("-")[1]?.trim()}</td>
//                     <td>Year {s.year_info?.split("-")[0]?.replace("Year ", "")}</td>
//                     <td>{s.name}</td>
//                     <td>
//                       <button onClick={() => handleDelete(s.id)}>
//                         Delete
//                       </button>
//                     </td>
//                   </tr>
//                 ))}
//               </tbody>
//             </table>

//             {subjects.length === 0 && <p>No subjects added yet</p>}
//           </div>

//         </div>
//       </div>
//     </div>
//   );
// }