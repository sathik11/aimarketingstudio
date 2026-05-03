import { useState, useEffect } from "react";
import { BrowserRouter, useLocation } from "react-router-dom";
import api from "./services/api";
import NavBar from "./components/NavBar";
import LoginPage from "./pages/LoginPage";
import GeneratePage from "./pages/GeneratePage";
import ScriptsPage from "./pages/ScriptsPage";
import SsmlPlayground from "./pages/SsmlPlayground";
import SettingsPage from "./pages/SettingsPage";
import VideoPage from "./pages/VideoPage";
import AssetsPage from "./pages/AssetsPage";

interface UserInfo {
  id: number; username: string; name: string;
  max_iterations: number; used_iterations: number; iterations_remaining: number;
  max_videos?: number; used_videos?: number; videos_remaining?: number;
  max_images?: number; used_images?: number; images_remaining?: number;
}

function AppRoutes({ onRefreshUser }: { onRefreshUser: () => void }) {
  const location = useLocation();
  const path = location.pathname;
  return (
    <>
      <div style={{ display: path === "/generate" || path === "/" ? "block" : "none" }}><GeneratePage onGenerated={onRefreshUser} /></div>
      <div style={{ display: path === "/video" ? "block" : "none" }}><VideoPage onGenerated={onRefreshUser} /></div>
      <div style={{ display: path === "/assets" ? "block" : "none" }}><AssetsPage /></div>
      <div style={{ display: path === "/ssml" ? "block" : "none" }}><SsmlPlayground /></div>
      <div style={{ display: path === "/settings" ? "block" : "none" }}><SettingsPage /></div>
      <div style={{ display: path === "/scripts" ? "block" : "none" }}><ScriptsPage /></div>
    </>
  );
}

function App() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [checking, setChecking] = useState(true);

  const checkAuth = () => {
    api.get("/api/auth/me").then(({ data }) => setUser(data)).catch(() => setUser(null)).finally(() => setChecking(false));
  };

  useEffect(() => { checkAuth(); }, []);

  const handleLogout = () => { api.post("/api/auth/logout").finally(() => setUser(null)); };

  if (checking) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", color: "#999" }}>Loading...</div>;
  if (!user) return <LoginPage onLogin={checkAuth} />;

  return (
    <BrowserRouter>
      <NavBar user={user} onLogout={handleLogout} />
      <AppRoutes onRefreshUser={checkAuth} />
    </BrowserRouter>
  );
}

export default App;
