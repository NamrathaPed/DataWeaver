import { Routes, Route, Navigate } from "react-router-dom";
import UploadPage from "@/pages/UploadPage";
import DashboardPage from "@/pages/DashboardPage";
import AgentPage from "@/pages/AgentPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<UploadPage />} />
      <Route path="/agent/:sessionId" element={<AgentPage />} />
      <Route path="/dashboard/:sessionId" element={<DashboardPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
