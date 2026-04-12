import { Routes, Route, Navigate } from "react-router-dom";
import LandingPage from "@/pages/LandingPage";
import ChatPage from "@/pages/ChatPage";
import DashboardPage from "@/pages/DashboardPage";

export default function App() {
  return (
    <Routes>
      {/* Landing / informational page */}
      <Route path="/" element={<LandingPage />} />

      {/* Main application */}
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/chat/:sessionId" element={<ChatPage />} />

      {/* Full analysis view */}
      <Route path="/dashboard/:sessionId" element={<DashboardPage />} />

      {/* Legacy redirects */}
      <Route path="/agent/:sessionId" element={<Navigate to="/chat" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
