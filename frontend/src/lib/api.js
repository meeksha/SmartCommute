// Single client for the SmartCommute backend. Every number shown in the UI
// comes from these responses - the frontend never recomputes CO2e, cost or time.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function api(url, { method = "GET", body, signal } = {}) {
  const response = await fetch(url, {
    method,
    signal,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let result = null;
  try {
    result = await response.json();
  } catch {
    result = null;
  }
  if (!response.ok) {
    const detail = result?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg?.replace(/^Value error, /, "")).join(" ")
      : detail || `Request failed (${response.status}). Please try again.`;
    throw new ApiError(message, response.status);
  }
  return result;
}

// Goal chips in the planner -> backend ranking profiles.
export const GOAL_TO_PROFILE = { balanced: "balanced", cost: "cheapest", time: "fastest", eco: "green_first" };

export function todayIST() {
  const now = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
  const pad = (n) => String(n).padStart(2, "0");
  return {
    date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
    time: `${pad(now.getHours())}:${pad(now.getMinutes())}`,
  };
}
