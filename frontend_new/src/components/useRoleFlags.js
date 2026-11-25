// ============================================================
// useRoleFlags — HOD / class tutor / placement coordinator / Principal (Wave 2)
// ============================================================
// These are ASSIGNMENTS, not roles, so they cannot be read from
// localStorage like user.role — the backend is asked, and it stays the
// single source of truth for who holds them.
//
// The answer is cached per logged-in user for the browser session, so
// the Navbar, Sidebar and home page share ONE set of requests instead of
// each firing their own on every page change. Logging out (or a different
// user logging in) clears the cache — see clearRoleFlags().
// ============================================================

import { useEffect, useState } from "react";
import API from "../api";

const EMPTY = { isHod: false, isTutor: false, isPlacementCoordinator: false, isPrincipal: false, loaded: false };

let cacheKey = null;     // which user the cache belongs to
let cachePromise = null; // in-flight / resolved request
let cacheValue = null;   // resolved flags

const readUser = () => {
  try {
    return JSON.parse(localStorage.getItem("user") || "{}") || {};
  } catch {
    return {};
  }
};

export function clearRoleFlags() {
  cacheKey = null;
  cachePromise = null;
  cacheValue = null;
}

function fetchFlags() {
  const settle = (p, pick) => p.then((r) => pick(r.data) || false).catch(() => false);

  return Promise.all([
    settle(API.get("users/my-department/"), (d) => d?.is_hod),
    settle(API.get("users/my-class/"), (d) => d?.is_tutor),
    settle(API.get("placement/me/"), (d) => d?.is_placement_coordinator),
    settle(API.get("users/principal/"), (d) => d?.is_me),           // WAVE 2
  ]).then(([isHod, isTutor, isPlacementCoordinator, isPrincipal]) => ({
    isHod,
    isTutor,
    isPlacementCoordinator,
    isPrincipal,
    loaded: true,
  }));
}

export default function useRoleFlags() {
  const user = readUser();
  const isTeacher = user.role === "teacher";
  const key = isTeacher ? `${user.id}:${user.username}` : null;

  const [flags, setFlags] = useState(() =>
    key && cacheKey === key && cacheValue ? cacheValue : { ...EMPTY, loaded: !isTeacher }
  );

  useEffect(() => {
    if (!key) return undefined;

    if (cacheKey !== key) {
      cacheKey = key;
      cacheValue = null;
      cachePromise = fetchFlags().then((v) => {
        if (cacheKey === key) cacheValue = v;
        return v;
      });
    }

    let alive = true;
    cachePromise.then((v) => {
      if (alive) setFlags(v);
    });
    return () => {
      alive = false;
    };
  }, [key]);

  return flags;
}
