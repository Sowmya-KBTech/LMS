import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import API from "../api";

function WatchLecture() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lectures, setLectures] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    API.get("learning/lectures/").then((res) => {
      setLectures(res.data);
      const found = res.data.find((l) => String(l.id) === String(id));
      setSelected(found || res.data[0]);
    });
  }, [id]);

  const getEmbedUrl = (url) => {
    if (!url) return null;
    if (url.includes("youtube.com/embed/")) return url;
    const shortMatch = url.match(/youtu\.be\/([a-zA-Z0-9_-]+)/);
    if (shortMatch) return `https://www.youtube.com/embed/${shortMatch[1]}`;
    const fullMatch = url.match(/[?&]v=([a-zA-Z0-9_-]+)/);
    if (fullMatch) return `https://www.youtube.com/embed/${fullMatch[1]}`;
    const driveMatch = url.match(/\/d\/([a-zA-Z0-9_-]+)/);
    if (driveMatch) return `https://drive.google.com/file/d/${driveMatch[1]}/preview`;
    return url;
  };

  const getVideoInfo = (lecture) => {
    if (!lecture) return null;
    const isEmbed = !!lecture.meeting_link;
    const url = isEmbed
      ? getEmbedUrl(lecture.meeting_link)
      : lecture.video_file?.startsWith("http")
      ? lecture.video_file
      : `http://127.0.0.1:8000${lecture.video_file}`;
    return { url, isEmbed };
  };

  const video = getVideoInfo(selected);

  return (
    <>
      <Navbar />
      <div style={styles.container}>

        {/* LEFT — Lecture List */}
        <div style={styles.sidebar}>
          <div style={styles.sidebarHeader}>
            <h3 style={styles.sidebarTitle}>📚 All Lectures</h3>
          </div>
          <div style={styles.lectureList}>
            {lectures.map((l) => (
              <div
                key={l.id}
                style={{
                  ...styles.lectureItem,
                  ...(selected?.id === l.id ? styles.lectureItemActive : {}),
                }}
                onClick={() => {
                  setSelected(l);
                  navigate(`/watch/${l.id}`, { replace: true });
                }}
              >
                <div style={styles.lectureIcon}>
                  {l.lecture_type === "live" ? "🔴" : "▶"}
                </div>
                <div>
                  <div style={styles.lectureTitle}>{l.title}</div>
                  <div style={styles.lectureMeta}>
                    {l.lecture_type}
                    {l.description ? ` · ${l.description}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT — Video Player */}
        <div style={styles.player}>
          {selected ? (
            <>
              <h2 style={styles.videoTitle}>{selected.title}</h2>
              {selected.description && (
                <p style={styles.videoDesc}>{selected.description}</p>
              )}
              <div style={styles.videoWrapper}>
                {video?.isEmbed ? (
                  <iframe
                    key={video.url}
                    src={video.url}
                    style={styles.iframe}
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                  />
                ) : (
                  <video
                    key={video?.url}
                    style={styles.video}
                    controls
                    autoPlay
                    preload="metadata"
                  >
                    <source src={video?.url} type="video/mp4" />
                    <source src={video?.url} type="video/webm" />
                    Your browser does not support video playback.
                  </video>
                )}
              </div>
            </>
          ) : (
            <div style={styles.empty}>Select a lecture to watch</div>
          )}
        </div>

      </div>
    </>
  );
}

const styles = {
  container: {
    display: "flex",
    marginTop: 56,
    height: "calc(100vh - 56px)",
    background: "#0f172a",
    overflow: "hidden",
  },
  sidebar: {
    width: 300,
    minWidth: 260,
    background: "#1e293b",
    borderRight: "1px solid #334155",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
  },
  sidebarHeader: {
    padding: "16px",
    borderBottom: "1px solid #334155",
    position: "sticky",
    top: 0,
    background: "#1e293b",
    zIndex: 1,
  },
  sidebarTitle: {
    color: "#f1f5f9",
    fontSize: 15,
    fontWeight: 700,
    margin: 0,
  },
  lectureList: {
    padding: "8px 0",
  },
  lectureItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: 12,
    padding: "12px 16px",
    cursor: "pointer",
    borderLeft: "3px solid transparent",
    transition: "background 0.15s",
  },
  lectureItemActive: {
    background: "#0f172a",
    borderLeft: "3px solid #2563eb",
  },
  lectureIcon: {
    fontSize: 14,
    marginTop: 2,
    color: "#94a3b8",
  },
  lectureTitle: {
    color: "#f1f5f9",
    fontSize: 14,
    fontWeight: 600,
    marginBottom: 4,
  },
  lectureMeta: {
    color: "#64748b",
    fontSize: 12,
  },
  player: {
    flex: 1,
    padding: "32px 40px",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
  },
  videoTitle: {
    color: "#f1f5f9",
    fontSize: 22,
    fontWeight: 700,
    marginBottom: 6,
    textAlign: "center",
    width: "100%",
    maxWidth: 900,
  },
  videoDesc: {
    color: "#94a3b8",
    fontSize: 14,
    marginBottom: 20,
    textAlign: "center",
    width: "100%",
    maxWidth: 900,
  },
  videoWrapper: {
    borderRadius: 12,
    overflow: "hidden",
    background: "#000",
    width: "100%",
    maxWidth: 900,
  },
  iframe: {
    width: "100%",
    height: 500,
    border: "none",
    display: "block",
  },
  video: {
    width: "100%",
    maxHeight: 500,
    display: "block",
    background: "#000",
  },
  empty: {
    color: "#64748b",
    marginTop: 100,
    textAlign: "center",
    fontSize: 16,
  },
};

export default WatchLecture;