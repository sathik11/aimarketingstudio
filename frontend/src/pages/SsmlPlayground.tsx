import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import api from "../services/api";

/* ------------------------------------------------------------------ */
/*  SSML Pretty Formatter                                              */
/* ------------------------------------------------------------------ */
function prettyFormatSsml(raw: string): string {
  // Simple XML pretty-printer for SSML
  let formatted = "";
  let indent = 0;
  const tab = "  ";
  // Normalize: remove existing whitespace between tags
  const cleaned = raw.replace(/>\s+</g, "><").trim();
  // Split by tags
  const tokens = cleaned.split(/(<[^>]+>)/g).filter(Boolean);

  for (const token of tokens) {
    if (token.startsWith("</")) {
      // Closing tag — dedent first
      indent = Math.max(0, indent - 1);
      formatted += tab.repeat(indent) + token + "\n";
    } else if (token.startsWith("<") && !token.endsWith("/>") && !token.startsWith("<?")) {
      // Opening tag
      formatted += tab.repeat(indent) + token + "\n";
      // Don't indent for self-closing or void-like tags
      if (!token.includes("</")) indent++;
    } else if (token.startsWith("<") && token.endsWith("/>")) {
      // Self-closing tag
      formatted += tab.repeat(indent) + token + "\n";
    } else {
      // Text content — trim and indent
      const text = token.trim();
      if (text) {
        formatted += tab.repeat(indent) + text + "\n";
      }
    }
  }
  return formatted.trimEnd();
}

/* ------------------------------------------------------------------ */
/*  SSML Reference Data                                                */
/* ------------------------------------------------------------------ */

const VOICES = [
  { id: "fil-PH-AngeloNeural", label: "Angelo (fil-PH, Male)", lang: "fil-PH" },
  { id: "fil-PH-BlessicaNeural", label: "Blessica (fil-PH, Female)", lang: "fil-PH" },
  { id: "en-US-Andrew:DragonHDLatestNeural", label: "Andrew DragonHD (en-US, Male)", lang: "en-US" },
  { id: "en-AU-WilliamMultilingualNeural", label: "William Multilingual (en-AU, Male)", lang: "en-AU" },
  { id: "en-US-AvaMultilingualNeural", label: "Ava Multilingual (en-US, Female)", lang: "en-US" },
];

interface TagSnippet {
  label: string;
  snippet: string;
  description: string;
  supported: "all" | "dragonhd-only" | "not-filph";
}

const SSML_TAGS: TagSnippet[] = [
  {
    label: '<break>',
    snippet: '<break time="500ms"/>',
    description: "Pause for a duration. Values: 0-20000ms. Or strength: x-weak, weak, medium, strong, x-strong.",
    supported: "all",
  },
  {
    label: '<prosody>',
    snippet: '<prosody rate="0%" pitch="default" volume="default">TEXT</prosody>',
    description: "Control rate (-50% to +100%), pitch (x-low to x-high, or ±Nst), volume (silent to x-loud, or 0-100).",
    supported: "all",
  },
  {
    label: '<emphasis>',
    snippet: '<emphasis level="moderate">TEXT</emphasis>',
    description: "Add word-level stress. Levels: reduced, none, moderate, strong. Limited voice support.",
    supported: "all",
  },
  {
    label: '<sub alias>',
    snippet: '<sub alias="REPLACEMENT">ORIGINAL</sub>',
    description: "Substitute pronunciation. e.g. <sub alias=\"B D O\">BDO</sub>. NOT supported by fil-PH voices.",
    supported: "not-filph",
  },
  {
    label: '<say-as>',
    snippet: '<say-as interpret-as="telephone">(02) 631-8000</say-as>',
    description: "Control how content is spoken: cardinal, ordinal, telephone, date, time, characters, spell-out.",
    supported: "all",
  },
  {
    label: '<lang>',
    snippet: '<lang xml:lang="fil-PH">Filipino text here</lang>',
    description: "Switch pronunciation language mid-speech. Only for Multilingual/DragonHD voices.",
    supported: "dragonhd-only",
  },
  {
    label: '<mstts:silence>',
    snippet: '<mstts:silence type="Sentenceboundary" value="200ms"/>',
    description: "Insert silence at boundaries. Types: Leading, Tailing, Sentenceboundary, Comma-exact, etc.",
    supported: "all",
  },
  {
    label: '<p> / <s>',
    snippet: '<p><s>Sentence one.</s><s>Sentence two.</s></p>',
    description: "Mark paragraphs and sentences explicitly for better pacing.",
    supported: "all",
  },
  {
    label: '<phoneme>',
    snippet: '<phoneme alphabet="ipa" ph="bɛˈniːnji">Benigni</phoneme>',
    description: "Specify exact IPA pronunciation. NOT supported by fil-PH voices.",
    supported: "not-filph",
  },
];

