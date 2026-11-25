import { useEffect, useState } from "react";
import API from "../../api";

export default function StudyMaterialStudent({ teachingId }) {

  // ================= STATES =================
  const [folders, setFolders] = useState([]);
  const [openFolder, setOpenFolder] = useState(null); // null = folder grid

  const [materials, setMaterials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  // ================= FETCH FOLDERS =================
  const fetchFolders = async () => {
    try {
      const res = await API.get(
        `/material-folders/?teaching_assignment=${teachingId}`
      );
      setFolders(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Folder fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  // ================= FETCH FILES IN A FOLDER =================
  const fetchMaterials = async (folderId) => {
    try {
      setLoading(true);
      const res = await API.get(
        `/study-materials/?teaching_assignment=${teachingId}&folder=${folderId}`
      );
      setMaterials(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Material fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  // ================= LOAD =================
  useEffect(() => {
    if (teachingId) fetchFolders();
  }, [teachingId]);

  // ================= OPEN / CLOSE FOLDER =================
  const handleOpenFolder = (folder) => {
    setOpenFolder(folder);
    setSearch("");
    fetchMaterials(folder.id);
  };

  const handleBack = () => {
    setOpenFolder(null);
    setMaterials([]);
  };

  // ================= FILTERED =================
  const filteredMaterials = materials.filter((m) =>
    m.title?.toLowerCase().includes(search.toLowerCase()) ||
    m.description?.toLowerCase().includes(search.toLowerCase()) ||
    m.uploaded_by_name?.toLowerCase().includes(search.toLowerCase())
  );

  // ================= FOLDER GRID VIEW =================
  if (!openFolder) {
    return (
      <div className="card">
        <div style={{ marginBottom: "20px" }}>
          <h2>Study Materials</h2>
          <p>Open a folder to view and download files</p>
        </div>

        {loading ? (
          <p>Loading folders...</p>
        ) : folders.length === 0 ? (
          <p>No folders yet</p>
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
                onClick={() => handleOpenFolder(f)}
                style={{
                  background: "#F6F6F8",
                  border: "1px solid #E7E7EC",
                  borderRadius: "14px",
                  padding: "20px 18px",
                  cursor: "pointer",
                }}
              >
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

      {/* header + search */}
      <div style={{ marginBottom: "20px" }}>
        <h3>{openFolder.name}</h3>
        <input
          type="text"
          placeholder="Search files..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: "100%", maxWidth: "350px", marginTop: "10px" }}
        />
      </div>

      {loading ? (
        <p>Loading files...</p>
      ) : filteredMaterials.length === 0 ? (
        <p>No files in this folder</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Description</th>
                <th>Uploaded By</th>
                <th>Date</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredMaterials.map((m) => (
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
                    {m.file ? (
                      <a href={m.file} target="_blank" rel="noreferrer">
                        <button className="btn-primary">View Material</button>
                      </a>
                    ) : (
                      <span>No file</span>
                    )}
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