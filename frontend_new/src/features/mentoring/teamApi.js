// frontend/src/features/mentoring/teamApi.js
import API from "../../api";

const S = "mentoring/student/teams/";
const A = "mentoring/staff/teams/";
const H = "mentoring/hod/";

// ================= STUDENT =================
export const getMyTeamPage = () => API.get(S).then((r) => r.data);

/** Omit teamId to start a new team instead of joining one. */
export const joinTeam = (teamId) =>
  API.post(`${S}join/`, teamId ? { team_id: teamId } : {}).then((r) => r.data);

export const leaveTeam = () => API.post(`${S}leave/`).then((r) => r.data);

// =================class tutor =================
export const getAdvisorTeams = () => API.get(A).then((r) => r.data);

export const placeStudent = (studentId, teamId) =>
  API.post(`${A}place/`, { student_id: studentId, team_id: teamId })
    .then((r) => r.data);

/** No team_id = mark the student as deliberately left unplaced. */
export const leaveUnplaced = (studentId) =>
  API.post(`${A}place/`, { student_id: studentId }).then((r) => r.data);

export const autoFillTeams = () => API.post(`${A}auto-fill/`).then((r) => r.data);

export const closeFormation = () => API.post(`${A}close/`).then((r) => r.data);

export const getTeamMentors = (resuggest = false) =>
  API.get(`${A}mentors/${resuggest ? "?resuggest=1" : ""}`).then((r) => r.data);

/** mentorId null clears the mentor. */
export const setTeamMentor = (teamId, mentorId) =>
  API.post(`${A}mentors/`, { team_id: teamId, mentor_id: mentorId })
    .then((r) => r.data);

export const submitTeams = () => API.post(`${A}submit/`).then((r) => r.data);

// ================= HOD =================
export const getMentorRules = () =>
  API.get(`${H}mentor-rules/`).then((r) => r.data);

export const saveMentorRules = (body) =>
  API.post(`${H}mentor-rules/`, body).then((r) => r.data);

export const getTeamProposals = () =>
  API.get(`${H}team-proposals/`).then((r) => r.data);

/** Reuses the existing endpoint. Pass mentorId to approve with a swap. */
export const decideProposals = (allocationIds, decision, note = "", mentorId) =>
  API.post(`${H}decide-proposals/`, {
    allocation_ids: allocationIds,
    decision,
    ...(note ? { note } : {}),
    ...(mentorId ? { mentor_id: mentorId } : {}),
  }).then((r) => r.data);

// ================= HELPERS =================
export const yearLabel = (y) => ({ 1: "I", 2: "II", 3: "III", 4: "IV" }[y] || y || "—");

export const prettyYear = (ay) => (ay || "").replace("-", "\u2013");

export const bandClass = (b) =>
  ({ A: "tm-band a", B: "tm-band b", C: "tm-band c" }[b] || "tm-band none");

export const errorText = (err, fallback = "Something went wrong.") => {
  const d = err?.response?.data;
  if (!d) return fallback;
  if (typeof d === "string") return d;
  if (d.detail) return d.detail;
  const first = Object.values(d)[0];
  if (Array.isArray(first)) return first[0];
  if (typeof first === "string") return first;
  return fallback;
};