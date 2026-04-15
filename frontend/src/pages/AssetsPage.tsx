import { useState, useEffect, useRef } from "react";
import api from "../services/api";

interface Avatar {
  id: number;
  name: string;
  description: string;
  source: string;
  model_used: string;
  landscape_file: string;
  portrait_file: string;
  landscape_url?: string;
  portrait_url?: string;
  is_builtin: boolean;
  created_at: string;
}

const s = {
  card: { background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" } as React.CSSProperties,
  label: { fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 4, display: "block" } as React.CSSProperties,
  input: { width: "100%", padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", fontSize: 13, color: "var(--text)", outline: "none", fontFamily: "inherit" } as React.CSSProperties,
};

export default function AssetsPage() {
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [loading, setLoading] = useState(true);

  // From photo
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoName, setPhotoName] = useState("");
  const [photoGenerating, setPhotoGenerating] = useState(false);
  const photoRef = useRef<HTMLInputElement>(null);

  // From text
  const [textDesc, setTextDesc] = useState("");
  const [textName, setTextName] = useState("");
  const [textModel, setTextModel] = useState("gpt-image-1.5");
  const [textGenerating, setTextGenerating] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadAvatars = () => {
    api.get("/api/assets/avatars").then(({ data }) => setAvatars(data)).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { loadAvatars(); }, []);

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPhotoFile(file);
      setPhotoPreview(URL.createObjectURL(file));
      if (!photoName) setPhotoName(file.name.split(".")[0]);
    }
  };

  const handleGenerateFromPhoto = async () => {
    if (!photoFile || !photoName.trim()) return;
    setPhotoGenerating(true);
    setError("");
    setSuccess("");
    try {
      const formData = new FormData();
      formData.append("photo", photoFile);
      formData.append("name", photoName.trim());
      await api.post("/api/assets/avatar/from-photo", formData, { headers: { "Content-Type": "multipart/form-data" } });
      setSuccess("Avatar created from photo!");
      setPhotoFile(null);
      setPhotoPreview(null);
      setPhotoName("");
      if (photoRef.current) photoRef.current.value = "";
      loadAvatars();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Failed to generate avatar");
    } finally {
      setPhotoGenerating(false);
    }
  };

  const handleGenerateFromText = async () => {
    if (!textDesc.trim() || !textName.trim()) return;
    setTextGenerating(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/api/assets/avatar/from-text", { description: textDesc.trim(), name: textName.trim(), model: textModel });
      setSuccess("Avatar created from description!");
      setTextDesc("");
      setTextName("");
      loadAvatars();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Failed to generate avatar");
    } finally {
      setTextGenerating(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this avatar?")) return;
    try {
      await api.delete(`/api/assets/avatar/${id}`);
      loadAvatars();
    } catch {
      alert("Failed to delete");
    }
  };

  const builtIn = avatars.filter(a => a.is_builtin);
  const userAvatars = avatars.filter(a => !a.is_builtin);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 24px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>Assets</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Create and manage character avatars for video generation. Upload a photo or describe a character.
        </p>
      </div>

      {/* Generate Section */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
        {/* From Photo */}
        <div style={{ ...s.card, padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "linear-gradient(135deg, #F59E0B, #F97316)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>📷</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>From Photo</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Upload a photo → AI creates animated avatar</div>
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
                <span style={s.label}>Avatar Name</span>
                <input value={photoName} onChange={e => setPhotoName(e.target.value)} placeholder="e.g. Maria"
                  style={s.input} />
              </div>
            </div>
          )}
          <button onClick={handleGenerateFromPhoto} disabled={photoGenerating || !photoFile || !photoName.trim()}
            style={{
              width: "100%", padding: 10, fontSize: 13, fontWeight: 600, border: "none", borderRadius: 8,
              background: photoGenerating || !photoFile ? "#ccc" : "linear-gradient(135deg, #F59E0B, #F97316)",
              color: "#fff", cursor: photoGenerating ? "wait" : "pointer",
            }}>
            {photoGenerating ? "Generating avatar…" : "Generate from Photo"}
          </button>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>Uses gpt-image-1.5 • Transforms photo into Pixar-style animation</div>
        </div>

        {/* From Text */}
        <div style={{ ...s.card, padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "linear-gradient(135deg, #6366F1, #8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>✍️</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>From Description</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Describe a character → AI generates avatar</div>
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>Avatar Name</span>
            <input value={textName} onChange={e => setTextName(e.target.value)} placeholder="e.g. Carlo"
              style={s.input} />
          </div>
          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>Character Description</span>
            <textarea value={textDesc} onChange={e => setTextDesc(e.target.value)} rows={3}
              placeholder="e.g. A confident Filipino businessman in his 30s, short black hair, wearing a navy suit..."
              style={{ ...s.input, resize: "vertical", lineHeight: 1.5 }} />
          </div>
          <div style={{ marginBottom: 10 }}>
            <span style={s.label}>Model</span>
            <select value={textModel} onChange={e => setTextModel(e.target.value)} style={s.input}>
              <option value="gpt-image-1.5">GPT Image 1.5 (best quality)</option>
              <option value="MAI-Image-2">MAI Image 2 (Microsoft)</option>
            </select>
          </div>
          <button onClick={handleGenerateFromText} disabled={textGenerating || !textDesc.trim() || !textName.trim()}
            style={{
              width: "100%", padding: 10, fontSize: 13, fontWeight: 600, border: "none", borderRadius: 8,
              background: textGenerating || !textDesc.trim() ? "#ccc" : "linear-gradient(135deg, #6366F1, #8B5CF6)",
              color: "#fff", cursor: textGenerating ? "wait" : "pointer",
            }}>
            {textGenerating ? "Generating avatar…" : "Generate from Description"}
          </button>
        </div>
      </div>

      {/* Status */}
      {error && <div style={{ padding: 10, borderRadius: 8, background: "#FEF2F2", color: "var(--error)", fontSize: 12, marginBottom: 16 }}>{error}</div>}
      {success && <div style={{ padding: 10, borderRadius: 8, background: "#F0FFF4", color: "#0D7C3D", fontSize: 12, marginBottom: 16 }}>{success}</div>}

      {/* Avatar Library */}
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Avatar Library</h2>

        {loading && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</p>}

        {/* User-created avatars */}
        {userAvatars.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10, display: "block" }}>
              Your Avatars
            </span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12 }}>
              {userAvatars.map(av => (
                <AvatarCard key={av.id} avatar={av} onDelete={() => handleDelete(av.id)} />
              ))}
            </div>
          </div>
        )}

        {/* Built-in avatars */}
        {builtIn.length > 0 && (
          <div>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10, display: "block" }}>
              Built-in Avatars
            </span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12 }}>
              {builtIn.map(av => (
                <AvatarCard key={av.id} avatar={av} />
              ))}
            </div>
          </div>
        )}

        {!loading && avatars.length === 0 && (
          <div style={{ ...s.card, padding: 40, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            No avatars yet. Generate one above!
          </div>
        )}
      </div>
    </div>
  );
}

