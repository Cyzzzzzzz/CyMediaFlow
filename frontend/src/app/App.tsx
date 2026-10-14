import { Navigate, Route, Routes } from "react-router-dom";
import { lazy, Suspense } from "react";
import { SideRail } from "../components/SideRail";
import { AccessGate } from "../features/access/AccessGate";
import { useQuery } from "@tanstack/react-query";
import { accessApi } from "../features/access/accessApi";

const LibraryPage = lazy(() =>
  import("../features/library/LibraryPage").then((m) => ({
    default: m.LibraryPage,
  })),
);
const SettingsPage = lazy(() =>
  import("../features/settings/SettingsPage").then((m) => ({
    default: m.SettingsPage,
  })),
);
const AutomationPage = lazy(() =>
  import("../features/automation/AutomationPage").then((m) => ({
    default: m.AutomationPage,
  })),
);
const SecuritySettings = lazy(() =>
  import("../features/access/SecuritySettings").then((m) => ({
    default: m.SecuritySettings,
  })),
);

export function App() {
  return (
    <AccessGate>
      <div className="app-shell">
        <SideRail />
        <main className="app-content">
          <Suspense fallback={<div className="page-state">正在载入…</div>}>
            <Routes>
              <Route path="/" element={<LibraryPage />} />
              <Route path="/settings" element={<AccountSettings />} />
              <Route path="/automation" element={<AutomationPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </AccessGate>
  );
}

function AccountSettings() {
  const status = useQuery({
    queryKey: ["access", "status"],
    queryFn: accessApi.status,
  });
  if (status.data?.enabled && status.data.user?.role !== "admin")
    return (
      <div className="automation-page">
        <h1>账号设置</h1>
        <SecuritySettings />
      </div>
    );
  return <SettingsPage />;
}
