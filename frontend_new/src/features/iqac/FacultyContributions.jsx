import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../App.css";

const CATEGORIES = [
  { value: "fdp", label: "FDP / Training Attended" },
  { value: "workshop_attended", label: "Workshop / Seminar Attended" },
  { value: "workshop_conducted", label: "Workshop / Seminar Conducted" },
  { value: "conference", label: "Conference Paper Presented" },
  { value: "journal", label: "Journal Publication" },
  { value: "certification", label: "Certification / MOOC (NPTEL etc.)" },
  { value: "guest_lecture", label: "Guest Lecture Delivered" },
  { value: "committee", label: "Committee / Cell Membership" },
  { value: "project", label: "Project / Grant / Consultancy" },
  { value: "book", label: "Book / Book chapter" },           // HRIS PART B
  { value: "patent", label: "Patent" },                      // HRIS PART B
  { value: "award", label: "Award / Recognition" },          // HRIS PART B
  { value: "other", label: "Other" },
];

const ROLES = [
  { value: "attended", label: "Attended" },
  { value: "conducted", label: "Conducted / Organized" },
  { value: "presented", label: "Presented" },
  { value: "published", label: "Published" },
  { value: "member", label: "Member" },
  { value: "other", label: "Other" },
];

// HRIS PART B: journal / conference indexing, and the status your HOD gives an entry
const INDEXING = [
  { value: "", label: "Not stated" },
  { value: "scopus", label: "Scopus" },
  { value: "sci", label: "SCI / SCIE" },
  { value: "wos", label: "Web of Science" },
  { value: "ugc_care", label: "UGC-CARE" },
  { value: "other", label: "Other / not indexed" },
];
const STATUS_PILL = { pending: "warn", verified: "ok", returned: "bad" };
const DETAILS_HINT = {
  journal: "Journal, volume, pages, DOI",
  conference: "Conference, place, proceedings / DOI",
  book: "Publisher, ISBN, chapter",
  patent: "Application / patent number, filed or granted",
  project: "Funding agency, your role (PI / Co-PI), period",
  award: "Given by, for what",
};

const emptyForm = {
  category: "fdp",
  title: "",
  organizer: "",
  activity_role: "attended",
  date: "",
  academic_year: "",
  proof: null,
  details: "",
  indexing: "",
  amount_lakhs: "",
};

