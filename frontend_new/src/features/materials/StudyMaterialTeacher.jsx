import { useEffect, useState } from "react";
import API from "../../api";

export default function StudyMaterialTeacher({ teachingId }) {

  // ================= FOLDER STATES =================
  const [folders, setFolders] = useState([]);
  const [openFolder, setOpenFolder] = useState(null); // null = folder grid
  const [newFolder, setNewFolder] = useState("");

  // ================= FILE STATES =================
  const [materials, setMaterials] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(false);

  const [form, setForm] = useState({
    title: "",
    description: "",
    file: null,
  });

  // ================= FETCH FOLDERS =================
  const fetchFolders = async () => {
    try {
      const res = await API.get(
        `/material-folders/?teaching_assignment=${teachingId}`
      );
      setFolders(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Folder fetch error:", err);
    }
  };

  // ================= FETCH FILES IN FOLDER =================
  const fetchMaterials = async (folderId) => {
    try {
      const res = await API.get(
        `/study-materials/?teaching_assignment=${teachingId}&folder=${folderId}`
      );
      setMaterials(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Material fetch error:", err);
    }
  };

  useEffect(() => {
    if (teachingId) fetchFolders();
  }, [teachingId]);

  // ================= CREATE FOLDER =================
  const createFolder = async () => {
    if (!newFolder.trim()) return alert("Folder name is required");
    try {
      await API.post("/material-folders/", {
        name: newFolder,
        teaching_assignment: teachingId,
      });
      setNewFolder("");
      fetchFolders();
      alert("Folder created");
    } catch (err) {
      console.log(err);
      // unique_together → duplicate name
      if (err.response?.data?.non_field_errors) {
        alert("A folder with that name already exists");
      } else {
        alert("Could not create folder");
      }
    }
  };

  // ================= DELETE FOLDER =================
  const deleteFolder = async (folder) => {
    const ok = window.confirm(
      `Delete "${folder.name}" and ALL files inside it? This cannot be undone.`
    );
    if (!ok) return;
    try {
      await API.delete(`/material-folders/${folder.id}/`);
      fetchFolders();
      alert("Folder deleted");
    } catch (err) {
      console.log(err);
      alert("Delete failed");
    }
  };

  // ================= OPEN / BACK =================
  const handleOpenFolder = (folder) => {
    setOpenFolder(folder);
    setShowForm(false);
    resetForm();
    fetchMaterials(folder.id);
  };

  const handleBack = () => {
    setOpenFolder(null);
    setMaterials([]);
    fetchFolders(); // refresh file counts
  };

  // ================= FORM HELPERS =================
  const handleChange = (e) =>
    setForm({ ...form, [e.target.name]: e.target.value });

  const handleFileChange = (e) =>
    setForm({ ...form, file: e.target.files[0] });

  const resetForm = () => {
    setForm({ title: "", description: "", file: null });
    setEditingId(null);
    setShowForm(false);
  };

  // ================= SAVE FILE =================
  const saveMaterial = async () => {
    if (!form.title.trim()) return alert("Title is required");
    if (!editingId && !form.file) return alert("Please upload a file");

    try {
      setLoading(true);

      const fd = new FormData();
      fd.append("title", form.title);
      fd.append("description", form.description);
      fd.append("teaching_assignment", teachingId);
      fd.append("folder", openFolder.id); // file belongs to this folder
      if (form.file) fd.append("file", form.file);

      if (editingId) {
        await API.patch(`/study-materials/${editingId}/`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        alert("Material updated");
      } else {
        await API.post("/study-materials/", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        alert("Material uploaded");
      }

      resetForm();
      fetchMaterials(openFolder.id);
    } catch (err) {
      console.log(err);
      alert("Operation failed");
    } finally {
      setLoading(false);
    }
  };

  // ================= EDIT / DELETE FILE =================
  const editMaterial = (m) => {
    setEditingId(m.id);
    setShowForm(true);
    setForm({
      title: m.title || "",
      description: m.description || "",
      file: null,
    });
  };

  const deleteMaterial = async (id) => {
    if (!window.confirm("Delete this material?")) return;
    try {
      await API.delete(`/study-materials/${id}/`);
      alert("Material deleted");
      fetchMaterials(openFolder.id);
    } catch (err) {
      console.log(err);
      alert("Delete failed");
    }
  };

  // ================= FOLDER GRID VIEW =================
  if (!openFolder) {
    return (
      <div className="card">
        <div style={{ marginBottom: "20px" }}>
          <h3>Study Materials</h3>
          <p>Create folders and upload files into them</p>
        </div>

        {/* create folder */}
        <div style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
          <input
            type="text"
            placeholder="New folder name (e.g. Question Bank)"
            value={newFolder}
            onChange={(e) => setNewFolder(e.target.value)}
            style={{ flex: 1, maxWidth: "320px" }}
          />
          <button className="btn-primary" onClick={createFolder}>
            + Create Folder
          </button>
        </div>

        {folders.length === 0 ? (
          <p>No folders yet. Create one to start uploading.</p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fill, minmax(190px, 1fr))",
              gap: "16px",
            }}
          >
            {folders.map((f) => (
              <div
                key={f.id}
                style={{
                  position: "relative",
                  background: "#F6F6F8",
                  border: "1px solid #E7E7EC",
                  borderRadius: "14px",
                  padding: "20px 18px",
                  cursor: "pointer",
                }}
                onClick={() => handleOpenFolder(f)}
              >
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteFolder(f);
                  }}
                  style={{
                    position: "absolute",
                    top: "10px",
                    right: "10px",
                    background: "#fee2e2",
                    color: "#dc2626",
                    border: "none",
                    borderRadius: "8px",
                    padding: "4px 8px",
                    fontSize: "13px",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  Delete
                </button>

                <div style={{ fontSize: "34px", lineHeight: 1 }}>📁</div>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: "15px",
                    marginTop: "12px",
                  }}
                >
                  {f.name}
                </div>
                <div
                  style={{
                    fontSize: "13.5px",
                    color: "#5D5A6B",
                    marginTop: "3px",
                  }}
                >
                  {f.file_count} file{f.file_count === 1 ? "" : "s"}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ================= INSIDE A FOLDER =================
  return (
    <div className="card">

      {/* breadcrumb */}
      <div style={{ marginBottom: "16px", fontSize: "15px", color: "#5D5A6B" }}>
        <span
          onClick={handleBack}
          style={{ color: "#4B32C3", fontWeight: 600, cursor: "pointer" }}
        >
          Study Materials
        </span>
        {"  ›  "}
        <strong style={{ color: "#17151F" }}>{openFolder.name}</strong>
      </div>

      {/* header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >
        <h3>{openFolder.name}</h3>
        <button
          className="btn-primary"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? "Cancel" : "+ Add File"}
        </button>
      </div>

      {/* upload form */}
      {showForm && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "12px",
            marginBottom: "20px",
          }}
        >
          <input
            type="text"
            name="title"
            placeholder="File Title"
            value={form.title}
            onChange={handleChange}
          />
          <textarea
            name="description"
            placeholder="Description"
            rows="4"
            value={form.description}
            onChange={handleChange}
          />
          <input
            type="file"
            accept=".pdf,.ppt,.pptx,.doc,.docx,.txt"
            onChange={handleFileChange}
          />
          <button
            className="btn-primary"
            onClick={saveMaterial}
            disabled={loading}
          >
            {loading
              ? "Saving..."
              : editingId
              ? "Update File"
              : `Upload to ${openFolder.name}`}
          </button>
        </div>
      )}

      {/* file table */}
      {materials.length === 0 ? (
        <p>No files in this folder</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Description</th>
                <th>Uploaded By</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {materials.map((m) => (
                <tr key={m.id}>
                  <td>{m.title}</td>
                  <td>{m.description || "-"}</td>
                  <td>{m.uploaded_by_name}</td>
                  <td>
                    {m.created_at
                      ? new Date(m.created_at).toLocaleDateString()
                      : "-"}
                  </td>
                  <td>
                    <div
                      style={{
                        display: "flex",
                        gap: "8px",
                        flexWrap: "wrap",
                      }}
                    >
                      {m.file && (
                        <a href={m.file} target="_blank" rel="noreferrer">
                          <button>View</button>
                        </a>
                      )}
                      <button
                        className="btn-primary"
                        onClick={() => editMaterial(m)}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => deleteMaterial(m.id)}
                        style={{
                          background: "red",
                          color: "white",
                          border: "none",
                          padding: "8px 12px",
                          borderRadius: "6px",
                          cursor: "pointer",
                        }}
                      >
                        Delete
                      </button>

                    </div>
                    
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}