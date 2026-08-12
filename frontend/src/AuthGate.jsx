import { useCallback, useEffect, useState } from "react";
import { LockKeyhole, LogIn, ShieldCheck, UserRound, X } from "lucide-react";
import "./auth.css";

const jsonHeaders = { "Content-Type": "application/json" };

async function jsonResult(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Permintaan gagal diproses");
  return data;
}

function AuthPanel({ admin, mode, setMode, onAuthenticated, onGuest, onClose }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [verifyEmail, setVerifyEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const effectiveMode = admin ? "admin" : mode;

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (effectiveMode === "admin") {
        const result = await jsonResult(await fetch("/api/admin/login", {
          method: "POST",
          headers: jsonHeaders,
          credentials: "same-origin",
          body: JSON.stringify({ password }),
        }));
        onAuthenticated(result);
        return;
      }

      if (effectiveMode === "register") {
        const result = await jsonResult(await fetch("/api/auth/register", {
          method: "POST",
          headers: jsonHeaders,
          credentials: "same-origin",
          body: JSON.stringify({ email, password }),
        }));
        setVerifyEmail(result.email || email);
        setMode("verify");
        setMessage("Kode 6 digit sudah dikirim ke email UII. Berlaku 10 menit.");
        return;
      }

      if (effectiveMode === "verify") {
        const result = await jsonResult(await fetch("/api/auth/register/verify", {
          method: "POST",
          headers: jsonHeaders,
          credentials: "same-origin",
          body: JSON.stringify({ email: verifyEmail, code }),
        }));
        onAuthenticated(result);
        return;
      }

      const result = await jsonResult(await fetch("/api/auth/login", {
        method: "POST",
        headers: jsonHeaders,
        credentials: "same-origin",
        body: JSON.stringify({ email, password }),
      }));
      onAuthenticated(result);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-backdrop" role="presentation">
      <section className="auth-card" role="dialog" aria-modal="true" aria-label={admin ? "Login laboran" : "Login LabHub"}>
        {onClose && <button className="auth-close" type="button" onClick={onClose} aria-label="Tutup login"><X size={18} /></button>}
        <div className="auth-mark">{admin ? <ShieldCheck size={26} /> : <UserRound size={26} />}</div>
        <p className="auth-eyebrow">LAB ROBOTIKA & INOVASI</p>
        <h1>{admin ? "Login Laboran" : effectiveMode === "register" ? "Daftar akun UII" : effectiveMode === "verify" ? "Verifikasi email" : "Masuk ke LabHub"}</h1>
        <p className="auth-description">
          {admin
            ? "Akses pengelolaan inventory, approval, dan operasional laboratorium."
            : effectiveMode === "verify"
              ? `Masukkan kode yang dikirim ke ${verifyEmail}.`
              : "Gunakan email resmi UII untuk mengajukan layanan laboratorium."}
        </p>

        <form className="auth-form" onSubmit={submit}>
          {!admin && effectiveMode !== "verify" && (
            <label>Email UII<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="nama@uii.ac.id" /></label>
          )}
          {effectiveMode !== "verify" && (
            <label>Password<input type="password" autoComplete={effectiveMode === "register" ? "new-password" : "current-password"} minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          )}
          {effectiveMode === "verify" && (
            <label>Kode verifikasi<input className="auth-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" /></label>
          )}
          {message && <div className="auth-message" role="status">{message}</div>}
          <button className="auth-primary" disabled={busy} type="submit"><LogIn size={17} />{busy ? "Memproses…" : effectiveMode === "register" ? "Kirim kode verifikasi" : effectiveMode === "verify" ? "Verifikasi & masuk" : "Masuk"}</button>
        </form>

        {!admin && effectiveMode !== "verify" && (
          <div className="auth-switch">
            {effectiveMode === "register" ? (
              <button type="button" onClick={() => { setMode("login"); setMessage(""); }}>Sudah punya akun? Masuk</button>
            ) : (
              <button type="button" onClick={() => { setMode("register"); setMessage(""); }}>Belum punya akun? Daftar</button>
            )}
          </div>
        )}

        {!admin && effectiveMode === "verify" && (
          <div className="auth-switch"><button type="button" onClick={() => { setMode("register"); setCode(""); setMessage(""); }}>Kirim ulang / ganti email</button></div>
        )}

        {!admin && onGuest && effectiveMode !== "verify" && (
          <button className="auth-guest" type="button" onClick={onGuest}>Lanjut sebagai tamu</button>
        )}
      </section>
    </div>
  );
}

export default function AuthGate({ children }) {
  const [adminPath, setAdminPath] = useState(() => window.location.pathname.startsWith("/admin"));
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [mode, setMode] = useState("login");
  const [showLogin, setShowLogin] = useState(false);

  useEffect(() => {
    let lastPath = window.location.pathname;
    const timer = window.setInterval(() => {
      if (window.location.pathname !== lastPath) {
        lastPath = window.location.pathname;
        setAdminPath(lastPath.startsWith("/admin"));
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, []);

  const refreshSession = useCallback(async () => {
    setLoading(true);
    const endpoint = adminPath ? "/api/admin/session" : "/api/auth/session";
    try {
      const response = await fetch(endpoint, { cache: "no-store", credentials: "same-origin" });
      if (!response.ok) throw new Error();
      setSession(await response.json());
      setShowLogin(false);
    } catch {
      setSession(null);
      setShowLogin(false);
    } finally {
      setLoading(false);
    }
  }, [adminPath]);

  useEffect(() => { refreshSession(); }, [refreshSession]);

  const guest = async () => {
    try {
      const result = await jsonResult(await fetch("/api/auth/guest", { method: "POST", credentials: "same-origin" }));
      setSession(result);
      setShowLogin(false);
    } catch {
      setSession(null);
    }
  };

  const logout = async () => {
    await fetch(adminPath ? "/api/admin/logout" : "/api/auth/logout", { method: "POST", credentials: "same-origin" });
    setSession(null);
    setShowLogin(false);
    setMode("login");
  };

  if (loading) return <div className="auth-loading"><span /><p>Memeriksa sesi…</p></div>;

  if (!session) {
    return <AuthPanel admin={adminPath} mode={mode} setMode={setMode} onAuthenticated={setSession} onGuest={adminPath ? null : guest} />;
  }

  return (
    <>
      {children}
      <div className="auth-session-chip">
        <span><LockKeyhole size={14} />{adminPath ? "Laboran" : session.guest ? "Tamu" : session.email}</span>
        {!adminPath && session.guest && <button type="button" onClick={() => { setMode("login"); setShowLogin(true); }}>Login UII</button>}
        <button type="button" onClick={logout}>Keluar</button>
      </div>
      {showLogin && <AuthPanel admin={false} mode={mode} setMode={setMode} onAuthenticated={(result) => { setSession(result); setShowLogin(false); }} onClose={() => setShowLogin(false)} />}
    </>
  );
}
