import HeaderSearch from "./components/HeaderSearch";
import { useCallback, useEffect, useState } from "react";
import {
  LayoutDashboard, Users, Lightbulb, Wallet, BarChart3, Settings as SettingsIcon, Leaf, Bell, Search, Menu, X,
  LogOut, ChevronRight, Activity, BadgeIndianRupee, Bus, ShieldCheck, Mail, Lock, Eye, EyeOff, Car, Loader2,
} from "lucide-react";
import { api } from "./lib/api";
import { clearPersistentState } from "./lib/usePersistentState";
import GoogleSignIn from "./components/GoogleSignIn";
import Dashboard from "./pages/Dashboard";
import Carpooling from "./pages/Carpooling";
import Insights from "./pages/Insights";
import Savings from "./pages/Savings";
import DigitalTwin from "./pages/DigitalTwin";
import Analytics from "./pages/Analytics";
import Incentives from "./pages/Incentives";
import Shuttles from "./pages/Shuttles";
import Team from "./pages/Team";
import SettingsPage from "./pages/Settings";
import "./app.css";
import "./additions.css";

const menu = [
  { name: "Dashboard", icon: LayoutDashboard },
  { name: "Carpooling", icon: Users },
  { name: "Recommendations", icon: Lightbulb },
  { name: "Savings", icon: Wallet },
  { name: "Digital Twin", icon: Activity, admin: true },
  { name: "Incentives", icon: BadgeIndianRupee, admin: true },
  { name: "Shuttles", icon: Bus, admin: true },
  { name: "Analytics", icon: BarChart3, admin: true },
  { name: "Team", icon: ShieldCheck, admin: true },
  { name: "Settings", icon: SettingsIcon },
];

const KEYWORDS = {
  Dashboard: ["plan", "route", "trip", "commute", "home"],
  Carpooling: ["carpool", "colleague", "share", "ride", "request", "contact"],
  Recommendations: ["insight", "learn", "preference", "history"],
  Savings: ["saving", "money", "co2", "carbon", "emission"],
  "Digital Twin": ["twin", "scenario", "simulat", "organisation", "organization"],
  Incentives: ["incentive", "budget", "subsid", "pass", "abatement", "cost curve", "spend"],
  Shuttles: ["shuttle", "bus route", "fleet", "pickup", "or-tools"],
  Team: ["team", "admin", "role", "users", "employees"],
  Analytics: ["analytic", "demand", "cluster", "ml", "model", "pricing", "driver"],
  Settings: ["setting", "vehicle", "profile", "employee", "reset"],
};

const descriptions = {
  Dashboard: "Plan your commute with real Bengaluru and Tumakuru transit data.",
  Carpooling: "Colleagues who could share your ride.",
  Recommendations: "What the planner has learned about how you like to travel.",
  Savings: "Your financial and environmental impact.",
  "Digital Twin": "Simulate organisation-wide commute policies.",
  Incentives: "Spend a commute budget where it cuts the most CO₂e.",
  Shuttles: "Plan company shuttles where public transport doesn't reach the office.",
  Team: "Who is a company admin and who is an employee.",
  Analytics: "Mobility patterns, carpool zones and ride-hailing demand.",
  Settings: "Your commute profile and vehicle.",
};

const allSearchPages = menu.map((m) => ({ ...m, keywords: KEYWORDS[m.name] || [], hint: descriptions[m.name] }));


