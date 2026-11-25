import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import ImportExport from "../../components/ImportExport";

import "../../App.css";

// ================= ROLE / SUB-ROLE CONFIG =================
const MAIN_ROLES = [
  { value: "student", label: "Student" },
  { value: "teacher", label: "Teacher" },
  { value: "admin", label: "Admin" },
  { value: "non_teaching", label: "Non-teaching staff" },
  { value: "parent", label: "Parent" },
];

const SUB_ROLES = {
  teacher: [
    { value: "assistant_professor", label: "Assistant Professor" },
    { value: "associate_professor", label: "Associate Professor" },
    { value: "professor", label: "Professor" },
  ],
  admin: [
    { value: "academic_admin", label: "Academic Admin" },
    { value: "exam_admin", label: "Examination Admin" },
    { value: "accounts_admin", label: "Accounts Admin" },
    { value: "iqac_admin", label: "IQAC Admin" },
    { value: "super_admin", label: "Super Admin" },
  ],
  non_teaching: [
    { value: "office_assistant", label: "Office Assistant" },
    { value: "lab_technician", label: "Lab Technician" },
    { value: "librarian", label: "Librarian" },
    { value: "clerk", label: "Clerk" },
  ],
};

const BLOOD_GROUPS = ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"];

const EMPTY_FORM = {
  // core (real User fields)
  username: "",
  email: "",
  password: "",
  role: "student",
  sub_role: "",
  department: "",
  course: "",
  year: "",
  semester: "",
  batch_year: "",
  is_active: true,

  // profile (goes into the profile object the serializer accepts)
  gender: "",
  date_of_birth: "",
  blood_group: "",
  address_line1: "",
  address_line2: "",
  city: "",
  district: "",
  state: "",
  pincode: "",
  admission_date: "",
  qualification: "",
  specialization: "",
  date_of_joining: "",
  experience_years: "",

  // parent (collected in the student's parent step)
  father_name: "",
  mother_name: "",
  guardian_phone: "",
  guardian_email: "",
  occupation: "",
};

// ================= STABLE FIELD WRAPPER =================
// Defined OUTSIDE the component so React keeps the same element across renders.
// (Defining it inside caused inputs to lose focus after every keystroke.)
function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={lbl}>{label}</div>
      {children}
    </div>
  );
}

