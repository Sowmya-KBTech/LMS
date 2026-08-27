
// ─── 1. Imports ──────────────────────────────────────────────────────────────
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import JSZip from "jszip";
import { saveAs } from "file-saver";
import ExcelJS from 'exceljs';
import API from "../api";

// ─── 2. Shared Styles ────────────────────────────────────────────────────────
const S = {
  card: { background:"#fff", borderRadius:14, padding:24, marginBottom:20, boxShadow:"0 1px 4px rgba(0,0,0,0.06)" },
  cardTitle: { fontSize:15, fontWeight:700, color:"#1a1f2e", marginBottom:18 },
  pageHeader: { textAlign:"center", marginBottom:28 },
  pageTitle: { fontSize:22, color:"#1a1f2e", fontWeight:700, margin:0 },
  pageSub: { color:"#7a8499", fontSize:13, marginTop:4 },
  th: { background:"#f4f7fc", color:"#7a8499", fontWeight:600, padding:"12px 16px", textAlign:"left", fontSize:12, whiteSpace:"nowrap" },
  td: { padding:"12px 16px", color:"#333", borderTop:"1px solid #f0f2f7", fontSize:13 },
  label: { display:"block", marginBottom:6, fontSize:13, fontWeight:600, color:"#94a3b8", textAlign:"left" },
  input: { background:"#1e2535", border:"1px solid #2e3648", borderRadius:8, color:"#d4dae8", fontSize:13, padding:"9px 12px", outline:"none", fontFamily:"inherit", width:"100%", boxSizing:"border-box" },
  select: { background:"#1e2535", border:"1px solid #2e3648", borderRadius:8, color:"#d4dae8", fontSize:13, padding:"9px 12px", outline:"none", fontFamily:"inherit", width:"100%", boxSizing:"border-box" },
  textarea: { background:"#1e2535", border:"1px solid #2e3648", borderRadius:8, color:"#d4dae8", fontSize:13, padding:"9px 12px", outline:"none", fontFamily:"inherit", width:"100%", boxSizing:"border-box", resize:"vertical", minHeight:70 },
  btnPrimary: { background:"#3d6ff5", color:"#fff", border:"none", padding:"9px 20px", borderRadius:8, fontSize:13, fontWeight:600, cursor:"pointer" },
  btnOutline: { background:"#fff", color:"#3d6ff5", border:"1.5px solid #3d6ff5", padding:"9px 20px", borderRadius:8, fontSize:13, fontWeight:600, cursor:"pointer" },
  btnDanger: { background:"#ef4444", color:"#fff", border:"none", padding:"5px 12px", borderRadius:6, fontSize:12, cursor:"pointer" },
  btnSuccess: { background:"#22b14c", color:"#fff", border:"none", padding:"5px 12px", borderRadius:6, fontSize:12, cursor:"pointer" },
  btnSm: { padding:"5px 12px", fontSize:12 },
  uploadArea: { border:"2px dashed #c5d0e8", borderRadius:10, padding:32, textAlign:"center", cursor:"pointer", color:"#8892a4", fontSize:13 },
  badge: { padding:"3px 10px", borderRadius:20, fontSize:11, fontWeight:600, display:"inline-block" },
  formRow: { display:"flex", gap:12, marginBottom:14, flexWrap:"wrap" },
  formGroup: { display:"flex", flexDirection:"column", gap:5, flex:1, minWidth:160 },
  // ✅ FIXED: tableWrap now properly scrolls horizontally
  tableWrap: { overflowX:"auto", borderRadius:10, border:"1px solid #e8edf5", width:"100%", display:"block" },
};

// ─── 3. Layout Components ────────────────────────────────────────────────────
//===============================teachersidebar====================================

function TeacherSidebar({ activePage, setActivePage }) {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const initials = user?.username?.slice(0,2).toUpperCase() || "TE";
  const navItems = [
    { key:"dashboard",   label:"📊 Dashboard" },
    { key:"my-courses",  label:"📚 My Courses" },
    { key:"assignments", label:"📋 Assignments" },
    { key:"submissions", label:"📤 Submissions" },
    { key:"lectures",    label:"🎬 Lectures" },
    { key:"notes",       label:"📄 Notes" },
    { key:"live-class",  label:"📅 Live Class" },
    { key:"quiz",        label:"❓ Quiz" },
    { key:"marks",       label:"📊 Marks" },
  ];
  return (
    <div style={{ width:240, minHeight:"100vh", background:"#1a1f2e", display:"flex", flexDirection:"column", flexShrink:0 }}>
      <div style={{ padding:"20px 16px", borderBottom:"1px solid #2a3040", display:"flex", alignItems:"center", gap:12 }}>
        <div style={{ width:44, height:44, borderRadius:"50%", background:"#3d6ff5", display:"flex", alignItems:"center", justifyContent:"center", fontWeight:700, color:"#fff", fontSize:15 }}>{initials}</div>
        <div>
          <div style={{ color:"#fff", fontWeight:600, fontSize:14 }}>{user?.username}</div>
          <div style={{ color:"#8892a4", fontSize:12 }}>Teacher</div>
        </div>
      </div>
      <nav style={{ padding:"16px 0", flex:1 }}>
        {navItems.map(item => (
          <div key={item.key} onClick={() => setActivePage(item.key)}
            style={{ padding:"10px 20px", color: activePage===item.key ? "#fff" : "#8892a4",
              fontSize:13, cursor:"pointer", display:"flex", alignItems:"center", gap:10,
              borderLeft: activePage===item.key ? "3px solid #fff" : "3px solid transparent",
              background: activePage===item.key ? "#3d6ff5" : "transparent",
              transition:"all 0.2s" }}>
            {item.label}
          </div>
        ))}
      </nav>
      <div style={{ padding:"16px 20px", borderTop:"1px solid #2a3040" }}>
        <button onClick={() => { localStorage.removeItem("user"); navigate("/"); }}
          style={{ background:"none", border:"1px solid #2a3040", color:"#8892a4", padding:"8px 14px", borderRadius:8, cursor:"pointer", fontSize:13, width:"100%" }}>
          ← Log out
        </button>
      </div>
    </div>
  );
}

//===============================teacher topbar====================================

function TopBar() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const initials = user?.username?.slice(0,2).toUpperCase() || "TE";
  return (
    <div style={{ background:"#fff", padding:"12px 28px", display:"flex", alignItems:"center", justifyContent:"space-between", borderBottom:"1px solid #e2e8f0" }}>
      <div style={{ fontWeight:700, color:"#1a1f2e", fontSize:15, display:"flex", alignItems:"center", gap:8 }}>
        <span style={{ color:"#3d6ff5", fontSize:18 }}>＋</span> Learning Management System
      </div>
      <div style={{ display:"flex", alignItems:"center", gap:16 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <div style={{ width:32, height:32, borderRadius:"50%", background:"#ede9fe", display:"flex", alignItems:"center", justifyContent:"center", fontWeight:700, color:"#5b21b6", fontSize:11 }}>{initials}</div>
          <div>
            <div style={{ fontWeight:600, fontSize:13, color:"#1a1f2e" }}>{user?.username}</div>
            <div style={{ background:"#ede9fe", color:"#5b21b6", fontSize:11, padding:"2px 8px", borderRadius:12, fontWeight:500 }}>Teacher</div>
          </div>
        </div>
        <button onClick={() => { localStorage.removeItem("user"); navigate("/"); }}
          style={{ background:"none", border:"1px solid #e2e8f0", padding:"6px 14px", borderRadius:6, color:"#555", fontSize:13, cursor:"pointer" }}>
          ↩ Log out
        </button>
      </div>
    </div>
  );
}

// ─── 4. Page Components ──────────────────────────────────────────────────────
//===============================teacher dashboard page====================================

function DashboardPage({ stats }) {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good Morning" : hour < 18 ? "Good Afternoon" : "Good Evening";
  const cards = [
    { label:"My Courses",   value: stats.total_courses||0,    bg:"#3d6ff5" },
    { label:"My Students",  value: stats.total_students||0,   bg:"#22b14c" },
    { label:"Enrollments",  value: stats.total_enrollments||0, bg:"#8b5cf6" },
    { label:"Assignments",  value: stats.total_assignments||0, bg:"#f97316" },
  ];
  return (
    <div>
      <div style={{ fontSize:22, fontWeight:700, color:"#1a1f2e", textAlign:"center", marginBottom:28 }}>
        {greeting}, {user?.username} 👋
      </div>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:20, marginBottom:24 }}>
        {cards.map(c => (
          <div key={c.label} style={{ borderRadius:14, padding:"28px 20px", background:c.bg, color:"#fff", textAlign:"center" }}>
            <div style={{ fontSize:14, fontWeight:600, marginBottom:12 }}>{c.label}</div>
            <div style={{ fontSize:36, fontWeight:700 }}>{c.value}</div>
          </div>
        ))}
      </div>
      <div style={{ ...S.card, textAlign:"center", color:"#8892a4", padding:40 }}>
        <div style={{ fontSize:40, marginBottom:12 }}>🎓</div>
        <div style={{ fontSize:15, fontWeight:600, color:"#1a1f2e" }}>Welcome to your LMS Teacher Dashboard</div>
        <div style={{ fontSize:13, marginTop:6 }}>Use the sidebar to manage your courses, lectures, assignments, and more.</div>
      </div>
    </div>
  );
}

//===============================my course page====================================

