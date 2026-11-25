// ============================================================
// useNotifications — one shared poll of the unread notifications
// ============================================================
// The bell (Navbar) and the "Notifications" badge (Sidebar) both need
// the unread list. Instead of each polling the API every 10 seconds,
// they subscribe to ONE poller here. The poller starts with the first
// subscriber and stops when the last one leaves (e.g. on the sign-in page).
// ============================================================

import { useEffect, useState } from "react";
import API from "../api";

const POLL_MS = 10000;

let items = [];
let timer = null;
const listeners = new Set();

const emit = () => listeners.forEach((fn) => fn(items));

async function refresh() {
  try {
    const res = await API.get("/notifications/?unread=true");
    items = res.data?.results || res.data || [];
    emit();
  } catch {
    /* keep the last good list; the next poll tries again */
  }
}

export async function markNotificationRead(id) {
  try {
    await API.post(`/notifications/${id}/mark_read/`);
  } finally {
    refresh();
  }
}

export default function useNotifications() {
  const [list, setList] = useState(items);

  useEffect(() => {
    listeners.add(setList);
    // a new subscriber already starts with the latest list (useState(items))
    if (!timer) {
      refresh();
      timer = setInterval(refresh, POLL_MS);
    }
    return () => {
      listeners.delete(setList);
      if (listeners.size === 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    };
  }, []);

  return list;
}