const FEATURE_TABLE = [
  { feature: "prosody (rate/pitch/vol)", filPH: true, dragonHD: true },
  { feature: "break", filPH: true, dragonHD: true },
  { feature: "emphasis", filPH: true, dragonHD: true },
  { feature: "say-as", filPH: true, dragonHD: true },
  { feature: "silence (mstts)", filPH: true, dragonHD: true },
  { feature: "p / s (paragraphs)", filPH: true, dragonHD: true },
  { feature: "sub alias", filPH: false, dragonHD: true },
  { feature: "phoneme", filPH: false, dragonHD: true },
  { feature: "custom lexicon", filPH: false, dragonHD: true },
  { feature: "lang (language switch)", filPH: false, dragonHD: true },
  { feature: "express-as (styles)", filPH: false, dragonHD: false },
  { feature: "viseme", filPH: false, dragonHD: true },
];

const DEFAULT_SSML = `<speak version="1.0" xml:lang="en-US"
  xmlns="http://www.w3.org/2001/10/synthesis"
  xmlns:mstts="https://www.w3.org/2001/mstts">
  <voice name="en-US-Andrew:DragonHDLatestNeural">
    <prosody rate="0%" pitch="default" volume="default">
      Let <sub alias="B D O">BDO</sub> handle your payments and collections
      <lang xml:lang="fil-PH">para maka focus ka sa business mo!</lang>
      <break time="300ms"/>
      <lang xml:lang="fil-PH">Tara na, mag-enroll na sa</lang>
      <sub alias="S M E">SME</sub> Online Banking!
    </prosody>
  </voice>
</speak>`;

