import { useState, useEffect, useRef, useCallback } from "react";
import api from "../services/api";

interface VideoStyle { id: string; label: string; description: string; }
interface VideoResolution { id: string; label: string; aspect: string; }
interface VideoJob {
  id: number; status: string; progress: number; script: string;
  generated_prompt: string; style: string; resolution: string;
  video_file?: string; video_url?: string; error?: string;
  created_at: string; updated_at: string;
}
interface VideoScene {
  id: number; scene_number: number; description: string; prompt: string;
  duration: number; status: string; progress: number;
  video_file?: string; video_url?: string; error?: string;
}
interface VideoProject {
  id: number; status: string; script: string; style: string; resolution: string;
  total_scenes: number; completed_scenes: number;
  final_video_file?: string; final_video_url?: string;
  error?: string; scenes: VideoScene[]; created_at: string;
}

const STYLE_COLORS: Record<string, string> = {
  animation: "#F59E0B", cinematic: "#6366F1", "motion-graphics": "#0EA5E9", illustration: "#EC4899",
};

const s = {
  card: { background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)" } as React.CSSProperties,
  label: { fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 4, display: "block" } as React.CSSProperties,
  input: { width: "100%", padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", fontSize: 13, color: "var(--text)", outline: "none", fontFamily: "inherit" } as React.CSSProperties,
};

export default function VideoPage({ onGenerated }: { onGenerated?: () => void }) {
  const [mode, setMode] = useState<"quick" | "storyboard">("storyboard");
  const [styles, setStyles] = useState<VideoStyle[]>([]);
  const [resolutions, setResolutions] = useState<VideoResolution[]>([]);
  const [script, setScript] = useState("");
  const [style, setStyle] = useState("animation");
  const [resolution, setResolution] = useState("1280x720");
  const [refImage, setRefImage] = useState<File | null>(null);
  const [refPreview, setRefPreview] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Storyboard state
  const [projects, setProjects] = useState<VideoProject[]>([]);
  const [planning, setPlanning] = useState(false);
  const [activeProject, setActiveProject] = useState<VideoProject | null>(null);
  const projectPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [selectedSceneIdx, setSelectedSceneIdx] = useState<number | null>(null);

  // Avatars — loaded from assets API
  const [avatars, setAvatars] = useState<{ id: number; name: string; description: string; landscape_file: string; portrait_file: string; landscape_url?: string; portrait_url?: string; is_builtin: boolean }[]>([]);
  const [selectedAvatar, setSelectedAvatar] = useState<number | null>(null);

  // Cohesion controls
  const [noTextOverlay, setNoTextOverlay] = useState(false);
  const [cameraStyle, setCameraStyle] = useState("slow-pan");
  const [colorMood, setColorMood] = useState("warm");
  const [nationality, setNationality] = useState("filipino");

  // Load config
  useEffect(() => {
    api.get("/api/video/config").then(({ data }) => {
      setStyles(data.styles);
      setResolutions(data.resolutions);
    }).catch(() => {});
    // Load avatars from assets API
    api.get("/api/assets/avatars").then(({ data }) => {
      setAvatars(data);
    }).catch(() => {});
  }, []);

  // Load existing jobs
  const loadJobs = useCallback(() => {
    api.get("/api/video/jobs").then(({ data }) => setJobs(data)).catch(() => {});
  }, []);

  useEffect(() => { loadJobs(); }, [loadJobs]);

  // Poll for in-progress jobs
  useEffect(() => {
    const hasActive = jobs.some(j => !["completed", "failed", "cancelled"].includes(j.status));
    if (hasActive) {
      if (!pollRef.current) {
        pollRef.current = setInterval(loadJobs, 10000);
      }
    } else {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [jobs, loadJobs]);

  // Storyboard: load projects
  const loadProjects = useCallback(() => {
    api.get("/api/video/storyboard").then(({ data }) => setProjects(data)).catch(() => {});
  }, []);

  useEffect(() => { if (mode === "storyboard") loadProjects(); }, [mode, loadProjects]);

  // Poll active project
  useEffect(() => {
    if (activeProject && !["completed", "failed"].includes(activeProject.status)) {
      if (!projectPollRef.current) {
        projectPollRef.current = setInterval(() => {
          api.get(`/api/video/storyboard/${activeProject.id}`).then(({ data }) => {
            setActiveProject(data);
            if (["completed", "failed"].includes(data.status)) {
              loadProjects();
              onGenerated?.();
            }
          }).catch(() => {});
        }, 10000);
      }
    } else {
      if (projectPollRef.current) { clearInterval(projectPollRef.current); projectPollRef.current = null; }
    }
    return () => { if (projectPollRef.current) clearInterval(projectPollRef.current); };
  }, [activeProject, loadProjects, onGenerated]);

  // Storyboard: plan scenes
  const handlePlanStoryboard = async () => {
    if (!script.trim()) return;
    setPlanning(true);
    setError("");
    try {
      const { data } = await api.post("/api/video/storyboard/plan", {
        script: script.trim(), style, resolution,
        avatar_id: style === "animation" && selectedAvatar ? selectedAvatar : undefined,
        no_text_overlay: noTextOverlay,
        camera_style: cameraStyle,
        color_mood: colorMood,
        nationality,
      });
      setActiveProject(data);
      loadProjects();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Planning failed");
    } finally {
      setPlanning(false);
    }
  };

  // Storyboard: generate all scenes
  const handleGenerateStoryboard = async () => {
    if (!activeProject) return;
    setError("");
    try {
      await api.post(`/api/video/storyboard/${activeProject.id}/generate`, {
        avatar_id: style === "animation" && selectedAvatar ? selectedAvatar : undefined,
      });
      const { data } = await api.get(`/api/video/storyboard/${activeProject.id}`);
      setActiveProject(data);
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Generation failed");
    }
  };

  // Update scene prompt
  const handleUpdateScene = async (sceneId: number, prompt: string) => {
    if (!activeProject) return;
    await api.put(`/api/video/storyboard/${activeProject.id}/update-scene`, { scene_id: sceneId, prompt });
    const { data } = await api.get(`/api/video/storyboard/${activeProject.id}`);
    setActiveProject(data);
  };

  // Handle image preview
  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setRefImage(file);
      const url = URL.createObjectURL(file);
      setRefPreview(url);
    }
  };

  const clearImage = () => {
    setRefImage(null);
    setRefPreview(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleGenerate = async () => {
    if (!script.trim()) return;
    setGenerating(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("script", script.trim());
      formData.append("style", style);
      formData.append("resolution", resolution);
      if (refImage) formData.append("reference_image", refImage);

      await api.post("/api/video/generate", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      loadJobs();
      onGenerated?.();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Video generation failed");
    } finally {
      setGenerating(false);
    }
  };

  // Retry a failed scene
  const handleRetryScene = async (sceneId: number) => {
    if (!activeProject) return;
    try {
      await api.post(`/api/video/storyboard/${activeProject.id}/retry-scene/${sceneId}`, {
        avatar_id: selectedAvatar || undefined,
      });
      // Re-fetch project
      const { data } = await api.get(`/api/video/storyboard/${activeProject.id}`);
      setActiveProject(data);
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { error?: string } } };
      setError(axErr?.response?.data?.error || "Retry failed");
    }
  };

  const wordCount = script.trim() ? script.trim().split(/\s+/).length : 0;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 24px" }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>
          Video Generation
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 14 }}>
          Create AI-generated videos from your marketing scripts using Sora 2.
        </p>
        {/* Mode Toggle */}
        <div style={{ display: "flex", gap: 4, background: "var(--border-light, #f0f0f0)", borderRadius: 8, padding: 3, width: "fit-content" }}>
          {([["storyboard", "Storyboard", "Multi-scene with stitching"], ["quick", "Quick Video", "Single 12s clip"]] as const).map(([id, label, desc]) => (
            <button key={id} onClick={() => setMode(id)}
              title={desc}
              style={{
                padding: "8px 20px", fontSize: 13, fontWeight: mode === id ? 600 : 400,
                border: "none", borderRadius: 6, cursor: "pointer",
                background: mode === id ? "var(--surface)" : "transparent",
                color: mode === id ? "var(--text)" : "var(--text-muted)",
                boxShadow: mode === id ? "var(--shadow-sm)" : "none",
                transition: "all 0.15s",
              }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {mode === "quick" && (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20 }}>
        {/* Left: Input */}
        <div>
          {/* Script */}
          <div style={{ ...s.card, padding: 20, marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>Marketing Script</span>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{wordCount} words</span>
            </div>
            <textarea value={script} onChange={e => setScript(e.target.value)}
              placeholder='e.g. "Let BDO handle your payments and collections para maka focus ka sa business mo!"'
              rows={4} style={{ ...s.input, resize: "vertical", lineHeight: 1.6, fontSize: 14 }} />
          </div>

          {/* Style Selection */}
          <div style={{ marginBottom: 16 }}>
            <span style={{ ...s.label, marginBottom: 8 }}>Visual Style</span>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {styles.map(st => (
                <button key={st.id} onClick={() => setStyle(st.id)}
                  style={{
                    ...s.card, padding: 14, border: style === st.id ? `2px solid ${STYLE_COLORS[st.id] || "#0052CC"}` : "1px solid var(--border)",
                    background: style === st.id ? (STYLE_COLORS[st.id] || "#0052CC") + "08" : "var(--surface)",
                    cursor: "pointer", textAlign: "left", transition: "all 0.15s",
                  }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: style === st.id ? STYLE_COLORS[st.id] : "var(--text)" }}>{st.label}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.4 }}>{st.description}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Resolution + Reference Image */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div>
              <span style={s.label}>Resolution</span>
              <select value={resolution} onChange={e => setResolution(e.target.value)} style={s.input}>
                {resolutions.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
            <div>
              <span style={s.label}>Reference Image <span style={{ fontWeight: 400, opacity: 0.6 }}>(optional)</span></span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input type="file" ref={fileRef} accept="image/jpeg,image/png,image/webp" onChange={handleImageChange}
                  style={{ ...s.input, padding: "5px 8px", fontSize: 12 }} />
                {refImage && <button onClick={clearImage} style={{ border: "none", background: "none", cursor: "pointer", color: "var(--error)", fontSize: 16 }}>×</button>}
              </div>
              {refPreview && (
                <div style={{ marginTop: 8, borderRadius: "var(--radius-sm)", overflow: "hidden", border: "1px solid var(--border)" }}>
                  <img src={refPreview} alt="Reference" style={{ width: "100%", maxHeight: 120, objectFit: "cover" }} />
                </div>
              )}
            </div>
          </div>

          {/* Generate Button */}
          <button onClick={handleGenerate} disabled={generating || !script.trim()}
            style={{
              padding: "14px 36px", fontSize: 15, fontWeight: 700,
              border: "none", borderRadius: 28,
              background: (generating || !script.trim()) ? "#aaa" : "linear-gradient(135deg, #F59E0B, #F97316)",
              color: "#fff", cursor: (generating || !script.trim()) ? "not-allowed" : "pointer",
              boxShadow: (generating || !script.trim()) ? "none" : "0 4px 16px rgba(245,158,11,0.35)",
              display: "flex", alignItems: "center", gap: 8, transition: "all 0.15s",
            }}>
            {generating ? (
              <><svg width="16" height="16" viewBox="0 0 16 16" style={{ animation: "spin 0.8s linear infinite" }}><circle cx="8" cy="8" r="6" stroke="white" strokeWidth="2" fill="none" strokeDasharray="28" strokeDashoffset="8" strokeLinecap="round"/></svg> Generating Video…</>
            ) : (
              <><svg width="16" height="16" viewBox="0 0 16 16" fill="white"><path d="M4 2l10 6-10 6V2z"/></svg> Generate Video</>
            )}
          </button>

          {error && <div style={{ marginTop: 12, padding: 10, borderRadius: "var(--radius-sm)", background: "#FEF2F2", color: "var(--error)", fontSize: 12 }}>{error}</div>}

          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>

        {/* Right: Jobs Panel */}
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>
            Video Jobs {jobs.length > 0 && <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400 }}>({jobs.length})</span>}
          </div>

          {jobs.length === 0 && (
            <div style={{ ...s.card, padding: 30, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
              No videos generated yet.
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {jobs.map(job => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        </div>
      </div>
      )}

      {/* === STORYBOARD MODE === */}
      {mode === "storyboard" && (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 200px", gap: 16 }}>
        {/* Main Content */}
        <div>
          {/* Top: Script + Controls */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16, marginBottom: 20 }}>
            <div style={{ ...s.card, padding: 20 }}>
              <span style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: "block" }}>Script</span>
              <textarea value={script} onChange={e => setScript(e.target.value)}
                placeholder="Paste your full marketing/explainer script here..."
                rows={5} style={{ ...s.input, resize: "vertical", lineHeight: 1.6, fontSize: 14 }} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div>
                  <span style={s.label}>Style</span>
                  <select value={style} onChange={e => setStyle(e.target.value)} style={s.input}>
                    {styles.map(st => <option key={st.id} value={st.id}>{st.label}</option>)}
                  </select>
                </div>
                <div>
                  <span style={s.label}>Resolution</span>
                  <select value={resolution} onChange={e => setResolution(e.target.value)} style={s.input}>
                    {resolutions.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                  </select>
                </div>
              </div>
              <div style={{ padding: 12, borderRadius: 8, background: "linear-gradient(135deg, #1a1a2e08, #16213e08)", border: "1px solid var(--border)" }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8, display: "block" }}>Cohesion</span>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  <div><span style={{ ...s.label, fontSize: 10 }}>Nationality</span>
                    <select value={nationality} onChange={e => setNationality(e.target.value)} style={{ ...s.input, fontSize: 11, padding: "4px 6px" }}>
                      {["filipino","chinese","indian","thai","indonesian","malay","vietnamese","japanese","korean","singaporean"].map(n => <option key={n} value={n}>{n.charAt(0).toUpperCase()+n.slice(1)}</option>)}
                    </select></div>
                  <div><span style={{ ...s.label, fontSize: 10 }}>Camera</span>
                    <select value={cameraStyle} onChange={e => setCameraStyle(e.target.value)} style={{ ...s.input, fontSize: 11, padding: "4px 6px" }}>
                      {[["static","Static"],["slow-pan","Slow Pan"],["dolly","Dolly"],["orbit","Orbit"],["handheld","Handheld"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
                    </select></div>
                  <div><span style={{ ...s.label, fontSize: 10 }}>Color Mood</span>
                    <select value={colorMood} onChange={e => setColorMood(e.target.value)} style={{ ...s.input, fontSize: 11, padding: "4px 6px" }}>
                      {[["warm","Warm"],["cool","Cool"],["neutral","Neutral"],["vibrant","Vibrant"],["pastel","Pastel"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
                    </select></div>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 11, color: "var(--text-secondary)", cursor: "pointer" }}>
                  <input type="checkbox" checked={noTextOverlay} onChange={e => setNoTextOverlay(e.target.checked)} style={{ accentColor: "#6366F1" }} />
                  Remove text from video
                </label>
              </div>
              {style === "animation" && avatars.length > 0 && (
                <div><span style={{ ...s.label, fontSize: 10 }}>Character</span>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    <button onClick={() => setSelectedAvatar(null)} style={{ padding: "4px 10px", borderRadius: 4, fontSize: 10, cursor: "pointer", border: selectedAvatar === null ? "2px solid #6366F1" : "1px solid var(--border)", background: selectedAvatar === null ? "#EDE9FE" : "var(--surface)", color: "var(--text-muted)" }}>None</button>
                    {avatars.map(av => (<button key={av.id} onClick={() => setSelectedAvatar(av.id)} title={av.name} style={{ padding: 2, borderRadius: 4, cursor: "pointer", width: 46, border: selectedAvatar === av.id ? "2px solid #6366F1" : "1px solid var(--border)" }}><img src={av.landscape_url || `/api/assets/avatar/file/${av.landscape_file}`} alt={av.name} style={{ width: "100%", height: 24, objectFit: "cover", borderRadius: 2 }} /></button>))}
                  </div>
                </div>
              )}
              <button onClick={handlePlanStoryboard} disabled={planning || !script.trim()}
                style={{ width: "100%", padding: "12px", fontSize: 13, fontWeight: 600, border: "none", borderRadius: 8, cursor: planning ? "wait" : "pointer", background: planning || !script.trim() ? "#ccc" : "linear-gradient(135deg, #6366F1, #8B5CF6)", color: "#fff", boxShadow: "0 2px 8px rgba(99,102,241,0.3)" }}>
                {planning ? "Planning scenes…" : "Plan Storyboard"}
              </button>
            </div>
          </div>

          {error && <div style={{ padding: 10, borderRadius: 8, background: "#FEF2F2", color: "var(--error)", fontSize: 12, marginBottom: 16 }}>{error}</div>}

          {/* Timeline */}
          {activeProject && (() => {
            const totalProgress = activeProject.total_scenes > 0
              ? Math.round((activeProject.completed_scenes / activeProject.total_scenes) * 100) : 0;
            return (
            <div style={{ borderRadius: 12, overflow: "hidden", background: "linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%)", border: "1px solid #2a2a4a", marginBottom: 16 }}>
              {/* Header with progress */}
              <div style={{ padding: "14px 20px", borderBottom: "1px solid #2a2a4a" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "#fff" }}>Storyboard</span>
                    <span style={{ padding: "2px 10px", borderRadius: 4, fontSize: 10, fontWeight: 600, textTransform: "uppercase", background: activeProject.status === "completed" ? "#0D7C3D33" : activeProject.status === "failed" ? "#D3202933" : "#6366F133", color: activeProject.status === "completed" ? "#4ADE80" : activeProject.status === "failed" ? "#F87171" : "#A5B4FC" }}>{activeProject.status}</span>
                    {activeProject.status === "generating" && <span style={{ fontSize: 12, fontWeight: 600, color: "#A5B4FC" }}>{totalProgress}%</span>}
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {(activeProject.status === "ready" || activeProject.status === "planning") && (
                      <button onClick={handleGenerateStoryboard} style={{ padding: "8px 20px", fontSize: 12, fontWeight: 600, border: "none", borderRadius: 16, background: "linear-gradient(135deg, #F59E0B, #F97316)", color: "#fff", cursor: "pointer", boxShadow: "0 2px 12px rgba(245,158,11,0.4)" }}>▶ Generate All</button>
                    )}
                  </div>
                </div>
                {/* Overall progress bar */}
                {activeProject.status === "generating" && (
                  <div style={{ height: 4, borderRadius: 2, background: "#2a2a4a", overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 2, background: "linear-gradient(90deg, #6366F1, #A5B4FC)", width: `${totalProgress}%`, transition: "width 0.5s" }} />
                  </div>
                )}
              </div>

              {/* Filmstrip */}
              <div style={{ padding: "16px 20px", overflowX: "auto" }}>
                <div style={{ display: "flex", gap: 0, minWidth: "fit-content", alignItems: "stretch" }}>
                  {activeProject.scenes.map((scene, idx) => {
                    const isSelected = selectedSceneIdx === idx;
                    const statusColor = scene.status === "completed" ? "#4ADE80" : scene.status === "failed" ? "#F87171" : (scene.status !== "pending" && scene.status !== "") ? "#A5B4FC" : "#555";
                    return (
                      <div key={scene.id} style={{ display: "flex", alignItems: "center" }}>
                        <div onClick={() => setSelectedSceneIdx(isSelected ? null : idx)} style={{ width: 160, cursor: "pointer", borderRadius: 8, border: isSelected ? "2px solid #A5B4FC" : "2px solid transparent", background: isSelected ? "#2a2a4a" : "#1e1e30", overflow: "hidden", transition: "all 0.15s", flexShrink: 0 }}>
                          <div style={{ height: 90, background: "#0a0a14", display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
                            {scene.status === "completed" && scene.video_url ? (
                              <video src={scene.video_url} style={{ width: "100%", height: "100%", objectFit: "cover" }} onMouseEnter={e => (e.currentTarget as HTMLVideoElement).play()} onMouseLeave={e => { const v = e.currentTarget as HTMLVideoElement; v.pause(); v.currentTime = 0; }} muted loop />
                            ) : <span style={{ fontSize: 28, opacity: 0.3 }}>🎬</span>}
                            <div style={{ position: "absolute", top: 4, right: 4, width: 8, height: 8, borderRadius: "50%", background: statusColor }} />
                            {scene.status !== "pending" && scene.status !== "completed" && scene.status !== "failed" && (
                              <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: "#333" }}>
                                <div style={{ height: "100%", background: "#A5B4FC", width: `${Math.max(scene.progress || 5, 5)}%`, transition: "width 0.5s" }} />
                              </div>
                            )}
                            {/* Retry button on failed */}
                            {scene.status === "failed" && (
                              <button onClick={ev => { ev.stopPropagation(); handleRetryScene(scene.id); }}
                                style={{ position: "absolute", bottom: 6, left: "50%", transform: "translateX(-50%)", padding: "3px 10px", fontSize: 9, fontWeight: 600, borderRadius: 4, border: "none", background: "#F87171", color: "#fff", cursor: "pointer" }}>
                                Retry
                              </button>
                            )}
                          </div>
                          <div style={{ padding: "6px 8px" }}>
                            <div style={{ fontSize: 11, fontWeight: 600, color: "#ccc" }}>Scene {scene.scene_number}</div>
                            <div style={{ fontSize: 9, color: "#888", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{scene.description}</div>
                            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>{scene.duration}s</div>
                          </div>
                        </div>
                        {idx < activeProject.scenes.length - 1 && <div style={{ width: 20, display: "flex", alignItems: "center", justifyContent: "center", color: "#444", fontSize: 14, flexShrink: 0 }}>→</div>}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Scene Detail */}
              {selectedSceneIdx !== null && activeProject.scenes[selectedSceneIdx] && (
                <SceneDetailPanel scene={activeProject.scenes[selectedSceneIdx]} editable={activeProject.status === "ready" || activeProject.status === "planning"} onUpdatePrompt={(prompt) => handleUpdateScene(activeProject.scenes[selectedSceneIdx].id, prompt)} onRetry={() => handleRetryScene(activeProject.scenes[selectedSceneIdx].id)} />
              )}

              {/* Final Video */}
              {activeProject.final_video_url && (
                <div style={{ padding: "16px 20px", borderTop: "1px solid #2a2a4a" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#4ADE80" }}>Final Stitched Video</span>
                    <a href={activeProject.final_video_url} download={`storyboard-${activeProject.id}.mp4`} style={{ fontSize: 11, color: "#A5B4FC", textDecoration: "none" }}>↓ Download MP4</a>
                  </div>
                  <video controls src={activeProject.final_video_url} style={{ width: "100%", borderRadius: 8, maxHeight: 360, background: "#000" }} />
                </div>
              )}

              {activeProject.error && <div style={{ padding: "10px 20px", color: "#F87171", fontSize: 12 }}>{activeProject.error}</div>}
            </div>
            );
          })()}
        </div>

        {/* Right: Past Projects Side Panel */}
        <div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8, display: "block" }}>Recent</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {projects.slice(0, 5).map(p => (
              <button key={p.id} onClick={() => { api.get(`/api/video/storyboard/${p.id}`).then(({ data }) => { setActiveProject(data); setSelectedSceneIdx(null); }); }}
                style={{
                  ...s.card, padding: "8px 10px", cursor: "pointer", textAlign: "left",
                  border: activeProject?.id === p.id ? "2px solid #6366F1" : "1px solid var(--border)",
                  background: activeProject?.id === p.id ? "#EDE9FE" : "var(--surface)",
                }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 11, fontWeight: 500 }}>#{p.id}</span>
                  <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3,
                    background: p.status === "completed" ? "#E8F5E9" : p.status === "failed" ? "#FEF2F2" : "#f0f0f5",
                    color: p.status === "completed" ? "#0D7C3D" : p.status === "failed" ? "#D32029" : "var(--text-muted)",
                  }}>{p.status}</span>
                </div>
                <div style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 2 }}>{p.scenes.length} scenes · {p.style}</div>
              </button>
            ))}
            {projects.length === 0 && <div style={{ fontSize: 11, color: "var(--text-muted)", padding: 10 }}>No projects yet</div>}
          </div>
        </div>
      </div>
      )}
    </div>
  );
}


function JobCard({ job }: { job: VideoJob }) {
  const isActive = !["completed", "failed", "cancelled"].includes(job.status);
  const styleColor = STYLE_COLORS[job.style] || "#666";

  return (
    <div style={{
      ...{
        background: "var(--surface)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)",
      },
      padding: 14, overflow: "hidden",
      borderLeft: `3px solid ${job.status === "failed" ? "var(--error)" : job.status === "completed" ? "var(--success, #0D7C3D)" : styleColor}`,
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600, textTransform: "uppercase",
            background: job.status === "completed" ? "#E8F5E9" : job.status === "failed" ? "#FEF2F2" : `${styleColor}14`,
            color: job.status === "completed" ? "#0D7C3D" : job.status === "failed" ? "var(--error)" : styleColor,
          }}>
            {job.status}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{job.style}</span>
        </div>
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
          {new Date(job.created_at).toLocaleTimeString()}
        </span>
      </div>

      {/* Progress bar for active jobs */}
      {isActive && (
        <div style={{ height: 4, borderRadius: 2, background: "var(--border-light, #eee)", marginBottom: 8, overflow: "hidden" }}>
          <div style={{
            height: "100%", borderRadius: 2,
            background: `linear-gradient(90deg, ${styleColor}, ${styleColor}AA)`,
            width: `${Math.max(job.progress || 5, 5)}%`,
            transition: "width 0.5s ease",
          }} />
        </div>
      )}

      {/* Script preview */}
      <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 6 }}>
        {job.script}
      </div>

      {/* Generated prompt (collapsed) */}
      {job.generated_prompt && (
        <details>
          <summary style={{ fontSize: 11, color: "var(--text-muted)", cursor: "pointer" }}>AI Prompt</summary>
          <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5, marginTop: 4, padding: 8, borderRadius: 4, background: "var(--bg)" }}>
            {job.generated_prompt}
          </div>
        </details>
      )}

      {/* Error */}
      {job.error && (
        <div style={{ fontSize: 11, color: "var(--error)", marginTop: 6 }}>{job.error}</div>
      )}

      {/* Video Player */}
      {job.status === "completed" && job.video_url && (
        <div style={{ marginTop: 10 }}>
          <video controls src={job.video_url} style={{ width: "100%", borderRadius: "var(--radius-sm)", maxHeight: 200 }} />
          <a href={job.video_url} download={`bdo-video-${job.id}.mp4`}
            style={{ display: "inline-block", marginTop: 6, fontSize: 11, color: "var(--accent)", textDecoration: "none" }}>
            ↓ Download MP4
          </a>
        </div>
      )}
    </div>
  );
}


function SceneDetailPanel({ scene, editable, onUpdatePrompt, onRetry }: {
  scene: VideoScene; editable: boolean; onUpdatePrompt: (prompt: string) => void; onRetry?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editPrompt, setEditPrompt] = useState(scene.prompt);

  // Sync when scene changes
  useEffect(() => { setEditPrompt(scene.prompt); setEditing(false); }, [scene.id, scene.prompt]);

  return (
    <div style={{ padding: "16px 20px", borderTop: "1px solid #2a2a4a", background: "#12121f" }}>
      <div style={{ display: "grid", gridTemplateColumns: scene.status === "completed" && scene.video_url ? "1fr 1fr" : "1fr", gap: 16 }}>
        {/* Left: Prompt */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#A5B4FC" }}>Scene {scene.scene_number} — {scene.description}</span>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span style={{ fontSize: 10, color: "#666" }}>{scene.duration}s</span>
              {editable && !editing && (
                <button onClick={() => setEditing(true)}
                  style={{ padding: "3px 10px", fontSize: 10, borderRadius: 4, border: "1px solid #444",
                    background: "transparent", color: "#A5B4FC", cursor: "pointer" }}>Edit Prompt</button>
              )}
            </div>
          </div>
          {editing ? (
            <div>
              <textarea value={editPrompt} onChange={e => setEditPrompt(e.target.value)} rows={5}
                style={{ width: "100%", padding: 10, borderRadius: 6, border: "1px solid #444", background: "#1a1a2e",
                  color: "#ccc", fontSize: 12, resize: "vertical", fontFamily: "'Cascadia Code', monospace", lineHeight: 1.6 }} />
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button onClick={() => { onUpdatePrompt(editPrompt); setEditing(false); }}
                  style={{ padding: "6px 16px", fontSize: 11, borderRadius: 4, border: "none", background: "#6366F1", color: "#fff", cursor: "pointer" }}>Save</button>
                <button onClick={() => { setEditPrompt(scene.prompt); setEditing(false); }}
                  style={{ padding: "6px 16px", fontSize: 11, borderRadius: 4, border: "1px solid #444", background: "transparent", color: "#888", cursor: "pointer" }}>Cancel</button>
              </div>
            </div>
          ) : (
            <div style={{ padding: 12, borderRadius: 6, background: "#1a1a2e", border: "1px solid #2a2a4a",
              fontSize: 12, color: "#999", lineHeight: 1.6, maxHeight: 150, overflow: "auto" }}>
              {scene.prompt}
            </div>
          )}
          {scene.error && (
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 11, color: "#F87171" }}>{scene.error}</span>
              {scene.status === "failed" && onRetry && (
                <button onClick={onRetry} style={{ padding: "4px 14px", fontSize: 10, fontWeight: 600, borderRadius: 4, border: "none", background: "#F87171", color: "#fff", cursor: "pointer" }}>
                  Retry Scene
                </button>
              )}
            </div>
          )}
        </div>

        {/* Right: Video Preview */}
        {scene.status === "completed" && scene.video_url && (
          <div>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#4ADE80", marginBottom: 8, display: "block" }}>Preview</span>
            <video controls src={scene.video_url} style={{ width: "100%", borderRadius: 6, background: "#000" }} />
          </div>
        )}
      </div>
    </div>
  );
}
