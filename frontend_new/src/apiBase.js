// SAAS PHASE 2 - the backend address for THIS college.
//
// Each college has its own address and the backend picks the college from
// the address a request is sent to. So the frontend must call the API on the
// same host it was opened on:
//
//   opened at  http://abc.localhost:5173  ->  API at  http://abc.localhost:8000/api/
//   opened at  http://xyz.localhost:5173  ->  API at  http://xyz.localhost:8000/api/
//
// Settings (frontend .env, optional):
//   VITE_API_PORT=8000        port of the Django server in development (default 8000)
//   VITE_API_BASE_URL=/api/   set ONLY when the API is served on the same address
//                             as the site (production behind Nginx). Never put a
//                             fixed host such as http://localhost:8000 here - every
//                             college would then talk to the same address.

function buildApiBase() {
  const fixed = import.meta.env.VITE_API_BASE_URL;
  if (fixed) return fixed.endsWith("/") ? fixed : `${fixed}/`;

  const { protocol, hostname } = window.location;
  const port = import.meta.env.VITE_API_PORT || "8000";
  return `${protocol}//${hostname}:${port}/api/`;
}

export const API_BASE_URL = buildApiBase();

// PLATFORM CONSOLE - is this the KB Technosoft platform address?
// The platform answers on addresses with no college code in front.
//   laptop: localhost, 127.0.0.1      server (.env): VITE_PLATFORM_HOSTS=admin.kbtechcampus.in
export function isPlatformHost() {
  const hosts = (import.meta.env.VITE_PLATFORM_HOSTS || "localhost,127.0.0.1")
    .split(",").map((h) => h.trim().toLowerCase()).filter(Boolean);
  return hosts.includes(window.location.hostname.toLowerCase());
}

// The address a new college gets: <code>.<suffix>  (matches the backend's COLLEGE_DOMAIN_SUFFIX)
export const COLLEGE_DOMAIN_SUFFIX = import.meta.env.VITE_COLLEGE_DOMAIN_SUFFIX || "localhost";