function BackendStatus() {
  const [health, setHealth] = useState(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    let active = true;
    let timer;
    async function poll() {
      try {
        const h = await api("/api/health");
        if (!active) return;
        setHealth(h);
        setDown(false);
        if (h.warmup?.state !== "ready" && h.warmup?.state !== "lazy") timer = setTimeout(poll, 3000);
      } catch {
        if (!active) return;
        setDown(true);
        timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { active = false; clearTimeout(timer); };
  }, []);
  if (down) return <span className="live-status status-down"><i/> Backend offline</span>;
  const state = health?.warmup?.state;
  if (state && state !== "ready" && state !== "lazy") {
    return <span className="live-status status-warming"><Loader2 size={13} className="spin"/> Loading transit data…</span>;
  }
  return <span className="live-status"><i/> {state ? "Engine ready" : "Connecting…"}</span>;
}

export function LoginPage({ onLogin, initialError = "" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(initialError);
  const [isRegistering, setIsRegistering] = useState(false);
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submitCredentials(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const result = await api(`/api/auth/${isRegistering ? "register" : "login"}`, {
        method: "POST",
        body: { email, password, remember }
      });
      onLogin(result.user);
    } catch (requestError) {
      setError(requestError.message || "Unable to sign in. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-visual">
        <div className="login-brand">
          <div className="login-brand-mark"><Leaf size={27}/></div>
          <div><strong>SmartCommute</strong><span>SUSTAINABLE MOBILITY</span></div>
        </div>

        <div className="login-visual-content">
          <span className="login-kicker">SMARTER JOURNEYS START HERE</span>
          <h1>Make every commute <em>count.</em></h1>
          <p>Connect with colleagues, reduce emissions and discover travel options that are better for you and the planet.</p>

          <div className="impact-preview">
            <div className="impact-icon"><Leaf size={24}/></div>
            <div><strong>Real Bengaluru data</strong><span>BMTC & Metro timetables · Namma Yatri · carpool matching</span></div>
          </div>
        </div>

        <div className="route-art" aria-hidden="true">
          <div className="route-line route-line-one"/>
          <div className="route-line route-line-two"/>
          <div className="route-point route-point-one"><span>Office</span></div>
          <div className="route-point route-point-two"><span>Whitefield</span></div>
          <div className="route-car"><Car size={21}/></div>
        </div>

        <p className="login-visual-footer">Building a greener tomorrow, one journey at a time.</p>
      </div>

      <div className="login-form-side">
        <div className="login-mobile-brand"><div className="login-brand-mark"><Leaf size={24}/></div><strong>SmartCommute</strong></div>
        <div className="login-card">
          <span className="login-welcome">{isRegistering ? "GET STARTED" : "WELCOME BACK"}</span>
          <h2>{isRegistering ? "Create your account" : "Sign in to your account"}</h2>
          <p className="login-subtitle">{isRegistering ? "Create an account to plan and save your commutes." : "Enter your details to continue to SmartCommute."}</p>

          <form onSubmit={submitCredentials}>
            {error && <div className="login-error" role="alert">{error}</div>}

            <label htmlFor="login-email">Email address</label>
            <div className="login-input">
              <Mail size={18}/>
              <input id="login-email" type="email" autoComplete="email" placeholder="you@company.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>

            <div className="password-label">
              <label htmlFor="login-password">Password</label>
              {!isRegistering && <button type="button" className="forgot-link" onClick={() => setError("Ask your administrator to reset your password (admin command: docker compose exec backend python -m app.tools.reset_password <email> <new password>).")}>Forgot password?</button>}
            </div>
            <div className="login-input">
              <Lock size={18}/>
              <input id="login-password" type={showPassword ? "text" : "password"} autoComplete={isRegistering ? "new-password" : "current-password"} minLength={isRegistering ? 8 : undefined} placeholder={isRegistering ? "At least 8 characters" : "Enter your password"} value={password} onChange={(event) => setPassword(event.target.value)} required />
              <button type="button" className="password-toggle" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((visible) => !visible)}>
                {showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}
              </button>
            </div>

            {!isRegistering && <label className="remember-row"><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)}/><span>Remember me</span></label>}
            <button type="submit" className="login-submit" disabled={submitting}>{submitting ? "Please wait..." : isRegistering ? "Create account" : "Sign in"} <ChevronRight size={18}/></button>
          </form>

          <div className="login-divider"><span>or continue with</span></div>
          <GoogleSignIn onLogin={onLogin} onError={setError}/>

          <p className="signup-copy">
            {isRegistering ? "Already have an account?" : "New to SmartCommute?"}{" "}
            <button type="button" onClick={() => { setIsRegistering((registering) => !registering); setError(""); }}>
              {isRegistering ? "Sign in" : "Create an account"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}


export default function App() {
  const [active, setActive] = useState("Dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [user, setUser] = useState(null);
  const [profile, setProfile] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const [pendingRequests, setPendingRequests] = useState(0);

  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    const check = () => api("/api/carpool/requests/count")
      .then((r) => { if (alive) setPendingRequests(r.pending_incoming); }).catch(() => {});
    check();
    const id = setInterval(check, 60000);
    return () => { alive = false; clearInterval(id); };
  }, [user]);

  useEffect(() => {
    let alive = true;
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(async (r) => {
        if (r.status === 401) return null;
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail || "Unable to verify your sign-in.");
        return body.user;
      })
      .then((account) => { if (alive && account) setUser(account); })
      .catch((e) => { if (alive) setAuthError(e.message || "Unable to connect to the account service."); })
      .finally(() => { if (alive) setAuthLoading(false); });
    return () => { alive = false; };
  }, []);

  const refreshProfile = useCallback(() => {
    api("/api/users/me").then(setProfile).catch(() => {});
  }, []);

  useEffect(() => {
    if (user) refreshProfile();
    else setProfile(null);
  }, [user, refreshProfile]);

  async function handleLogout() {
    setLoggingOut(true);
    setAuthError("");
    try {
      await api("/api/auth/logout", { method: "POST" });
      clearPersistentState();
      setUser(null);
      setActive("Dashboard");
    } catch (e) {
      setAuthError(e.message || "Unable to sign out. Please try again.");
    } finally {
      setLoggingOut(false);
    }
  }

  function renderPage() {
    const page = menu.find((m) => m.name === active);
    if (page?.admin && !isAdmin) return <Dashboard user={user} onTripsChanged={refreshProfile} goTo={setActive}/>;
    switch (active) {
      case "Carpooling": return <Carpooling goTo={setActive} onRequestsChanged={setPendingRequests}/>;
      case "Recommendations": return <Insights profile={profile} goTo={setActive}/>;
      case "Savings": return <Savings goTo={setActive}/>;
      case "Digital Twin": return <DigitalTwin/>;
      case "Analytics": return <Analytics/>;
      case "Incentives": return <Incentives/>;
      case "Shuttles": return <Shuttles/>;
      case "Team": return <Team me={user}/>;
      case "Settings": return <SettingsPage profile={profile} onSaved={setProfile}/>;
      default: return <Dashboard user={user} onTripsChanged={refreshProfile} goTo={setActive}/>;
    }
  }

  if (authLoading) return <div className="auth-loading" role="status">Loading your SmartCommute account...</div>;
  if (!user) return <LoginPage onLogin={setUser} initialError={authError}/>;

  const displayName = profile?.name || user.email;
  const isAdmin = user.role === "admin";
  const employeeMenu = menu.filter((m) => !m.admin);
  const adminMenu = isAdmin ? menu.filter((m) => m.admin) : [];
  const searchPages = allSearchPages.filter((m) => isAdmin || !m.admin);
  const navButton = ({ name, icon: Icon }) => (
    <button key={name} className={`nav-item ${active === name ? "active" : ""}`} onClick={() => { setActive(name); setSidebarOpen(false); }}>
      <Icon size={19}/><span>{name}</span>
      {name === "Carpooling" && pendingRequests > 0 && <span className="nav-badge">{pendingRequests}</span>}
      {active === name && <ChevronRight size={16} className="nav-arrow"/>}
    </button>
  );
  return (
    <div className="app-shell">
      {sidebarOpen && <div className="mobile-overlay" onClick={() => setSidebarOpen(false)}/>}
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand"><div className="brand-icon"><Leaf size={25}/></div><div><h2>SmartCommute</h2><span>SUSTAINABLE MOBILITY</span></div><button className="close-menu" onClick={() => setSidebarOpen(false)}><X/></button></div>
        <div className="menu-label">MY COMMUTE</div>
        <nav>{employeeMenu.map(navButton)}</nav>
        {adminMenu.length > 0 && <>
          <div className="menu-label admin-label">COMPANY ADMIN</div>
          <nav>{adminMenu.map(navButton)}</nav>
        </>}
        <div className="sidebar-bottom">
          <div className="eco-card"><Leaf size={20}/><strong>Go Green!</strong><p>Every shared ride makes a difference.</p></div>
          <div className="profile"><div className="profile-avatar">{displayName.charAt(0).toUpperCase()}</div><div><strong>{displayName}</strong><span>{isAdmin ? "Company admin" : "Employee"}{profile?.employee_id ? ` · ${profile.employee_id}` : ""}</span></div></div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setSidebarOpen(true)}><Menu/></button>
          <HeaderSearch pages={searchPages} onNavigate={(name) => { setActive(name); setSidebarOpen(false); }}/>
          <div className="top-actions">
            <button className="notification" aria-label={`${pendingRequests} carpool request(s)`} title={pendingRequests ? `${pendingRequests} carpool request(s) waiting` : "No new carpool requests"} onClick={() => setActive("Carpooling")}>
              <Bell size={19}/>{pendingRequests > 0 && <span className="notif-count">{pendingRequests}</span>}
            </button>
            <div className="top-user"><div className="profile-avatar">{displayName.charAt(0).toUpperCase()}</div><span>{displayName}</span></div>
            <button type="button" className="logout-button" onClick={handleLogout} disabled={loggingOut}><LogOut size={16}/>{loggingOut ? "Signing out..." : "Sign out"}</button>
          </div>
        </header>
        <div className="page-content">
          {authError && <p className="auth-session-error" role="alert">{authError}</p>}
          <div className="page-title"><div><h2>{active === "Recommendations" ? "Your insights" : active}</h2><p>{descriptions[active]}</p></div><BackendStatus/></div>
          {renderPage()}
          <footer>© 2026 SmartCommute · Building a greener tomorrow, one journey at a time.</footer>
        </div>
      </main>
    </div>
  );
}
