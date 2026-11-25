import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function PlacementCompanies() {

  const [open, setOpen] = useState(false);

  const [companies, setCompanies] = useState([]);
  const [categories, setCategories] = useState([]);

  // ================= FORM =================
  const [editingId, setEditingId] = useState(null);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("other");
  const [website, setWebsite] = useState("");
  const [contactPerson, setContactPerson] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [about, setAbout] = useState("");

  // ================= FILTERS =================
  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // ================= INIT =================
  useEffect(() => {
    loadCompanies();

    // Category options come from the model via the API, never hardcoded
    // here -- otherwise adding a category means editing the model AND this
    // dropdown, and the day they disagree the form offers a value the
    // database rejects.
    API.get("placement/companies/categories/")
      .then((res) => setCategories(res.data || []))
      .catch((err) => console.error("Categories error:", err));
  }, []);

  const loadCompanies = () => {
    setLoading(true);

    API.get("placement/companies/")
      .then((res) => setCompanies(res.data || []))
      .catch((err) => {
        console.error("Companies load error:", err.response?.data || err);
        setError("Could not load companies.");
      })
      .finally(() => setLoading(false));
  };

  // ================= FORM HELPERS =================
  const resetForm = () => {
    setEditingId(null);
    setName("");
    setCategory("other");
    setWebsite("");
    setContactPerson("");
    setContactEmail("");
    setContactPhone("");
    setAbout("");
  };

  const startEdit = (c) => {
    setEditingId(c.id);
    setName(c.name || "");
    setCategory(c.category || "other");
    setWebsite(c.website || "");
    setContactPerson(c.contact_person || "");
    setContactEmail(c.contact_email || "");
    setContactPhone(c.contact_phone || "");
    setAbout(c.about || "");

    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ================= SAVE =================
  const handleSave = async () => {

    setError("");

    if (!name.trim()) {
      return alert("Enter the company name");
    }

    const payload = {
      name: name.trim(),
      category,
      website,
      contact_person: contactPerson,
      contact_email: contactEmail,
      contact_phone: contactPhone,
      about,
    };

    try {
      setSaving(true);

      if (editingId) {
        const res = await API.patch(
          `placement/companies/${editingId}/`,
          payload
        );
        setCompanies((prev) =>
          prev.map((c) => (c.id === editingId ? res.data : c))
        );
      } else {
        const res = await API.post("placement/companies/", payload);
        setCompanies((prev) => [...prev, res.data].sort((a, b) =>
          (a.name || "").localeCompare(b.name || "")
        ));
      }

      resetForm();

    } catch (err) {
      const data = err.response?.data;
      console.error("Company save error:", data);

      // the backend returns a readable message for a duplicate name
      const message =
        data?.name?.[0] ||
        data?.contact_email?.[0] ||
        data?.website?.[0] ||
        data?.detail ||
        "Could not save the company.";

      setError(message);

    } finally {
      setSaving(false);
    }
  };

  // ================= DEACTIVATE / REACTIVATE =================
  const handleDeactivate = async (c) => {

    if (!window.confirm(`Mark ${c.name} as no longer recruiting?`)) {
      return;
    }

    setError("");

    try {
      setSaving(true);

      await API.delete(`placement/companies/${c.id}/`);

      // The row is NOT removed -- the backend deactivates it so past drives
      // and offers keep pointing at a real company. Reflect that here.
      setCompanies((prev) =>
        prev.map((x) => (x.id === c.id ? { ...x, is_active: false } : x))
      );

    } catch (err) {
      console.error("Deactivate error:", err.response?.data || err);
      setError("Could not deactivate.");
    } finally {
      setSaving(false);
    }
  };

  const handleReactivate = async (c) => {
    setError("");

    try {
      setSaving(true);

      const res = await API.patch(`placement/companies/${c.id}/`, {
        is_active: true,
      });

      setCompanies((prev) =>
        prev.map((x) => (x.id === c.id ? res.data : x))
      );

    } catch (err) {
      console.error("Reactivate error:", err.response?.data || err);
      setError("Could not reactivate.");
    } finally {
      setSaving(false);
    }
  };

  // ================= VISIBLE ROWS =================
  // Filtering happens here rather than by refetching -- the list is small and
  // typing in the search box should not fire a request per keystroke.
  const visible = companies.filter((c) => {
    if (!showInactive && !c.is_active) {
      return false;
    }
    if (search.trim()) {
      return (c.name || "")
        .toLowerCase()
        .includes(search.trim().toLowerCase());
    }
    return true;
  });

  const activeCount = companies.filter((c) => c.is_active).length;
  const inactiveCount = companies.length - activeCount;

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Companies</h2>
              <p>
                Recruiters on your list. Drives are created against a company,
                so add it here first.
              </p>
            </div>

            {/* ================= ERROR ================= */}
            {error && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #dc2626", color: "#991b1b" }}
              >
                {error}
              </div>
            )}

            {/* ================= ADD / EDIT ================= */}
            <div className="card">

              <h3>{editingId ? "Edit Company" : "Add Company"}</h3>

              <div className="form-grid form-grid--row">

                <input
                  placeholder="Company name *"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />

                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {categories.length === 0 ? (
                    <option value="other">Loading...</option>
                  ) : (
                    categories.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))
                  )}
                </select>

                <input
                  placeholder="Website (https://...)"
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                />

                <input
                  placeholder="Contact person"
                  value={contactPerson}
                  onChange={(e) => setContactPerson(e.target.value)}
                />

                <input
                  type="email"
                  placeholder="Contact email"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                />

                <input
                  placeholder="Contact phone"
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                />

                <input
                  placeholder="Notes"
                  value={about}
                  onChange={(e) => setAbout(e.target.value)}
                />

                <button
                  className="btn-primary"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? "Saving..." : editingId ? "Update" : "Add"}
                </button>

                {editingId && (
                  <button className="btn-edit" onClick={resetForm}>
                    Cancel
                  </button>
                )}

              </div>

            </div>

            {/* ================= FILTERS ================= */}
            <div className="card">

              <div className="form-grid form-grid--row">

                <input
                  placeholder="Search by name"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />

                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "15px",
                    color: "#5D5A6B",
                    whiteSpace: "nowrap",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={showInactive}
                    onChange={(e) => setShowInactive(e.target.checked)}
                  />
                  Show inactive ({inactiveCount})
                </label>

              </div>

            </div>

            {/* ================= LIST ================= */}
            <div className="card">

              <h3>
                {showInactive ? "All companies" : "Active companies"}
                {loading ? "" : ` (${visible.length})`}
              </h3>

              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Contact</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan="7">Loading...</td>
                    </tr>
                  ) : visible.length > 0 ? (
                    visible.map((c) => (
                      <tr key={c.id}>

                        <td>
                          {c.website ? (
                            <a
                              href={c.website}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {c.name}
                            </a>
                          ) : (
                            c.name
                          )}
                        </td>

                        <td>{c.category_display || "-"}</td>
                        <td>{c.contact_person || "-"}</td>
                        <td>{c.contact_email || "-"}</td>
                        <td>{c.contact_phone || "-"}</td>

                        <td>
                          {c.is_active ? (
                            <span style={{ color: "#166534" }}>Active</span>
                          ) : (
                            <span style={{ color: "#5D5A6B" }}>Inactive</span>
                          )}
                        </td>

                        <td>
                          <div className="action-buttons">

                            <button
                              className="btn-edit"
                              onClick={() => startEdit(c)}
                              disabled={saving}
                            >
                              Edit
                            </button>

                            {c.is_active ? (
                              <button
                                className="btn-delete"
                                onClick={() => handleDeactivate(c)}
                                disabled={saving}
                              >
                                Deactivate
                              </button>
                            ) : (
                              <button
                                className="btn-edit"
                                onClick={() => handleReactivate(c)}
                                disabled={saving}
                              >
                                Reactivate
                              </button>
                            )}

                          </div>
                        </td>

                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="7">
                        {search
                          ? "No company matches that search."
                          : "No companies added yet."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

            </div>

          </div>

        </div>

      </div>

    </div>
  );
}