import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

const GSI_SRC = "https://accounts.google.com/gsi/client";

function loadGsi() {
  if (window.google?.accounts?.id) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${GSI_SRC}"]`);
    const s = existing || document.createElement("script");
    s.src = GSI_SRC;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load Google sign-in. Check your internet connection."));
    if (!existing) document.head.appendChild(s);
  });
}

// Google Identity Services: Google returns a signed ID token, the backend
// verifies it and starts the same HttpOnly session as password sign-in.
// The client ID is read from the backend (/api/auth/config), so no rebuild is
// needed when it changes.
export default function GoogleSignIn({ onLogin, onError }) {
  const ref = useRef(null);
  const [state, setState] = useState("loading"); // loading | ready | disabled | error
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const cfg = await api("/api/auth/config");
        if (!cfg.google_enabled) {
          if (active) { setState("disabled"); setMessage(cfg.problem || ""); }
          return;
        }
        await loadGsi();
        if (!active) return;
        window.google.accounts.id.initialize({
          client_id: cfg.google_client_id,
          ux_mode: "popup",
          callback: async ({ credential }) => {
            try {
              const result = await api("/api/auth/google", { method: "POST", body: { credential } });
              onLogin(result.user);
            } catch (e) {
              onError?.(e.message);
            }
          },
        });
        window.google.accounts.id.renderButton(ref.current, {
          theme: "outline", size: "large", shape: "rectangular", text: "signin_with",
          width: Math.min(380, ref.current?.offsetWidth || 340),
        });
        setState("ready");
      } catch (e) {
        if (active) { setState("error"); setMessage(e.message); }
      }
    })();
    return () => { active = false; };
  }, []);

  return (
    <>
      <div ref={ref} className="google-btn-host" style={{ display: state === "ready" ? "flex" : "none" }}/>
      {state !== "ready" && (
        <button type="button" className="google-btn" disabled title="Google sign-in is not available">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.5-.2-2.2H12v4.3h5.4a4.6 4.6 0 0 1-2 3v2.8h3.3c1.9-1.8 2.9-4.4 2.9-7.9z"/><path fill="#34A853" d="M12 22c2.7 0 5-.9 6.7-2.4l-3.3-2.8c-.9.6-2.1 1-3.4 1a5.8 5.8 0 0 1-5.5-4H3.1v2.9A10 10 0 0 0 12 22z"/><path fill="#FBBC05" d="M6.5 13.8a6 6 0 0 1 0-3.6V7.3H3.1a10 10 0 0 0 0 9.4l3.4-2.9z"/><path fill="#EA4335" d="M12 6.2c1.5 0 2.9.5 3.9 1.5l2.9-2.9A10 10 0 0 0 3.1 7.3l3.4 2.9A5.8 5.8 0 0 1 12 6.2z"/></svg>
          {state === "loading" ? "Loading Google sign-in…" : "Sign in with Google"}
        </button>
      )}
      {state === "disabled" && <p className="oauth-note">{message || "Google sign-in is off: the server has no GOOGLE_CLIENT_ID set (see README)."}</p>}
      {state === "error" && <p className="oauth-note">{message}</p>}
    </>
  );
}