/* ------------------------------------------------------------------ */
/*  Styles                                                             */
/* ------------------------------------------------------------------ */
const s = {
  card: { background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" } as React.CSSProperties,
  label: { fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 4, display: "block" } as React.CSSProperties,
  input: { width: "100%", padding: "7px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", fontSize: 13, color: "var(--text)", outline: "none", fontFamily: "inherit" } as React.CSSProperties,
  btnPrimary: { padding: "10px 24px", borderRadius: "var(--radius-sm)", border: "none", background: "var(--bdo-blue)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" } as React.CSSProperties,
  btnOutline: { padding: "6px 12px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", fontSize: 12, cursor: "pointer", fontFamily: "inherit" } as React.CSSProperties,
  mono: { fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace", fontSize: 13, lineHeight: 1.6 } as React.CSSProperties,
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function SsmlPlayground() {
  const location = useLocation();
  const [ssml, setSsml] = useState(DEFAULT_SSML);
  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  // Load SSML from navigation state (from "Edit in Playground" button)
  useEffect(() => {
    const state = location.state as { ssml?: string } | null;
    if (state?.ssml) {
      setSsml(prettyFormatSsml(state.ssml));
    }
  }, [location.state]);

  const handleSynthesize = async () => {
    if (!ssml.trim()) return;
    setLoading(true);
    setError("");
    setAudioUrl(null);
    try {
      const { data } = await api.post("/api/generate/ssml-playground", { ssml });
      setAudioUrl(data.audio_url || null);
    } catch (err: unknown) {
      if (err && typeof err === "object" && "response" in err) {
        const axErr = err as { response?: { data?: { error?: string } } };
        setError(axErr.response?.data?.error || "Synthesis failed");
      } else {
        setError("Synthesis failed");
      }
    } finally {
      setLoading(false);
    }
  };

  const insertSnippet = (snippet: string) => {
    const textarea = document.getElementById("ssml-editor") as HTMLTextAreaElement;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const before = ssml.slice(0, start);
    const after = ssml.slice(end);
    const selected = ssml.slice(start, end);
    const toInsert = snippet.includes("TEXT") ? snippet.replace("TEXT", selected || "your text") : snippet;
    setSsml(before + toInsert + after);
    setTimeout(() => {
      textarea.focus();
      textarea.selectionStart = start + toInsert.length;
      textarea.selectionEnd = start + toInsert.length;
    }, 0);
  };

  const formatSsml = () => {
    setSsml(prettyFormatSsml(ssml));
  };

  const setVoice = (voiceId: string) => {
    const voice = VOICES.find(v => v.id === voiceId);
    if (!voice) return;
    setSsml(prev => {
      let updated = prev.replace(/xml:lang="[^"]*"/, `xml:lang="${voice.lang}"`);
      updated = updated.replace(/name="[^"]*"/, `name="${voice.id}"`);
      return updated;
    });
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 24px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>
          SSML Playground
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Edit SSML directly and test with Azure Speech. Use the quick-insert buttons to add elements.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 20 }}>
        {/* Left — Editor */}
        <div>
          {/* Voice quick-select */}
          <div style={{ marginBottom: 12 }}>
            <span style={s.label}>Quick Voice Select</span>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {VOICES.map(v => (
                <button key={v.id} onClick={() => setVoice(v.id)}
                  style={{ ...s.btnOutline, fontSize: 11, padding: "4px 10px" }}>
                  {v.label}
                </button>
              ))}
            </div>
          </div>

          {/* Quick-insert tags */}
          <div style={{ marginBottom: 12 }}>
            <span style={s.label}>Quick Insert</span>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {SSML_TAGS.map(t => (
                <button
                  key={t.label}
                  onClick={() => insertSnippet(t.snippet)}
                  title={`${t.description}\n${t.supported === "not-filph" ? "⚠ Not supported by fil-PH voices" : t.supported === "dragonhd-only" ? "⚠ DragonHD/Multilingual only" : "✓ All voices"}`}
                  style={{
                    ...s.btnOutline,
                    fontSize: 11,
                    padding: "3px 8px",
                    color: t.supported === "not-filph" ? "var(--error)" : t.supported === "dragonhd-only" ? "var(--accent)" : "var(--text-secondary)",
                    borderColor: t.supported === "not-filph" ? "#fcc" : t.supported === "dragonhd-only" ? "#cce" : "var(--border)",
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
              <span style={{ color: "var(--text-secondary)" }}>■</span> All voices
              <span style={{ color: "var(--accent)", marginLeft: 10 }}>■</span> DragonHD/Multilingual only
              <span style={{ color: "var(--error)", marginLeft: 10 }}>■</span> Not supported by fil-PH
            </div>
          </div>

          {/* SSML Editor */}
          <div style={{ ...s.card, padding: 0, overflow: "hidden", marginBottom: 12 }}>
            <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border-light)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>SSML Editor</span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{ssml.length} chars</span>
            </div>
            <textarea
              id="ssml-editor"
              value={ssml}
              onChange={e => setSsml(e.target.value)}
              rows={18}
              spellCheck={false}
              style={{
                ...s.input, ...s.mono,
                border: "none",
                borderRadius: 0,
                padding: "12px 16px",
                resize: "vertical",
                minHeight: 300,
                background: "#1e1e2e",
                color: "#cdd6f4",
              }}
            />
          </div>

          {/* Actions */}
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button
              onClick={handleSynthesize}
              disabled={loading || !ssml.trim()}
              style={{
                ...s.btnPrimary,
                opacity: loading || !ssml.trim() ? 0.5 : 1,
                cursor: loading ? "wait" : "pointer",
              }}
            >
              {loading ? "Synthesizing…" : "Synthesize SSML"}
            </button>
            <button onClick={() => setSsml(DEFAULT_SSML)} style={s.btnOutline}>
              Reset to Example
            </button>
            <button onClick={formatSsml} style={s.btnOutline}>
              Format SSML
            </button>
          </div>

          {/* Error */}
          {error && (
            <div style={{ marginTop: 12, padding: 10, borderRadius: "var(--radius-sm)", background: "#FEF2F2", color: "var(--error)", fontSize: 12 }}>
              {error}
            </div>
          )}

          {/* Audio Result */}
          {audioUrl && (
            <div style={{ marginTop: 16, ...s.card, padding: 16 }}>
              <span style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, display: "block" }}>Result</span>
              <audio controls src={audioUrl} style={{ width: "100%", height: 40, marginBottom: 8 }} />
              <a href={audioUrl} download style={{ fontSize: 12, color: "var(--accent)", textDecoration: "none" }}>
                ↓ Download WAV
              </a>
            </div>
          )}
        </div>

        {/* Right — Reference Panel */}
        <div>
          {/* Feature Compatibility Table */}
          <div style={{ ...s.card, padding: 14, marginBottom: 16 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 10px" }}>Feature Support</h3>
            <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th style={{ textAlign: "left", padding: "4px 0", color: "var(--text-muted)" }}>Feature</th>
                  <th style={{ textAlign: "center", padding: "4px 0", color: "var(--text-muted)" }}>fil-PH</th>
                  <th style={{ textAlign: "center", padding: "4px 0", color: "var(--text-muted)" }}>DragonHD</th>
                </tr>
              </thead>
              <tbody>
                {FEATURE_TABLE.map(f => (
                  <tr key={f.feature} style={{ borderBottom: "1px solid var(--border-light)" }}>
                    <td style={{ padding: "4px 0", color: "var(--text-secondary)" }}>{f.feature}</td>
                    <td style={{ textAlign: "center", padding: "4px 0" }}>{f.filPH ? "✓" : "✗"}</td>
                    <td style={{ textAlign: "center", padding: "4px 0" }}>{f.dragonHD ? "✓" : "✗"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* SSML Quick Reference */}
          <div style={{ ...s.card, padding: 14 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 10px" }}>SSML Quick Reference</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {SSML_TAGS.map(t => (
                <div key={t.label}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <code style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)" }}>{t.label}</code>
                    <span style={{
                      fontSize: 10, padding: "1px 6px", borderRadius: 3,
                      background: t.supported === "all" ? "#e8f5e9" : t.supported === "dragonhd-only" ? "var(--accent-light)" : "#fce4ec",
                      color: t.supported === "all" ? "var(--success)" : t.supported === "dragonhd-only" ? "var(--accent)" : "var(--error)",
                    }}>
                      {t.supported === "all" ? "All" : t.supported === "dragonhd-only" ? "DragonHD" : "Not fil-PH"}
                    </span>
                  </div>
                  <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "2px 0 0", lineHeight: 1.5 }}>
                    {t.description}
                  </p>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--border-light)" }}>
              <a href="https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup"
                target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 11, color: "var(--accent)", textDecoration: "none" }}>
                Full SSML Documentation →
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
