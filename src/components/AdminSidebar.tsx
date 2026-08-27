import {
  ChevronDown,
  CircleHelp,
  LayoutDashboard,
  LogOut,
  Moon,
  Network,
  Settings2,
  ShieldCheck,
  Sun,
  UserRound,
  UsersRound
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useThemeSettings } from "../theme/ThemeProvider";

export type AdminPage = "dashboard" | "resellers" | "clients" | "inbounds" | "settings";

type Props = {
  page: AdminPage;
  setPage: (page: AdminPage) => void;
  username: string;
  onLogout: () => void;
};

const nav = [
  { icon: LayoutDashboard, label: "Dashboard", page: "dashboard" as AdminPage },
  { icon: ShieldCheck, label: "Representatives", page: "resellers" as AdminPage },
  { icon: UsersRound, label: "Clients", page: "clients" as AdminPage },
  { icon: Network, label: "Inbounds", page: "inbounds" as AdminPage },
  { icon: Settings2, label: "Settings", page: "settings" as AdminPage }
];

export default function AdminSidebar({ page, setPage, username, onLogout }: Props) {
  const { resolvedMode, toggleQuickMode } = useThemeSettings();
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  return (
    <aside className="sidebar">
      <div className="brand-row">
        <div className="brand-mark">X</div>
        <div className="brand-copy"><div className="brand-name">x-ui</div><div className="brand-version">Admin Panel</div></div>
      </div>

      <div className="nav-section-label">Platform</div>
      <nav className="nav-list">
        {nav.map((item) => {
          const Icon = item.icon;
          return (
            <button className={`nav-item ${page === item.page ? "active" : ""}`} key={item.page} type="button" onClick={() => setPage(item.page)}>
              <Icon size={18} strokeWidth={1.8}/><span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-spacer" />

      <div className="sidebar-support">
        <div className="support-row"><CircleHelp size={18}/><span>Support Us</span></div>
        <div className="sidebar-utility-row">
          <button className="mini-button" type="button" onClick={toggleQuickMode} title={resolvedMode === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
            {resolvedMode === "dark" ? <Sun size={16}/> : <Moon size={16}/>}
          </button>
        </div>
      </div>

      <div className="account-menu-wrap" ref={accountRef}>
        {accountOpen && (
          <div className="account-popover">
            <div className="account-popover-main">
              <div className="account-popover-title-row"><strong>{username}</strong><span className="account-role-chip"><UserRound size={14}/>super admin</span></div>
              <div className="account-popover-stat"><ShieldCheck size={15}/><span>Full management access</span></div>
              <div className="account-popover-stat"><Network size={15}/><span>All inbounds visible</span></div>
              <div className="account-popover-stat"><UsersRound size={15}/><span>All representatives & clients</span></div>
            </div>
            <button className="account-logout-button" type="button" onClick={onLogout}><LogOut size={19}/><span>Log out</span></button>
          </div>
        )}

        <button className={`account-panel account-panel-button ${accountOpen ? "open" : ""}`} type="button" onClick={() => setAccountOpen(v => !v)}>
          <div className="account-main-row"><div><div className="account-name">{username}</div><div className="account-usage">Super Administrator</div></div><ChevronDown className="account-chevron" size={17}/></div>
        </button>
      </div>
    </aside>
  );
}