function AvatarCard({ avatar, onDelete }: { avatar: Avatar; onDelete?: () => void }) {
  return (
    <div style={{ ...{ background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" }, overflow: "hidden" }}>
      {avatar.landscape_url && (
        <img src={avatar.landscape_url} alt={avatar.name}
          style={{ width: "100%", height: 100, objectFit: "cover" }} />
      )}
      <div style={{ padding: "10px 12px" }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{avatar.name}</div>
        <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
          <span style={{
            padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 600,
            background: avatar.source === "photo" ? "#FEF3C7" : avatar.source === "builtin" ? "#E8F5E9" : "#EDE9FE",
            color: avatar.source === "photo" ? "#92400E" : avatar.source === "builtin" ? "#0D7C3D" : "#6366F1",
          }}>
            {avatar.source === "photo" ? "From Photo" : avatar.source === "builtin" ? "Built-in" : "AI Generated"}
          </span>
          {avatar.model_used && (
            <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, background: "var(--bg)", color: "var(--text-muted)" }}>
              {avatar.model_used}
            </span>
          )}
        </div>
        {avatar.description && (
          <div style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
            {avatar.description}
          </div>
        )}
        {onDelete && (
          <button onClick={onDelete}
            style={{ marginTop: 6, padding: "3px 10px", fontSize: 10, borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-muted)", cursor: "pointer" }}>
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
