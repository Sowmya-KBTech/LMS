import { useEffect, useMemo, useRef, useState } from "react";
import API from "../../api";

const initials = (name = "") =>
  name.replace(/[^A-Za-z. ]/g, "").split(/[ .]/).filter(Boolean)
    .map((p) => p[0]).slice(0, 2).join("").toUpperCase();

export default function HOdTutors() {
  const [query, setQuery] = useState("");
  const [courses, setCourses] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [activeCourseId, setActiveCourseId] = useState(null);
  const [grid, setGrid] = useState(null);
  const [loadingGrid, setLoadingGrid] = useState(false);
  const [pickingYear, setPickingYear] = useState(null);
  const [pickValue, setPickValue] = useState("");
  const [toast, setToast] = useState("");
  const gridRef = useRef(null);

  useEffect(() => { fetchOverview(); }, []);

  useEffect(() => {
    if (activeCourseId && gridRef.current) {
      gridRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [activeCourseId, grid]);

  const fetchOverview = async () => {
    setLoadingList(true);
    try {
      const res = await API.get("users/hod-tutor-overview/");
      setCourses(res.data?.courses || []);
    } catch {
      setCourses([]);
    } finally {
      setLoadingList(false);
    }
  };

  const fetchGrid = async (courseId) => {
    setLoadingGrid(true);
    try {
      const res = await API.get(`users/hod-tutor-grid/${courseId}/`);
      setGrid(res.data);
    } catch {
      setGrid(null);
    } finally {
      setLoadingGrid(false);
    }
  };

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return courses;
    return courses.filter((c) => c.name.toLowerCase().includes(q));
  }, [courses, query]);

  const visibleCourses = activeCourseId
    ? courses.filter((c) => c.id === activeCourseId)
    : filtered;

  const openCourse = (id) => {
    setActiveCourseId(id);
    setPickingYear(null);
    fetchGrid(id);
  };

  const closeGrid = () => {
    setActiveCourseId(null);
    setGrid(null);
    setPickingYear(null);
  };

  const startPick = (yearId) => {
    setPickingYear(yearId);
    setPickValue("");
  };

  const confirmPick = async (yearId) => {
    if (!pickValue) return alert("Choose a teacher first");
    try {
      await API.post("users/hod-assign-tutor/", {
        course: activeCourseId,
        year: yearId,
        teacher: pickValue,
      });
      const teacher = grid.teachers.find((t) => String(t.id) === String(pickValue));
      showToast(`${teacher?.username || "Teacher"} assigned as class in-charge`);
      setPickingYear(null);
      await fetchGrid(activeCourseId);
      fetchOverview();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not assign class in-charge");
    }
  };

  const removeTutor = async (tutorId, teacherName) => {
    try {
      await API.delete(`users/hod-remove-tutor/${tutorId}/`);
      showToast(`${teacherName} removed as class in-charge`);
      await fetchGrid(activeCourseId);
      fetchOverview();
    } catch {
      alert("Could not remove class in-charge");
    }
  };

  return (
    <>
      {/* COURSE LIST */}
      <div className="sd-panel">
        <div className="sd-pt">Your department's courses</div>
        <p style={{ color: "#5D5A6B", fontSize: 14.5, margin: "0 0 14px" }}>
          Pick a course, then assign a class in-charge to each year.
        </p>
        <input
          placeholder="Course name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ width: "100%" }}
        />
        {loadingList && <div style={{ marginTop: 14, color: "#5D5A6B" }}>Loading…</div>}
        {!loadingList && visibleCourses.length === 0 && (
          <div style={{ marginTop: 14, color: "#5D5A6B" }}>
            No course in your department matches{query ? ` "${query}"` : ""}.
          </div>
        )}
        {!loadingList && visibleCourses.map((c) => (
          <div
            key={c.id}
            onClick={() => openCourse(c.id)}
            style={{
              display: "flex", alignItems: "center", gap: 14,
              border: c.id === activeCourseId ? "1px solid #3b5bdb" : "1px solid #e7ecf3",
              background: c.id === activeCourseId ? "#f3f6ff" : "#fff",
              borderRadius: 14, padding: "16px 18px", cursor: "pointer", marginTop: 12,
            }}
          >
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15.5, fontWeight: 600 }}>{c.name}</div>
              <div style={{ fontSize: 14, color: "#5D5A6B", marginTop: 3 }}>
                {c.total_years} year{c.total_years !== 1 ? "s" : ""} ·{" "}
                {c.pending > 0 ? (
                  <span style={{ color: "#8A4B0A", fontWeight: 700 }}>
                    {c.pending} year(s) without a class in-charge
                  </span>
                ) : "all years covered"}
              </div>
            </div>
            <span style={{ color: "#3b5bdb", fontWeight: 600, fontSize: 14.5 }}>Assign class in-charges ›</span>
          </div>
        ))}
      </div>

      {/* GRID */}
      {activeCourseId && (
        <div className="sd-panel" style={{ marginTop: 16 }} ref={gridRef}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
            <span style={{ fontSize: 16, fontWeight: 700, flex: 1 }}>
              {grid?.course?.name || "…"} · Class In-charges
            </span>
            <button className="btn-delete" onClick={closeGrid}>Change course</button>
          </div>
          {loadingGrid && <div style={{ color: "#5D5A6B" }}>Loading…</div>}
          {!loadingGrid && grid && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
              {grid.years.map((y) => (
                <div
                  key={y.year_id}
                  style={{
                    border: "1px solid #e7ecf3", borderRadius: 12, padding: "14px 16px", minHeight: 84,
                    background: y.tutor ? "#f0faf4" : pickingYear === y.year_id ? "#f3f6ff" : "#fffaf2",
                    borderColor: y.tutor ? "#c6ebd4" : pickingYear === y.year_id ? "#3b5bdb" : "#f0c79a",
                    borderStyle: y.tutor || pickingYear === y.year_id ? "solid" : "dashed",
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#9aa4b6", letterSpacing: 0.5 }}>
                    YEAR {y.year_number}
                  </div>

                  {y.tutor ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                      <span style={{
                        width: 26, height: 26, borderRadius: "50%",
                        background: "#16a34a", color: "#fff",
                        fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center",
                      }}>
                        {initials(y.tutor.teacher_name)}
                      </span>
                      <span style={{ fontSize: 14.5, fontWeight: 600 }}>{y.tutor.teacher_name}</span>
                      <button
                        title="Remove"
                        onClick={() => removeTutor(y.tutor.id, y.tutor.teacher_name)}
                        style={{ marginLeft: "auto", border: "none", background: "transparent", color: "#9aa4b6", cursor: "pointer", fontSize: 15 }}
                      >×</button>
                    </div>
                  ) : pickingYear === y.year_id ? (
                    <div style={{ marginTop: 8 }}>
                      <select value={pickValue} onChange={(e) => setPickValue(e.target.value)} style={{ width: "100%" }}>
                        <option value="">Choose teacher…</option>
                        {grid.teachers.map((t) => (
                          <option key={t.id} value={t.id}>{t.username} · {t.employee_id || "—"}</option>
                        ))}
                      </select>
                      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                        <button className="btn-primary" style={{ flex: 1, padding: "7px" }} onClick={() => confirmPick(y.year_id)}>Assign</button>
                        <button className="btn-delete" style={{ flex: 1, padding: "7px" }} onClick={() => setPickingYear(null)}>Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div
                      onClick={() => startPick(y.year_id)}
                      style={{ color: "#8A4B0A", fontWeight: 600, fontSize: 14, marginTop: 10, cursor: "pointer" }}
                    >+ Assign class in-charge</div>
                  )}
                </div>
              ))}

              {grid.teachers.length === 0 && (
                <p style={{ gridColumn: "1 / -1", marginTop: 6, color: "#85839A", fontSize: 14 }}>
                  No teachers teach this course yet, so there's no one to pick from.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {toast && (
        <div style={{
          position: "fixed", right: 24, bottom: 24, background: "#0f3d2e", color: "#fff",
          padding: "14px 20px", borderRadius: 12, display: "flex", alignItems: "center",
          gap: 10, boxShadow: "0 12px 30px rgba(0,0,0,.25)", zIndex: 50,
        }}>
          <span style={{
            background: "#16a34a", width: 24, height: 24, borderRadius: "50%",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14,
          }}>✓</span>
          <span>{toast}</span>
        </div>
      )}
    </>
  );
}