import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import Navbar from "../components/Navbar";
import API from "../api";
import "../App.css";

export default function Users() {
  const currentUser = JSON.parse(localStorage.getItem("user") || "{}");

  const [users, setUsers] = useState([]);
  const [toast, setToast] = useState(null);
  const [editingUser, setEditingUser] = useState(null);

  const [newUser, setNewUser] = useState({
    username: "",
    password: "",
    role: "student",
    department: "CS",
  });

  const departments = ["CS", "IT", "ECE", "EEE"];

  useEffect(() => {
    fetchUsers();
  }, []);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const fetchUsers = async () => {
    try {
      const res = await API.get("users/");
      setUsers(res.data);
    } catch {
      showToast("Error loading users");
    }
  };

  const handleAddUser = async () => {
    if (!newUser.username || !newUser.password) {
      return showToast("Fill all fields");
    }

    try {
      const res = await API.post("users/", newUser);
      setUsers((prev) => [...prev, res.data]);

      setNewUser({
        username: "",
        password: "",
        role: "student",
        department: "CS",
      });

      showToast("User added");
    } catch {
      showToast("Error adding user");
    }
  };

  const handleEdit = (u) => {
    setEditingUser(u);
    setNewUser({
      username: u.username,
      password: "",
      role: u.role,
      department: u.department,
    });
  };

  const handleUpdateUser = async () => {
    try {
      await API.put(`users/${editingUser.id}/`, {
        username: newUser.username,
        role: newUser.role,
        department: newUser.department,
      });

      setEditingUser(null);
      fetchUsers();

      setNewUser({
        username: "",
        password: "",
        role: "student",
        department: "CS",
      });

      showToast("User updated");
    } catch {
      showToast("Update failed");
    }
  };

  const handleDelete = async (id) => {
    try {
      await API.delete(`users/${id}/`);
      setUsers((prev) => prev.filter((u) => u.id !== id));
      showToast("User deleted");
    } catch {
      showToast("Delete failed");
    }
  };

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good Morning";
    if (hour < 18) return "Good Afternoon";
    return "Good Evening";
  };

  return (
    <div className="layout">
      <Sidebar />

      <div className="main">
        <Navbar />

        <div className="content">
          <h1>LMS Administrator</h1>
          <p className="subtitle">User Management</p>

          <p className="greeting">
            {getGreeting()}, {currentUser.username}
          </p>

          {/* FORM */}
          <div className="card">
            <h3>{editingUser ? "Edit User" : "Register User"}</h3>

            <div className="form-grid">
              <input
                placeholder="Username"
                value={newUser.username}
                onChange={(e) =>
                  setNewUser({ ...newUser, username: e.target.value })
                }
              />

              <input
                type="password"
                placeholder="Password"
                value={newUser.password}
                onChange={(e) =>
                  setNewUser({ ...newUser, password: e.target.value })
                }
              />

              <select
                value={newUser.department}
                onChange={(e) =>
                  setNewUser({ ...newUser, department: e.target.value })
                }
              >
                {departments.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>

              <select
                value={newUser.role}
                onChange={(e) =>
                  setNewUser({ ...newUser, role: e.target.value })
                }
              >
                <option value="student">Student</option>
                <option value="teacher">Teacher</option>
              </select>

              {editingUser ? (
                <button className="btn btn-primary" onClick={handleUpdateUser}>
                  Update
                </button>
              ) : (
                <button className="btn btn-primary" onClick={handleAddUser}>
                  Create
                </button>
              )}
            </div>
          </div>

          {/* TABLE */}
          <div className="card">
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Dept</th>
                  <th>Role</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.username}</td>
                    <td>{u.department}</td>
                    <td>
                      <span className={`role-badge role-${u.role}`}>
                        {u.role}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn-edit"
                        onClick={() => handleEdit(u)}
                      >
                        Edit
                      </button>

                      <button
                        className="btn btn-danger"
                        onClick={() => handleDelete(u.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
/*   background: #e8f0fe; */

