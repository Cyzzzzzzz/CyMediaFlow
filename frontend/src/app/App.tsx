import { Navigate, Route, Routes } from "react-router-dom";
import { SideRail } from "../components/SideRail";
import { LibraryPage } from "../features/library/LibraryPage";
import { SettingsPage } from "../features/settings/SettingsPage";

export function App() {
  return <div className="app-shell"><SideRail /><main className="app-content"><Routes>
    <Route path="/" element={<LibraryPage />} />
    <Route path="/settings" element={<SettingsPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></main></div>;
}
