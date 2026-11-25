import axios from "axios";
import { API_BASE_URL } from "./apiBase";   // SAAS PHASE 2: this college's API


const API = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

API.interceptors.request.use((req) => {
  const token = localStorage.getItem("token");
  if (token) {
    req.headers["Authorization"] = `Bearer ${token}`;
  }
  return req;
});

// PHASE 5 PART 4: the server refused our sign-in (signed out elsewhere, password
// changed, or expired) -> clear it and go to the sign-in page, which shows why.
export const SIGNIN_NOTE_KEY = "kb_signin_note";

API.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401 && localStorage.getItem("token")) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      const why = err.response.data?.detail;
      try {
        sessionStorage.setItem(SIGNIN_NOTE_KEY,
          typeof why === "string" ? why : "Your session has ended. Please sign in again.");
      } catch { /* private mode: the page still goes to sign-in */ }
      window.location.assign("/");
    }
    return Promise.reject(err);
  },
);

export default API;