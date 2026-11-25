// Frontend/src/features/timetable/RoomsPanel.jsx
//
// Rooms are shared college-wide, set up once here.
//
// A room's job in the timetable is to be a place two classes can't occupy at
// once — the grid uses these to detect room clashes. Name is what a teacher
// reads on the grid; type and capacity are just metadata for now.

import { useEffect, useState } from "react";

import API from "../../api";

const ROOMS_URL = "/rooms/";

const ROOM_TYPES = [
  { value: "classroom", label: "Classroom" },
  { value: "lab", label: "Lab" },
  { value: "seminar", label: "Seminar hall" },
  { value: "auditorium", label: "Auditorium" },
  { value: "other", label: "Other" },
];

const blankForm = { name: "", type: "classroom", capacity: "" };

export default function RoomsPanel() {
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(blankForm);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");

  const showToast = (msg) => {
    setToast(msg);
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => setToast(""), 2200);
  };

  const load = async () => {
    setLoading(true);
    try {
      const r = await API.get(ROOMS_URL);
      setRooms(r.data || []);
    } catch (err) {
      console.error("Rooms load error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const change = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const resetForm = () => {
    setForm(blankForm);
    setEditingId(null);
    setError("");
  };

  const save = async () => {
    const name = form.name.trim();
    if (!name) {
      setError("Enter a room name.");
      return;
    }

    const payload = {
      name,
      type: form.type,
      capacity: form.capacity === "" ? null : Number(form.capacity),
    };

    setSaving(true);
    setError("");
    try {
      if (editingId) {
        await API.put(`${ROOMS_URL}${editingId}/`, payload);
        showToast("✓ Room updated");
      } else {
        await API.post(ROOMS_URL, payload);
        showToast("✓ Room added");
      }
      resetForm();
      load();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        data?.name?.[0] ||
          data?.non_field_errors?.[0] ||
          data?.detail ||
          "Could not save the room. A room with that name may already exist."
      );
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (room) => {
    setEditingId(room.id);
    setForm({
      name: room.name || "",
      type: room.type || "classroom",
      capacity: room.capacity ?? "",
    });
    setError("");
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this room? Any timetable using it will lose the room label."))
      return;
    try {
      await API.delete(`${ROOMS_URL}${id}/`);
      if (editingId === id) resetForm();
      load();
      showToast("✓ Room removed");
    } catch (err) {
      const data = err?.response?.data;
      setError(data?.detail || "Could not delete — it may be in use by a timetable.");
    }
  };

  const typeLabel = (v) => ROOM_TYPES.find((t) => t.value === v)?.label || v || "—";

  return (
    <div>
      {toast && (
        <div
          style={{
            position: "fixed", top: 24, left: "50%", transform: "translateX(-50%)",
            zIndex: 1000, background: "#15803d", color: "#fff", fontSize: 15,
            fontWeight: 600, padding: "11px 22px", borderRadius: 12,
            boxShadow: "0 8px 24px rgba(0,0,0,.22)",
          }}
        >
          {toast}
        </div>
      )}

      {/* ---------- add / edit form ---------- */}
      <div className="tb-card">
        <h3 className="tb-card-title">{editingId ? "Edit room" : "Add a room"}</h3>
        <p className="tb-hint" style={{ marginTop: 0, marginBottom: 14 }}>
          Rooms are shared across every department. Add each teaching space once.
        </p>

        <div className="tb-controls">
          <input
            name="name"
            placeholder="Room name (e.g. Block A - 201)"
            value={form.name}
            onChange={change}
            onKeyDown={(e) => e.key === "Enter" && save()}
          />
          <select name="type" value={form.type} onChange={change}>
            {ROOM_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <input
            name="capacity"
            type="number"
            min="0"
            placeholder="Capacity (optional)"
            value={form.capacity}
            onChange={change}
            onKeyDown={(e) => e.key === "Enter" && save()}
          />
        </div>

        {error && <div className="tb-error">{error}</div>}

        <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
          <button className="tb-btn" onClick={save} disabled={saving}>
            {saving ? "Saving…" : editingId ? "Save changes" : "Add room"}
          </button>
          {editingId && (
            <button className="tb-cancel" onClick={resetForm}>
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* ---------- rooms list ---------- */}
      <div className="tb-card">
        <h3 className="tb-card-title">Rooms ({rooms.length})</h3>

        {loading ? (
          <p className="tb-state">Loading…</p>
        ) : rooms.length === 0 ? (
          <p className="tb-state">No rooms yet. Add your first one above.</p>
        ) : (
          <table className="tb-list">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Capacity</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rooms.map((r) => (
                <tr key={r.id}>
                  <td><strong>{r.name}</strong></td>
                  <td>{typeLabel(r.type)}</td>
                  <td>{r.capacity ?? "—"}</td>
                  <td className="tb-right">
                    <div className="tb-actions">
                      <button className="tb-edit" onClick={() => startEdit(r)}>
                        Edit
                      </button>
                      <button className="tb-del" onClick={() => remove(r.id)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}