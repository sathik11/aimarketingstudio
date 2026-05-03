import { Link, useLocation } from "react-router-dom";

interface UserQuotas {
  name: string;
  iterations_remaining: number;
  max_iterations: number;
  videos_remaining?: number;
  max_videos?: number;
  images_remaining?: number;
  max_images?: number;
}

export default function NavBar({ user, onLogout }: { user: UserQuotas; onLogout: () => void }) {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path;

  const voiceLeft = user.iterations_remaining;
  const videoLeft = user.videos_remaining ?? 0;
  const videoMax = user.max_videos ?? 5;
  const imageLeft = user.images_remaining ?? 0;
  const imageMax = user.max_images ?? 20;

  return (
    <nav style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 28px", height: 54,
      background: "linear-gradient(135deg, #00204A 0%, #003478 50%, #004090 100%)",
      boxShadow: "0 2px 12px rgba(0,20,60,0.3)",
    }}>
      {/* Left: BDO Logo + Title */}
      <Link to="/generate" style={{ display: "flex", alignItems: "center", gap: 14, textDecoration: "none" }}>
        {/* BDO Logo — navy bg with white BD and gold O */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 0, fontFamily: "'Inter', Arial, sans-serif", fontWeight: 800, fontSize: 26, letterSpacing: -1, lineHeight: 1 }}>
          <span style={{ color: "#fff" }}>BD</span>
          <span style={{ color: "#F5A623" }}>O</span>
        </div>
        <div style={{ height: 22, width: 1, background: "rgba(255,255,255,0.2)" }} />
        <span style={{ fontWeight: 600, fontSize: 15, color: "#fff", letterSpacing: -0.2 }}>
          Media Studio
        </span>
      </Link>

      {/* Center: Nav Links */}
      <div style={{ display: "flex", gap: 2 }}>
        {[
          { path: "/generate", label: "Voice" },
          { path: "/video", label: "Video" },
          { path: "/assets", label: "Assets" },
          { path: "/ssml", label: "SSML" },
          { path: "/settings", label: "Settings" },
        ].map(({ path, label }) => (
          <Link
            key={path}
            to={path}
            style={{
              padding: "7px 18px",
              textDecoration: "none",
              fontSize: 13,
              fontWeight: isActive(path) ? 600 : 400,
              color: isActive(path) ? "#fff" : "rgba(255,255,255,0.7)",
              background: isActive(path) ? "rgba(245,166,35,0.2)" : "transparent",
              borderBottom: isActive(path) ? "2px solid #F5A623" : "2px solid transparent",
              borderRadius: "4px 4px 0 0",
              transition: "all 0.15s ease",
            }}
          >
            {label}
          </Link>
        ))}
      </div>

      {/* Right: User info + quotas */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ display: "flex", gap: 6 }}>
          <QuotaBadge label="Voice" remaining={voiceLeft} max={user.max_iterations} />
          <QuotaBadge label="Video" remaining={videoLeft} max={videoMax} />
          <QuotaBadge label="Image" remaining={imageLeft} max={imageMax} />
        </div>
        <span style={{ fontSize: 12, color: "rgba(255,255,255,0.7)" }}>{user.name}</span>
        <button onClick={onLogout} style={{
          padding: "4px 12px", borderRadius: 4, border: "1px solid rgba(255,255,255,0.3)",
          background: "transparent", color: "rgba(255,255,255,0.7)", fontSize: 11, cursor: "pointer",
        }}>Logout</button>
      </div>
    </nav>
  );
}

function QuotaBadge({ label, remaining, max }: { label: string; remaining: number; max: number }) {
  const bg = remaining > Math.ceil(max * 0.2)
    ? "rgba(255,255,255,0.15)"
    : remaining > 0
      ? "rgba(245,166,35,0.3)"
      : "rgba(220,50,50,0.3)";
  return (
    <div style={{
      padding: "3px 8px", borderRadius: 12, background: bg,
      fontSize: 10, fontWeight: 600, color: "#fff", whiteSpace: "nowrap",
    }}>
      {label}: {remaining}/{max}
    </div>
  );
}