export default function UserManagement() {

  // ================= STATES =================
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [courses, setCourses] = useState([]);

  const [roleFilter, setRoleFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [deptFilter, setDeptFilter] = useState("all");
  const [semFilter, setSemFilter] = useState("all");

  // add / edit modal
  const [modalOpen, setModalOpen] = useState(false);
  const [mode, setMode] = useState("add");
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [step, setStep] = useState(1);

  // student-admin panels
  const [showPromote, setShowPromote] = useState(false);

  // promote state
  const [promoteCourse, setPromoteCourse] = useState("");
  const [promoteYear, setPromoteYear] = useState("");
  const [promoteSemester, setPromoteSemester] = useState("");
  const [promoting, setPromoting] = useState(false);

  // ================= LOAD =================
  useEffect(() => {
    fetchUsers();
    fetchDepartments();
    fetchCourses();
  }, []);

  const fetchUsers = async () => {
    try {
      const res = await API.get("users/");
      const data = res.data?.results || res.data;
      setUsers(Array.isArray(data) ? data : []);
    } catch {
      alert("Failed to load users");
    }
  };

  const fetchDepartments = async () => {
    try {
      const res = await API.get("users/departments/");
      const data = res.data?.results || res.data;
      setDepartments(Array.isArray(data) ? data : []);
    } catch {
      alert("Failed to load departments");
    }
  };

  const fetchCourses = async () => {
    try {
      const res = await API.get("courses/");
      const data = res.data?.results || res.data;
      setCourses(Array.isArray(data) ? data : []);
    } catch {
      alert("Failed to load courses");
    }
  };

  // ================= STEP DEFINITIONS PER ROLE =================
  // returns an array of step keys for the current role
  const stepsForRole = (role) => {
    if (role === "student") return ["basic", "address", "student", "parent"];
    if (role === "teacher") return ["basic", "address", "faculty"];
    if (role === "non_teaching") return ["basic", "address", "faculty"];
    if (role === "admin") return ["basic", "adminDetails"];
    if (role === "parent") return ["basic", "parentContact"];
    return ["basic"];
  };

  const steps = stepsForRole(form.role);
  const totalSteps = steps.length;
  const currentStepKey = steps[step - 1];

  // ================= OPEN ADD =================
  const openAdd = () => {
    setMode("add");
    setEditingId(null);
    setForm(EMPTY_FORM);
    setStep(1);
    setModalOpen(true);
  };

  // ================= OPEN EDIT =================
  const openEdit = (u) => {
    const p = u.profile_data || {};
    setMode("edit");
    setEditingId(u.id);
    setForm({
      ...EMPTY_FORM,
      username: u.username || "",
      email: u.email || "",
      password: "",
      role: u.role || "student",
      sub_role: u.sub_role || "",
      department: u.department || "",
      course: u.course || "",
      year: u.year || "",
      semester: u.semester || "",
      batch_year: u.batch_year || "",
      is_active: u.is_active,
      // profile fields (if present)
      gender: p.gender || "",
      date_of_birth: p.date_of_birth || "",
      blood_group: p.blood_group || "",
      address_line1: p.address_line1 || "",
      address_line2: p.address_line2 || "",
      city: p.city || "",
      district: p.district || "",
      state: p.state || "",
      pincode: p.pincode || "",
      admission_date: p.admission_date || "",
      qualification: p.qualification || "",
      specialization: p.specialization || "",
      date_of_joining: p.date_of_joining || "",
      experience_years: p.experience_years || "",
      // guardian details (merged back from the linked parent by the serializer).
      // Only one guardian name is stored, so it pre-fills father_name;
      // mother_name stays blank because it isn't persisted separately.
      father_name: p.guardian_name || "",
      mother_name: "",
      guardian_phone: p.guardian_phone || "",
      guardian_email: p.guardian_email || "",
      occupation: p.occupation || "",
    });
    setStep(1);
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setStep(1);
  };

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  // ================= BUILD PAYLOAD =================
  const buildPayload = () => {
    const p = {
      username: form.username,
      email: form.email,
      role: form.role,
      is_active: form.is_active,
    };

    if (form.password) p.password = form.password;

    if (form.role === "student") {
      p.department = form.department ? Number(form.department) : null;
      p.course = form.course ? Number(form.course) : null;
      p.year = form.year ? Number(form.year) : null;
      p.semester = form.semester ? Number(form.semester) : null;
      p.batch_year = form.batch_year ? Number(form.batch_year) : null;
    }

    if (form.role === "teacher" || form.role === "non_teaching") {
      p.department = form.department ? Number(form.department) : null;
      p.sub_role = form.sub_role || null;
    }

    if (form.role === "admin") {
      p.sub_role = form.sub_role || null;
    }

    // profile object (address / personal / employment details)
    const profile = {};
    const addIf = (key) => { if (form[key] !== "" && form[key] !== null) profile[key] = form[key]; };

    if (form.role === "student") {
      ["gender", "date_of_birth", "blood_group", "address_line1", "address_line2",
       "city", "district", "state", "pincode", "admission_date",
       "father_name", "mother_name", "guardian_phone", "guardian_email", "occupation"].forEach(addIf);
    }

    if (form.role === "teacher" || form.role === "non_teaching") {
      ["gender", "date_of_birth", "blood_group", "address_line1", "address_line2",
       "city", "district", "state", "pincode",
       "qualification", "specialization", "date_of_joining", "experience_years"].forEach(addIf);
    }

    if (Object.keys(profile).length > 0) p.profile = profile;

    return p;
  };

  // ================= SAVE (add or edit) =================
  const handleSave = async () => {
    if (!form.username || !form.email) {
      return alert("Username and email are required");
    }
    if (mode === "add" && !form.password) {
      return alert("Password is required for a new user");
    }
    if (form.role === "student") {
      if (!form.department || !form.course || !form.year || !form.semester) {
        return alert("Please fill department, course, year and semester for a student");
      }
    }

    const payload = buildPayload();

    try {
      if (mode === "add") {
        await API.post("users/", payload);
        alert("User created");
      } else {
        await API.patch(`users/${editingId}/`, payload);
        alert("User updated");
      }
      fetchUsers();
      closeModal();
    } catch (err) {
      const errorData = err.response?.data;
      if (errorData?.email) alert("Email already exists");
      else if (errorData?.username) alert("Username already exists");
      else alert("Something went wrong");
    }
  };

  const next = () => {
    if (step < totalSteps) setStep(step + 1);
    else handleSave();
  };
  const back = () => { if (step > 1) setStep(step - 1); };

  // ================= DELETE =================
  const handleDelete = async (u) => {
    if (!window.confirm(`Delete ${u.username}?`)) return;
    try {
      await API.delete(`users/${u.id}/`);
      setUsers(users.filter((x) => x.id !== u.id));
      alert("User deleted");
    } catch (err) {
      alert(err.response?.data?.error || "Delete failed");
    }
  };

  // ================= PROMOTE STUDENTS =================
  const handlePromote = async () => {
    if (!promoteCourse || !promoteYear || !promoteSemester) {
      return alert("Select course, year and semester to promote.");
    }
    const courseName =
      courses.find((c) => String(c.id) === String(promoteCourse))?.name || "this course";
    const nextSem = Number(promoteSemester) + 1;
    if (Number(promoteSemester) >= 8) {
      return alert("Semester 8 is the final semester — these students cannot be promoted further.");
    }
    if (!window.confirm(
      `Promote all students in ${courseName}, Year ${promoteYear}, Semester ${promoteSemester} ` +
      `to Semester ${nextSem}?\n\nThis changes their year/semester. Their past results and marks are kept.`
    )) return;

    setPromoting(true);
    try {
      const res = await API.post("users/promote-students/", {
        course: promoteCourse,
        year: promoteYear,
        semester: promoteSemester,
      });
      alert(res.data?.detail || "Promotion complete.");
      setPromoteCourse(""); setPromoteYear(""); setPromoteSemester("");
      setShowPromote(false);
      fetchUsers();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not promote students.");
    } finally {
      setPromoting(false);
    }
  };

  // ================= FILTER =================
  const filteredUsers = users.filter((u) => {
    const roleMatch = roleFilter === "all" || u.role === roleFilter;
    const deptMatch =
      deptFilter === "all" || String(u.department) === String(deptFilter);
    const semMatch =
      semFilter === "all" || String(u.semester) === String(semFilter);
    const text = search.toLowerCase();
    const searchMatch =
      (u.username || "").toLowerCase().includes(text) ||
      (u.first_name || "").toLowerCase().includes(text) ||
      (u.roll_number || "").toLowerCase().includes(text) ||
      (u.employee_id || "").toLowerCase().includes(text);
    return roleMatch && deptMatch && semMatch && searchMatch;
  });

  const subRoleOptions = SUB_ROLES[form.role] || [];

  // ================= FIELD HELPER (for the modal) =================
  // NOTE: `Field` is defined at module scope (bottom of this file) so it is NOT
  // recreated on every render — that is what was stealing focus after one letter.
  const textInput = (key, placeholder = "", type = "text") => (
    <input type={type} placeholder={placeholder} value={form[key]}
      onChange={(e) => set(key, e.target.value)} style={{ width: "100%" }} />
  );

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h2>User Management</h2>
                <p>Manage all users in one place</p>
              </div>
              <button className="btn-primary" onClick={openAdd}>+ Add User</button>
            </div>

            {/* ================= IMPORT / EXPORT + PROMOTE ================= */}
            {/* Export uses the filters chosen in the table below. */}
            <div className="kb-um-actions">
              <ImportExport
                onDone={fetchUsers}
                sets={[
                  {
                    importer: "students",
                    title: "Students",
                    label: "students",
                    matchLabel: "roll number",
                    exportParams: { department: deptFilter, semester: semFilter },
                  },
                  {
                    importer: "staff",
                    title: "Staff",
                    label: "staff",
                    matchLabel: "employee ID",
                    exportParams: {
                      department: deptFilter,
                      role: ["teacher", "non_teaching"].includes(roleFilter) ? roleFilter : "",
                    },
                  },
                ]}
              />
              <button
                type="button"
                className={`kb-btn${showPromote ? " kb-btn--soft" : ""}`}
                onClick={() => setShowPromote((v) => !v)}
              >
                Promote to Next Semester
              </button>
            </div>

            {/* ================= PROMOTE PANEL ================= */}
            {showPromote && (
              <div className="card" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <strong style={{ fontSize: 15, color: "#17151F" }}>Promote to Next Semester:</strong>

                <select value={promoteCourse} onChange={(e) => setPromoteCourse(e.target.value)} style={{ minWidth: 160 }}>
                  <option value="">Select Course</option>
                  {courses.map((c) => (<option key={c.id} value={c.id}>{c.name}</option>))}
                </select>

                <select value={promoteYear} onChange={(e) => setPromoteYear(e.target.value)} style={{ minWidth: 110 }}>
                  <option value="">Year</option>
                  {[1, 2, 3, 4].map((y) => <option key={y} value={y}>Year {y}</option>)}
                </select>

                <select value={promoteSemester} onChange={(e) => setPromoteSemester(e.target.value)} style={{ minWidth: 130 }}>
                  <option value="">Semester</option>
                  {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => <option key={s} value={s}>Semester {s}</option>)}
                </select>

                <button
                  onClick={handlePromote}
                  disabled={promoting}
                  style={{ ...csvBtn, background: "#17151F", color: "#fff", border: "none" }}
                >
                  {promoting ? "Promoting…" : "Promote"}
                </button>

                <span style={{ fontSize: 13, color: "#5D5A6B" }}>
                  Moves the whole class up one semester. Past results &amp; marks are kept.
                </span>
              </div>
            )}

            {/* ================= TABLE ================= */}
            <div className="card">

              <div className="top-filters" style={{ alignItems: "center", flexWrap: "wrap" }}>
                <input
                  className="search-box"
                  placeholder="Search name, roll no or emp id..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />

                <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
                  <option value="all">All Roles</option>
                  {MAIN_ROLES.map((r) => (<option key={r.value} value={r.value}>{r.label}</option>))}
                </select>

                <select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)}>
                  <option value="all">All Departments</option>
                  {departments.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
                </select>

                <select value={semFilter} onChange={(e) => setSemFilter(e.target.value)}>
                  <option value="all">All Semesters</option>
                  {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (<option key={s} value={s}>Semester {s}</option>))}
                </select>

                <span style={{ marginLeft: "auto", fontSize: "15px", color: "#5D5A6B" }}>
                  Showing {filteredUsers.length} of {users.length}
                </span>
              </div>

              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Roll No / Emp ID</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <div>{u.first_name || u.username}</div>
                          <div style={{ fontSize: 13, color: "#85839A" }}>{u.email}</div>
                        </td>
                        <td>{u.roll_number || u.employee_id || "\u2014"}</td>
                        <td>
                          <div>{u.role_label || u.role}</div>
                          {u.sub_role_label && (
                            <div style={{ fontSize: 13, color: "#85839A" }}>{u.sub_role_label}</div>
                          )}
                        </td>
                        <td>
                          <span style={u.is_active ? statusActive : statusInactive}>
                            {u.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td>
                          <div className="action-buttons">
                            <button className="btn-edit" onClick={() => openEdit(u)}>Edit</button>
                            <button className="btn-delete" onClick={() => handleDelete(u)}>Delete</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {filteredUsers.length === 0 && (
                      <tr>
                        <td colSpan="5" style={{ textAlign: "center" }}>No users found</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ================= ADD / EDIT STEPPED POPUP ================= */}
      {modalOpen && (
        <div
          onClick={closeModal}
          style={{
            position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#fff", borderRadius: 14, width: 500, maxWidth: "92%",
              maxHeight: "88vh", overflowY: "auto",
              padding: "24px 24px 20px", boxShadow: "0 20px 50px rgba(0,0,0,.25)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h3 style={{ margin: 0, fontSize: 18 }}>{mode === "add" ? "Add user" : "Edit user"}</h3>
              <span onClick={closeModal} style={{ cursor: "pointer", fontSize: 20, color: "#5D5A6B" }}>&times;</span>
            </div>

            {/* progress bar */}
            <div style={{ display: "flex", gap: 6, margin: "16px 0 6px" }}>
              {steps.map((_, i) => (
                <div key={i} style={{
                  flex: 1, height: 4, borderRadius: 2,
                  background: (i + 1) <= step ? "#4B32C3" : "#E7E7EC",
                }} />
              ))}
            </div>
            <p style={{ fontSize: 13, color: "#85839A", margin: "0 0 16px" }}>
              Step {step} of {totalSteps}
            </p>

            {/* ---------- STEP: BASIC ---------- */}
            {currentStepKey === "basic" && (
              <>
                <Field label="Username">{textInput("username", "arun_kumar")}</Field>
                <Field label="Email">{textInput("email", "arun@college.edu", "email")}</Field>
                <Field label={`Password ${mode === "edit" ? "(leave blank to keep)" : ""}`}>
                  {textInput("password", "", "password")}
                </Field>

                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <Field label="Main role">
                      <select value={form.role}
                        onChange={(e) => { set("role", e.target.value); set("sub_role", ""); setStep(1); }}
                        style={{ width: "100%" }}>
                        {MAIN_ROLES.map((r) => (<option key={r.value} value={r.value}>{r.label}</option>))}
                      </select>
                    </Field>
                  </div>
                  <div style={{ flex: 1 }}>
                    <Field label="Status">
                      <select value={form.is_active ? "1" : "0"}
                        onChange={(e) => set("is_active", e.target.value === "1")}
                        style={{ width: "100%" }}>
                        <option value="1">Active</option>
                        <option value="0">Inactive</option>
                      </select>
                    </Field>
                  </div>
                </div>

                {subRoleOptions.length > 0 && (
                  <Field label="Sub role">
                    <select value={form.sub_role} onChange={(e) => set("sub_role", e.target.value)} style={{ width: "100%" }}>
                      <option value="">Select sub role</option>
                      {subRoleOptions.map((s) => (<option key={s.value} value={s.value}>{s.label}</option>))}
                    </select>
                  </Field>
                )}

                {form.role !== "admin" && form.role !== "parent" && (
                  <div style={{ display: "flex", gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <Field label="Gender">
                        <select value={form.gender} onChange={(e) => set("gender", e.target.value)} style={{ width: "100%" }}>
                          <option value="">Select</option>
                          <option>Male</option><option>Female</option><option>Other</option>
                        </select>
                      </Field>
                    </div>
                    <div style={{ flex: 1 }}>
                      <Field label="Date of birth">{textInput("date_of_birth", "", "date")}</Field>
                    </div>
                    <div style={{ flex: 1 }}>
                      <Field label="Blood group">
                        <select value={form.blood_group} onChange={(e) => set("blood_group", e.target.value)} style={{ width: "100%" }}>
                          <option value="">Select</option>
                          {BLOOD_GROUPS.map((b) => (<option key={b} value={b}>{b}</option>))}
                        </select>
                      </Field>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ---------- STEP: ADDRESS ---------- */}
            {currentStepKey === "address" && (
              <>
                <Field label="Address line 1">{textInput("address_line1", "12, Gandhi Street")}</Field>
                <Field label="Address line 2">{textInput("address_line2", "Near bus stand")}</Field>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}><Field label="City / town">{textInput("city", "Tiruchirappalli")}</Field></div>
                  <div style={{ flex: 1 }}><Field label="District">{textInput("district", "Trichy")}</Field></div>
                </div>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}><Field label="State">{textInput("state", "Tamil Nadu")}</Field></div>
                  <div style={{ flex: 1 }}><Field label="Pincode">{textInput("pincode", "620001")}</Field></div>
                </div>
              </>
            )}

            {/* ---------- STEP: STUDENT DETAILS ---------- */}
            {currentStepKey === "student" && (
              <>
                <p style={{ fontSize: 13, color: "#85839A", margin: "0 0 12px" }}>
                  Roll number is generated automatically from department and batch year.
                </p>
                <Field label="Department">
                  <select value={form.department} onChange={(e) => set("department", e.target.value)} style={{ width: "100%" }}>
                    <option value="">Select department</option>
                    {departments.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
                  </select>
                </Field>
                <Field label="Course">
                  <select value={form.course} onChange={(e) => set("course", e.target.value)} style={{ width: "100%" }}>
                    <option value="">Select course</option>
                    {courses.map((c) => (<option key={c.id} value={c.id}>{c.name}</option>))}
                  </select>
                </Field>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <Field label="Year">
                      <select value={form.year} onChange={(e) => set("year", e.target.value)} style={{ width: "100%" }}>
                        <option value="">Year</option>
                        {[1, 2, 3, 4].map((y) => <option key={y} value={y}>Year {y}</option>)}
                      </select>
                    </Field>
                  </div>
                  <div style={{ flex: 1 }}>
                    <Field label="Semester">
                      <select value={form.semester} onChange={(e) => set("semester", e.target.value)} style={{ width: "100%" }}>
                        <option value="">Semester</option>
                        {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => <option key={s} value={s}>Sem {s}</option>)}
                      </select>
                    </Field>
                  </div>
                  <div style={{ flex: 1 }}>
                    <Field label="Batch year">{textInput("batch_year", "2021")}</Field>
                  </div>
                </div>
                <Field label="Admission date">{textInput("admission_date", "", "date")}</Field>
              </>
            )}

            {/* ---------- STEP: FACULTY / NON-TEACHING DETAILS ---------- */}
            {currentStepKey === "faculty" && (
              <>
                <p style={{ fontSize: 13, color: "#85839A", margin: "0 0 12px" }}>
                  Employee ID is generated automatically.
                </p>
                <Field label="Department">
                  <select value={form.department} onChange={(e) => set("department", e.target.value)} style={{ width: "100%" }}>
                    <option value="">Select department</option>
                    {departments.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
                  </select>
                </Field>
                <Field label="Qualification">{textInput("qualification", "M.E., Ph.D.")}</Field>
                <Field label="Specialization">{textInput("specialization", "Machine Learning")}</Field>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}><Field label="Date of joining">{textInput("date_of_joining", "", "date")}</Field></div>
                  <div style={{ flex: 1 }}><Field label="Experience (years)">{textInput("experience_years", "6")}</Field></div>
                </div>
              </>
            )}

            {/* ---------- STEP: ADMIN DETAILS ---------- */}
            {currentStepKey === "adminDetails" && (
              <>
                <p style={{ fontSize: 13, color: "#85839A", margin: "0 0 12px" }}>
                  Choose the admin sub role. Employee ID is generated automatically.
                </p>
                <Field label="Sub role">
                  <select value={form.sub_role} onChange={(e) => set("sub_role", e.target.value)} style={{ width: "100%" }}>
                    <option value="">Select sub role</option>
                    {(SUB_ROLES.admin).map((s) => (<option key={s.value} value={s.value}>{s.label}</option>))}
                  </select>
                </Field>
              </>
            )}

            {/* ---------- STEP: PARENT (of a student) ---------- */}
            {currentStepKey === "parent" && (
              <>
                <p style={{ fontSize: 13, color: "#85839A", margin: "0 0 12px" }}>
                  Guardian details for this student (optional).
                </p>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}><Field label="Father's name">{textInput("father_name", "Kumar S")}</Field></div>
                  <div style={{ flex: 1 }}><Field label="Mother's name">{textInput("mother_name", "Latha K")}</Field></div>
                </div>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}><Field label="Guardian phone">{textInput("guardian_phone", "98765 12345")}</Field></div>
                  <div style={{ flex: 1 }}><Field label="Guardian email">{textInput("guardian_email", "parent@gmail.com", "email")}</Field></div>
                </div>
                <Field label="Occupation">{textInput("occupation", "Teacher")}</Field>
              </>
            )}

            {/* ---------- STEP: PARENT CONTACT (parent role) ---------- */}
            {currentStepKey === "parentContact" && (
              <>
                <p style={{ fontSize: 13, color: "#85839A", margin: "0 0 12px" }}>
                  Basic parent account. Linking to a student can be done later.
                </p>
                <Field label="Occupation">{textInput("occupation", "Teacher")}</Field>
              </>
            )}

            {/* ---------- NAV BUTTONS ---------- */}
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginTop: 18 }}>
              <button className="btn-delete" style={{ padding: "9px 16px", visibility: step === 1 ? "hidden" : "visible" }} onClick={back}>
                Back
              </button>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn-delete" style={{ padding: "9px 16px" }} onClick={closeModal}>Cancel</button>
                <button className="btn-primary" style={{ padding: "9px 18px" }} onClick={next}>
                  {step === totalSteps ? (mode === "add" ? "Save user" : "Save changes") : "Next"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ================= INLINE STYLES =================
// ================= INLINE STYLES =================
const lbl = {
  fontSize: 13.5,
  color: "#5D5A6B",
  marginBottom: 6,
  fontWeight: 500,
};

const statusActive = {
  fontSize: 12.5,
  fontWeight: 500,
  padding: "3px 11px",
  borderRadius: 999,
  background: "#ecfdf3",
  color: "#15803d",
  display: "inline-block",
};

const statusInactive = {
  fontSize: 12.5,
  fontWeight: 500,
  padding: "3px 11px",
  borderRadius: 999,
  background: "#ECECF0",
  color: "#5D5A6B",
  display: "inline-block",
};

const csvBtn = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  background: "#ffffff",
  color: "#5D5A6B",
  border: "1px solid #E7E7EC",
  borderRadius: 9,
  padding: "10px 16px",
  fontSize: 15,
  fontWeight: 500,
  cursor: "pointer",
  transition: "0.15s",
};
