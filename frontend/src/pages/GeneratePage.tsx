import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchVoices,
  generateAudio,
  createScript,
  fetchScripts,
  type VoiceInfo,
  type GenerateResponse,
  type Script,
} from "../services/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Variant {
  id: string;
  method: string;
  voice: string;
  rate: string;
  pitch: string;
  volume: string;
  language: string;
  format: string;
  translate: boolean;
  systemPrompt: string;
  instructions: string;
  temperature: number;
  maxOutputTokens: number;
}

interface ResultItem {
  variantId: string;
  variant: Variant;
  response: GenerateResponse | null;
  error: string;
  loading: boolean;
}

const METHODS = [
  { id: "azure-tts",    label: "Azure Speech",  tag: "SSML",     color: "#0078D4", gradient: "linear-gradient(135deg, #0078D4, #00BCF2)" },
  { id: "gpt-ssml",     label: "GPT + SSML",    tag: "AI+SSML",  color: "#5B2D90", gradient: "linear-gradient(135deg, #5B2D90, #8661C5)" },
  { id: "gpt-audio",    label: "GPT Audio",     tag: "AI Audio", color: "#0D7C3D", gradient: "linear-gradient(135deg, #0D7C3D, #34B76F)" },
  { id: "gpt-realtime", label: "GPT Realtime",  tag: "Realtime", color: "#C4314B", gradient: "linear-gradient(135deg, #C4314B, #E8627C)" },
  { id: "mai-voice-1",  label: "MAI Voice 1",   tag: "MAI",      color: "#0E7490", gradient: "linear-gradient(135deg, #0E7490, #06B6D4)" },
];

const METHOD_MAP = Object.fromEntries(METHODS.map(m => [m.id, m]));

const DEFAULT_PRONUNCIATION: Record<string, string> = {
  BDO: "B D O", SME: "S M E", ATM: "A T M", OTP: "O T P", PIN: "P I N",
};

let _variantCounter = 0;
function nextId() { return `v-${++_variantCounter}-${Date.now()}`; }

function defaultVariant(method = "azure-tts", voice = ""): Variant {
  return {
    id: nextId(), method, voice,
    rate: "0%", pitch: "default", volume: "default",
    language: "fil-PH", format: "wav", translate: true,
    systemPrompt: "", instructions: "",
    temperature: 0.8, maxOutputTokens: 4096,
  };
}

/* ------------------------------------------------------------------ */
/*  Shared Styles                                                      */
/* ------------------------------------------------------------------ */

