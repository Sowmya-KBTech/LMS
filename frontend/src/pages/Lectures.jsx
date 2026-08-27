import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import API from "../api";

// =============================================================
//  Lectures Page — View, Upload & Manage Lectures
// =============================================================

export default function Lectures() {

  // ─────────────────────────────────────────────────────────
  //  HOOKS & AUTH
  // ─────────────────────────────────────────────────────────

  const navigate = useNavigate();
  const user     = JSON.parse(localStorage.getItem("user"));


  // ─────────────────────────────────────────────────────────
  //  STATE
  // ─────────────────────────────────────────────────────────

  const [lectures,    setLectures]    = useState([]);
  const [showForm,    setShowForm]    = useState(false);
  const [uploading,   setUploading]   = useState(false);
  const [activeTab,   setActiveTab]   = useState("all");
  const [activeVideo, setActiveVideo] = useState(null);

  const [form, setForm] = useState({
    title:        "",
    description:  "",
    lecture_type: "recorded",
    video_file:   null,
    meeting_link: "",
    scheduled_at: "",
  });


  // ─────────────────────────────────────────────────────────
  //  LIFECYCLE
  // ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!user) navigate("/");
  }, []);

  useEffect(() => {
    fetchLectures();
  }, []);


  // ─────────────────────────────────────────────────────────
  //  API CALLS
  // ─────────────────────────────────────────────────────────

  const fetchLectures = async () => {
    try {
      const res = await API.get("learning/lectures/");
      setLectures(res.data);
    } catch {
      console.log("Error loading lectures");
    }
  };

  const deleteLecture = async (id) => {
    if (!window.confirm("Delete this lecture?")) return;
    await API.delete(`learning/lectures/${id}/`);
    fetchLectures();
  };


  // ─────────────────────────────────────────────────────────
  //  FORM HANDLER
  // ─────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!form.title) return;

    setUploading(true);

    const formData = new FormData();
    formData.append("title",        form.title);
    formData.append("description",  form.description);
    formData.append("lecture_type", form.lecture_type);

    if (form.lecture_type === "recorded") {
      if (form.video_file)   formData.append("video_file",   form.video_file);
      if (form.meeting_link) formData.append("meeting_link", form.meeting_link);
    }

    if (form.lecture_type === "live") {
      formData.append("meeting_link", form.meeting_link);
      formData.append("scheduled_at", form.scheduled_at);
    }

    try {
      await API.post("learning/lectures/", formData);
      setShowForm(false);
      fetchLectures();
    } catch {
      console.log("Upload failed");
    } finally {
      setUploading(false);
    }
  };


  // ─────────────────────────────────────────────────────────
  //  DERIVED STATE & HELPERS
  // ─────────────────────────────────────────────────────────

  const canUpload = user?.role === "admin" || user?.role === "teacher";

  const filtered = lectures.filter((l) =>
    activeTab === "all" ? true : l.lecture_type === activeTab
  );

  const convertToEmbed = (url) => {
    const shortMatch = url.match(/youtu\.be\/([a-zA-Z0-9_-]+)/);
    if (shortMatch) return `https://www.youtube.com/embed/${shortMatch[1]}`;

    const fullMatch = url.match(/[?&]v=([a-zA-Z0-9_-]+)/);
    if (fullMatch) return `https://www.youtube.com/embed/${fullMatch[1]}`;

    const driveMatch = url.match(/\/d\/([a-zA-Z0-9_-]+)/);
    if (driveMatch) return `https://drive.google.com/file/d/${driveMatch[1]}/preview`;

    return url;
  };


  // ─────────────────────────────────────────────────────────
  //  RENDER
  // ─────────────────────────────────────────────────────────

  return (
    <>
      <Navbar />

      <div style={styles.page}>

        {/* ── Page Header ───────────────────────────────── */}
        <div style={styles.header}>
          <div>
            <h2>Lectures</h2>
            <p>{lectures.length} total lectures</p>
          </div>

          {canUpload && (
            <button
              style={styles.primaryBtn}
              onClick={() => setShowForm(!showForm)}
            >
              {showForm ? "Cancel" : "+ Add Lecture"}
            </button>
          )}
        </div>

        {/* ── Add Lecture Form ──────────────────────────── */}
        {showForm && (
          <div style={styles.formCard}>

            <input
              placeholder="Title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />

            <select
              value={form.lecture_type}
              onChange={(e) => setForm({ ...form, lecture_type: e.target.value })}
            >
              <option value="recorded">Recorded</option>
              <option value="live">Live</option>
            </select>

            {/* ── Recorded Fields ── */}
            {form.lecture_type === "recorded" && (
              <>
                <input
                  type="file"
                  onChange={(e) => setForm({ ...form, video_file: e.target.files[0] })}
                />
                <input
                  placeholder="Or paste YouTube / Google Drive link"
                  value={form.meeting_link}
                  onChange={(e) => setForm({ ...form, meeting_link: e.target.value })}
                />
              </>
            )}

            {/* ── Live Fields ── */}
            {form.lecture_type === "live" && (
              <>
                <input
                  placeholder="Meeting link"
                  value={form.meeting_link}
                  onChange={(e) => setForm({ ...form, meeting_link: e.target.value })}
                />
                <input
                  type="datetime-local"
                  onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
                />
              </>
            )}

            <button onClick={handleSubmit}>
              {uploading ? "Uploading..." : "Save"}
            </button>

          </div>
        )}

        {/* ── Tabs ──────────────────────────────────────── */}
        <div style={styles.tabs}>
          {["all", "recorded", "live"].map((tab) => (
            <button
              key={tab}
              style={activeTab === tab ? styles.activeTab : styles.tab}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* ── Lecture Grid / Empty State ────────────────── */}
        {filtered.length === 0 ? (
          <div style={styles.empty}>
            <div style={{ fontSize: 50 }}>📚</div>
            <h3>No lectures yet</h3>
            <p>Add lectures to see them here</p>
          </div>
        ) : (
          <div style={styles.grid}>
            {filtered.map((l) => (
              <div key={l.id} style={styles.card}>
                <h3>{l.title}</h3>

                {l.lecture_type === "recorded" && (l.video_file || l.meeting_link) && (
                  <button
                    style={styles.watchBtn}
                    onClick={() => window.open(`/watch/${l.id}`, "_blank")}
                  >
                    ▶ Watch
                  </button>
                )}

                {l.lecture_type === "live" && (
                  <a href={l.meeting_link} target="_blank" rel="noreferrer">
                    Join Live
                  </a>
                )}

                {canUpload && (
                  <button onClick={() => deleteLecture(l.id)}>Delete</button>
                )}
              </div>
            ))}
          </div>
        )}

      </div>

      {/* ── Video Modal ───────────────────────────────────── */}
      {activeVideo && (
        <div style={styles.modalOverlay} onClick={() => setActiveVideo(null)}>
          <div style={styles.modalBox} onClick={(e) => e.stopPropagation()}>

            {/* Modal Header */}
            <div style={styles.modalHeader}>
              <h3 style={{ margin: 0, color: "#f1f5f9" }}>{activeVideo.title}</h3>
              <button style={styles.closeBtn} onClick={() => setActiveVideo(null)}>
                ✕
              </button>
            </div>

            {/* Video Player */}
            {activeVideo.isEmbed ? (
              <iframe
                key={activeVideo.url}
                src={activeVideo.url}
                style={{ width: "100%", height: 400, borderRadius: 8, border: "none" }}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <video
                key={activeVideo.url}
                style={{ width: "100%", borderRadius: 8, background: "#000" }}
                controls
                autoPlay
                preload="metadata"
                onError={(e) => console.error("Video error:", e.target.error)}
              >
                <source src={activeVideo.url} type="video/webm" />
                <source src={activeVideo.url} type="video/mp4" />
                Your browser does not support the video tag.
              </video>
            )}

            {/* Jump-to Controls */}
            <div style={styles.jumpControls}>
              <span style={{ color: "#94a3b8", fontSize: 13 }}>Jump to:</span>

              {[1, 5, 10, 15, 30].map((min) => (
                <button
                  key={min}
                  style={styles.jumpBtn}
                  onClick={() => {
                    const vid = document.querySelector("video");
                    if (vid) vid.currentTime = min * 60;
                  }}
                >
                  {min}m
                </button>
              ))}

              <button
                style={styles.jumpBtn}
                onClick={() => {
                  const vid = document.querySelector("video");
                  if (vid) vid.currentTime = Math.max(0, vid.currentTime - 10);
                }}
              >
                ⏪ 10s
              </button>

              <button
                style={styles.jumpBtn}
                onClick={() => {
                  const vid = document.querySelector("video");
                  if (vid) vid.currentTime = vid.currentTime + 10;
                }}
              >
                10s ⏩
              </button>
            </div>

          </div>
        </div>
      )}
    </>
  );
}


// =============================================================
//  STYLES
// =============================================================

const styles = {
  page: {
    marginTop:  "70px",
    padding:    "30px",
    background: "#f1f5f9",
    minHeight:  "100vh",
  },
  header: {
    display:        "flex",
    justifyContent: "space-between",
    marginBottom:   "20px",
  },
  primaryBtn: {
    background:   "#2563eb",
    color:        "#fff",
    padding:      "10px 16px",
    border:       "none",
    borderRadius: "8px",
    cursor:       "pointer",
  },
  formCard: {
    background:     "#fff",
    padding:        "20px",
    borderRadius:   "10px",
    marginBottom:   "20px",
    display:        "flex",
    flexDirection:  "column",
    gap:            "10px",
  },
  tabs: {
    display:      "flex",
    gap:          "10px",
    marginBottom: "20px",
  },
  tab: {
    padding:    "6px 12px",
    background: "#e2e8f0",
    border:     "none",
    cursor:     "pointer",
  },
  activeTab: {
    padding:    "6px 12px",
    background: "#2563eb",
    color:      "#fff",
    border:     "none",
    cursor:     "pointer",
  },
  empty: {
    textAlign:  "center",
    marginTop:  "80px",
    color:      "#64748b",
  },
  grid: {
    display:               "grid",
    gridTemplateColumns:   "repeat(auto-fill,minmax(250px,1fr))",
    gap:                   "20px",
  },
  card: {
    background:   "#fff",
    padding:      "16px",
    borderRadius: "10px",
    boxShadow:    "0 4px 10px rgba(0,0,0,0.08)",
  },
  watchBtn: {
    background:   "#2563eb",
    color:        "#fff",
    border:       "none",
    borderRadius: "6px",
    padding:      "6px 12px",
    cursor:       "pointer",
    marginTop:    "8px",
  },
  modalOverlay: {
    position:       "fixed",
    inset:          0,
    background:     "rgba(0,0,0,0.7)",
    display:        "flex",
    alignItems:     "center",
    justifyContent: "center",
    zIndex:         1000,
  },
  modalBox: {
    background:   "#0f172a",
    borderRadius: "12px",
    padding:      "20px",
    width:        "90%",
    maxWidth:     "800px",
  },
  modalHeader: {
    display:        "flex",
    justifyContent: "space-between",
    alignItems:     "center",
    marginBottom:   "12px",
  },
  closeBtn: {
    background: "transparent",
    border:     "none",
    color:      "#94a3b8",
    fontSize:   "18px",
    cursor:     "pointer",
  },
  jumpControls: {
    display:    "flex",
    alignItems: "center",
    gap:        8,
    padding:    "10px 4px 4px",
    flexWrap:   "wrap",
  },
  jumpBtn: {
    background:  "#1e293b",
    color:       "#cbd5e1",
    border:      "1px solid #334155",
    borderRadius: 6,
    padding:     "4px 10px",
    fontSize:    12,
    cursor:      "pointer",
    fontFamily:  '"Segoe UI", system-ui, sans-serif',
  },
};