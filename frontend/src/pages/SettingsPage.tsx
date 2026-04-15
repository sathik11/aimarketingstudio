import { useState, useEffect } from "react";
import api from "../services/api";

interface PromptInfo {
  value: string;
  description: string;
  method: string;
}

const s = {
  card: { background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" } as React.CSSProperties,
  label: { fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 4, display: "block" } as React.CSSProperties,
  input: { width: "100%", padding: "7px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", fontSize: 13, color: "var(--text)", outline: "none", fontFamily: "inherit" } as React.CSSProperties,
  btnPrimary: { padding: "10px 24px", borderRadius: "var(--radius-sm)", border: "none", background: "var(--bdo-blue)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" } as React.CSSProperties,
  btnOutline: { padding: "6px 12px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", fontSize: 12, cursor: "pointer", fontFamily: "inherit" } as React.CSSProperties,
};

const METHOD_COLORS: Record<string, string> = {
  "GPT + SSML": "#5B2D90",
  "GPT Audio": "#0D7C3D",
  "GPT Realtime": "#C4314B",
};

export default function SettingsPage() {
  const [prompts, setPrompts] = useState<Record<string, PromptInfo>>({});
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    api.get("/api/settings/prompts").then(({ data }) => {
      setPrompts(data.prompts);
      const init: Record<string, string> = {};
      for (const [k, v] of Object.entries(data.prompts as Record<string, PromptInfo>)) {
        init[k] = v.value;
      }
      setEdited(init);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const hasChanges = Object.keys(edited).some(k => edited[k] !== prompts[k]?.value);

  const handleSave = async () => {
    setSaving(true);
    setStatus("");
    const changes: Record<string, string> = {};
    for (const k of Object.keys(edited)) {
      if (edited[k] !== prompts[k]?.value) {
        changes[k] = edited[k];
      }
    }
    try {
      const { data } = await api.put("/api/settings/prompts", { prompts: changes });
      setStatus(`Saved ${data.updated.length} prompt(s). Changes take effect on next generation.`);
      // Update local state
      setPrompts(prev => {
        const next = { ...prev };
        for (const k of data.updated) {
          if (next[k]) next[k] = { ...next[k], value: edited[k] };
        }
        return next;
      });
    } catch {
      setStatus("Failed to save.");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = (key: string) => {
    setEdited(prev => ({ ...prev, [key]: prompts[key]?.value || "" }));
  };

  // Group by method
  const grouped: Record<string, { key: string; info: PromptInfo }[]> = {};
  for (const [k, info] of Object.entries(prompts)) {
    const method = info.method || "Other";
    if (!grouped[method]) grouped[method] = [];
    grouped[method].push({ key: k, info });
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "28px 24px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>
          Prompt Settings
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Edit the system prompts used by each TTS method. Changes apply to the current session and reset on restart.
        </p>
      </div>

      {loading && <p style={{ color: "var(--text-muted)" }}>Loading prompts...</p>}

      {!loading && Object.entries(grouped).map(([method, items]) => (
        <div key={method} style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{
              display: "inline-block", padding: "2px 10px", borderRadius: 4,
              fontSize: 12, fontWeight: 600, letterSpacing: 0.3,
              background: (METHOD_COLORS[method] || "#666") + "14",
              color: METHOD_COLORS[method] || "#666",
            }}>
              {method}
            </span>
          </div>

          {items.map(({ key, info }) => {
            const isChanged = edited[key] !== info.value;
            return (
              <div key={key} style={{ ...s.card, padding: 16, marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                  <div>
                    <code style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)" }}>{key}</code>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "2px 0 0" }}>{info.description}</p>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    {isChanged && (
                      <button onClick={() => handleReset(key)} style={{ ...s.btnOutline, fontSize: 11, padding: "3px 10px" }}>
                        Reset
                      </button>
                    )}
                    {isChanged && (
                      <span style={{ fontSize: 10, padding: "3px 8px", borderRadius: 3, background: "#FFF3E0", color: "#E65100", fontWeight: 500 }}>
                        Modified
                      </span>
                    )}
                  </div>
                </div>
                <textarea
                  value={edited[key] || ""}
                  onChange={e => setEdited(prev => ({ ...prev, [key]: e.target.value }))}
                  rows={6}
                  style={{
                    ...s.input,
                    fontFamily: "'Cascadia Code', 'Fira Code', monospace",
                    fontSize: 12,
                    lineHeight: 1.6,
                    resize: "vertical",
                    minHeight: 100,
                    borderColor: isChanged ? "#E65100" : "var(--border)",
                  }}
                />
              </div>
            );
          })}
        </div>
      ))}

      {!loading && (
        <div style={{ display: "flex", gap: 12, alignItems: "center", position: "sticky", bottom: 0, padding: "16px 0", background: "var(--bg)" }}>
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges}
            style={{ ...s.btnPrimary, opacity: saving || !hasChanges ? 0.5 : 1 }}
          >
            {saving ? "Saving…" : "Save All Changes"}
          </button>
          {status && (
            <span style={{ fontSize: 12, color: status.includes("Failed") ? "var(--error)" : "var(--success)" }}>
              {status}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
