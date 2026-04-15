import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

export default api;

// --- API functions ---

export interface VoiceInfo {
  id: string;
  name: string;
  locale?: string;
  gender?: string;
}

export interface VoicesResponse {
  voices: Record<string, VoiceInfo[]>;
  formats: Record<string, string[]>;
}

export interface GenerateRequest {
  text: string;
  voice?: string;
  rate?: string;
  pitch?: string;
  volume?: string;
  language?: string;
  format?: string;
  translate?: boolean;
  pronunciation?: Record<string, string>;
  system_prompt?: string;
  instructions?: string;
  script_id?: number;
}

export interface AlternateResult {
  text_output?: string;
  ssml?: string;
  local_audio_file?: string;
  audio_url?: string;
  storage_url?: string | null;
  error?: string;
}

export interface GenerateResponse {
  method: string;
  text_output: string;
  original_text?: string;
  ssml?: string;
  local_audio_file: string;
  audio_url?: string;
  speech_output?: string;
  storage_url?: string | null;
  storage_error?: string | null;
  alternate?: AlternateResult;
}

export interface Script {
  id: number;
  title: string;
  text: string;
  language: string;
  created_at: string;
  updated_at: string;
  generations?: Generation[];
}

export interface Generation {
  id: number;
  script_id: number | null;
  method: string;
  voice: string | null;
  params_json: string | null;
  audio_file: string | null;
  format: string;
  text_output: string | null;
  created_at: string;
}

export async function fetchVoices(): Promise<VoicesResponse> {
  const { data } = await api.get<VoicesResponse>("/api/voices");
  return data;
}

export async function generateAudio(
  method: string,
  params: GenerateRequest
): Promise<GenerateResponse> {
  const { data } = await api.post<GenerateResponse>(
    `/api/generate/${method}`,
    params
  );
  return data;
}

export async function fetchScripts(): Promise<Script[]> {
  const { data } = await api.get<Script[]>("/api/scripts");
  return data;
}

export async function fetchScript(id: number): Promise<Script> {
  const { data } = await api.get<Script>(`/api/scripts/${id}`);
  return data;
}

export async function createScript(
  title: string,
  text: string,
  language: string = "fil-PH"
): Promise<Script> {
  const { data } = await api.post<Script>("/api/scripts", {
    title,
    text,
    language,
  });
  return data;
}

export async function updateScript(
  id: number,
  updates: Partial<Pick<Script, "title" | "text" | "language">>
): Promise<Script> {
  const { data } = await api.put<Script>(`/api/scripts/${id}`, updates);
  return data;
}

export async function deleteScript(id: number): Promise<void> {
  await api.delete(`/api/scripts/${id}`);
}
