// ============================================================
// useModules — which modules this college has switched on
// ============================================================
// The backend decides this from ENABLED_MODULES in backend/.env and
// reports it at GET /api/modules/. hubs.js uses the answer to hide links,
// sidebar sections and home cards for modules that are off, and
// ProtectedRoute uses it to show a friendly message if someone opens an
// old bookmark to a switched-off page.
//
// Fetched ONCE per browser session and shared by every component (same
// idea as useRoleFlags). The list is the same for every user of the
// college, so it is not keyed by user.
//
// While loading, or if the request fails, `loaded` is false and nothing
// is hidden — the backend still refuses requests to modules that are off,
// so failing open never exposes anything.
// ============================================================

import { useEffect, useState } from "react";
import API from "../api";

const LOADING = { enabled: [], loaded: false };

let cachePromise = null; // in-flight / resolved request
let cacheValue = null;   // resolved { enabled, loaded }

export function clearModules() {
  cachePromise = null;
  cacheValue = null;
}

function fetchModules() {
  return API.get("modules/")
    .then((r) => ({ enabled: r.data?.enabled || [], loaded: true }))
    .catch(() => LOADING); // unknown -> show everything, try again next session
}

export default function useModules() {
  const [modules, setModules] = useState(() => cacheValue || LOADING);

  useEffect(() => {
    if (!cachePromise) {
      cachePromise = fetchModules().then((v) => {
        if (v.loaded) cacheValue = v;
        else cachePromise = null; // failed: allow a retry on the next page
        return v;
      });
    }

    let alive = true;
    cachePromise.then((v) => {
      if (alive) setModules(v);
    });
    return () => {
      alive = false;
    };
  }, []);

  return modules;
}

// true when the module is on — or when we don't know yet (fail open)
export function hasModule(modules, name) {
  if (!name || !modules?.loaded) return true;
  return modules.enabled.includes(name);
}
