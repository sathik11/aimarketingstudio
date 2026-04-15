import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchScripts,
  deleteScript,
  type Script,
} from "../services/api";

export default function ScriptsPage() {
  const [scripts, setScripts] = useState<Script[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const loadScripts = () => {
    setLoading(true);
    fetchScripts()
      .then(setScripts)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadScripts();
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this script?")) return;
    try {
      await deleteScript(id);
      loadScripts();
    } catch {
      alert("Failed to delete script");
    }
  };

  const handleLoad = (script: Script) => {
    navigate("/generate", { state: { text: script.text, language: script.language, scriptId: script.id } });
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "28px 24px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>Saved Scripts</h1>
      <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
        Load a saved script to quickly generate audio with different variants.
      </p>

      {loading && <p style={{ color: "var(--text-muted)" }}>Loading...</p>}

      {!loading && scripts.length === 0 && (
        <div style={{
          padding: 40, textAlign: "center", borderRadius: "var(--radius)",
          background: "var(--surface)", border: "1px dashed var(--border)", color: "var(--text-muted)", fontSize: 13,
        }}>
          No scripts saved yet. Generate audio first, then save your scripts.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {scripts.map((s) => (
          <div
            key={s.id}
            style={{
              padding: 16,
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              background: "var(--surface)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{s.title}</h3>
                <p style={{ color: "var(--text-muted)", fontSize: 12, margin: "4px 0 0" }}>
                  {s.language} · Updated {new Date(s.updated_at).toLocaleDateString()}
                </p>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={() => handleLoad(s)}
                  style={{
                    padding: "6px 14px", borderRadius: "var(--radius-sm)", fontSize: 12, fontWeight: 500,
                    border: "1px solid var(--accent)", background: "var(--accent-light)", color: "var(--accent)", cursor: "pointer",
                  }}
                >
                  Load & Generate
                </button>
                <button
                  onClick={() => handleDelete(s.id)}
                  style={{
                    padding: "6px 12px", borderRadius: "var(--radius-sm)", fontSize: 12,
                    border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-muted)", cursor: "pointer",
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
            <pre style={{ margin: "10px 0 0", whiteSpace: "pre-wrap", fontSize: 12, color: "var(--text-secondary)", maxHeight: 80, overflow: "hidden", lineHeight: 1.6 }}>
              {s.text}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}