function MyCoursesPage({ courses }) {
  return (
    <div>
      <div style={S.pageHeader}>
        <h1 style={S.pageTitle}>My Courses</h1>
        <p style={S.pageSub}>Courses assigned to you</p>
      </div>
      <div style={S.card}>
        <div style={S.cardTitle}>All Courses</div>
        <div style={S.tableWrap}><table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
          
            <thead><tr>
              {["Course Name","Subject","Enrolled Students","Status","Actions"].map(h=>(
                <th key={h} style={S.th}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {courses.length === 0 ? (
                <tr><td colSpan={5} style={{ padding:20, textAlign:"center", color:"#7a8499" }}>No courses assigned</td></tr>
              ) : courses.map((c,i) => (
                <tr key={i}>
                  <td style={S.td}>{c.title||c.name}</td>
                  <td style={S.td}>{c.department||"General"}</td>
                  <td style={S.td}>{c.student_count||0}</td>
                  <td style={S.td}><span style={{ ...S.badge, background:"#dcfce7", color:"#166534" }}>Active</span></td>
                  <td style={S.td}><button style={{ ...S.btnPrimary, ...S.btnSm, marginRight:4 }}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


//===============================assignment page====================================

function AssignmentsPage({ courses }) {
  const [assignments, setAssignments] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title:"", description:"", due_date:"", course_id:"", target_group:"All Students", max_marks:100, allowed_types:["PDF","DOCX"], reference_file: null });
  const [toast, setToast] = useState(null);
  const notify = (msg, type="success") => { setToast({msg,type}); setTimeout(()=>setToast(null),3000); };
  const fetchAssignments = async () => {
    try { const res = await API.get("learning/assignments/"); setAssignments(res.data); }
    catch { notify("Failed to load assignments","error"); }
  };
  useEffect(() => { fetchAssignments(); }, []);
  const createAssignment = async () => {
    if (!form.title) return;
    try {
      const payload = new FormData();
      payload.append("title", form.title);
      payload.append("description", form.description);
      payload.append("due_date", form.due_date || "");
      payload.append("course", form.course_id ? Number(form.course_id) : "");
      payload.append("max_marks", form.max_marks);
      payload.append("target_group", form.target_group);
      payload.append("allowed_types", form.allowed_types.join(","));
      if (form.reference_file) payload.append("reference_file", form.reference_file);
      await API.post("learning/assignments/", payload, { headers: { "Content-Type": "multipart/form-data" } });
      setForm({title:"", description:"", due_date:"", course_id:"", target_group:"All Students", max_marks:100, allowed_types:["PDF","DOCX"], reference_file:null});
      setShowForm(false);
      notify("Assignment created!");
      fetchAssignments();
    }
    catch { notify("Create failed","error"); }
  };
  const deleteAssignment = async (id) => {
    try { await API.delete(`learning/assignments/${id}/`); notify("Deleted"); fetchAssignments(); }
    catch { notify("Delete failed","error"); }
  };
  return (
    <div>
      {toast && (
        <div style={{ position:"fixed", top:24, right:24, zIndex:999, padding:"12px 20px", borderRadius:12,
          background: toast.type==="error" ? "#fff1f2" : "#f0fdf4",
          border:`1px solid ${toast.type==="error" ? "#fecdd3" : "#bbf7d0"}`,
          color: toast.type==="error" ? "#e11d48" : "#16a34a", fontSize:13.5, fontWeight:600 }}>
          {toast.msg}
        </div>
      )}
      <div style={S.pageHeader}>
        <h1 style={S.pageTitle}>Assignments</h1>
        <p style={S.pageSub}>{assignments.length} total assignments</p>
      </div>
      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:16 }}>
        <button style={S.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? "✕ Cancel" : "+ New Assignment"}
        </button>
      </div>
      {showForm && (
        <div style={S.card}>
          <div style={S.cardTitle}>New Assignment</div>
          <div style={S.formRow}>
            <div style={S.formGroup}>
              <label style={S.label}>Assignment Title</label>
              <input style={S.input} placeholder="e.g. ML Mini Project" value={form.title} onChange={e=>setForm({...form,title:e.target.value})} />
            </div>
            <div style={S.formGroup}>
              <label style={S.label}>Select Course</label>
              <select style={S.select} value={form.course_id} onChange={e=>setForm({...form,course_id:e.target.value})}>
                <option value="">-- Select Course --</option>
                {courses.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
              </select>
            </div>
          </div>
          <div style={{ display:"flex", gap:16, marginBottom:14, flexWrap:"wrap", alignItems:"flex-start" }}>
            <div style={{ flex:1, minWidth:180 }}>
              <label style={S.label}>Target Students / Group</label>
              <select style={S.select} value={form.target_group} onChange={e=>setForm({...form,target_group:e.target.value})}>
                <option>All Students</option>
              </select>
            </div>
            <div style={{ flex:1, minWidth:180 }}>
              <label style={S.label}>Submission Deadline</label>
              <input type="date" style={S.input} value={form.due_date} onChange={e=>setForm({...form,due_date:e.target.value})} />
            </div>
            <div style={{ flex:1, minWidth:140 }}>
              <label style={S.label}>Maximum Marks</label>
              <input type="number" style={S.input} value={form.max_marks} onChange={e=>setForm({...form,max_marks:e.target.value})} />
            </div>
          </div>
          <div style={{ marginBottom:14 }}>
            <label style={S.label}>Instructions / Description</label>
            <textarea style={S.textarea} placeholder="Describe the assignment task clearly..." value={form.description} onChange={e=>setForm({...form,description:e.target.value})} />
          </div>
          <button style={S.btnPrimary} onClick={createAssignment}>Create Assignment</button>
        </div>
      )}
      <div style={S.card}>
        <div style={S.cardTitle}>All Assignments</div>
        <div style={S.tableWrap}>
          <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
            <thead><tr>
              {["Title","Deadline","Status","Actions"].map(h=>(
                <th key={h} style={S.th}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {assignments.length === 0 ? (
                <tr><td colSpan={4} style={{ padding:20, textAlign:"center", color:"#7a8499" }}>No assignments yet</td></tr>
              ) : assignments.map(a => {
                const overdue = a.due_date && new Date(a.due_date) < new Date();
                return (
                  <tr key={a.id}>
                    <td style={S.td}>{a.title}</td>
                    <td style={S.td}>{a.due_date ? new Date(a.due_date).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"}) : "---"}</td>
                    <td style={S.td}>
                      <span style={{ ...S.badge, background: overdue?"#fee2e2":"#dcfce7", color: overdue?"#991b1b":"#166534" }}>
                        {overdue ? "Overdue" : "Active"}
                      </span>
                    </td>
                    <td style={S.td}>
                      <button style={{ ...S.btnDanger }} onClick={()=>deleteAssignment(a.id)}>Delete</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

//===============================lectures page====================================

function LecturesPage({ courses }) {
  const navigate = useNavigate();
  const [lectures, setLectures] = useState([]);
  const [activeVideo, setActiveVideo] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const [form, setForm] = useState({ title:"", description:"",
  lecture_type:"recorded", course_id:"", video_file:null,
  meeting_link:"", scheduled_at:"", chapter:"", video_link:"" });
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const notify = (msg, type="success") => { setToast({msg,type}); setTimeout(()=>setToast(null),3000); };
  const fetchLectures = async () => {
    try { const res = await API.get("learning/lectures/"); setLectures(res.data); }
    catch {}
  };
  useEffect(() => { fetchLectures(); }, []);
  const handleUpload = async () => {
    if (!form.title) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("title", form.title);
    fd.append("description", form.description);
    fd.append("lecture_type", form.lecture_type);
    if (form.lecture_type === "recorded") {
      if (form.video_file)
        fd.append("video_file", form.video_file);
      if (form.video_link)
        fd.append("meeting_link", form.video_link); 
      }
    if (form.lecture_type === "live") {
      fd.append("meeting_link", form.meeting_link);
      fd.append("scheduled_at", form.scheduled_at);
    }
    try {
      await API.post("learning/lectures/", fd);
      notify("Lecture uploaded!");
      setForm({ title:"", description:"", lecture_type:"recorded", course_id:"", video_file:null, meeting_link:"", scheduled_at:"", chapter:"", video_link:"" });
      setShowForm(false);
      fetchLectures();
    }
    catch { notify("Upload failed","error"); }
    finally { setUploading(false); }
  };
  const deleteLecture = async (id) => {
    try { await API.delete(`learning/lectures/${id}/`); notify("Deleted"); fetchLectures(); }
    catch { notify("Delete failed","error"); }
  };
  return (
    <div>
      {toast && (
        <div style={{ position:"fixed", top:24, right:24, zIndex:999, padding:"12px 20px", borderRadius:12,
          background: toast.type==="error" ? "#fff1f2" : "#f0fdf4",
          border:`1px solid ${toast.type==="error" ? "#fecdd3" : "#bbf7d0"}`,
          color: toast.type==="error" ? "#e11d48" : "#16a34a", fontSize:13.5, fontWeight:600 }}>
          {toast.msg}
        </div>
      )}
      <div style={S.pageHeader}><h1 style={S.pageTitle}>Upload Lectures</h1></div>
      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:16 }}>
        <button style={S.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? "✕ Cancel" : "+ Add Lecture"}
        </button>
      </div>
      {showForm && (
        <div style={S.card}>
          <div style={S.cardTitle}>Upload New Lecture</div>
          <div style={S.formRow}>
            <div style={S.formGroup}>
              <label style={S.label}>Lecture Title</label>
              <input style={S.input} placeholder="e.g. Introduction to ML" value={form.title} onChange={e=>setForm({...form,title:e.target.value})} />
            </div>
            <div style={S.formGroup}>
              <label style={S.label}>Select Course</label>
              <select style={S.select} value={form.course_id} onChange={e=>setForm({...form,course_id:e.target.value})}>
                <option value="">-- Select Course --</option>
                {courses.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
              </select>
            </div>
          </div>
          <div style={S.formRow}>
            <div style={S.formGroup}>
              <label style={S.label}>Chapter / Week Number</label>
              <input style={S.input} placeholder="e.g. Week 1 / Chapter 3" value={form.chapter} onChange={e=>setForm({...form,chapter:e.target.value})} />
            </div>
            <div style={S.formGroup}>
              <label style={S.label}>Description</label>
              <input style={S.input} placeholder="Brief description of lecture" value={form.description} onChange={e=>setForm({...form,description:e.target.value})} />
            </div>
          </div>
          <div style={S.formRow}>
            <div style={S.formGroup}>
              <label style={S.label}>Upload Video File</label>
              <div style={{ border:"2px dashed #c5d0e8", borderRadius:10, padding:32, textAlign:"center", cursor:"pointer", color:"#8892a4", fontSize:13 }}
                onClick={()=>document.getElementById("vid-upload").click()}>
                <div style={{ fontSize:28, marginBottom:8 }}>🎬</div>
                <div>{form.video_file ? form.video_file.name : "Drag & drop a video file here"}</div>
                <div style={{ fontSize:11, marginTop:4 }}>MP4, MOV, AVI -- Max 2GB</div>
                <input id="vid-upload" type="file" accept="video/*" style={{ display:"none" }} onChange={e=>setForm({...form,video_file:e.target.files[0]})} />
              </div>
            </div>
            <div style={S.formGroup}>
              <label style={S.label}>Or Paste Video Link</label>
              <input style={S.input} placeholder="YouTube / Google Drive / Vimeo URL" value={form.video_link} onChange={e=>setForm({...form,video_link:e.target.value})} />
              <div style={{ marginTop:10, borderRadius:10, overflow:"hidden", background:"#1e2535", height:160, display:"flex", alignItems:"center", justifyContent:"center" }}>
                {form.video_link ? (
                  <iframe width="100%" height="160" src={
                    form.video_link.includes("youtube.com/watch")
                      ? form.video_link.replace("watch?v=","embed/")
                      : form.video_link.includes("youtu.be/")
                      ? form.video_link.replace("youtu.be/","youtube.com/embed/")
                      : form.video_link
                  } frameBorder="0" allowFullScreen style={{ borderRadius:10 }} />
                ) : (
                  <div style={{ color:"#8892a4", fontSize:24 }}>▶</div>
                )}
              </div>
            </div>
          </div>
          <button style={S.btnPrimary} onClick={handleUpload} disabled={uploading}>
            {uploading ? "Uploading..." : "Upload Lecture"}
          </button>
        </div>
      )}
      <div style={S.card}>
        <div style={S.cardTitle}>Uploaded Lectures</div>
        <div style={S.tableWrap}>
          <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
            <thead><tr>
              {["Title","Type","Description","Actions"].map(h=>(
                <th key={h} style={S.th}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {lectures.length === 0 ? (
                <tr><td colSpan={4} style={{ padding:20, textAlign:"center", color:"#7a8499" }}>No lectures uploaded yet</td></tr>
              ) : lectures.map(l => (
                <tr key={l.id}>
                  <td style={S.td}>{l.title}</td>
                  <td style={S.td}>{l.lecture_type === "live" ? "Live" : "Recorded"}</td>
                  <td style={S.td}>{l.description || "---"}</td>
                  <td style={S.td}>
                    <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                      
                      {l.lecture_type === "recorded" && (l.video_file || l.meeting_link) && (
                        <button
                          style={S.watchBtn}
                          onClick={() => window.open(`/watch/${l.id}`, "_blank")}
                        >
                          ▶ Watch
                        </button>
                      )}
                    {l.lecture_type === "live" && l.meeting_link && (
                      <a href={l.meeting_link} target="_blank" rel="noreferrer">
                        <button style={{ background:"#22b14c", color:"#fff", border:"none", padding:"6px 14px", borderRadius:7, cursor:"pointer", fontSize:12, fontWeight:600 }}>
                          📡 Join Live
                          </button>
                          </a>
                        )}
                        <button style={{ ...S.btnDanger }} onClick={()=>deleteLecture(l.id)}>Delete</button>
                        </div>
                      </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

  </div>

  {activeVideo && (
    <div style={S.modalOverlay} onClick={() => setActiveVideo(null)}>
      <div style={S.modalBox} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHeader}>
          <span style={{ fontWeight:700, fontSize:15 }}>{activeVideo.title}</span>
          <button style={S.closeBtn} onClick={() => setActiveVideo(null)}>✕</button>
          </div>
          {activeVideo.isEmbed ? (
            <iframe
              key={activeVideo.url}
              src={activeVideo.url}
              width="100%"
              height="420"
              frameBorder="0"
              allowFullScreen
              allow="autoplay; encrypted-media"
              style={{ borderRadius:10 }}
            />
          ) : (
            <video
            key={activeVideo.url}
            controls
            autoPlay
            style={{ width:"100%", borderRadius:10, background:"#000", maxHeight:420 }}
          >
            <source src={activeVideo.url} type="video/webm" />
            <source src={activeVideo.url} type="video/mp4" />
            Your browser does not support video playback.
          </video>
        )}
    </div>
  </div>
)}

</div>

);

}


//===============================note page====================================

function NotesPage({ courses }) {
  const [notes, setNotes] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title:"", course_id:"", chapter:"", description:"", file:null });
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const [editNote, setEditNote] = useState(null);
  const [editForm, setEditForm] = useState({ title:"", course_id:"", chapter:"", description:"" });

  const notify = (msg, type="success") => { setToast({msg,type}); setTimeout(()=>setToast(null),3000); };

  const fetchNotes = async () => {
    try { const res = await API.get("learning/notes/"); setNotes(res.data); }
    catch {}
  };

  useEffect(() => { fetchNotes(); }, []);

  const handleUpload = async () => {
    if (!form.title || !form.file) { notify("Title and file are required","error"); return; }
    setUploading(true);
    const fd = new FormData();
    fd.append("title", form.title);
    fd.append("description", form.description);
    fd.append("chapter", form.chapter);
    if (form.course_id) fd.append("course", form.course_id);
    fd.append("file", form.file);
    try {
      await API.post("learning/notes/", fd);
      notify("Note uploaded!");
      setForm({ title:"", course_id:"", chapter:"", description:"", file:null });
      setShowForm(false);
      fetchNotes();
    }
    catch { notify("Upload failed","error"); }
    finally { setUploading(false); }
  };

  const deleteNote = async (id) => {
    try { await API.delete(`learning/notes/${id}/`); notify("Deleted"); fetchNotes(); }
    catch { notify("Delete failed","error"); }
  };

  const openEdit = (n) => {
    setEditNote(n);
    setEditForm({ title: n.title, course_id: n.course || "", chapter: n.chapter || "", description: n.description || "" });
  };

  const handleUpdate = async () => {
    try {
      await API.patch(`learning/notes/${editNote.id}/`, editForm);
      notify("Note updated!");
      setEditNote(null);
      fetchNotes();
    } catch { notify("Update failed", "error"); }
  };

  return (
    <div>

      {/* ── EDIT MODAL ── */}
      {editNote && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.45)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center" }}>
          <div style={{ background:"#fff", borderRadius:14, padding:28, width:460, boxShadow:"0 8px 32px rgba(0,0,0,0.18)" }}>
            <h3 style={{ marginBottom:16, fontSize:16, fontWeight:700, color:"#1a1f2e" }}>✏️ Edit Note</h3>
            <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
              <div>
                <label style={{ ...S.label, color:"#475569" }}>Note Title</label>
                <input style={S.input} placeholder="Note Title" value={editForm.title}
                  onChange={e => setEditForm({...editForm, title: e.target.value})} />
              </div>
              <div>
                <label style={{ ...S.label, color:"#475569" }}>Select Course</label>
                <select style={S.select} value={editForm.course_id}
                  onChange={e => setEditForm({...editForm, course_id: e.target.value})}>
                  <option value="">-- Select Course --</option>
                  {courses.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
                </select>
              </div>
              <div>
                <label style={{ ...S.label, color:"#475569" }}>Chapter / Topic</label>
                <input style={S.input} placeholder="Chapter / Topic" value={editForm.chapter}
                  onChange={e => setEditForm({...editForm, chapter: e.target.value})} />
              </div>
              <div>
                <label style={{ ...S.label, color:"#475569" }}>Description (optional)</label>
                <input style={S.input} placeholder="Description (optional)" value={editForm.description}
                  onChange={e => setEditForm({...editForm, description: e.target.value})} />
              </div>
            </div>
            <div style={{ display:"flex", gap:10, marginTop:20, justifyContent:"flex-end" }}>
              <button style={S.btnDanger} onClick={() => setEditNote(null)}>Cancel</button>
              <button style={S.btnPrimary} onClick={handleUpdate}>💾 Save Changes</button>
            </div>
          </div>
        </div>
      )}

      {/* ── TOAST ── */}
      {toast && (
        <div style={{ position:"fixed", top:24, right:24, zIndex:999, padding:"12px 20px", borderRadius:12,
          background: toast.type==="error" ? "#fff1f2" : "#f0fdf4",
          border:`1px solid ${toast.type==="error" ? "#fecdd3" : "#bbf7d0"}`,
          color: toast.type==="error" ? "#e11d48" : "#16a34a", fontSize:13.5, fontWeight:600 }}>
          {toast.msg}
        </div>
      )}

      <div style={S.pageHeader}><h1 style={S.pageTitle}>Upload Notes</h1></div>

      {/* ── TOGGLE BUTTON ── */}
      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:16 }}>
        <button style={S.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? "✕ Cancel" : "+ Upload Notes"}
        </button>
      </div>

      {/* ── UPLOAD FORM ── */}
      {showForm && (
        <div style={S.card}>
          <div style={S.cardTitle}>Upload New Notes</div>
          <div style={S.formRow}>
            <div style={S.formGroup}><label style={S.label}>Note Title</label>
              <input style={S.input} placeholder="e.g. Regression Algorithms" value={form.title}
                onChange={e=>setForm({...form,title:e.target.value})} />
            </div>
            <div style={S.formGroup}><label style={S.label}>Select Course</label>
              <select style={S.select} value={form.course_id} onChange={e=>setForm({...form,course_id:e.target.value})}>
                <option value="">-- Select Course --</option>
                {courses.map(c => (<option key={c.id} value={c.id}>{c.title}</option>))}
              </select>
            </div>
          </div>
          <div style={S.formRow}>
            <div style={S.formGroup}><label style={S.label}>Topic / Chapter</label>
              <input style={S.input} placeholder="e.g. Chapter 2" value={form.chapter}
                onChange={e=>setForm({...form,chapter:e.target.value})} />
            </div>
            <div style={S.formGroup}><label style={S.label}>Description (optional)</label>
              <input style={S.input} placeholder="Short note about this file" value={form.description}
                onChange={e=>setForm({...form,description:e.target.value})} />
            </div>
          </div>
          <div style={S.formRow}>
            <div style={S.formGroup}>
              <label style={S.label}>Upload File</label>
              <div style={S.uploadArea} onClick={()=>document.getElementById("notes-file").click()}>
                <div style={{ fontSize:28, marginBottom:8 }}>📄</div>
                <div>{form.file ? form.file.name : "Upload PDF, Word Doc, or Image"}</div>
                <div style={{ fontSize:11, marginTop:4 }}>.pdf .docx .jpg .png -- Max 50MB</div>
                <input id="notes-file" type="file" accept=".pdf,.docx,.jpg,.png" style={{ display:"none" }}
                  onChange={e=>setForm({...form, file:e.target.files[0]})} />
              </div>
            </div>
          </div>
          <button style={S.btnPrimary} onClick={handleUpload} disabled={uploading}>
            {uploading ? "Uploading..." : "Upload Note"}
          </button>
        </div>
      )}

      {/* ── UPLOADED NOTES TABLE ── */}
      {/* ✅ KEY FIX: removed overflow:hidden from card, table scrolls properly now */}
      <div style={{ ...S.card, overflow:"visible" }}>
        <div style={S.cardTitle}>Uploaded Notes</div>

        {/* ✅ FIX: inline scroll wrapper — does NOT depend on S.tableWrap being block */}
        <div style={{ overflowX:"auto", width:"100%" }}>
          <table style={{ minWidth:800, width:"100%", borderCollapse:"collapse", fontSize:13, tableLayout:"auto" }}>
            <thead>
              <tr>
                <th style={{ ...S.th, minWidth:160 }}>Note Title</th>
                <th style={{ ...S.th, minWidth:130 }}>Course</th>
                <th style={{ ...S.th, minWidth:130 }}>Chapter/Topic</th>
                <th style={{ ...S.th, minWidth:150 }}>File</th>
                {/* ✅ Actions column is always visible — highlighted in blue */}
                <th style={{ ...S.th, minWidth:160, background:"#e8f0fe", color:"#3d6ff5" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {notes.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding:20, textAlign:"center", color:"#7a8499" }}>
                    No notes uploaded yet
                  </td>
                </tr>
              ) : notes.map(n => (
                <tr key={n.id}>
                  <td style={S.td}>{n.title}</td>
                  <td style={S.td}>{n.course_title || "---"}</td>
                  <td style={S.td}>{n.chapter || "---"}</td>

                  {/* ── FILE COLUMN (View + Download) ── */}
                  <td style={S.td}>
                    {n.file && (() => {
                      const fileUrl = n.file.startsWith("http") ? n.file : `http://127.0.0.1:8000${n.file}`;
                      const isPdf = n.file.toLowerCase().endsWith(".pdf");
                      return (
                        <div style={{ display:"flex", gap:6, alignItems:"center", flexWrap:"nowrap" }}>
                          {isPdf && (
                            <a href={fileUrl} target="_blank" rel="noreferrer"
                              style={{ color:"#3d6ff5", fontSize:12, textDecoration:"none", whiteSpace:"nowrap" }}>
                              👁 View
                            </a>
                          )}
                          <a
                            href="#"
                            style={{ color:"#3d6ff5", fontSize:12, textDecoration:"none", cursor:"pointer", whiteSpace:"nowrap" }}
                            onClick={async (e) => {
                              e.preventDefault();
                              try {
                                const res = await fetch(fileUrl);
                                const blob = await res.blob();
                                const blobUrl = window.URL.createObjectURL(blob);
                                const a = document.createElement("a");
                                a.href = blobUrl;
                                a.download = n.file.split("/").pop();
                                document.body.appendChild(a);
                                a.click();
                                a.remove();
                                window.URL.revokeObjectURL(blobUrl);
                              } catch (err) {
                                alert("Download failed. Please try again.");
                              }
                            }}
                          >
                            📥 Download
                          </a>
                        </div>
                      );
                    })()}
                  </td>

                  {/* ✅ ACTIONS COLUMN — Edit + Delete always visible */}
                  <td style={{ ...S.td, background:"#fafbff" }}>
                    <div style={{ display:"flex", gap:8, alignItems:"center", flexWrap:"nowrap" }}>
                      <button
                        style={{
                          background:"#fff7ed",
                          color:"#f97316",
                          border:"1px solid #fed7aa",
                          padding:"6px 14px",
                          borderRadius:6,
                          fontSize:12,
                          cursor:"pointer",
                          fontWeight:600,
                          whiteSpace:"nowrap"
                        }}
                        onClick={() => openEdit(n)}
                      >
                        ✏️ Edit
                      </button>
                      <button
                        style={{
                          ...S.btnDanger,
                          padding:"6px 14px",
                          whiteSpace:"nowrap"
                        }}
                        onClick={() => deleteNote(n.id)}
                      >
                        🗑 Delete
                      </button>
                    </div>
                  </td>

                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

//===============================live class page====================================

function LiveClassPage({ courses }) {
  const [form, setForm] = useState({ title:"", course_id:"", date:"", time:"", duration:60, meeting_link:"", agenda:"" });
  const [sessions, setSessions] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState("upcoming");
  const [reminder, setReminder] = useState(true);
  const notify = (msg, type="success") => { setToast({msg,type}); setTimeout(()=>setToast(null),3000); };
  const fetchSessions = async () => {
    try { const res = await API.get("learning/live-sessions/"); setSessions(res.data); } catch {}
  };
  useEffect(() => { fetchSessions(); }, []);
  const handleSchedule = async () => {
    if (!form.title || !form.date || !form.meeting_link) { notify("Title, date and meeting link are required","error"); return; }
    setUploading(true);
    try {
      await API.post("learning/live-sessions/", { title:form.title, course:form.course_id||null, date:form.date, time:form.time, duration:form.duration, meeting_link:form.meeting_link, agenda:form.agenda, send_reminder:reminder });
      notify("Session scheduled!");
      setForm({ title:"", course_id:"", date:"", time:"", duration:60, meeting_link:"", agenda:"" });
      setShowForm(false);
      fetchSessions();
    } catch { notify("Failed to schedule","error"); }
    finally { setUploading(false); }
  };
  const handleCancel = async (id) => {
    if (!window.confirm("Cancel this session?")) return;
    try { await API.delete(`learning/live-sessions/${id}/`); notify("Session cancelled"); fetchSessions(); }
    catch { notify("Failed to cancel","error"); }
  };
  const getPlatform = (link) => {
    if (!link) return "";
    if (link.includes("meet.google")) return "Google Meet";
    if (link.includes("zoom")) return "Zoom";
    if (link.includes("teams")) return "Teams";
    return "Online";
  };
  const formatDate = (d) => { if (!d) return ""; return new Date(d).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"}); };
  const formatTime = (t) => { if (!t) return ""; const [h,m]=t.split(":"); const dt=new Date(); dt.setHours(h,m); return dt.toLocaleTimeString("en-US",{hour:"numeric",minute:"2-digit"}); };
  const now = new Date();
  const upcomingSessions = sessions.filter(s => new Date(`${s.date}T${s.time||"23:59:59"}`) >= now);
  const pastSessions = sessions.filter(s => new Date(`${s.date}T${s.time||"23:59:59"}`) < now);
  const displayedSessions = activeTab === "upcoming" ? upcomingSessions : pastSessions;
  return (
    <div>
      {toast && (<div style={{ padding:"10px 16px", background:toast.type==="error"?"#fee2e2":"#dcfce7", color:toast.type==="error"?"#dc2626":"#166534", borderRadius:8, marginBottom:12 }}>{toast.msg}</div>)}
      <div style={S.pageHeader}><h1 style={S.pageTitle}>Schedule Live Class</h1></div>
      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:16 }}>
        <button style={S.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? "✕ Cancel" : "+ Schedule Live Class"}
        </button>
      </div>
      {showForm && (
        <div style={S.card}>
          <div style={S.cardTitle}>Schedule New Session</div>
          <div style={S.formRow}>
            <div style={S.formGroup}><label style={S.label}>Session Title</label>
              <input style={S.input} placeholder="e.g. Midterm Revision -- ML" value={form.title} onChange={e=>setForm({...form,title:e.target.value})} />
            </div>
            <div style={S.formGroup}><label style={S.label}>Select Course</label>
              <select style={S.select} value={form.course_id} onChange={e=>setForm({...form,course_id:e.target.value})}>
                <option value="">-- Select Course --</option>
                {courses.map(c=><option key={c.id} value={c.id}>{c.title}</option>)}
              </select>
            </div>
          </div>
          <div style={S.formRow}>
            <div style={S.formGroup}><label style={S.label}>Date</label><input type="date" style={S.input} value={form.date} onChange={e=>setForm({...form,date:e.target.value})} /></div>
            <div style={S.formGroup}><label style={S.label}>Time</label><input type="time" style={S.input} value={form.time} onChange={e=>setForm({...form,time:e.target.value})} /></div>
            <div style={S.formGroup}><label style={S.label}>Duration (minutes)</label><input type="number" style={S.input} value={form.duration} onChange={e=>setForm({...form,duration:e.target.value})} /></div>
          </div>
          <div style={S.formRow}>
            <div style={{...S.formGroup,flex:1}}><label style={S.label}>Meeting Link (Zoom / Meet / Teams)</label>
              <input type="url" style={S.input} placeholder="https://meet.google.com/..." value={form.meeting_link} onChange={e=>setForm({...form,meeting_link:e.target.value})} />
            </div>
          </div>
          <div style={{marginBottom:14}}><label style={S.label}>Agenda / Description</label>
            <textarea style={S.textarea} placeholder="Describe the agenda of this session..." value={form.agenda} onChange={e=>setForm({...form,agenda:e.target.value})} />
          </div>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <label style={{display:"flex",alignItems:"center",gap:10,cursor:"pointer",fontSize:13,color:"#475569"}}>
              <div onClick={()=>setReminder(!reminder)} style={{width:42,height:24,borderRadius:12,cursor:"pointer",background:reminder?"#3b82f6":"#cbd5e1",position:"relative",transition:"background 0.2s"}}>
                <div style={{position:"absolute",top:3,left:reminder?20:3,width:18,height:18,borderRadius:"50%",background:"#fff",transition:"left 0.2s"}} />
              </div>
              Send auto-reminder to students
            </label>
            <button style={S.btnPrimary} onClick={handleSchedule} disabled={uploading}>{uploading?"Scheduling...":"Schedule Session"}</button>
          </div>
        </div>
      )}
      <div style={S.card}>
        <div style={{display:"flex",borderBottom:"1px solid #e2e8f0",marginBottom:16}}>
          {["upcoming","past"].map(tab=>(
            <button key={tab} onClick={()=>setActiveTab(tab)}
              style={{padding:"10px 20px",border:"none",background:"none",cursor:"pointer",fontWeight:activeTab===tab?600:400,color:activeTab===tab?"#3b82f6":"#64748b",borderBottom:activeTab===tab?"2px solid #3b82f6":"2px solid transparent",fontSize:14,textTransform:"capitalize"}}>
              {tab==="upcoming"?"Upcoming Sessions":"Past Sessions"}
            </button>
          ))}
        </div>
        {displayedSessions.length===0 ? (
          <div style={{padding:20,textAlign:"center",color:"#7a8499",fontSize:13}}>No {activeTab} sessions</div>
        ) : displayedSessions.map(s=>(
          <div key={s.id} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"14px 16px",borderLeft:"3px solid #3b82f6",background:"#f8fafc",borderRadius:8,marginBottom:10}}>
            <div>
              <div style={{fontWeight:600,fontSize:15,color:"#0f172a",marginBottom:4}}>{s.title}</div>
              <div style={{fontSize:13,color:"#64748b"}}>📅 {formatDate(s.date)} &nbsp;|&nbsp; 🕐 {formatTime(s.time)} &nbsp;|&nbsp; {s.duration} min &nbsp;|&nbsp; {getPlatform(s.meeting_link)}</div>
            </div>
            <div style={{display:"flex",gap:8}}>
              {s.meeting_link && (<a href={s.meeting_link} target="_blank" rel="noreferrer" style={{padding:"6px 14px",background:"#eff6ff",color:"#3b82f6",borderRadius:6,fontSize:13,textDecoration:"none",fontWeight:500}}>Join</a>)}
              {activeTab==="upcoming" && (<>
                <button style={{padding:"6px 14px",background:"#fff",border:"1px solid #e2e8f0",borderRadius:6,fontSize:13,cursor:"pointer",color:"#374151"}}>Reschedule</button>
                <button onClick={()=>handleCancel(s.id)} style={{padding:"6px 14px",background:"#fee2e2",border:"none",borderRadius:6,fontSize:13,cursor:"pointer",color:"#dc2626",fontWeight:500}}>Cancel</button>
              </>)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==============================QUIZ PAGE =====================================

function QuizPage({ courses }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title:"", course_id:"", time_limit:30, available_from:"", available_until:"", total_marks:50 });
  const [questions, setQuestions] = useState([]);
  const [quizzes, setQuizzes] = useState([]);
  const [expandedQuiz, setExpandedQuiz] = useState(null);
  const [editingQuizId, setEditingQuizId] = useState(null);
  const [questionForm, setQuestionForm] = useState(null);
  const [addingQuestionToQuiz, setAddingQuestionToQuiz] = useState(null);
  const [newQuestion, setNewQuestion] = useState({
    question_text:"", question_type:"mcq",
    option_a:"", option_b:"", option_c:"", option_d:"",
    correct_answer:"", marks:5
  });
  const [toast, setToast] = useState(null);
  const notify = (msg, type="success") => { setToast({msg,type}); setTimeout(()=>setToast(null),3000); };

  const fetchQuizzes = async () => {
    try { const res = await API.get("learning/quizzes/"); setQuizzes(res.data); } catch {}
  };
  useEffect(() => { fetchQuizzes(); }, []);

  const addQuestion = () => setQuestions([...questions, { question_text:"", question_type:"mcq", option_a:"", option_b:"", option_c:"", option_d:"", correct_answer:"", marks:5 }]);
  const updateQuestion = (index, field, value) => { const u=[...questions]; u[index][field]=value; setQuestions(u); };
  const removeQuestion = (index) => setQuestions(questions.filter((_,i)=>i!==index));

  const handleEdit = (quiz) => {
    setForm({ title:quiz.title, course_id:quiz.course ? String(quiz.course) : "", time_limit:quiz.time_limit, available_from:quiz.available_from||"", available_until:quiz.available_until||"", total_marks:quiz.total_marks });
    setEditingQuizId(quiz.id);
    setShowForm(true);
    setQuestions([]);
    window.scrollTo({ top:0, behavior:"smooth" });
  };
  const handleCancelEdit = () => {
    setEditingQuizId(null);
    setShowForm(false);
    setForm({ title:"", course_id:"", time_limit:30, available_from:"", available_until:"", total_marks:50 });
    setQuestions([]);
  };

  const handlePublish = async () => {
    if (!form.title) { notify("Quiz title is required","error"); return; }
    const payload = { title:form.title, course:form.course_id||null, time_limit:form.time_limit, available_from:form.available_from||null, available_until:form.available_until||null, total_marks:form.total_marks };
    try {
      if (editingQuizId) {
        await API.put(`learning/quizzes/${editingQuizId}/`, payload);
        notify("Quiz updated successfully!");
        setEditingQuizId(null);
        setShowForm(false);
      } else {
        if (questions.length === 0) { notify("Add at least one question","error"); return; }
        const quizRes = await API.post("learning/quizzes/", payload);
        const quizId = quizRes.data.id;
        for (const q of questions) await API.post("learning/questions/", {...q, quiz:quizId});
        notify("Quiz published!");
        setQuestions([]);
        setShowForm(false);
      }
      setForm({ title:"", course_id:"", time_limit:30, available_from:"", available_until:"", total_marks:50 });
      fetchQuizzes();
    } catch(err) {
      console.log("Quiz error:", err.response?.data);
      notify("Failed: " + JSON.stringify(err.response?.data), "error");
    }
  };

  const deleteQuiz = async (id) => {
    if (!window.confirm("Delete this quiz and all its questions?")) return;
    try { await API.delete(`learning/quizzes/${id}/`); notify("Quiz deleted!"); fetchQuizzes(); }
    catch { notify("Delete failed","error"); }
  };

  const deleteQuestion = async (questionId) => {
    if (!window.confirm("Delete this question?")) return;
    try { await API.delete(`learning/questions/${questionId}/`); notify("Question deleted!"); fetchQuizzes(); }
    catch { notify("Delete failed","error"); }
  };

  const saveEditedQuestion = async () => {
    if (!questionForm) return;
    try {
      await API.put(`learning/questions/${questionForm.question.id}/`, { ...questionForm.question, quiz:questionForm.quizId });
      notify("Question updated!");
      setQuestionForm(null);
      fetchQuizzes();
    } catch { notify("Update failed","error"); }
  };

  const saveNewQuestion = async (quizId) => {
    if (!newQuestion.question_text) { notify("Question text required","error"); return; }
    try {
      await API.post("learning/questions/", { ...newQuestion, quiz:quizId });
      notify("Question added!");
      setAddingQuestionToQuiz(null);
      setNewQuestion({ question_text:"", question_type:"mcq", option_a:"", option_b:"", option_c:"", option_d:"", correct_answer:"", marks:5 });
      fetchQuizzes();
    } catch { notify("Failed to add question","error"); }
  };

  return (
    <div>
      {toast && (
        <div style={{ position:"fixed", top:24, right:24, zIndex:999, padding:"12px 20px", borderRadius:12,
          background:toast.type==="error"?"#fff1f2":"#f0fdf4",
          border:`1px solid ${toast.type==="error"?"#fecdd3":"#bbf7d0"}`,
          color:toast.type==="error"?"#e11d48":"#16a34a", fontSize:13.5, fontWeight:600 }}>
          {toast.msg}
        </div>
      )}

      <div style={S.pageHeader}>
        <h1 style={S.pageTitle}>{editingQuizId ? "✏️ Edit Quiz" : "Create Quiz"}</h1>
        {editingQuizId && (
          <p style={{...S.pageSub, color:"#f97316", fontWeight:600}}>
            Editing quiz — update the details below and click "Update Quiz"
          </p>
        )}
      </div>

      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:16 }}>
        <button style={S.btnPrimary} onClick={() => {
          if (showForm && !editingQuizId) { setShowForm(false); }
          else if (!showForm) { setShowForm(true); }
        }}>
          {showForm && !editingQuizId ? "✕ Cancel" : "+ Create Quiz"}
        </button>
      </div>

      {showForm && (
        <>
          <div style={{...S.card, ...(editingQuizId ? {border:"2px solid #f97316"} : {})}}>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:18}}>
              <div style={S.cardTitle}>Quiz Details</div>
              {editingQuizId && (
                <button onClick={handleCancelEdit}
                  style={{padding:"6px 14px", background:"#fff7ed", color:"#f97316", border:"1px solid #fed7aa", borderRadius:8, fontSize:12, cursor:"pointer", fontWeight:600}}>
                  ✕ Cancel Edit
                </button>
              )}
            </div>
            <div style={S.formRow}>
              <div style={S.formGroup}><label style={S.label}>Quiz Title</label>
                <input style={S.input} placeholder="e.g. Unit 1 -- ML Basics Quiz" value={form.title} onChange={e=>setForm({...form,title:e.target.value})} />
              </div>
              <div style={S.formGroup}><label style={S.label}>Course / Subject</label>
                <select style={S.select} value={form.course_id} onChange={e=>setForm({...form,course_id:e.target.value})}>
                  <option value="">-- Select Course --</option>
                  {courses.map(c=>(<option key={c.id} value={c.id}>{c.title}</option>))}
                </select>
              </div>
              <div style={S.formGroup}><label style={S.label}>Time Limit (minutes)</label>
                <input type="number" style={S.input} value={form.time_limit} onChange={e=>setForm({...form,time_limit:e.target.value})} />
              </div>
            </div>
            <div style={S.formRow}>
              <div style={S.formGroup}><label style={S.label}>Available From</label>
                <input type="date" style={S.input} value={form.available_from} onChange={e=>setForm({...form,available_from:e.target.value})} />
              </div>
              <div style={S.formGroup}><label style={S.label}>Available Until</label>
                <input type="date" style={S.input} value={form.available_until} onChange={e=>setForm({...form,available_until:e.target.value})} />
              </div>
              <div style={S.formGroup}><label style={S.label}>Total Marks</label>
                <input type="number" style={S.input} value={form.total_marks} onChange={e=>setForm({...form,total_marks:e.target.value})} />
              </div>
            </div>
          </div>

          {/* New-quiz questions — hidden in edit mode */}
          {!editingQuizId && (
            <div style={S.card}>
              <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16}}>
                <div style={S.cardTitle}>Questions</div>
                <button style={S.btnPrimary} onClick={addQuestion}>+ Add Question</button>
              </div>
              {questions.length === 0 ? (
                <div style={{padding:20, textAlign:"center", color:"#7a8499", fontSize:13}}>
                  No questions added yet. Click "+ Add Question" to start.
                </div>
              ) : questions.map((q,i) => (
                <div key={i} style={{border:"1px solid #e2e8f0", borderRadius:10, padding:16, marginBottom:14}}>
                  <div style={{display:"flex", justifyContent:"space-between", marginBottom:10}}>
                    <div style={{display:"flex", gap:8, alignItems:"center"}}>
                      <span style={{fontWeight:700, color:"#3d6ff5"}}>Q{i+1}</span>
                      <select style={{...S.select, width:"auto", padding:"4px 8px"}}
                        value={q.question_type} onChange={e=>updateQuestion(i,"question_type",e.target.value)}>
                        <option value="mcq">MCQ</option>
                        <option value="truefalse">True/False</option>
                      </select>
                      <input type="number" style={{...S.input, width:80}} placeholder="Marks"
                        value={q.marks} onChange={e=>updateQuestion(i,"marks",e.target.value)} />
                    </div>
                    <button onClick={()=>removeQuestion(i)}
                      style={{background:"#fee2e2", border:"none", color:"#dc2626", padding:"4px 10px", borderRadius:6, cursor:"pointer"}}>
                      ✕ Remove
                    </button>
                  </div>
                  <input style={{...S.input, marginBottom:10}} placeholder="Enter question text..."
                    value={q.question_text} onChange={e=>updateQuestion(i,"question_text",e.target.value)} />
                  {q.question_type === "mcq" ? (
                    <>
                      {["a","b","c","d"].map(opt=>(
                        <div key={opt} style={{display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
                          <input type="radio" name={`correct_${i}`}
                            checked={q.correct_answer===q[`option_${opt}`] && q[`option_${opt}`]!==""}
                            onChange={()=>updateQuestion(i,"correct_answer",q[`option_${opt}`])} />
                          <input style={S.input} placeholder={`Option ${opt.toUpperCase()}`} value={q[`option_${opt}`]}
                            onChange={e=>{
                              updateQuestion(i,`option_${opt}`,e.target.value);
                              if(q.correct_answer===q[`option_${opt}`] || q.correct_answer===`option_${opt}`){
                                updateQuestion(i,"correct_answer",e.target.value);
                              }
                            }} />
                        </div>
                      ))}
                      <div style={{fontSize:12, color:"#1a1f2e", marginTop:4, fontWeight:600}}>🔘 Type options first, then select the correct answer</div>
                    </>
                  ) : (
                    <div style={{display:"flex", gap:16}}>
                      {["True","False"].map(opt=>(
                        <label key={opt} style={{display:"flex", alignItems:"center", gap:6, cursor:"pointer"}}>
                          <input type="radio" name={`tf_${i}`} checked={q.correct_answer===opt} onChange={()=>updateQuestion(i,"correct_answer",opt)} />
                          <span style={{color:"#d4dae8"}}>{opt}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <button style={S.btnPrimary} onClick={handlePublish}>Publish Quiz</button>
            </div>
          )}

          {/* Update button in edit mode */}
          {editingQuizId && (
            <div style={{display:"flex", gap:10, marginBottom:20}}>
              <button style={{...S.btnPrimary, background:"#f97316"}} onClick={handlePublish}>💾 Update Quiz</button>
              <button onClick={handleCancelEdit} style={{...S.btnPrimary, background:"#94a3b8"}}>Cancel</button>
            </div>
          )}
        </>
      )}

      {/* Published Quizzes */}
      {quizzes.length > 0 && (
        <div style={S.card}>
          <div style={S.cardTitle}>Published Quizzes</div>
          <div style={S.tableWrap}>
            <table style={{width:"100%", borderCollapse:"collapse", fontSize:13, tableLayout:"fixed"}}>
              <thead>
                <tr>
                  <th style={{...S.th, width:"18%"}}>Title</th>
                  <th style={{...S.th, width:"14%"}}>Course</th>
                  <th style={{...S.th, width:"12%"}}>Time Limit</th>
                  <th style={{...S.th, width:"12%"}}>Total Marks</th>
                  <th style={{...S.th, width:"16%"}}>Available Until</th>
                  <th style={{...S.th, width:"28%"}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {quizzes.map(q => (
                  <React.Fragment key={q.id}>
                    <tr style={{background: editingQuizId===q.id ? "#fff7ed" : "transparent"}}>
                      <td style={{...S.td, color:"#1a1f2e", fontWeight:600}}>{q.title}</td>
                      <td style={{...S.td, color:"#1a1f2e"}}>{q.course_title || "---"}</td>
                      <td style={{...S.td, color:"#1a1f2e"}}>{q.time_limit} min</td>
                      <td style={{...S.td, color:"#1a1f2e"}}>{q.total_marks}</td>
                      <td style={{...S.td, color:"#1a1f2e"}}>{q.available_until || "---"}</td>
                      <td style={S.td}>
                        <div style={{display:"flex", gap:6, flexWrap:"wrap"}}>
                          <button onClick={()=>handleEdit(q)}
                            style={{padding:"4px 10px", background:"#fff7ed", color:"#f97316", border:"1px solid #fed7aa", borderRadius:6, fontSize:12, cursor:"pointer", fontWeight:600}}>
                            ✏️ Edit
                          </button>
                          <button onClick={()=>setExpandedQuiz(expandedQuiz===q.id ? null : q.id)}
                            style={{padding:"4px 10px", background:"#eff6ff", color:"#3b82f6", border:"1px solid #bfdbfe", borderRadius:6, fontSize:12, cursor:"pointer"}}>
                            {expandedQuiz===q.id ? "▲ Hide" : "▼ Questions"}
                          </button>
                          <button onClick={()=>deleteQuiz(q.id)}
                            style={{padding:"4px 10px", background:"#fee2e2", color:"#dc2626", border:"none", borderRadius:6, fontSize:12, cursor:"pointer"}}>
                            🗑 Delete
                          </button>
                        </div>
                      </td>
                    </tr>

                    {expandedQuiz === q.id && (
                      <tr>
                        <td colSpan={6} style={{padding:"0 16px 16px", background:"#f8fafc"}}>
                          {!q.questions || q.questions.length === 0 ? (
                            <div style={{color:"#7a8499", fontSize:13, padding:12}}>No questions added.</div>
                          ) : q.questions.map((ques, idx) => (
                            <div key={ques.id} style={{padding:"12px 0", borderBottom:"1px solid #e2e8f0"}}>

                              {questionForm && questionForm.question.id === ques.id ? (
                                <div style={{background:"#fff", border:"1px solid #f97316", borderRadius:10, padding:14}}>
                                  <div style={{fontWeight:600, color:"#f97316", marginBottom:10, fontSize:13}}>✏️ Editing Q{idx+1}</div>
                                  <input style={{...S.input, marginBottom:8}} placeholder="Question text"
                                    value={questionForm.question.question_text}
                                    onChange={e=>setQuestionForm({...questionForm, question:{...questionForm.question, question_text:e.target.value}})} />
                                  <div style={{display:"flex", gap:8, marginBottom:8}}>
                                    <select style={{...S.select, width:"auto"}}
                                      value={questionForm.question.question_type}
                                      onChange={e=>setQuestionForm({...questionForm, question:{...questionForm.question, question_type:e.target.value}})}>
                                      <option value="mcq">MCQ</option>
                                      <option value="truefalse">True/False</option>
                                    </select>
                                    <input type="number" style={{...S.input, width:80}} placeholder="Marks"
                                      value={questionForm.question.marks}
                                      onChange={e=>setQuestionForm({...questionForm, question:{...questionForm.question, marks:e.target.value}})} />
                                  </div>
                                  {questionForm.question.question_type === "mcq" ? (
                                    ["a","b","c","d"].map(opt=>(
                                      <div key={opt} style={{display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
                                        <input type="radio" name={`edit_correct_${ques.id}`}
                                          checked={questionForm.question.correct_answer===questionForm.question[`option_${opt}`] && questionForm.question[`option_${opt}`]!==""}
                                          onChange={()=>setQuestionForm({...questionForm, question:{...questionForm.question, correct_answer:questionForm.question[`option_${opt}`]}})} />
                                        <input style={S.input} placeholder={`Option ${opt.toUpperCase()}`}
                                          value={questionForm.question[`option_${opt}`]||""}
                                          onChange={e=>{
                                            const updated={...questionForm.question, [`option_${opt}`]:e.target.value};
                                            if(questionForm.question.correct_answer===questionForm.question[`option_${opt}`]){
                                              updated.correct_answer=e.target.value;
                                            }
                                            setQuestionForm({...questionForm, question:updated});
                                          }} />
                                      </div>
                                    ))
                                  ) : (
                                    <div style={{display:"flex", gap:16, marginBottom:8}}>
                                      {["True","False"].map(opt=>(
                                        <label key={opt} style={{display:"flex", alignItems:"center", gap:6, cursor:"pointer"}}>
                                          <input type="radio" name={`edit_tf_${ques.id}`}
                                            checked={questionForm.question.correct_answer===opt}
                                            onChange={()=>setQuestionForm({...questionForm, question:{...questionForm.question, correct_answer:opt}})} />
                                          <span style={{color:"#d4dae8"}}>{opt}</span>
                                        </label>
                                      ))}
                                    </div>
                                  )}
                                  <div style={{display:"flex", gap:8, marginTop:10}}>
                                    <button onClick={saveEditedQuestion}
                                      style={{padding:"6px 14px", background:"#f97316", color:"#fff", border:"none", borderRadius:6, fontSize:12, cursor:"pointer", fontWeight:600}}>
                                      💾 Save Question
                                    </button>
                                    <button onClick={()=>setQuestionForm(null)}
                                      style={{padding:"6px 14px", background:"#f1f5f9", color:"#64748b", border:"none", borderRadius:6, fontSize:12, cursor:"pointer"}}>
                                      Cancel
                                    </button>
                                  </div>
                                </div>

                              ) : (
                                <>
                                  <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start"}}>
                                    <div style={{fontWeight:600, color:"#1a1f2e", marginBottom:8, fontSize:13, flex:1}}>
                                      Q{idx+1}. {ques.question_text}
                                      <span style={{marginLeft:8, fontSize:11, color:"#3b82f6", background:"#eff6ff", padding:"2px 8px", borderRadius:10}}>
                                        {ques.question_type==="mcq" ? "MCQ" : "True/False"} | {ques.marks} marks
                                      </span>
                                    </div>
                                    <div style={{display:"flex", gap:6, marginLeft:12, flexShrink:0}}>
                                      <button onClick={()=>setQuestionForm({quizId:q.id, question:{...ques}})}
                                        style={{padding:"3px 10px", background:"#fff7ed", color:"#f97316", border:"1px solid #fed7aa", borderRadius:6, fontSize:11, cursor:"pointer", fontWeight:600}}>
                                        ✏️ Edit
                                      </button>
                                      <button onClick={()=>deleteQuestion(ques.id)}
                                        style={{padding:"3px 10px", background:"#fee2e2", color:"#dc2626", border:"none", borderRadius:6, fontSize:11, cursor:"pointer"}}>
                                        🗑
                                      </button>
                                    </div>
                                  </div>
                                  {ques.question_type === "mcq" ? (
                                    <div style={{display:"flex", flexDirection:"column", gap:4, paddingLeft:12}}>
                                      {["a","b","c","d"].map(opt=>(
                                        ques[`option_${opt}`] && (
                                          <div key={opt} style={{
                                            color: ques.correct_answer===ques[`option_${opt}`] ? "#16a34a" : "#475569",
                                            fontWeight: ques.correct_answer===ques[`option_${opt}`] ? 700 : 400,
                                            fontSize:13, padding:"2px 0"
                                          }}>
                                            {opt.toUpperCase()}. {ques[`option_${opt}`]}
                                            {ques.correct_answer===ques[`option_${opt}`] && " ✅"}
                                          </div>
                                        )
                                      ))}
                                    </div>
                                  ) : (
                                    <div style={{paddingLeft:12, fontSize:13}}>
                                      <span style={{color:ques.correct_answer==="True"?"#16a34a":"#475569", fontWeight:ques.correct_answer==="True"?700:400}}>
                                        True {ques.correct_answer==="True" && "✅"}
                                      </span>
                                      {" / "}
                                      <span style={{color:ques.correct_answer==="False"?"#16a34a":"#475569", fontWeight:ques.correct_answer==="False"?700:400}}>
                                        False {ques.correct_answer==="False" && "✅"}
                                      </span>
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                          ))}

                          {addingQuestionToQuiz === q.id ? (
                            <div style={{background:"#fff", border:"1px solid #3d6ff5", borderRadius:10, padding:14, marginTop:12}}>
                              <div style={{fontWeight:600, color:"#3d6ff5", marginBottom:10, fontSize:13}}>➕ New Question</div>
                              <input style={{...S.input, marginBottom:8}} placeholder="Question text"
                                value={newQuestion.question_text}
                                onChange={e=>setNewQuestion({...newQuestion, question_text:e.target.value})} />
                              <div style={{display:"flex", gap:8, marginBottom:8}}>
                                <select style={{...S.select, width:"auto"}}
                                  value={newQuestion.question_type}
                                  onChange={e=>setNewQuestion({...newQuestion, question_type:e.target.value})}>
                                  <option value="mcq">MCQ</option>
                                  <option value="truefalse">True/False</option>
                                </select>
                                <input type="number" style={{...S.input, width:80}} placeholder="Marks"
                                  value={newQuestion.marks}
                                  onChange={e=>setNewQuestion({...newQuestion, marks:e.target.value})} />
                              </div>
                              {newQuestion.question_type === "mcq" ? (
                                ["a","b","c","d"].map(opt=>(
                                  <div key={opt} style={{display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
                                    <input type="radio" name="new_correct"
                                      checked={newQuestion.correct_answer===newQuestion[`option_${opt}`] && newQuestion[`option_${opt}`]!==""}
                                      onChange={()=>setNewQuestion({...newQuestion, correct_answer:newQuestion[`option_${opt}`]})} />
                                    <input style={S.input} placeholder={`Option ${opt.toUpperCase()}`}
                                      value={newQuestion[`option_${opt}`]}
                                      onChange={e=>{
                                        const updated={...newQuestion, [`option_${opt}`]:e.target.value};
                                        if(newQuestion.correct_answer===newQuestion[`option_${opt}`]){
                                          updated.correct_answer=e.target.value;
                                        }
                                        setNewQuestion(updated);
                                      }} />
                                  </div>
                                ))
                              ) : (
                                <div style={{display:"flex", gap:16, marginBottom:8}}>
                                  {["True","False"].map(opt=>(
                                    <label key={opt} style={{display:"flex", alignItems:"center", gap:6, cursor:"pointer"}}>
                                      <input type="radio" name="new_tf"
                                        checked={newQuestion.correct_answer===opt}
                                        onChange={()=>setNewQuestion({...newQuestion, correct_answer:opt})} />
                                      <span style={{color:"#1a1f2e"}}>{opt}</span>
                                    </label>
                                  ))}
                                </div>
                              )}
                              <div style={{display:"flex", gap:8, marginTop:10}}>
                                <button onClick={()=>saveNewQuestion(q.id)}
                                  style={{padding:"6px 14px", background:"#3d6ff5", color:"#fff", border:"none", borderRadius:6, fontSize:12, cursor:"pointer", fontWeight:600}}>
                                  ➕ Add Question
                                </button>
                                <button onClick={()=>{ setAddingQuestionToQuiz(null); setNewQuestion({question_text:"",question_type:"mcq",option_a:"",option_b:"",option_c:"",option_d:"",correct_answer:"",marks:5}); }}
                                  style={{padding:"6px 14px", background:"#f1f5f9", color:"#64748b", border:"none", borderRadius:6, fontSize:12, cursor:"pointer"}}>
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <button onClick={()=>setAddingQuestionToQuiz(q.id)}
                              style={{marginTop:12, padding:"6px 14px", background:"#eff6ff", color:"#3d6ff5", border:"1px solid #bfdbfe", borderRadius:6, fontSize:12, cursor:"pointer", fontWeight:600}}>
                              ➕ Add Question to this Quiz
                            </button>
                          )}

                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ==============================MARk PAGE =====================================

function MarksPage({ courses, students }) {
  const [showForm, setShowForm] = useState(false);
  const [selectedCourse, setSelectedCourse] = useState("");
  const [selectedStudent, setSelectedStudent] = useState("");
  const [assessmentType, setAssessmentType] = useState("Assignment");
  const [marksObtained, setMarksObtained] = useState("");
  const [maxMarks, setMaxMarks] = useState("");
  const [marksList, setMarksList] = useState([]);
  const [toast, setToast] = useState(null);
  const [editingMarkId, setEditingMarkId] = useState(null);
  const [editMarksObtained, setEditMarksObtained] = useState("");
  const [editMaxMarks, setEditMaxMarks] = useState("");

  const notify = (msg, type="success") => { setToast({msg,type}); setTimeout(()=>setToast(null),3000); };

  const fetchMarks = async () => {
    try {
      const res = await API.get("learning/marks/");
      setMarksList(res.data);
    } catch { console.log("Failed to fetch marks"); }
  };

  useEffect(() => { fetchMarks(); }, []);

  const handleSave = async () => {
    if (!selectedCourse || !selectedStudent || !marksObtained || !maxMarks) {
      notify("Please fill all fields", "error"); return;
    }
    try {
      await API.post("learning/marks/", {
        student: Number(selectedStudent),
        course: Number(selectedCourse),
        assessment_type: assessmentType,
        marks_obtained: Number(marksObtained),
        max_marks: Number(maxMarks),
      });
      notify("Marks saved!");
      setMarksObtained("");
      setMaxMarks("");
      setShowForm(false);
      fetchMarks();
    } catch (err) {
      notify("Failed to save marks", "error");
      console.log(err.response?.data);
    }
  };

  const handleDeleteMark = async (id) => {
    if (!window.confirm("Delete this mark?")) return;
    try {
      await API.delete(`learning/marks/${id}/`);
      notify("Deleted successfully!");
      fetchMarks();
    } catch { notify("Delete failed", "error"); }
  };

  const handleEditSave = async (id) => {
    try {
      await API.patch(`learning/marks/${id}/`, {
        marks_obtained: Number(editMarksObtained),
        max_marks: Number(editMaxMarks),
      });
      notify("Marks updated!");
      setEditingMarkId(null);
      fetchMarks();
    } catch { notify("Update failed", "error"); }
  };

  const filteredMarks = selectedCourse
    ? marksList.filter(m => String(m.course) === String(selectedCourse))
    : marksList;

  return (
    <div>
      {toast && (
        <div style={{ position:"fixed", top:24, right:24, zIndex:999, padding:"12px 20px", borderRadius:12,
          background:toast.type==="error"?"#fff1f2":"#f0fdf4",
          border:`1px solid ${toast.type==="error"?"#fecdd3":"#bbf7d0"}`,
          color:toast.type==="error"?"#e11d48":"#16a34a", fontSize:13.5, fontWeight:600 }}>
          {toast.msg}
        </div>
      )}
      <div style={S.pageHeader}><h1 style={S.pageTitle}>Assign Marks</h1></div>
      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:16 }}>
        <button style={S.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? "✕ Cancel" : "+ Add Marks"}
        </button>
      </div>
      {showForm && (
        <div style={S.card}>
          <div style={S.cardTitle}>Enter Marks</div>
          <div style={S.formRow}>
            <div style={S.formGroup}><label style={S.label}>Select Course</label>
              <select style={S.select} value={selectedCourse} onChange={e=>setSelectedCourse(e.target.value)}>
                <option value="">-- Select Course --</option>
                {courses.map(c=>(<option key={c.id} value={c.id}>{c.title}</option>))}
              </select>
            </div>
            <div style={S.formGroup}><label style={S.label}>Select Student</label>
              <select style={S.select} value={selectedStudent} onChange={e=>setSelectedStudent(e.target.value)}>
                <option value="">-- Select Student --</option>
                {students.map(s=>(<option key={s.id} value={s.id}>{s.username} ({s.roll_number||"N/A"})</option>))}
              </select>
            </div>
            <div style={S.formGroup}><label style={S.label}>Assessment Type</label>
              <select style={S.select} value={assessmentType} onChange={e=>setAssessmentType(e.target.value)}>
                <option>Assignment</option>
                <option>Internal Assessment</option>
              </select>
            </div>
          </div>
          <div style={S.formRow}>
            <div style={S.formGroup}><label style={S.label}>Marks Obtained</label>
              <input type="number" style={S.input} placeholder="e.g. 85" value={marksObtained} onChange={e=>setMarksObtained(e.target.value)} />
            </div>
            <div style={S.formGroup}><label style={S.label}>Maximum Marks</label>
              <input type="number" style={S.input} placeholder="e.g. 100" value={maxMarks} onChange={e=>setMaxMarks(e.target.value)} />
            </div>
          </div>
          <button style={S.btnPrimary} onClick={handleSave}>Save Marks</button>
        </div>
      )}

      {/* Performance Summary */}
      <div style={S.card}>
        <div style={S.cardTitle}>Performance Summary</div>
        {filteredMarks.length === 0 ? (
          <div style={{padding:20, textAlign:"center", color:"#7a8499", fontSize:13}}>No marks saved yet</div>
        ) : (
          <div style={S.tableWrap}>
            <table style={{width:"100%", borderCollapse:"collapse", fontSize:13, tableLayout:"fixed", minWidth:800}}>
              <thead><tr>
                <th style={{...S.th, width:"15%"}}>Student</th>
                <th style={{...S.th, width:"15%"}}>Course</th>
                <th style={{...S.th, width:"18%"}}>Assessment</th>
                <th style={{...S.th, width:"10%"}}>Marks</th>
                <th style={{...S.th, width:"10%"}}>Out Of</th>
                <th style={{...S.th, width:"12%"}}>Percentage</th>
                <th style={{...S.th, width:"20%"}}>Actions</th>
              </tr></thead>
              <tbody>
                {filteredMarks.map(m => (
                  <tr key={m.id}>
                    <td style={S.td}>{m.student_name}</td>
                    <td style={S.td}>{m.course_title}</td>
                    <td style={S.td}>{m.assessment_type}</td>

                    <td style={S.td}>
                      {editingMarkId === m.id ? (
                        <input type="number" style={{...S.input, width:70}}
                          value={editMarksObtained}
                          onChange={e => setEditMarksObtained(e.target.value)} />
                      ) : m.marks_obtained}
                    </td>

                    <td style={S.td}>
                      {editingMarkId === m.id ? (
                        <input type="number" style={{...S.input, width:70}}
                          value={editMaxMarks}
                          onChange={e => setEditMaxMarks(e.target.value)} />
                      ) : m.max_marks}
                    </td>

                    <td style={S.td}>
                      <span style={{
                        ...S.badge,
                        background: (m.marks_obtained/m.max_marks)*100 >= 50 ? "#dcfce7" : "#fee2e2",
                        color: (m.marks_obtained/m.max_marks)*100 >= 50 ? "#166534" : "#991b1b"
                      }}>
                        {((m.marks_obtained/m.max_marks)*100).toFixed(1)}%
                      </span>
                    </td>

                    <td style={S.td}>
                      {editingMarkId === m.id ? (
                        <div style={{display:"flex", gap:6}}>
                          <button onClick={() => handleEditSave(m.id)}
                            style={{padding:"5px 12px", fontSize:12, background:"#22b14c", color:"#fff", border:"none", borderRadius:6, cursor:"pointer", fontWeight:600}}>
                            💾 Save
                          </button>
                          <button onClick={() => setEditingMarkId(null)}
                            style={{padding:"5px 12px", fontSize:12, background:"#f1f5f9", color:"#64748b", border:"none", borderRadius:6, cursor:"pointer"}}>
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div style={{display:"flex", gap:6}}>
                          <button onClick={() => {
                            setEditingMarkId(m.id);
                            setEditMarksObtained(m.marks_obtained);
                            setEditMaxMarks(m.max_marks);
                          }}
                            style={{padding:"5px 12px", fontSize:12, background:"#fff7ed", color:"#f97316", border:"1px solid #fed7aa", borderRadius:6, cursor:"pointer", fontWeight:600}}>
                            ✏️ Edit
                          </button>
                          <button onClick={() => handleDeleteMark(m.id)}
                            style={{padding:"5px 12px", fontSize:12, background:"#ef4444", color:"#fff", border:"none", borderRadius:6, cursor:"pointer"}}>
                            🗑 Delete
                          </button>
                        </div>
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
  );
}

//================================Submissions — helper: build marksheet Excel blob====================================

async function buildMarksheetBlob(assignmentTitle, courseName, subs, teacherName) {
  const workbook = new ExcelJS.Workbook();
  const ws = workbook.addWorksheet("Marks Register");

  const today = new Date();
  const dateStr = today.toLocaleDateString("en-GB").replace(/\//g, "-");

  // ── Column widths ──
  ws.columns = [
    { width: 10 },
    { width: 20 },
    { width: 10 },
    { width: 12 },
    { width: 16 },
    { width: 10 },
    { width: 14 },
    { width: 14 },
    { width: 10 },
  ];

  // ── Row 1: Title (merged A1:I1) ──
  ws.addRow(["ASSIGNMENT MARKS REGISTER"]);
  ws.mergeCells("A1:I1");
  ws.getCell("A1").font = { bold: true, size: 14 };
  ws.getCell("A1").alignment = { horizontal: "center" };

  // ── Row 2: blank ──
  ws.addRow([]);

  // ── Row 3: Teacher / Subject / Academic Year ──
  ws.addRow([
    `Teacher: ${teacherName}`, "", `Subject: ${courseName}`, "",
    `Academic Year: ${today.getFullYear()} – ${today.getFullYear() + 1}`,
  ]);

  // ── Row 4: blank ──
  ws.addRow([]);

  // ── Row 5: Assignment details ──
  ws.addRow([
    `Assignment: ${assignmentTitle}`, "",
    `Max Mark: ${subs[0]?.max_marks ?? 100}`,
    `Pass Mark: ${Math.round((subs[0]?.max_marks ?? 100) * 0.4)}`,
    `Due Date: ${dateStr}`,
  ]);

  // ── Row 6: blank ──
  ws.addRow([]);

  // ── Row 7: Header row ──
  const headerRow = ws.addRow([
    "Roll No", "Student Name", "Class", "Submitted?",
    "Submission Date", "On Time?", "Marks Obtained", "Percentage (%)", "Status",
  ]);
  headerRow.eachCell(cell => {
    cell.font = { bold: true };
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFD9E1F2" } };
    cell.alignment = { horizontal: "center" };
  });

  // ── Data rows ──
  let passCount = 0, failCount = 0, highestMark = 0, totalMarks = 0, gradedCount = 0;

  subs.forEach((sub, idx) => {
    const submitted = sub.file || sub.text_entry || sub.url_entry ? "Yes" : "No";
    const subDate = sub.submitted_at
      ? new Date(sub.submitted_at).toLocaleDateString("en-GB")
      : "—";

    let onTime = "—";
    if (sub.submitted_at && sub.due_date) {
      onTime = new Date(sub.submitted_at) <= new Date(sub.due_date) ? "Yes" : "Late";
    }

    const marks = sub.marks !== null && sub.marks !== undefined ? sub.marks : null;
    const maxM = sub.max_marks ?? 100;
    const pct = marks !== null ? ((marks / maxM) * 100).toFixed(1) + "%" : "—";
    const passThreshold = maxM * 0.4;
    const status =
      submitted === "No" ? "Fail"
      : marks === null ? "—"
      : marks >= passThreshold ? "Pass"
      : "Fail";

    if (marks !== null) {
      if (marks >= passThreshold) passCount++;
      else failCount++;
      if (marks > highestMark) highestMark = marks;
      totalMarks += marks;
      gradedCount++;
    } else if (submitted === "No") {
      failCount++;
    }

    ws.addRow([
      sub.student_roll || String(idx + 1).padStart(3, "0"),
      sub.student_name,
      sub.student_class || "10 – A",
      submitted,
      subDate,
      onTime,
      marks !== null ? marks : "—",
      pct,
      status,
    ]);
  });

  // ── Summary row ──
  const totalStudents = subs.length;
  const submittedCount = subs.filter(s => s.file || s.text_entry || s.url_entry).length;
  const classAvg =
    gradedCount > 0
      ? ((totalMarks / gradedCount / (subs[0]?.max_marks ?? 100)) * 100).toFixed(1) + "%"
      : "—";

  ws.addRow([]);
  ws.addRow([
    `Total Students: ${totalStudents}`,
    `Submitted: ${submittedCount}`,
    `Not Submitted: ${totalStudents - submittedCount}`,
    `Passed: ${passCount}`,
    `Failed: ${failCount}`,
    "",
    `Highest Mark: ${highestMark}`,
    `Class Average: ${classAvg}`,
  ]);

  // ── Signature rows ──
  ws.addRow([]);
  ws.addRow([teacherName, "", dateStr, "", "", "", "", "Head of Department Signature"]);
  ws.addRow(["Teacher Signature", "", "Date", "", "", "", "", ""]);

  // ── Generate blob ──
  const buffer = await workbook.xlsx.writeBuffer();
  return new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function SubmissionsPage({ courses }) {
  const [submissions, setSubmissions] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [filterCourse, setFilterCourse] = React.useState("all");
  const [filterStatus, setFilterStatus] = React.useState("all");
  const [marks, setMarks] = React.useState({});
  const [feedbackSub, setFeedbackSub] = React.useState(null);
  const [feedbackText, setFeedbackText] = React.useState("");
  const [toast, setToast] = React.useState(null);
  const [editingId, setEditingId] = React.useState(null);

  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const notify = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  React.useEffect(() => {
    setLoading(true);
    API.get(`learning/submissions/?teacher_id=${user.id}`)
      .then((r) => {
        setSubmissions(r.data);
        const m = {};
        r.data.forEach((s) => { m[s.id] = s.marks ?? ""; });
        setMarks(m);
      })
      .catch(() => notify("Failed to load submissions", "error"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = submissions.filter((s) => {
    const courseMatch =
      filterCourse === "all" ||
      courses.find(
        (c) => String(c.id) === filterCourse && s.course_title === c.title
      );
    const statusMatch = filterStatus === "all" || s.status === filterStatus;
    return courseMatch && statusMatch;
  });

  const saveGrade = async (sub) => {
    try {
      await API.patch(`learning/submissions/${sub.id}/`, {
        marks: marks[sub.id] !== "" ? parseFloat(marks[sub.id]) : null,
        feedback: feedbackSub?.id === sub.id ? feedbackText : sub.feedback,
        status: "evaluated",
      });
      notify("Grade saved!");
      const r = await API.get(`learning/submissions/?teacher_id=${user.id}`);
      setSubmissions(r.data);
    } catch {
      notify("Failed to save grade", "error");
    }
  };

  const openFeedback = (sub) => {
    setFeedbackSub(sub);
    setFeedbackText(sub.feedback || "");
  };

  const downloadMarksheetZip = async () => {
    if (filtered.length === 0) {
      notify("No submissions to export.", "error");
      return;
    }
    notify("Preparing styled marksheet, please wait...");
    try {
      const user = JSON.parse(localStorage.getItem("user") || "{}");
      const response = await fetch(
        `http://127.0.0.1:8000/api/download-marksheet/?teacher_id=${user.id}`,
        {
          headers: { Authorization: `Token ${user.token}` },
        }
      );
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "marksheets.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      notify("Styled marksheet downloaded!");
    } catch {
      notify("Download failed. Check backend.", "error");
    }

    const zip = new JSZip();

    const byAssignment = {};
    filtered.forEach((sub) => {
      const key = sub.assignment_title || `Assignment_${sub.assignment}`;
      if (!byAssignment[key]) byAssignment[key] = [];
      byAssignment[key].push(sub);
    });

    // ✅ buildMarksheetBlob is now async (ExcelJS), so we await each call
    for (const [assignmentTitle, subs] of Object.entries(byAssignment)) {
      const courseName = subs[0]?.course_title || "Course";
      const blob = await buildMarksheetBlob(
        assignmentTitle,
        courseName,
        subs,
        user.username || "Teacher"
      );
      const safeName = assignmentTitle.replace(/\s+/g, "_");
      zip.file(`${safeName}_marksheet.xlsx`, blob);
    }

    const content = await zip.generateAsync({ type: "blob" });
    saveAs(content, "marksheets.zip");
    notify("Marksheet ZIP downloaded successfully!");
  };

  const statusStyle = {
    pending:   { background: "#fef3c7", color: "#b45309", border: "1px solid #fcd34d" },
    evaluated: { background: "#d1fae5", color: "#065f46", border: "1px solid #6ee7b7" },
    late:      { background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" },
  };

  return (
    <div style={{ fontFamily: "'Segoe UI', sans-serif" }}>

      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 9999,
          background: toast.type === "error" ? "#fee2e2" : "#dcfce7",
          color: toast.type === "error" ? "#b91c1c" : "#166534",
          padding: "10px 20px", borderRadius: 8, fontWeight: 600, fontSize: 13,
          boxShadow: "0 2px 12px rgba(0,0,0,0.15)"
        }}>{toast.msg}</div>
      )}

      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 26, fontWeight: 800, color: "#0f172a", margin: 0 }}>LMS Teacher</h2>
        <p style={{ color: "#64748b", fontSize: 14, margin: "4px 0 0" }}>Evaluate Submissions</p>
      </div>

      <div style={{ background: "#fff", borderRadius: 14, boxShadow: "0 1px 6px rgba(0,0,0,0.09)", padding: 28, width: "100%", boxSizing: "border-box" }}>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 22, flexWrap: "wrap", gap: 12 }}>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "#1e293b" }}>Assignment Submissions</h3>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <select
              value={filterCourse}
              onChange={(e) => setFilterCourse(e.target.value)}
              style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #1e293b", fontSize: 13, fontWeight: 600, background: "#1e293b", color: "#fff", cursor: "pointer" }}
            >
              <option value="all">All Courses</option>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>

            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #1e293b", fontSize: 13, fontWeight: 600, background: "#1e293b", color: "#fff", cursor: "pointer" }}
            >
              <option value="all">All Status</option>
              <option value="pending">Pending</option>
              <option value="evaluated">Evaluated</option>
              <option value="late">Late</option>
            </select>

            <button
              style={{
                padding: "8px 16px", borderRadius: 8, border: "1.5px solid #6366f1",
                fontSize: 13, fontWeight: 600, background: "#fff", color: "#6366f1",
                cursor: "pointer", display: "flex", alignItems: "center", gap: 6
              }}
              onClick={downloadMarksheetZip}
            >
              ⬇ Download All (ZIP)
            </button>
          </div>
        </div>

        {loading && (
          <p style={{ color: "#6366f1", fontWeight: 600, textAlign: "center", padding: 40 }}>
            Loading submissions…
          </p>
        )}

        {!loading && filtered.length === 0 && (
          <div style={{ textAlign: "center", padding: "50px 20px", color: "#94a3b8" }}>
            <div style={{ fontSize: 36, marginBottom: 10 }}>🗂️</div>
            <p style={{ fontSize: 15 }}>No submissions found</p>
          </div>
        )}

        {!loading && filtered.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%",  borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #f1f5f9" }}>
                  {[
                    { label: "Student",    width: 120 },
                    { label: "Assignment", width: 130 },
                    { label: "Course",     width: 100 },
                    { label: "Submitted",  width: 100 },
                    { label: "Status",     width: 90 },
                    { label: "Marks",      width: 70  },
                    { label: "Actions",    width: 140 },
                  ].map((h) => (
                    <th key={h.label} style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, color: "#64748b", fontSize: 13, width: h.width, minWidth: h.width }}>
                      {h.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((sub, i) => (
                  <tr key={sub.id} style={{ borderBottom: "1px solid #f1f5f9", background: i % 2 === 0 ? "#fff" : "#fafafa" }}>

                    <td style={{ padding: "14px 14px", fontWeight: 600, color: "#0f172a" }}>{sub.student_name}</td>
                    <td style={{ padding: "14px 14px", color: "#334155" }}>{sub.assignment_title}</td>
                    <td style={{ padding: "14px 14px", color: "#334155" }}>{sub.course_title}</td>
                    <td style={{ padding: "14px 14px", color: "#64748b", fontSize: 13 }}>
                      {new Date(sub.submitted_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    </td>

                    <td style={{ padding: "14px 14px" }}>
                      <span style={{ ...(statusStyle[sub.status] || statusStyle.pending), padding: "4px 12px", borderRadius: 20, fontSize: 12, fontWeight: 700 }}>
                        {sub.status === "evaluated" ? "Evaluated" : sub.status === "late" ? "Late" : "Pending"}
                      </span>
                    </td>

                    <td style={{ padding: "14px 14px" }}>
                      {sub.status === "evaluated" && editingId !== sub.id ? (
                        <span style={{ fontWeight: 700, color: "#0f172a" }}>{sub.marks} / {sub.max_marks}</span>
                      ) : (
                        <input
                          type="number"
                          value={marks[sub.id] ?? ""}
                          onChange={(e) => setMarks((prev) => ({ ...prev, [sub.id]: e.target.value }))}
                          placeholder="---"
                          style={{ width: 60, padding: "5px 8px", borderRadius: 7, border: "1.5px solid #cbd5e1", fontSize: 13, textAlign: "center", background: "#1e293b", color: "#fff" }}
                        />
                      )}
                    </td>

                    <td style={{ padding: "14px 14px" }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        {sub.file && (
                          <a href={sub.file} target="_blank" rel="noreferrer">
                            <button style={{ background: "#3b82f6", color: "#fff", border: "none", padding: "6px 12px", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>View File</button>
                          </a>
                        )}
                        {!sub.file && (
                          <button onClick={() => openFeedback(sub)} style={{ background: "#3b82f6", color: "#fff", border: "none", padding: "6px 12px", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>View</button>
                        )}
                        {sub.status === "evaluated" && editingId !== sub.id ? (
                          <button
                            onClick={() => { setEditingId(sub.id); setMarks((prev) => ({ ...prev, [sub.id]: sub.marks })); }}
                            style={{ background: "#fff", color: "#6366f1", border: "1.5px solid #6366f1", padding: "6px 12px", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                          >Edit</button>
                        ) : (
                          <div style={{ display: "flex", gap: 6 }}>
                            <button
                              onClick={() => { saveGrade(sub); setEditingId(null); }}
                              style={{ background: "#22c55e", color: "#fff", border: "none", padding: "6px 12px", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                            >Save</button>
                            {editingId === sub.id && (
                              <button
                                onClick={() => setEditingId(null)}
                                style={{ background: "#f1f5f9", color: "#64748b", border: "none", padding: "6px 12px", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                              >Cancel</button>
                            )}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {feedbackSub && (
          <div style={{ marginTop: 28, borderTop: "1px solid #e2e8f0", paddingTop: 24 }}>
            <h4 style={{ margin: "0 0 14px", fontSize: 15, fontWeight: 700, color: "#1e293b" }}>
              Feedback for: {feedbackSub.student_name} — {feedbackSub.assignment_title}
            </h4>
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="Write your feedback for this student's submission..."
              rows={5}
              style={{ width: "100%", padding: "12px 16px", borderRadius: 10, border: "1.5px solid #cbd5e1", fontSize: 14, resize: "vertical", boxSizing: "border-box", fontFamily: "'Segoe UI', sans-serif", color: "#1e293b" }}
            />
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button
                onClick={async () => { await saveGrade(feedbackSub); setFeedbackSub(null); }}
                style={{ background: "#6366f1", color: "#fff", border: "none", padding: "9px 20px", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600 }}
              >Save & Close</button>
              <button
                onClick={() => setFeedbackSub(null)}
                style={{ background: "#3b82f6", color: "#fff", border: "none", padding: "9px 20px", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600 }}
              >Cancel</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

//================================teacherhome page====================================

function TeacherHome() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [activePage, setActivePage] = useState("dashboard");
  const [stats, setStats] = useState({ total_courses:0, total_students:0, total_enrollments:0, total_assignments:0, courses:[] });
  const [students, setStudents] = useState([]);
  useEffect(() => {
    if (!user || user.role !== "teacher") { navigate("/"); return; }
    API.get(`teacher-dashboard/?teacher_id=${user.id}`).then(r=>setStats(r.data)).catch(()=>{});
    API.get(`teacher-students/?teacher_id=${user.id}`).then(r=>setStudents(r.data)).catch(()=>{});
  }, []);
  const courses = stats.courses || [];
  const renderPage = () => {
    switch(activePage) {
      case "dashboard":   return <DashboardPage stats={stats} />;
      case "my-courses":  return <MyCoursesPage courses={courses} />;
      case "assignments": return <AssignmentsPage courses={courses} />;
      case "submissions": return <SubmissionsPage courses={courses} />;
      case "lectures":    return <LecturesPage courses={courses} />;
      case "notes":       return <NotesPage courses={courses} />;
      case "live-class":  return <LiveClassPage courses={courses} />;
      case "quiz":        return <QuizPage courses={courses} />;
      case "marks":       return <MarksPage courses={courses} students={students} />;
      default:            return <DashboardPage stats={stats} />;
    }
  };
  return (
    <div style={{ display:"flex", minHeight:"100vh", background:"#e8edf5", fontFamily:"'Segoe UI', sans-serif" }}>
      <TeacherSidebar activePage={activePage} setActivePage={setActivePage} />
      {/* ✅ FIXED: changed overflow:"hidden" to overflow:"auto" so table columns don't get clipped */}
      <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"auto" }}>
        <TopBar />
        <div style={{ flex:1, overflowY:"auto", padding:28 }}>
          {renderPage()}
        </div>
      </div>
    </div>
  );
}

export default TeacherHome;
