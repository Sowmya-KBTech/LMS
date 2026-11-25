import { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";
import "../../App.css";

// ================= DESIGN TOKENS (match App.css) =================
const BRAND = "#4B32C3";
const INK = "#17151F";
const MUTED = "#5D5A6B";
const LINE = "#E7E7EC";

const AUD_COLOR = {
  everyone: BRAND,
  students: "#15803d",
  teachers: "#8A4B0A",
  parents:  "#7c3aed",
};
const AUD_LABEL = {
  everyone: "Everyone",
  students: "Students",
  teachers: "Teachers",
  parents:  "Parents",
};

// roles that can post announcements
const POSTER_ROLES = ["admin", "accounts_admin", "exam_admin", "academic_admin"];

export default function Announcements() {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const canPost = POSTER_ROLES.includes((user.role || "").toLowerCase());

  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [audience, setAudience] = useState("everyone");
  const [posting, setPosting] = useState(false);

  const load = () => {
    setLoading(true);
    API.get("/announcements/")
      .then((res) => setItems(res.data?.results || res.data || []))
      .catch((err) => console.log("announcements error:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const post = async () => {
    if (!title.trim() || !message.trim()) {
      alert("Please enter a title and message.");
      return;
    }
    setPosting(true);
    try {
      await API.post("/announcements/", {
        title: title.trim(),
        message: message.trim(),
        audience: audience,
      });
      setTitle(""); setMessage(""); setAudience("everyone");
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not post announcement.");
    } finally {
      setPosting(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this announcement?")) return;
    try {
      await API.delete(`/announcements/${id}/`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not delete.");
    }
  };

  const fmtDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) +
      " · " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  };

  const board = (
    <>
      {loading ? (
        <div style={S.card}><div style={{ textAlign: "center", color: "#85839A" }}>Loading…</div></div>
      ) : items.length === 0 ? (
        <div style={S.card}><div style={{ textAlign: "center", color: "#85839A" }}>No announcements yet.</div></div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {items.map((a) => {
            const accent = AUD_COLOR[a.audience] || AUD_COLOR.everyone;
            return (
              <div key={a.id} style={{ ...S.card, borderLeft: `4px solid ${accent}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <span style={{ ...S.badge, background: accent + "1a", color: accent }}>
                    {AUD_LABEL[a.audience] || "Everyone"}
                  </span>
                  <span style={{ fontSize: 16, fontWeight: 600, color: INK, flex: 1 }}>{a.title}</span>
                  {canPost && (
                    <button className="btn-delete" onClick={() => remove(a.id)}>Delete</button>
                  )}
                </div>
                <div style={{ fontSize: 15, color: "#5D5A6B", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{a.message}</div>
                <div style={{ fontSize: 13.5, color: "#85839A", marginTop: 12 }}>
                  {a.posted_by_name ? `Posted by ${a.posted_by_name}` : "Posted"} · {fmtDate(a.created_at)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            {/* ── HEADER ── */}
            <div className="header-box">
              <h2>Announcements</h2>
              <p>
                {canPost ? "Post updates and choose who each one is for." : "Latest updates from the college."}
              </p>
            </div>

            {/* side-by-side for posters: form left, board right */}
            <div style={{
              display: "grid",
              gridTemplateColumns: canPost ? "minmax(0,340px) minmax(0,1fr)" : "1fr",
              gap: 18, alignItems: "start",
            }}>

              {canPost && (
                <div style={S.card}>
                  <h3 style={{ fontSize: 17, fontWeight: 600, margin: "0 0 15px", color: INK }}>New announcement</h3>

                  <label style={S.label}>Title</label>
                  <input style={S.input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Fee payment due date" />

                  <label style={S.label}>Message</label>
                  <textarea style={{ ...S.input, minHeight: 100, resize: "vertical" }} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Write the announcement…" />

                  <label style={S.label}>Who is this for?</label>
                  <select style={S.input} value={audience} onChange={(e) => setAudience(e.target.value)}>
                    <option value="everyone">Everyone</option>
                    <option value="students">Students</option>
                    <option value="teachers">Teachers</option>
                    <option value="parents">Parents</option>
                  </select>

                  <button
                    className="btn-primary"
                    onClick={post}
                    disabled={posting}
                    style={{ width: "100%", marginTop: 16, padding: "11px 16px", opacity: posting ? 0.65 : 1 }}
                  >
                    {posting ? "Posting…" : "Post & notify"}
                  </button>
                </div>
              )}

              <div>{board}</div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}

const S = {
  card:  { background: "#fff", border: `1px solid ${LINE}`, borderRadius: 14, padding: 22, boxShadow: "0 1px 3px rgba(16,24,40,0.04)" },
  label: { display: "block", fontSize: 13.5, color: MUTED, marginBottom: 6, marginTop: 12, fontWeight: 500 },
  input: { width: "100%", border: "1px solid #E7E7EC", borderRadius: 9, padding: "10px 12px", fontSize: 15, background: "#fff", outline: "none", fontFamily: "inherit", boxSizing: "border-box", color: "#17151F" },
  badge: { fontSize: 12.5, fontWeight: 500, padding: "3px 11px", borderRadius: 999 },
};