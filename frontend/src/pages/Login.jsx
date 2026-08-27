import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const handleLogin = async () => {
    setError("");

    if (!username || !password) {
      setError("Please enter username and password");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/users/login/",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ username, password }),
        }
      );

      const data = await response.json();
      console.log("LOGIN RESPONSE:", data);

      if (response.ok) {
        // ✅ SAVE TOKEN
        localStorage.setItem("token", data.access);
        localStorage.setItem("user", JSON.stringify(data));

        const role = (data.role || "").toLowerCase();
        const subRole = (data.sub_role || "").toLowerCase();

        // first-login users must set a new password before anything else
        if (data.must_change_password === true) {
          navigate("/change-password");
          return;
        }

        // superuser -> always the main admin dashboard
        if (data.is_superuser === true) {
          navigate("/dashboard");
        }
        // admins: decide by sub_role
        else if (role === "admin") {
          if (subRole === "accounts_admin") {
            navigate("/admin/fees");   // ACCOUNTS ADMIN
          }
          else if (subRole === "exam_admin") {
            navigate("/results");      // EXAMINATION ADMIN
          }
          else if (subRole === "academic_admin") {
            navigate("/courses");      // ACADEMIC ADMIN
          }
          else if (subRole === "iqac_admin") {
            navigate("/iqac");         // IQAC ADMIN
          }
          else {
            navigate("/dashboard");    // plain / super admin
          }
        }
        else if (role === "teacher") {
          navigate("/teacher");        // TEACHER
        }
        else if (role === "student") {
          navigate("/student");        // STUDENT
        }
        else if (role === "parent") {
          navigate("/parent");         // PARENT
        }
        else {
          console.log("Unknown role:", data);
          setError("Invalid role");
        }
      } else {
        setError(data.error || "Invalid credentials");
      }

    } catch (err) {
      console.log(err);
      setError("Server error");
    }

    setLoading(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      handleLogin();
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.wrapper}>

        {/* ── Left panel ── */}
        <div style={styles.left}>
          <div style={styles.blobTopLeft} />
          <div style={styles.blobBottomRight} />
          <div style={styles.blobCenter} />

          <div style={styles.leftContent}>
            <div style={styles.brandRow}>
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="10" fill="rgba(255,255,255,0.2)" />
                <path d="M8 16h16M16 8v16" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
              <span style={styles.brandName}>LMS</span>
            </div>

            <div style={styles.leftBody}>
              <div style={styles.welcomeTag}>WELCOME</div>
              <div style={styles.headline}>Learning Management System</div>
              <div style={styles.subline}>
                Your complete platform for courses, lectures, and student management.
              </div>
            </div>
          </div>
        </div>

        {/* ── Right panel ── */}
        <div style={styles.right}>
          <div style={styles.formBox}>

            <div style={styles.formHeader}>
              <div style={styles.formTitle}>Sign in</div>
              <div style={styles.formSub}>Enter your credentials to continue</div>
            </div>

            {/* Error */}
            {error && (
              <div style={styles.errorBanner}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="6" stroke="#b91c1c" strokeWidth="1.2" />
                  <path d="M7 4v3.5M7 9.5h.01" stroke="#b91c1c" strokeWidth="1.3" strokeLinecap="round" />
                </svg>
                {error}
              </div>
            )}

            {/* Username */}
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Username</label>
              <div style={styles.inputWrap}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={styles.inputIcon}>
                  <circle cx="8" cy="5.5" r="2.5" stroke="#94a3b8" strokeWidth="1.2" />
                  <path d="M2.5 14c0-3.04 2.46-5.5 5.5-5.5s5.5 2.46 5.5 5.5" stroke="#94a3b8" strokeWidth="1.2" />
                </svg>
                <input
                  type="text"
                  placeholder="Enter your username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onKeyDown={handleKeyDown}
                  style={styles.input}
                />
              </div>
            </div>

            {/* Password */}
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Password</label>
              <div style={styles.inputWrap}>
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  style={{ ...styles.input, paddingRight: 48 }}
                />
                <button onClick={() => setShowPassword(!showPassword)} style={styles.eyeBtn}>
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button onClick={handleLogin} disabled={loading} style={styles.submitBtn}>
              {loading ? "Signing in..." : "Sign in"}
            </button>

          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#e8f0fe",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: '"Segoe UI", system-ui, sans-serif',
    padding: "24px",
    boxSizing: "border-box",
  },
  wrapper: {
    display: "flex",
    width: "100%",
    maxWidth: 900,
    minHeight: 520,
    borderRadius: 24,
    overflow: "hidden",
    boxShadow: "0 24px 64px rgba(30,64,175,0.18)",
  },

  // ── Left ──
  left: {
    flex: 1,
    background: "#1d4ed8",
    position: "relative",
    overflow: "hidden",
    padding: "40px",
    display: "flex",
    flexDirection: "column",
  },
  blobTopLeft: {
    position: "absolute",
    top: -60,
    left: -60,
    width: 220,
    height: 220,
    borderRadius: "50%",
    background: "rgba(255,255,255,0.08)",
  },
  blobBottomRight: {
    position: "absolute",
    bottom: -80,
    right: -60,
    width: 260,
    height: 260,
    borderRadius: "50%",
    background: "rgba(255,255,255,0.08)",
  },
  blobCenter: {
    position: "absolute",
    bottom: 60,
    left: 40,
    width: 140,
    height: 140,
    borderRadius: "50%",
    background: "rgba(255,255,255,0.06)",
  },
  leftContent: {
    position: "relative",
    zIndex: 2,
    display: "flex",
    flexDirection: "column",
    height: "100%",
  },
  brandRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: "auto",
  },
  brandName: {
    fontSize: 20,
    fontWeight: 700,
    color: "#fff",
    letterSpacing: "-0.01em",
  },
  leftBody: {
    marginBottom: 32,
  },
  welcomeTag: {
    fontSize: 40,
    fontWeight: 700,
    color: "rgba(255,255,255,0.6)",
    letterSpacing: "0.12em",
    marginBottom: 50,
  },
  headline: {
    fontSize: 26,
    fontWeight: 700,
    color: "#fff",
    lineHeight: 1.25,
    marginBottom: 12,
    letterSpacing: "-0.02em",
  },
  subline: {
    fontSize: 13,
    color: "rgba(255,255,255,0.7)",
    lineHeight: 1.7,
    maxWidth: 280,
  },
  pillRow: {
    display: "flex",
    gap: 8,
  },
  pill: {
    fontSize: 11,
    fontWeight: 600,
    padding: "5px 14px",
    borderRadius: 99,
    background: "rgba(255,255,255,0.15)",
    color: "rgba(255,255,255,0.9)",
    border: "0.5px solid rgba(255,255,255,0.25)",
  },

  // ── Right ──
  right: {
    width: 420,
    background: "#ffffff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "48px 40px",
  },
  formBox: {
    width: "100%",
  },
  formHeader: {
    marginBottom: 28,
  },
  formTitle: {
    fontSize: 26,
    fontWeight: 700,
    color: "#0f172a",
    marginBottom: 6,
    letterSpacing: "-0.02em",
  },
  formSub: {
    fontSize: 13,
    color: "#64748b",
  },

  // Error
  errorBanner: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "#fef2f2",
    border: "0.5px solid #fecaca",
    borderRadius: 8,
    padding: "10px 14px",
    fontSize: 13,
    color: "#b91c1c",
    marginBottom: 20,
  },

  // Fields
  fieldGroup: {
    marginBottom: 20,
  },
  label: {
    display: "block",
    fontSize: 12,
    fontWeight: 600,
    color: "#374151",
    marginBottom: 7,
    letterSpacing: "0.01em",
  },
  inputWrap: {
    position: "relative",
    display: "flex",
    alignItems: "center",
  },
  inputIcon: {
    position: "absolute",
    left: 13,
    pointerEvents: "none",
  },
  input: {
    width: "100%",
    padding: "12px 14px 12px 38px",
    fontSize: 14,
    border: "1px solid #e2e8f0",
    borderRadius: 10,
    background: "#f8fafc",
    color: "#0f172a",
    outline: "none",
    transition: "border-color 0.15s, box-shadow 0.15s",
    boxSizing: "border-box",
    fontFamily: '"Segoe UI", system-ui, sans-serif',
  },
  eyeBtn: {
    position: "absolute",
    right: 12,
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 11,
    fontWeight: 700,
    color: "#3b82f6",
    padding: "4px 6px",
    width: "auto",
    fontFamily: '"Segoe UI", system-ui, sans-serif',
  },

  // Submit
  submitBtn: {
    width: "100%",
    padding: "13px 0",
    fontSize: 15,
    fontWeight: 700,
    background: "#1d4ed8",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    cursor: "pointer",
    marginTop: 4,
    fontFamily: '"Segoe UI", system-ui, sans-serif',
    letterSpacing: "0.01em",
    transition: "background 0.15s",
  },
  spinnerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  spinner: {
    display: "inline-block",
    width: 14,
    height: 14,
    border: "2px solid rgba(255,255,255,0.3)",
    borderTopColor: "#fff",
    borderRadius: "50%",
    animation: "spin 0.7s linear infinite",
  },

  // Divider
  dividerRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    margin: "20px 0",
  },
  dividerLine: {
    flex: 1,
    height: "0.5px",
    background: "#e2e8f0",
  },
  dividerText: {
    fontSize: 12,
    color: "#94a3b8",
    fontWeight: 500,
  },

  // Hint
  hint: {
    fontSize: 12,
    color: "#94a3b8",
    textAlign: "center",
    lineHeight: 1.6,
  },
};

export default Login;