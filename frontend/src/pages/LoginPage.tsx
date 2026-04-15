import { useState } from "react";
import api from "../services/api";

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setLoading(true);
    setError("");
    try {
      await api.post("/api/auth/login", { username: username.trim(), password });
      onLogin();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "linear-gradient(135deg, #00204A 0%, #003478 50%, #004090 100%)" }}>
      <div style={{ width: 380, padding: 40, borderRadius: 16, background: "#fff", boxShadow: "0 8px 40px rgba(0,0,0,0.2)" }}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{ display: "inline-flex", alignItems: "baseline", fontWeight: 800, fontSize: 36, letterSpacing: -1 }}>
            <span style={{ color: "#003478" }}>BD</span><span style={{ color: "#F5A623" }}>O</span>
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#003478", marginTop: 4 }}>Media Studio</div>
          <p style={{ fontSize: 12, color: "#888", marginTop: 8 }}>Sign in with your trial account</p>
        </div>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 14 }}>
            <label style={{ fontSize: 12, fontWeight: 500, color: "#555", display: "block", marginBottom: 4 }}>Username</label>
            <input type="text" value={username} onChange={e => setUsername(e.target.value)} autoFocus autoComplete="username"
              style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid #ddd", fontSize: 14, outline: "none" }} />
          </div>
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 12, fontWeight: 500, color: "#555", display: "block", marginBottom: 4 }}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password"
              style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid #ddd", fontSize: 14, outline: "none" }} />
          </div>
          {error && <div style={{ padding: 10, borderRadius: 8, background: "#FEF2F2", color: "#D32029", fontSize: 12, marginBottom: 14 }}>{error}</div>}
          <button type="submit" disabled={loading || !username.trim() || !password}
            style={{ width: "100%", padding: 12, borderRadius: 8, border: "none", background: loading ? "#999" : "linear-gradient(135deg, #003478, #0052CC)", color: "#fff", fontSize: 14, fontWeight: 600, cursor: loading ? "wait" : "pointer" }}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
        <div style={{ textAlign: "center", marginTop: 20, fontSize: 10, color: "#bbb", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
          <span>Powered by</span>
          <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><rect x="0" y="0" width="6.5" height="6.5" fill="#F25022"/><rect x="7.5" y="0" width="6.5" height="6.5" fill="#7FBA00"/><rect x="0" y="7.5" width="6.5" height="6.5" fill="#00A4EF"/><rect x="7.5" y="7.5" width="6.5" height="6.5" fill="#FFB900"/></svg>
          <span>Microsoft Azure</span>
        </div>
      </div>
    </div>
  );
}
