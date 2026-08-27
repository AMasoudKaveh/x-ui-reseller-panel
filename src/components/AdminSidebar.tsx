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

        <a
          className="github-project-link"
          href="https://github.com/AMasoudKaveh/x-ui-reseller-panel"
          target="_blank"
          rel="noopener noreferrer"
          title="GitHub Project"
        >
          <svg
            className="github-project-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              fill="currentColor"
              d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.02c-3.22.7-3.9-1.37-3.9-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.57-.29-5.27-1.29-5.27-5.74 0-1.27.45-2.3 1.19-3.11-.12-.29-.52-1.47.11-3.07 0 0 .97-.31 3.16 1.19a10.9 10.9 0 0 1 5.76 0c2.19-1.5 3.16-1.19 3.16-1.19.63 1.6.23 2.78.11 3.07.74.81 1.19 1.84 1.19 3.11 0 4.46-2.71 5.44-5.3 5.73.42.36.79 1.07.79 2.16v3.04c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z"
            />
          </svg>

          <span>GitHub Project</span>
        </a>

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
