import { useEffect, useState } from "react";

// State that survives switching pages (module memory) and reloading the tab
// (sessionStorage). Cleared when the tab is closed or the user signs out.
const memory = new Map();
const PREFIX = "smartcommute-planner:";

export function usePersistentState(key, initial) {
  const [value, setValue] = useState(() => {
    if (memory.has(key)) return memory.get(key);
    try {
      const raw = sessionStorage.getItem(PREFIX + key);
      if (raw !== null) return JSON.parse(raw);
    } catch { /* storage unavailable */ }
    return typeof initial === "function" ? initial() : initial;
  });
  useEffect(() => {
    memory.set(key, value);
    try {
      if (value === undefined || value === null) sessionStorage.removeItem(PREFIX + key);
      else sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
    } catch { /* quota or private mode: memory copy still works */ }
  }, [key, value]);
  // Updates pushed from elsewhere (e.g. the header search) while this page is mounted.
  useEffect(() => {
    const onPush = (e) => { if (e.detail?.key === key) setValue(e.detail.value); };
    window.addEventListener(EVENT, onPush);
    return () => window.removeEventListener(EVENT, onPush);
  }, [key]);
  return [value, setValue];
}

const EVENT = "smartcommute-planner-set";

// Set planner state from outside the page that owns it.
export function setPersistentValue(key, value) {
  memory.set(key, value);
  try {
    if (value === undefined || value === null) sessionStorage.removeItem(PREFIX + key);
    else sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { key, value } }));
}

export function clearPersistentState() {
  memory.clear();
  try {
    Object.keys(sessionStorage).filter((k) => k.startsWith(PREFIX)).forEach((k) => sessionStorage.removeItem(k));
  } catch { /* ignore */ }
}
