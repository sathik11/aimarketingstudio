import { useState, useEffect, useRef } from "react";
import api from "../services/api";

interface Avatar {
  id: number;
  name: string;
  description: string;
  source: string;
  model_used: string;
  asset_type: string;
  style: string;
  status?: string;
  quality?: string;
  error_message?: string;
  landscape_file: string;
  portrait_file: string;
  landscape_url?: string;
  portrait_url?: string;
  is_builtin: boolean;
  created_at: string;
}

interface StyleOption { id: string; label: string; description: string; }
interface AssetTypeOption { id: string; label: string; description: string; }
interface QualityOption { id: string; label: string; description: string; }

const EXAMPLE_PROMPTS: Record<string, string[]> = {
  character: [
    "A confident Filipino businesswoman in her 30s, shoulder-length black hair, wearing a navy blazer and gold accessories",
    "A friendly Filipino bank teller in his 20s, short hair, warm smile, wearing a corporate uniform",
    "A young Filipino entrepreneur with glasses, smart-casual outfit, holding a laptop",
    "An elderly Filipino grandmother, warm face, traditional floral blouse, gentle smile",
  ],
  background: [
    "Modern bank branch interior with glass walls, warm lighting, and BDO blue accents",
    "Manila city skyline at golden hour with skyscrapers and traffic below",
    "Cozy Filipino home living room with wooden furniture and family photos",
    "Clean modern office workspace with dual monitors and a coffee mug",
  ],
  prop: [
    "A modern smartphone showing a banking app dashboard with blue UI",
    "A gold and blue credit card with chip visible, floating at an angle",
    "A piggy bank shaped like a carabao (water buffalo), painted in blue and gold",
    "A stack of Philippine peso bills fanned out neatly",
  ],
  "logo-icon": [
    "A minimalist shield icon representing financial security, in blue and gold",
    "A simple line icon of a handshake, representing trust and partnership",
    "A modern mobile banking icon with a phone and money symbol",
    "A clean checkmark icon inside a circle, representing approval",
  ],
};

