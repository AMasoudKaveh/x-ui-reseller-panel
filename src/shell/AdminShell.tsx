import { useEffect, useState } from "react";
import AdminSidebar, { type AdminPage } from "../components/AdminSidebar";
import AdminDashboardPage from "../pages/admin/AdminDashboardPage";
import RepresentativesPage from "../pages/admin/RepresentativesPage";
import AdminClientsPage from "../pages/admin/AdminClientsPage";
import InboundsPage from "../pages/admin/InboundsPage";
import AdminSettingsPage from "../pages/admin/AdminSettingsPage";

function getAdminPageFromHash(): AdminPage {
  const part = window.location.hash.replace(/^#\/admin\/?/, "").split(/[/?#]/)[0];
  if (part === "resellers" || part === "clients" || part === "inbounds" || part === "settings") return part;
  return "dashboard";
}

export default function AdminShell({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [page, setPage] = useState<AdminPage>(getAdminPageFromHash);

  useEffect(() => {
    const sync = () => setPage(getAdminPageFromHash());
    window.addEventListener("hashchange", sync);
    sync();
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const navigate = (next: AdminPage) => {
    setPage(next);
    const target = `#/admin/${next}`;
    if (window.location.hash !== target) window.location.hash = target;
  };

  return (
    <div className="app-shell">
      <AdminSidebar page={page} setPage={navigate} username={username} onLogout={onLogout} />
      <div className="content-shell">
        {page === "dashboard" && <AdminDashboardPage onNavigate={navigate} />}
        {page === "resellers" && <RepresentativesPage />}
        {page === "clients" && <AdminClientsPage />}
        {page === "inbounds" && <InboundsPage />}
        {page === "settings" && <AdminSettingsPage />}
      </div>
    </div>
  );
}