const card: React.CSSProperties = {
  background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)",
  boxShadow: "var(--shadow-sm)",
};
const label: React.CSSProperties = {
  fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 4, display: "block",
};
const input: React.CSSProperties = {
  width: "100%", padding: "7px 10px", borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)", fontSize: 13, color: "var(--text)",
  outline: "none", transition: "border 0.15s",
};
const btnPrimary: React.CSSProperties = {
  padding: "10px 24px", borderRadius: "var(--radius-sm)", border: "none",
  background: "var(--bdo-blue)", color: "#fff", fontSize: 13, fontWeight: 600,
  cursor: "pointer", transition: "background 0.15s",
};
const btnOutline: React.CSSProperties = {
  ...btnPrimary, background: "transparent", border: "1px solid var(--border)",
  color: "var(--text-secondary)",
};
const tag = (color: string): React.CSSProperties => ({
  display: "inline-block", padding: "2px 8px", borderRadius: 4,
  fontSize: 11, fontWeight: 600, letterSpacing: 0.3,
  background: color + "14", color, whiteSpace: "nowrap",
});

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function GeneratePage({ onGenerated }: { onGenerated?: () => void }) {
  // Shared state
  const [text, setText] = useState("");
  const [pronunciation, setPronunciation] = useState(DEFAULT_PRONUNCIATION);
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");

  // Voices from API
  const [voices, setVoices] = useState<Record<string, VoiceInfo[]>>({});
  const [formats, setFormats] = useState<Record<string, string[]>>({});

  // Variants & results
  const [variants, setVariants] = useState<Variant[]>([defaultVariant()]);
  const [results, setResults] = useState<ResultItem[]>([]);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    fetchVoices().then((d) => { setVoices(d.voices); setFormats(d.formats); }).catch(() => {});
  }, []);

  // Auto-assign default voice when voices load
  useEffect(() => {
    if (Object.keys(voices).length === 0) return;
    setVariants(prev => prev.map(v => {
      if (v.voice) return v;
      const list = voices[v.method] || [];
      return { ...v, voice: list[0]?.id || "" };
    }));
  }, [voices]);

  const updateVariant = (id: string, patch: Partial<Variant>) => {
    setVariants(prev => prev.map(v => v.id === id ? { ...v, ...patch } : v));
  };

  const removeVariant = (id: string) => {
    setVariants(prev => prev.length > 1 ? prev.filter(v => v.id !== id) : prev);
  };

  const addVariant = (method = "azure-tts") => {
    const list = voices[method] || [];
    setVariants(prev => [...prev, defaultVariant(method, list[0]?.id || "")]);
  };

  const duplicateVariant = (v: Variant) => {
    setVariants(prev => [...prev, { ...v, id: nextId() }]);
  };

  /* ---- generate all variants ---- */
  const handleGenerateAll = useCallback(async () => {
    if (!text.trim() || variants.length === 0) return;
    setGenerating(true);

    const items: ResultItem[] = variants.map(v => ({
      variantId: v.id, variant: { ...v }, response: null, error: "", loading: true,
    }));
    setResults(items);

    const promises = variants.map(async (v, idx) => {
      const params: Record<string, unknown> = { text: text.trim(), voice: v.voice, format: v.format };
      if (v.method === "azure-tts" || v.method === "gpt-ssml") {
        params.rate = v.rate; params.pitch = v.pitch; params.volume = v.volume;
        params.language = v.language; params.pronunciation = pronunciation;
      }
      if (v.method === "gpt-ssml") params.translate = v.translate;
      if (v.method === "gpt-audio") params.system_prompt = v.systemPrompt || undefined;
      if (v.method === "gpt-realtime") {
        params.instructions = v.instructions || undefined;
        params.temperature = v.temperature;
        params.max_output_tokens = v.maxOutputTokens;
      }
      if (v.method === "mai-voice-1") {
        params.pronunciation = pronunciation;
      }

      try {
        const res = await generateAudio(v.method, params as never);
        setResults(prev => prev.map((r, i) => i === idx ? { ...r, response: res, loading: false } : r));
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed";
        setResults(prev => prev.map((r, i) => i === idx ? { ...r, error: msg, loading: false } : r));
      }
    });
    await Promise.allSettled(promises);
    onGenerated?.();
    setGenerating(false);
  }, [text, variants, pronunciation, onGenerated]);

  const handleSaveScript = async () => {
    if (!text.trim()) return;
    const title = prompt("Enter script title:");
    if (!title) return;
    try { await createScript(title, text); alert("Script saved!"); }
    catch { alert("Failed to save script"); }
  };

  // Scripts popover
  const [showScripts, setShowScripts] = useState(false);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [loadingScripts, setLoadingScripts] = useState(false);
  const scriptsRef = useRef<HTMLDivElement>(null);

  const loadScripts = () => {
    setLoadingScripts(true);
    fetchScripts().then(setScripts).catch(() => {}).finally(() => setLoadingScripts(false));
  };

  // Close popover on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (scriptsRef.current && !scriptsRef.current.contains(e.target as Node)) setShowScripts(false);
    };
    if (showScripts) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showScripts]);

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 24px" }}>
      {/* --- Header --- */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>
          Voice Generation
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Configure multiple variants side-by-side, generate all at once, and compare the results.
        </p>
      </div>

      {/* --- Script Input --- */}
      <div style={{ ...card, padding: 20, marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Script Text</span>
          <div style={{ display: "flex", gap: 8, alignItems: "center", position: "relative" }} ref={scriptsRef}>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {wordCount} words · {text.length} chars
            </span>
            <button onClick={() => { setShowScripts(!showScripts); if (!showScripts) loadScripts(); }}
              style={{
                padding: "7px 18px", fontSize: 12, fontWeight: 600,
                display: "flex", alignItems: "center", gap: 6,
                border: "none", borderRadius: 20,
                background: "linear-gradient(135deg, #F5A623, #F7C948)",
                color: "#003478", cursor: "pointer",
                boxShadow: "0 2px 8px rgba(245,166,35,0.3)",
                transition: "transform 0.15s",
              }}
              onMouseEnter={e => (e.currentTarget.style.transform = "translateY(-1px)")}
              onMouseLeave={e => (e.currentTarget.style.transform = "translateY(0)")}
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 1l1.5 3.5L13 6l-3.5 1.5L8 11 6.5 7.5 3 6l3.5-1.5z"/>
                <path d="M12 10l.8 1.8L15 13l-2.2.8L12 16l-.8-2.2L9 13l2.2-.8z" opacity=".6"/>
              </svg>
              Load Script
            </button>
            <button onClick={handleSaveScript} disabled={!text.trim()}
              style={{
                padding: "7px 16px", fontSize: 12, fontWeight: 500,
                border: "1px solid var(--border)", borderRadius: 20,
                background: "var(--surface)", color: "var(--text-secondary)",
                cursor: text.trim() ? "pointer" : "default",
                opacity: text.trim() ? 1 : 0.4,
                transition: "all 0.15s",
              }}>
              Save
            </button>

            {/* Scripts Popover */}
            {showScripts && (
              <div style={{
                position: "absolute", top: "100%", right: 0, marginTop: 6,
                width: 380, maxHeight: 340, overflowY: "auto",
                background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)",
                boxShadow: "var(--shadow-lg)", zIndex: 100,
              }}>
                <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-light)", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                  Saved Scripts
                </div>
                {loadingScripts && <div style={{ padding: 14, fontSize: 12, color: "var(--text-muted)" }}>Loading...</div>}
                {!loadingScripts && scripts.length === 0 && (
                  <div style={{ padding: 14, fontSize: 12, color: "var(--text-muted)" }}>No saved scripts yet.</div>
                )}
                {scripts.map(s => (
                  <div
                    key={s.id}
                    onClick={() => { setText(s.text); setShowScripts(false); }}
                    style={{
                      padding: "10px 14px", cursor: "pointer", borderBottom: "1px solid var(--border-light)",
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = "var(--bg)")}
                    onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                  >
                    <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 2 }}>{s.title}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.text}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <textarea
          value={text} onChange={e => setText(e.target.value)}
          placeholder='e.g. "Nasubukan niyo na bang mag check ng account balance niyo habang nag-aalmusal?"'
          rows={4}
          style={{ ...input, resize: "vertical", lineHeight: 1.6, fontSize: 14 }}
        />
        {/* Pronunciation */}
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
            Pronunciation Overrides ({Object.keys(pronunciation).length})
          </summary>
          <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
            {Object.entries(pronunciation).map(([k, v]) => (
              <span key={k} style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                padding: "3px 10px", borderRadius: 20, background: "var(--accent-light)",
                fontSize: 12, color: "var(--accent)",
              }}>
                <strong>{k}</strong> → {v}
                <button onClick={() => setPronunciation(p => { const n = { ...p }; delete n[k]; return n; })}
                  style={{ border: "none", background: "none", cursor: "pointer", color: "var(--accent)", fontWeight: 700, fontSize: 14, lineHeight: 1 }}>×</button>
              </span>
            ))}
            <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
              <input placeholder="Term" value={newKey} onChange={e => setNewKey(e.target.value)}
                style={{ ...input, width: 80, padding: "3px 8px", fontSize: 12 }} />
              <input placeholder="Says as" value={newVal} onChange={e => setNewVal(e.target.value)}
                style={{ ...input, width: 120, padding: "3px 8px", fontSize: 12 }} />
              <button onClick={() => { if (newKey.trim() && newVal.trim()) { setPronunciation(p => ({ ...p, [newKey.trim()]: newVal.trim() })); setNewKey(""); setNewVal(""); }}}
                style={{ ...btnOutline, padding: "3px 10px", fontSize: 12 }}>+</button>
            </span>
          </div>
        </details>
      </div>

      {/* --- Variant Configuration Cards --- */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontSize: 14, fontWeight: 600 }}>Variants</span>
        <div style={{ display: "flex", gap: 8 }}>
          {METHODS.map(m => (
            <button key={m.id} onClick={() => addVariant(m.id)}
              style={{
                padding: "8px 18px", fontSize: 12, fontWeight: 600,
                display: "flex", alignItems: "center", gap: 6,
                border: "none", borderRadius: 24,
                background: m.gradient, color: "#fff",
                cursor: "pointer", boxShadow: "0 2px 8px " + m.color + "40",
                transition: "transform 0.15s, box-shadow 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 4px 14px " + m.color + "50"; }}
              onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "0 2px 8px " + m.color + "40"; }}
            >
              <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> {m.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(variants.length, 3)}, 1fr)`, gap: 12, marginBottom: 20 }}>
        {variants.map(v => (
          <VariantCard
            key={v.id}
            variant={v}
            voices={voices[v.method] || []}
            formats={formats[v.method] || ["wav"]}
            onChange={patch => updateVariant(v.id, patch)}
            onRemove={() => removeVariant(v.id)}
            onDuplicate={() => duplicateVariant(v)}
            canRemove={variants.length > 1}
          />
        ))}
      </div>

      {/* --- Generate All --- */}
      <div style={{ display: "flex", gap: 12, marginBottom: 28 }}>
        <button onClick={handleGenerateAll} disabled={generating || !text.trim() || variants.length === 0}
          style={{
            padding: "14px 40px", fontSize: 15, fontWeight: 700,
            border: "none", borderRadius: 28,
            background: (generating || !text.trim()) ? "#aaa" : "linear-gradient(135deg, #003478, #0052CC, #00BCF2)",
            color: "#fff", letterSpacing: 0.3,
            cursor: (generating || !text.trim()) ? "not-allowed" : "pointer",
            boxShadow: (generating || !text.trim()) ? "none" : "0 4px 16px rgba(0,52,120,0.35)",
            transition: "transform 0.15s, box-shadow 0.15s",
            display: "flex", alignItems: "center", gap: 8,
          }}
          onMouseEnter={e => { if (!generating && text.trim()) { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 6px 24px rgba(0,52,120,0.45)"; }}}
          onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,52,120,0.35)"; }}
        >
          {generating ? (
            <><svg width="16" height="16" viewBox="0 0 16 16" style={{ animation: "spin 0.8s linear infinite" }}><circle cx="8" cy="8" r="6" stroke="white" strokeWidth="2" fill="none" strokeDasharray="28" strokeDashoffset="8" strokeLinecap="round"/></svg> Generating {variants.length} variant{variants.length > 1 ? "s" : ""}…</>
          ) : (
            <><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="white" strokeWidth="1.5" strokeLinecap="round"><path d="M3 8h10M10 4l4 4-4 4"/></svg> Generate {variants.length} Variant{variants.length > 1 ? "s" : ""}</>
          )}
        </button>
      </div>

      {/* --- Results Comparison Panel --- */}
      {results.length > 0 && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>Results</span>
            <button onClick={() => setResults([])} style={{ ...btnOutline, padding: "4px 12px", fontSize: 11 }}>
              Clear
            </button>
          </div>
          <div style={{ ...card, overflow: "hidden" }}>
            {results.map((r, i) => (
              <ResultRow key={r.variantId + "-" + i} item={r} index={i} isLast={i === results.length - 1} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Variant Configuration Card                                         */
/* ------------------------------------------------------------------ */

function VariantCard({ variant: v, voices: voiceList, formats: fmtList, onChange, onRemove, onDuplicate, canRemove }: {
  variant: Variant;
  voices: VoiceInfo[];
  formats: string[];
  onChange: (patch: Partial<Variant>) => void;
  onRemove: () => void;
  onDuplicate: () => void;
  canRemove: boolean;
}) {
  const m = METHOD_MAP[v.method];
  const isSsml = v.method === "azure-tts" || v.method === "gpt-ssml";

  // Sync voice when method changes
  useEffect(() => {
    if (voiceList.length > 0 && !voiceList.find(x => x.id === v.voice)) {
      onChange({ voice: voiceList[0].id });
    }
  }, [v.method, voiceList]);

  return (
    <div style={{ ...card, padding: 16, position: "relative" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span style={tag(m.color)}>{m.label}</span>
        <div style={{ display: "flex", gap: 4 }}>
          <button onClick={onDuplicate} title="Duplicate variant"
            style={{ border: "none", background: "none", cursor: "pointer", fontSize: 16, color: "var(--text-muted)", padding: 2 }}>⧉</button>
          {canRemove && (
            <button onClick={onRemove} title="Remove variant"
              style={{ border: "none", background: "none", cursor: "pointer", fontSize: 16, color: "var(--text-muted)", padding: 2 }}>×</button>
          )}
        </div>
      </div>

      {/* Method */}
      <div style={{ marginBottom: 10 }}>
        <span style={label}>Method</span>
        <select value={v.method} onChange={e => onChange({ method: e.target.value })} style={input}>
          {METHODS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
      </div>

      {/* Voice */}
      <div style={{ marginBottom: 10 }}>
        <span style={label}>Voice</span>
        <select value={v.voice} onChange={e => onChange({ voice: e.target.value })} style={input}>
          {voiceList.map(x => (
            <option key={x.id} value={x.id}>
              {x.name}{x.gender ? ` (${x.gender})` : ""}{x.locale ? ` · ${x.locale}` : ""}
            </option>
          ))}
        </select>
      </div>

      {/* Format */}
      <div style={{ marginBottom: 10 }}>
        <span style={label}>Format</span>
        <select value={v.format} onChange={e => onChange({ format: e.target.value })} style={input}>
          {fmtList.map(f => <option key={f} value={f}>{f.toUpperCase()}</option>)}
        </select>
      </div>

      {/* SSML controls */}
      {isSsml && (
        <div style={{ padding: 10, borderRadius: "var(--radius-sm)", background: "var(--bg)", marginBottom: 8 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
            <div>
              <span style={label}>Rate</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input type="range" min={-50} max={50} step={5} value={parseInt(v.rate)}
                  onChange={e => onChange({ rate: `${e.target.value}%` })}
                  style={{ flex: 1, accentColor: "var(--accent)" }} />
                <span style={{ fontSize: 11, color: "var(--text-muted)", minWidth: 32 }}>{v.rate}</span>
              </div>
            </div>
            <div>
              <span style={label}>Language</span>
              <select value={v.language} onChange={e => onChange({ language: e.target.value })} style={input}>
                <option value="fil-PH">Filipino</option>
                <option value="en-US">English US</option>
                <option value="en-AU">English AU</option>
              </select>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <span style={label}>Pitch</span>
              <select value={v.pitch} onChange={e => onChange({ pitch: e.target.value })} style={input}>
                {["default","x-low","low","medium","high","x-high"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <span style={label}>Volume</span>
              <select value={v.volume} onChange={e => onChange({ volume: e.target.value })} style={input}>
                {["default","silent","x-soft","soft","medium","loud","x-loud"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>
          {v.method === "gpt-ssml" && (
            <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 12, color: "var(--text-secondary)", cursor: "pointer" }}>
              <input type="checkbox" checked={v.translate} onChange={e => onChange({ translate: e.target.checked })}
                style={{ accentColor: "var(--accent)" }} />
              Translate to Taglish
            </label>
          )}
        </div>
      )}

      {/* GPT Audio prompt */}
      {v.method === "gpt-audio" && (
        <div>
          <span style={label}>Additional Style Instructions <span style={{ fontWeight: 400, opacity: 0.7 }}>(appended to default BDO prompt)</span></span>
          <textarea value={v.systemPrompt} onChange={e => onChange({ systemPrompt: e.target.value })}
            placeholder="e.g. Speak with a cheerful, upbeat energy for a social media ad..."
            rows={2} style={{ ...input, resize: "vertical", fontSize: 12 }} />
          <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6 }}>
            Requires <strong>gpt-audio-1.5</strong> deployment. Base prompt always includes: BDO brand voice, warm professional tone, Taglish support.
          </span>
        </div>
      )}

      {/* GPT Realtime */}
      {v.method === "gpt-realtime" && (
        <div>
          <span style={label}>Additional Session Instructions <span style={{ fontWeight: 400, opacity: 0.7 }}>(appended to default prompt)</span></span>
          <textarea value={v.instructions} onChange={e => onChange({ instructions: e.target.value })}
            placeholder="e.g. Emphasize urgency and excitement for a promo announcement..."
            rows={2} style={{ ...input, resize: "vertical", fontSize: 12, marginBottom: 8 }} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, padding: 10, borderRadius: "var(--radius-sm)", background: "var(--bg)" }}>
            <div>
              <span style={label}>Temperature: {v.temperature}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input type="range" min={0} max={1.2} step={0.1} value={v.temperature}
                  onChange={e => onChange({ temperature: parseFloat(e.target.value) })}
                  style={{ flex: 1, accentColor: "var(--accent)" }} />
                <span style={{ fontSize: 11, color: "var(--text-muted)", minWidth: 24 }}>{v.temperature}</span>
              </div>
            </div>
            <div>
              <span style={label}>Max Output Tokens</span>
              <select value={v.maxOutputTokens} onChange={e => onChange({ maxOutputTokens: parseInt(e.target.value) })} style={input}>
                <option value={1024}>1024</option>
                <option value={2048}>2048</option>
                <option value={4096}>4096 (default)</option>
              </select>
            </div>
          </div>
          <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6, marginTop: 6, display: "block" }}>
            Requires <strong>gpt-realtime-1.5</strong> deployment. Generates original + AI suggested version.
          </span>
        </div>
      )}

      {/* MAI Voice 1 */}
      {v.method === "mai-voice-1" && (
        <div style={{ padding: 10, borderRadius: "var(--radius-sm)", background: "linear-gradient(135deg, #0E749008, #06B6D408)", border: "1px solid #0E749020" }}>
          <span style={{ fontSize: 11, color: "#0E7490", fontWeight: 600, display: "block", marginBottom: 4 }}>
            Microsoft MAI-Voice-1 (Preview)
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6 }}>
            Highly expressive neural voice that automatically adapts emotion, pace, and rhythm.
            Optimized for conversational and engaging speech. <strong>Most suited for English only</strong>
          </span>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Result Row — compact horizontal layout                             */
/* ------------------------------------------------------------------ */

function ResultRow({ item, index, isLast }: { item: ResultItem; index: number; isLast: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const v = item.variant;
  const m = METHOD_MAP[v.method];
  const r = item.response;

  const voiceShort = v.voice.includes("-") ? v.voice.split("-").pop()?.replace("Neural","") || v.voice : v.voice;

  return (
    <div style={{ borderBottom: isLast ? "none" : "1px solid var(--border-light)" }}>
      {/* Main row — always visible, compact */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "32px 100px 1fr 200px 100px",
          alignItems: "center",
          gap: 10,
          padding: "10px 16px",
          cursor: "pointer",
          background: expanded ? "var(--bg)" : "transparent",
          transition: "background 0.1s",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        {/* # */}
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)" }}>#{index + 1}</span>

        {/* Method tag */}
        <span style={tag(m.color)}>{m.label}</span>

        {/* Params pills */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
          <ParamPill label="Voice" value={voiceShort} />
          <ParamPill label="Fmt" value={v.format.toUpperCase()} />
          {(v.method === "azure-tts" || v.method === "gpt-ssml") && v.rate !== "0%" && (
            <ParamPill label="Rate" value={v.rate} />
          )}
          {(v.method === "azure-tts" || v.method === "gpt-ssml") && (
            <ParamPill label="Lang" value={v.language.replace("fil-PH","🇵🇭").replace("en-US","🇺🇸").replace("en-AU","🇦🇺")} />
          )}
          {v.method === "gpt-ssml" && v.translate && <ParamPill label="" value="Taglish" accent />}
        </div>

        {/* Audio player inline */}
        <div onClick={e => e.stopPropagation()}>
          {item.loading && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 14, height: 14, borderRadius: "50%", border: `2px solid ${m.color}33`, borderTopColor: m.color, animation: "spin 0.8s linear infinite" }} />
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Generating…</span>
            </div>
          )}
          {item.error && <span style={{ fontSize: 11, color: "var(--error)" }}>Failed</span>}
          {r?.audio_url && !item.loading && (
            <audio controls src={r.audio_url} style={{ width: 200, height: 32 }} />
          )}
        </div>

        {/* Expand indicator */}
        <div style={{ textAlign: "right" }}>
          {r && !item.loading && (
            <span style={{ fontSize: 18, color: "var(--text-muted)", transition: "transform 0.15s", display: "inline-block", transform: expanded ? "rotate(180deg)" : "rotate(0deg)" }}>▾</span>
          )}
        </div>
      </div>

      {/* Expanded detail panel */}
      {expanded && r && !item.loading && (
        <div style={{ padding: "0 16px 14px 58px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Original */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
              Original Script
            </div>
            {r.text_output && (
              <div style={{ padding: 10, borderRadius: "var(--radius-sm)", background: "var(--bg)", fontSize: 12, lineHeight: 1.6, color: "var(--text-secondary)", maxHeight: 100, overflow: "auto", marginBottom: 8 }}>
                {r.text_output}
              </div>
            )}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {r.audio_url && (
                <a href={r.audio_url} download={r.local_audio_file}
                  style={{ ...btnOutline, padding: "3px 10px", fontSize: 11, textDecoration: "none", borderRadius: 4 }}>
                  ↓ Download
                </a>
              )}
              {r.ssml && (
                <button onClick={() => navigator.clipboard.writeText(r.ssml!)}
                  style={{ ...btnOutline, padding: "3px 10px", fontSize: 11, borderRadius: 4 }}>
                  Copy SSML
                </button>
              )}
              {r.ssml && (
                <button onClick={() => navigate("/ssml", { state: { ssml: r.ssml } })}
                  style={{ ...btnOutline, padding: "3px 10px", fontSize: 11, borderRadius: 4, color: "var(--accent)", borderColor: "var(--accent)" }}>
                  Edit in Playground
                </button>
              )}
            </div>
          </div>

          {/* Alternate (AI version) */}
          <div>
            {r.alternate && !r.alternate.error && r.alternate.audio_url ? (
              <>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--accent)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
                  AI Suggested Version
                </div>
                <audio controls src={r.alternate.audio_url} style={{ width: "100%", height: 32, marginBottom: 6 }} />
                {r.alternate.text_output && (
                  <div style={{ padding: 10, borderRadius: "var(--radius-sm)", background: "var(--accent-light)", fontSize: 12, lineHeight: 1.6, color: "var(--accent)", maxHeight: 100, overflow: "auto", marginBottom: 6 }}>
                    {r.alternate.text_output}
                  </div>
                )}
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <a href={r.alternate.audio_url} download={r.alternate.local_audio_file}
                    style={{ ...btnOutline, padding: "3px 10px", fontSize: 11, textDecoration: "none", borderRadius: 4 }}>
                    ↓ Download Alt
                  </a>
                </div>
              </>
            ) : r.alternate?.error ? (
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 20 }}>AI alternate: {r.alternate.error}</div>
            ) : (
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 20 }}>No AI alternate for this method</div>
            )}
          </div>
        </div>
      )}

      {/* CSS animations */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  );
}

/* tiny param display pill */
function ParamPill({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "2px 8px", borderRadius: 4, fontSize: 11,
      background: accent ? "var(--accent-light)" : "var(--bg)",
      color: accent ? "var(--accent)" : "var(--text-muted)", fontWeight: 500,
    }}>
      {label && <span style={{ opacity: 0.6 }}>{label}:</span>}
      {value}
    </span>
  );
}