const s = {
  card: { background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" } as React.CSSProperties,
  label: { fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 4, display: "block" } as React.CSSProperties,
  input: { width: "100%", padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", fontSize: 13, color: "var(--text)", outline: "none", fontFamily: "inherit" } as React.CSSProperties,
};

const TYPE_ICONS: Record<string, string> = { character: "👤", background: "🏞️", prop: "📦", "logo-icon": "✦" };

export default function AssetsPage() {
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [loading, setLoading] = useState(true);
  const [styles, setStyles] = useState<StyleOption[]>([]);
  const [assetTypes, setAssetTypes] = useState<AssetTypeOption[]>([]);
  const [qualities, setQualities] = useState<QualityOption[]>([]);

  // From photo
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoName, setPhotoName] = useState("");
  const [photoStyle, setPhotoStyle] = useState("pixar-3d");
  const [photoQuality, setPhotoQuality] = useState("medium");
  const [photoGenerating, setPhotoGenerating] = useState(false);
  const photoRef = useRef<HTMLInputElement>(null);

  // From text
  const [textDesc, setTextDesc] = useState("");
  const [textName, setTextName] = useState("");
  const [textStyle, setTextStyle] = useState("pixar-3d");
  const [textAssetType, setTextAssetType] = useState("character");
  const [textQuality, setTextQuality] = useState("medium");
  const [textGenerating, setTextGenerating] = useState(false);

  // Filter
  const [filterType, setFilterType] = useState<string>("all");

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [lightbox, setLightbox] = useState<{ url: string; name: string } | null>(null);

  const loadAvatars = () => {
    api.get("/api/assets/avatars").then(({ data }) => setAvatars(data)).catch(() => {}).finally(() => setLoading(false));
  };

  // Poll for generating avatars
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    const generating = avatars.filter(a => a.status === "generating");
    if (generating.length > 0 && !pollRef.current) {
      pollRef.current = setInterval(() => {
        loadAvatars();
      }, 3000);
    } else if (generating.length === 0 && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [avatars]);

  useEffect(() => {
    loadAvatars();
    api.get("/api/assets/config").then(({ data }) => {
      setStyles(data.styles || []);
      setAssetTypes(data.asset_types || []);
      setQualities(data.qualities || []);
    }).catch(() => {});
  }, []);

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPhotoFile(file);
      setPhotoPreview(URL.createObjectURL(file));
      if (!photoName) setPhotoName(file.name.split(".")[0]);
    }
  };

  const handleGenerateFromPhoto = async () => {
    if (!photoFile || !photoName.trim() || photoGenerating) return;
    setPhotoGenerating(true);
    setError("");
    setSuccess("");
    try {
      const formData = new FormData();
      formData.append("photo", photoFile);
      formData.append("name", photoName.trim());
      formData.append("style", photoStyle);
      formData.append("quality", photoQuality);
      await api.post("/api/assets/avatar/from-photo", formData, { headers: { "Content-Type": "multipart/form-data" } });
      setSuccess("Generation started! Your character will appear below.");
      setPhotoFile(null);
      setPhotoPreview(null);
      setPhotoName("");
      if (photoRef.current) photoRef.current.value = "";
      loadAvatars();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Failed to submit generation");
    } finally {
      setPhotoGenerating(false);
    }
  };

  const handleGenerateFromText = async () => {
    if (!textDesc.trim() || !textName.trim() || textGenerating) return;
    setTextGenerating(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/api/assets/avatar/from-text", {
        description: textDesc.trim(),
        name: textName.trim(),
        model: "gpt-image-2",
        style: textStyle,
        asset_type: textAssetType,
        quality: textQuality,
      });
      setSuccess("Generation started! Your asset will appear below.");
      setTextDesc("");
      setTextName("");
      loadAvatars();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Failed to submit generation");
    } finally {
      setTextGenerating(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this asset?")) return;
    try {
      await api.delete(`/api/assets/avatar/${id}`);
      loadAvatars();
    } catch {
      alert("Failed to delete");
    }
  };

  const builtIn = avatars.filter(a => a.is_builtin);
  const userAssets = avatars.filter(a => !a.is_builtin);
  const filteredUser = filterType === "all" ? userAssets : userAssets.filter(a => (a.asset_type || "character") === filterType);
  const filteredBuiltIn = filterType === "all" ? builtIn : builtIn.filter(a => (a.asset_type || "character") === filterType);

  const examples = EXAMPLE_PROMPTS[textAssetType] || EXAMPLE_PROMPTS.character;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 24px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>Assets</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Create characters, backgrounds, props, and icons for your videos and marketing materials. Choose from multiple art styles powered by GPT Image 2.
        </p>
      </div>

      {/* Generate Section */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
        {/* From Photo (characters only) */}
        <div style={{ ...s.card, padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "linear-gradient(135deg, #F59E0B, #F97316)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>📷</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>From Photo</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Upload a photo → AI creates a styled character</div>
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>Photo</span>
            <input type="file" ref={photoRef} accept="image/*" onChange={handlePhotoChange}
              style={{ ...s.input, padding: "5px 8px", fontSize: 12 }} />
          </div>
          {photoPreview && (
            <div style={{ marginBottom: 10, display: "flex", gap: 10, alignItems: "center" }}>
              <img src={photoPreview} alt="Preview" style={{ width: 60, height: 60, borderRadius: 8, objectFit: "cover", border: "1px solid var(--border)" }} />
              <div style={{ flex: 1 }}>
                <span style={s.label}>Character Name</span>
                <input value={photoName} onChange={e => setPhotoName(e.target.value)} placeholder="e.g. Maria"
                  style={s.input} />
              </div>
            </div>
          )}
          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>Art Style</span>
            <select value={photoStyle} onChange={e => setPhotoStyle(e.target.value)} style={s.input}>
              {styles.map(st => (
                <option key={st.id} value={st.id}>{st.label}</option>
              ))}
            </select>
          </div>
          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>Quality</span>
            <div style={{ display: "flex", gap: 4 }}>
              {qualities.map(q => (
                <button key={q.id} onClick={() => setPhotoQuality(q.id)} title={q.description}
                  style={{
                    flex: 1, padding: "5px 8px", borderRadius: 6, fontSize: 11, fontWeight: photoQuality === q.id ? 600 : 400,
                    border: photoQuality === q.id ? "2px solid #F59E0B" : "1px solid var(--border)",
                    background: photoQuality === q.id ? "#FEF3C7" : "var(--surface)",
                    color: photoQuality === q.id ? "#92400E" : "var(--text-secondary)", cursor: "pointer",
                  }}>{q.label}</button>
              ))}
            </div>
          </div>
          <button onClick={handleGenerateFromPhoto} disabled={photoGenerating || !photoFile || !photoName.trim()}
            style={{
              width: "100%", padding: 10, fontSize: 13, fontWeight: 600, border: "none", borderRadius: 8,
              background: photoGenerating || !photoFile ? "#ccc" : "linear-gradient(135deg, #F59E0B, #F97316)",
              color: "#fff", cursor: photoGenerating ? "wait" : "pointer",
            }}>
            {photoGenerating ? "Submitting…" : "Generate from Photo"}
          </button>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>Uses gpt-image-2 (East US 2)</div>
        </div>

        {/* From Text (all asset types) */}
        <div style={{ ...s.card, padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "linear-gradient(135deg, #6366F1, #8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>✍️</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>From Description</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Describe what you need → AI generates it</div>
            </div>
          </div>

          {/* Asset Type Selector */}
          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>What are you creating?</span>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {assetTypes.map(t => (
                <button key={t.id} onClick={() => setTextAssetType(t.id)}
                  title={t.description}
                  style={{
                    padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: textAssetType === t.id ? 600 : 400,
                    border: textAssetType === t.id ? "2px solid #6366F1" : "1px solid var(--border)",
                    background: textAssetType === t.id ? "#EDE9FE" : "var(--surface)",
                    color: textAssetType === t.id ? "#6366F1" : "var(--text-secondary)",
                    cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
                  }}>
                  <span>{TYPE_ICONS[t.id] || "✦"}</span> {t.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
            <div>
              <span style={s.label}>Name</span>
              <input value={textName} onChange={e => setTextName(e.target.value)} placeholder={textAssetType === "character" ? "e.g. Carlo" : "e.g. Bank Interior"}
                style={s.input} />
            </div>
            <div>
              <span style={s.label}>Art Style</span>
              <select value={textStyle} onChange={e => setTextStyle(e.target.value)} style={s.input}>
                {styles.map(st => (
                  <option key={st.id} value={st.id}>{st.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ marginBottom: 8 }}>
            <span style={s.label}>Description</span>
            <textarea value={textDesc} onChange={e => setTextDesc(e.target.value)} rows={3}
              placeholder="Describe your asset in detail…"
              style={{ ...s.input, resize: "vertical", lineHeight: 1.5 }} />
          </div>

          {/* Example prompts */}
          <div style={{ marginBottom: 10 }}>
            <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>Quick examples</span>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
              {examples.map((ex, i) => (
                <button key={i} onClick={() => { setTextDesc(ex); if (!textName) setTextName(`Asset ${i + 1}`); }}
                  style={{
                    padding: "4px 10px", borderRadius: 12, fontSize: 10, border: "1px solid var(--border)",
                    background: "var(--surface)", color: "var(--text-secondary)", cursor: "pointer",
                    maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}
                  title={ex}>
                  {ex.length > 60 ? ex.slice(0, 60) + "…" : ex}
                </button>
              ))}
            </div>
          </div>

          {textAssetType === "character" && textStyle === "hyper-realistic" && (
            <div style={{ padding: 8, borderRadius: 6, background: "#FEF3C7", border: "1px solid #F59E0B40", fontSize: 11, color: "#92400E", marginBottom: 10, lineHeight: 1.5 }}>
              ⚠️ <strong>Heads up:</strong> Hyper-realistic human characters may be <strong>rejected by Sora video generation</strong> due to content moderation policies.
              For reliable video generation, consider using Pixar 3D, Anime, or other non-photorealistic styles.
            </div>
          )}

          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>Quality</span>
            <div style={{ display: "flex", gap: 4 }}>
              {qualities.map(q => (
                <button key={q.id} onClick={() => setTextQuality(q.id)} title={q.description}
                  style={{
                    flex: 1, padding: "5px 8px", borderRadius: 6, fontSize: 11, fontWeight: textQuality === q.id ? 600 : 400,
                    border: textQuality === q.id ? "2px solid #6366F1" : "1px solid var(--border)",
                    background: textQuality === q.id ? "#EDE9FE" : "var(--surface)",
                    color: textQuality === q.id ? "#6366F1" : "var(--text-secondary)", cursor: "pointer",
                  }}>{q.label}</button>
              ))}
            </div>
          </div>

          <button onClick={handleGenerateFromText} disabled={textGenerating || !textDesc.trim() || !textName.trim()}
            style={{
              width: "100%", padding: 10, fontSize: 13, fontWeight: 600, border: "none", borderRadius: 8,
              background: textGenerating || !textDesc.trim() ? "#ccc" : "linear-gradient(135deg, #6366F1, #8B5CF6)",
              color: "#fff", cursor: textGenerating ? "wait" : "pointer",
            }}>
            {textGenerating ? "Submitting…" : `Generate ${textAssetType === "character" ? "Character" : "Asset"}`}
          </button>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>Uses gpt-image-2 (East US 2)</div>
        </div>
      </div>

      {/* Status */}
      {error && <div style={{ padding: 10, borderRadius: 8, background: "#FEF2F2", color: "var(--error)", fontSize: 12, marginBottom: 16 }}>{error}</div>}
      {success && <div style={{ padding: 10, borderRadius: 8, background: "#F0FFF4", color: "#0D7C3D", fontSize: 12, marginBottom: 16 }}>{success}</div>}

      {/* Asset Library */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600 }}>Asset Library</h2>
          <div style={{ display: "flex", gap: 4 }}>
            {[{ id: "all", label: "All" }, ...assetTypes].map(t => (
              <button key={t.id} onClick={() => setFilterType(t.id)}
                style={{
                  padding: "4px 12px", borderRadius: 12, fontSize: 11, fontWeight: filterType === t.id ? 600 : 400,
                  border: filterType === t.id ? "2px solid #6366F1" : "1px solid var(--border)",
                  background: filterType === t.id ? "#EDE9FE" : "var(--surface)",
                  color: filterType === t.id ? "#6366F1" : "var(--text-muted)", cursor: "pointer",
                }}>
                {t.id !== "all" && <span style={{ marginRight: 3 }}>{TYPE_ICONS[t.id] || ""}</span>}{t.label}
              </button>
            ))}
          </div>
        </div>

        {loading && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</p>}

        {/* User-created assets */}
        {filteredUser.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10, display: "block" }}>
              Your Assets
            </span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
              {filteredUser.map(av => (
                <AssetCard key={av.id} avatar={av} onDelete={() => handleDelete(av.id)} onView={(url, name) => setLightbox({ url, name })} />
              ))}
            </div>
          </div>
        )}

        {/* Built-in assets */}
        {filteredBuiltIn.length > 0 && (
          <div>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10, display: "block" }}>
              Built-in Characters
            </span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
              {filteredBuiltIn.map(av => (
                <AssetCard key={av.id} avatar={av} onView={(url, name) => setLightbox({ url, name })} />
              ))}
            </div>
          </div>
        )}

        {!loading && avatars.length === 0 && (
          <div style={{ ...s.card, padding: 40, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            No assets yet. Generate one above!
          </div>
        )}
      </div>

      {/* Lightbox Modal */}
      {lightbox && (
        <div onClick={() => setLightbox(null)} style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", zIndex: 10000,
          display: "flex", alignItems: "center", justifyContent: "center", cursor: "zoom-out",
        }}>
          <div onClick={e => e.stopPropagation()} style={{ position: "relative", maxWidth: "90vw", maxHeight: "90vh", cursor: "default" }}>
            <img src={lightbox.url} alt={lightbox.name} style={{
              maxWidth: "90vw", maxHeight: "85vh", borderRadius: 12,
              boxShadow: "0 20px 60px rgba(0,0,0,0.5)", objectFit: "contain", display: "block",
            }} />
            <button onClick={() => setLightbox(null)} style={{
              position: "absolute", top: -14, right: -14, width: 36, height: 36, borderRadius: "50%",
              background: "#fff", border: "none", fontSize: 20, fontWeight: 700, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", color: "#333",
              boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
            }}>×</button>
            <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}>
              <a href={lightbox.url} download={`${lightbox.name}.png`}
                style={{
                  padding: "8px 20px", borderRadius: 8, background: "#fff", color: "#1F2937",
                  fontSize: 13, fontWeight: 600, textDecoration: "none", display: "flex", alignItems: "center", gap: 6,
                }}>
                ⬇ Download
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const TYPE_LABELS: Record<string, string> = { character: "Character", background: "Background", prop: "Prop", "logo-icon": "Logo/Icon" };
const STYLE_LABELS: Record<string, string> = {
  "pixar-3d": "Pixar 3D", "hyper-realistic": "Realistic", anime: "Anime", watercolor: "Watercolor",
  "flat-vector": "Flat", "comic-book": "Comic", corporate: "Corporate",
};

function AssetCard({ avatar, onDelete, onView }: { avatar: Avatar; onDelete?: () => void; onView?: (url: string, name: string) => void }) {
  const assetType = avatar.asset_type || "character";
  const style = avatar.style || "pixar-3d";
  const status = avatar.status || "ready";
  const imageUrl = avatar.landscape_url || avatar.portrait_url;

  return (
    <div style={{ ...{ background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }, overflow: "hidden", position: "relative" }}>
      {/* Generating placeholder */}
      {status === "generating" && (
        <div style={{
          width: "100%", height: 110, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          background: "linear-gradient(135deg, #EDE9FE, #E0E7FF, #DBEAFE)",
          backgroundSize: "200% 200%",
          animation: "shimmer 2s ease-in-out infinite",
        }}>
          <div style={{
            width: 28, height: 28, border: "3px solid #C7D2FE",
            borderTopColor: "#6366F1", borderRadius: "50%",
            animation: "spin 1s linear infinite",
          }} />
          <div style={{ fontSize: 11, fontWeight: 600, color: "#6366F1", marginTop: 6 }}>Generating…</div>
          <div style={{ fontSize: 9, color: "#818CF8", marginTop: 2 }}>{avatar.quality === "high" ? "~40-70s" : avatar.quality === "low" ? "~10-15s" : "~15-25s"}</div>
          <style>{`
            @keyframes shimmer { 0%,100% { background-position: 0% 50% } 50% { background-position: 100% 50% } }
            @keyframes spin { to { transform: rotate(360deg) } }
          `}</style>
        </div>
      )}
      {/* Failed placeholder */}
      {status === "failed" && (
        <div style={{
          width: "100%", height: 110, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          background: "#FEF2F2",
        }}>
          <div style={{ fontSize: 24 }}>⚠️</div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#DC2626", marginTop: 4 }}>Failed</div>
          <div style={{ fontSize: 9, color: "#EF4444", marginTop: 2, padding: "0 8px", textAlign: "center" }}>
            {(avatar.error_message || "Generation failed").slice(0, 60)}
          </div>
        </div>
      )}
      {/* Ready image */}
      {status === "ready" && imageUrl && (
        <div onClick={() => onView?.(imageUrl, avatar.name)} style={{ cursor: "pointer", position: "relative" }}>
          <img src={imageUrl} alt={avatar.name}
            style={{ width: "100%", height: 110, objectFit: "cover", display: "block" }} />
          <div style={{
            position: "absolute", inset: 0, background: "rgba(0,0,0,0)", display: "flex",
            alignItems: "center", justifyContent: "center", transition: "background 0.2s",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "rgba(0,0,0,0.3)")}
          onMouseLeave={e => (e.currentTarget.style.background = "rgba(0,0,0,0)")}>
            <span style={{ color: "#fff", fontSize: 20, opacity: 0, transition: "opacity 0.2s" }}
              ref={el => {
                if (el) {
                  el.parentElement!.onmouseenter = () => { el.style.opacity = "1"; (el.parentElement as HTMLElement).style.background = "rgba(0,0,0,0.3)"; };
                  el.parentElement!.onmouseleave = () => { el.style.opacity = "0"; (el.parentElement as HTMLElement).style.background = "rgba(0,0,0,0)"; };
                }
              }}>🔍</span>
          </div>
        </div>
      )}
      <div style={{ padding: "10px 12px" }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 3 }}>{avatar.name}</div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 4 }}>
          <span style={{
            padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 600,
            background: status === "generating" ? "#EDE9FE" : status === "failed" ? "#FEF2F2" : avatar.source === "photo" ? "#FEF3C7" : avatar.source === "builtin" ? "#E8F5E9" : "#EDE9FE",
            color: status === "generating" ? "#6366F1" : status === "failed" ? "#DC2626" : avatar.source === "photo" ? "#92400E" : avatar.source === "builtin" ? "#0D7C3D" : "#6366F1",
          }}>
            {status === "generating" ? "⏳ Generating" : status === "failed" ? "❌ Failed" : avatar.source === "photo" ? "From Photo" : avatar.source === "builtin" ? "Built-in" : "AI Generated"}
          </span>
          <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, background: "#F0F4FF", color: "#4B5563" }}>
            {TYPE_ICONS[assetType] || ""} {TYPE_LABELS[assetType] || assetType}
          </span>
          <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, background: "var(--bg)", color: "var(--text-muted)" }}>
            {STYLE_LABELS[style] || style}
          </span>
        </div>
        {avatar.description && (
          <div style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
            {avatar.description}
          </div>
        )}
        <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
          {status === "ready" && imageUrl && (
            <a href={imageUrl} download={`${avatar.name}.png`}
              style={{ padding: "3px 10px", fontSize: 10, borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-muted)", cursor: "pointer", textDecoration: "none" }}>
              ⬇ Download
            </a>
          )}
          {onDelete && (
            <button onClick={onDelete}
              style={{ padding: "3px 10px", fontSize: 10, borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-muted)", cursor: "pointer" }}>
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