export default function FacultyContributions() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [editingId, setEditingId] = useState(null);   // HRIS PART B: correcting a waiting / returned entry

  const showToast = (msg) => {
    setToast(msg);
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => setToast(""), 2200);
  };

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const load = async () => {
    setLoading(true);
    try {
      const r = await API.get("users/participation/");
      setItems(r.data || []);
    } catch (err) {
      console.error("Load participation error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const catLabel = (v) => CATEGORIES.find((c) => c.value === v)?.label || v;

  const add = async () => {
    setError("");
    if (!form.title || !form.date) {
      setError("Please fill the title and date.");
      return;
    }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append("category", form.category);
      fd.append("title", form.title);
      fd.append("organizer", form.organizer);
      fd.append("activity_role", form.activity_role);
      fd.append("date", form.date);
      fd.append("academic_year", form.academic_year);
      fd.append("details", form.details);
      fd.append("indexing", form.indexing);
      if (form.amount_lakhs !== "") fd.append("amount_lakhs", form.amount_lakhs);
      if (form.proof) fd.append("proof", form.proof);

      if (editingId) {
        await API.patch(`users/achievements/${editingId}/`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      } else {
        await API.post("users/participation/add/", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }

      setForm(emptyForm);
      setEditingId(null);
      // clear the file input element
      const fileInput = document.getElementById("proof-input");
      if (fileInput) fileInput.value = "";
      await load();
      showToast(editingId ? "✓ Sent to your HOD again" : "✓ Added. Your HOD will verify it");
    } catch (err) {
      const data = err?.response?.data;
      const first = data && typeof data === "object" ? Object.values(data).flat()[0] : null;
      setError(data?.detail || (typeof first === "string" ? first : "") || "Could not save. Please check the fields.");
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (it) => {
    setEditingId(it.id);
    setError("");
    setForm({
      category: it.category, title: it.title, organizer: it.organizer || "", activity_role: it.activity_role,
      date: it.date ? String(it.date).slice(0, 10) : "", academic_year: it.academic_year || "", proof: null,
      details: it.details || "", indexing: it.indexing || "",
      amount_lakhs: it.amount_lakhs == null ? "" : String(it.amount_lakhs),
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const verifiedCount = items.filter((x) => x.status === "verified").length;

  const remove = async (id) => {
    // FIX #31: deleting removes the record and its proof file for good - ask first
    const it = items.find((x) => x.id === id);
    if (!window.confirm(`Remove "${it?.title || "this activity"}"? Its proof file is deleted too. This cannot be undone.`)) return;
    try {
      await API.delete(`users/participation/${id}/delete/`);
      setItems((list) => list.filter((x) => x.id !== id));
      showToast("✓ Removed");
    } catch (err) {
      console.error("Delete error:", err);
      showToast(err?.response?.data?.detail || "Could not remove it.");
    }
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="sd-root">

              {toast && (
                <div
                  style={{
                    position: "fixed", top: 24, left: "50%", transform: "translateX(-50%)",
                    zIndex: 1000, background: "#15803d", color: "#fff", fontSize: 15, fontWeight: 600,
                    padding: "11px 22px", borderRadius: 12, boxShadow: "0 8px 24px rgba(0,0,0,.22)",
                  }}
                >
                  {toast}
                </div>
              )}

              <h1 className="sd-hello">My Contributions</h1>
              <p className="sd-sub">
                Record your FDPs, papers, patents, projects and other activities. Your HOD verifies each one;
                only verified entries count in your appraisal and in the NAAC / NBA reports.
              </p>

              {/* ===== ADD FORM ===== */}
              <div className="sd-panel" style={{ marginBottom: 20 }}>
                <div className="sd-pt">{editingId ? "Correct this entry" : "Add an activity"}</div>
                {editingId && items.find((x) => x.id === editingId)?.review_note && (
                  <div className="fc-note">
                    <b>Your HOD wrote:</b> {items.find((x) => x.id === editingId).review_note}
                  </div>
                )}

                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="sd-label">Type</span>
                    <select value={form.category} onChange={(e) => setField("category", e.target.value)}>
                      {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="sd-label">Your role</span>
                    <select value={form.activity_role} onChange={(e) => setField("activity_role", e.target.value)}>
                      {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: 6, gridColumn: "1 / -1" }}>
                    <span className="sd-label">Title</span>
                    <input
                      value={form.title}
                      placeholder="e.g. AI Workshop at IIT Madras"
                      onChange={(e) => setField("title", e.target.value)}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="sd-label">Organizer / Venue</span>
                    <input
                      value={form.organizer}
                      placeholder="e.g. IIT Madras"
                      onChange={(e) => setField("organizer", e.target.value)}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="sd-label">Date</span>
                    <input type="date" value={form.date} onChange={(e) => setField("date", e.target.value)} />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="sd-label">Academic year</span>
                    <input
                      value={form.academic_year}
                      placeholder="e.g. 2025-26"
                      onChange={(e) => setField("academic_year", e.target.value)}
                    />
                  </label>

                  {DETAILS_HINT[form.category] && (
                    <label style={{ display: "flex", flexDirection: "column", gap: 6, gridColumn: "1 / -1" }}>
                      <span className="sd-label">Details</span>
                      <input
                        value={form.details}
                        maxLength={300}
                        placeholder={DETAILS_HINT[form.category]}
                        onChange={(e) => setField("details", e.target.value)}
                      />
                    </label>
                  )}

                  {(form.category === "journal" || form.category === "conference") && (
                    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <span className="sd-label">Indexed in</span>
                      <select value={form.indexing} onChange={(e) => setField("indexing", e.target.value)}>
                        {INDEXING.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
                      </select>
                    </label>
                  )}

                  {form.category === "project" && (
                    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <span className="sd-label">Amount sanctioned (₹ lakh)</span>
                      <input
                        type="number" min="0" step="0.01"
                        value={form.amount_lakhs}
                        placeholder="e.g. 4.5"
                        onChange={(e) => setField("amount_lakhs", e.target.value)}
                      />
                    </label>
                  )}

                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="sd-label">{editingId ? "Replace proof (optional)" : "Proof (certificate / PDF / image)"}</span>
                    <input
                      id="proof-input"
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png"
                      onChange={(e) => setField("proof", e.target.files?.[0] || null)}
                    />
                  </label>
                </div>

                {error && <div style={{ color: "#dc2626", fontSize: 14, marginTop: 10 }}>{error}</div>}

                <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <button
                    onClick={add}
                    disabled={saving}
                    style={{
                      background: "#4B32C3", color: "#fff", border: "none", borderRadius: 8,
                      padding: "9px 18px", fontSize: 14, fontWeight: 600, cursor: saving ? "default" : "pointer",
                    }}
                  >
                    {saving ? "Saving…" : editingId ? "Send to HOD again" : "Add Activity"}
                  </button>
                  {editingId && (
                    <button
                      type="button"
                      className="btn-edit"
                      onClick={() => { setEditingId(null); setForm(emptyForm); setError(""); }}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>

              {/* ===== MY LIST ===== */}
              <div className="sd-panel">
                <div className="sd-pt">
                  My activities ({items.length}) · {verifiedCount} verified
                </div>

                {loading ? (
                  <div className="sd-empty">Loading…</div>
                ) : items.length === 0 ? (
                  <div className="sd-empty">No activities added yet.</div>
                ) : (
                  <table className="sd-tbl">
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Type</th>
                        <th>Date</th>
                        <th>Proof</th>
                        <th>Status</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it) => (
                        <tr key={it.id}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{it.title}</div>
                            {it.organizer && <div style={{ fontSize: 13, color: "#5D5A6B" }}>{it.organizer}</div>}
                            {it.details && <div style={{ fontSize: 13, color: "#5D5A6B" }}>{it.details}</div>}
                          </td>
                          <td>{it.category_label || catLabel(it.category)}</td>
                          <td className="sd-num">{it.date ? String(it.date).slice(0, 10).split("-").reverse().join("-") : ""}</td>
                          <td>
                            {it.proof_url ? (
                              <a href={it.proof_url} target="_blank" rel="noreferrer" style={{ color: "#4B32C3", fontSize: 14 }}>
                                View
                              </a>
                            ) : (
                              <span style={{ color: "#85839A", fontSize: 14 }}>—</span>
                            )}
                          </td>
                          <td>
                            <span className={`kb-pill ${STATUS_PILL[it.status] || ""} fc-pill`}>
                              {it.status === "pending" ? "Waiting for HOD" : it.status_label}
                            </span>
                            {it.status === "returned" && it.review_note && (
                              <div className="fc-why">{it.review_note}</div>
                            )}
                            {it.status === "verified" && it.verified_by_name && (
                              <div className="fc-why">by {it.verified_by_name}</div>
                            )}
                          </td>
                          <td className="sd-num">
                            {it.status !== "verified" && (
                            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                            <button type="button" className="btn-edit" onClick={() => startEdit(it)}>
                              {it.status === "returned" ? "Correct" : "Edit"}
                            </button>
                            <button
                              onClick={() => remove(it.id)}
                              style={{
                                background: "#fff", color: "#dc2626", border: "1px solid #fecaca",
                                borderRadius: 8, padding: "5px 12px", fontSize: 13.5, fontWeight: 600, cursor: "pointer",
                              }}
                            >
                              Delete
                            </button>
                            </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}