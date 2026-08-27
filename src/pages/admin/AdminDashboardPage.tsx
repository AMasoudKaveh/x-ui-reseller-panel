import { Database, Network, ShieldCheck, UsersRound, Wifi } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { AdminPage } from "../../components/AdminSidebar";
import {
  getAdminDashboard,
  type AdminDashboardData,
} from "../../api/adminDashboard";

const GB = 1024 ** 3;

const emptyDashboard: AdminDashboardData = {
  summary: {
    representatives: 0,
    active: 0,
    suspended: 0,
    clients: 0,
    online: 0,
    quota_bytes: 0,
    used_bytes: 0,
    remaining_bytes: 0,
    inbounds: 0,
    available_inbounds: 0,
  },
  representatives: [],
  inbounds: [],
  inbounds_live: false,
  trend: [],
};

function bytesToGB(value: number): number {
  return Number(value || 0) / GB;
}

function trafficGB(value: number, digits = 1): string {
  return `${bytesToGB(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} GB`;
}

function dayLabel(value: string): string {
  const parts = String(value || "").split("-");
  if (parts.length !== 3) return value;
  return `${parts[1]}/${parts[2]}`;
}

export default function AdminDashboardPage({ onNavigate }: { onNavigate: (page: AdminPage) => void }) {
  const [dashboard, setDashboard] = useState<AdminDashboardData>(emptyDashboard);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      try {
        const result = await getAdminDashboard();
        if (alive) setDashboard(result);
      } catch {
        // Keep the latest successful snapshot if backend/x-ui is temporarily unavailable.
      }
    };

    void load();

    const timer = window.setInterval(() => void load(), 3000);
    const focus = () => void load();
    const visibility = () => {
      if (document.visibilityState === "visible") void load();
    };

    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", visibility);

    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);

  const summary = dashboard.summary;
  const quotaGB = bytesToGB(summary.quota_bytes);
  const usedGB = bytesToGB(summary.used_bytes);
  const quotaPercent = summary.quota_bytes > 0
    ? Math.min(100, summary.used_bytes / summary.quota_bytes * 100)
    : 0;

  const chart = useMemo(() => {
    const max = Math.max(0, ...dashboard.trend.map(item => item.bytes));
    return dashboard.trend.map((item) => ({
      ...item,
      height: max > 0
        ? Math.max(item.bytes > 0 ? 4 : 0, item.bytes / max * 100)
        : 0,
    }));
  }, [dashboard.trend]);

  const cards = [
    { icon: ShieldCheck, title: "Representatives", value: summary.representatives, meta: `${summary.active} active · ${summary.suspended} suspended` },
    { icon: UsersRound, title: "Clients", value: summary.clients, meta: "Across all representatives" },
    { icon: Wifi, title: "Online", value: summary.online, meta: "Current active connections" },
    { icon: Database, title: "Allocated Traffic", value: trafficGB(summary.quota_bytes), meta: `${trafficGB(summary.used_bytes)} consumed` },
    { icon: Network, title: "Inbounds", value: summary.inbounds, meta: `${summary.available_inbounds} available` }
  ];

  return (
    <>
      <header className="page-header">
        <div><div className="page-title-row"><h1>Dashboard</h1><span className="help-chip">?</span></div><p>Super Admin Management Dashboard</p></div>
      </header>

      <main className="ad-page">
        <section className="ad-stats-grid">
          {cards.map(({icon:Icon,title,value,meta}) => (
            <article className="ad-stat-card" key={title}>
              <div className="ad-stat-title"><div className="ad-icon-box"><Icon size={20}/></div><span>{title}</span></div>
              <strong>{value}</strong><small>{meta}</small>
            </article>
          ))}
        </section>

        <section className="ad-traffic-panel">
          <div className="ad-panel-head"><div><h2>Representative Traffic</h2><p>Consumed traffic compared with allocated quota</p></div><strong>{usedGB.toFixed(1)} / {quotaGB.toLocaleString()} GB</strong></div>
          <div className="ad-master-progress"><i style={{width:`${quotaPercent}%`}}/></div>
          <div className="ad-master-meta"><span>{quotaPercent.toFixed(1)}% used</span><span>{trafficGB(summary.remaining_bytes)} remaining across accounts</span></div>
        </section>

        <div className="ad-dashboard-lower">
          <section className="ad-panel">
            <div className="ad-panel-head"><div><h2>Representatives</h2><p>Quota, usage and current status</p></div><button type="button" onClick={()=>onNavigate("resellers")}>View all</button></div>
            <div className="ad-list">
              {dashboard.representatives.map(item => {
                const pct = item.quota_bytes > 0
                  ? Math.min(100, item.used_bytes / item.quota_bytes * 100)
                  : 0;
                return <div className="ad-list-row" key={item.id}>
                  <div className="ad-list-main"><strong>{item.username}</strong><span>{item.users} users · {item.online} online</span></div>
                  <div className="ad-list-usage"><div className="ad-line-progress"><i style={{width:`${pct}%`}}/></div><span>{bytesToGB(item.used_bytes).toFixed(1)} / {bytesToGB(item.quota_bytes).toFixed(1)} GB</span></div>
                  <span className={`ad-status ${item.status === "Active" ? "active" : "suspended"}`}>{item.status}</span>
                </div>;
              })}
            </div>
          </section>

          <section className="ad-panel">
            <div className="ad-panel-head"><div><h2>Inbound Health</h2><p>Read-only live infrastructure overview</p></div><button type="button" onClick={()=>onNavigate("inbounds")}>View all</button></div>
            <div className="ad-list">
              {dashboard.inbounds.map(item => <div className="ad-list-row" key={item.id}>
                <span className="ad-health-dot"/><div className="ad-list-main"><strong>{item.name}</strong><span>{item.protocol} · :{item.port}</span></div><div className="ad-right-stat"><strong>{item.online}</strong><span>online</span></div>
              </div>)}
            </div>
          </section>
        </div>

        <section className="ad-panel ad-chart-panel">
          <div className="ad-panel-head"><div><h2>Traffic Trend</h2><p>Representative usage during the last 7 days</p></div><div className="ad-range">7 days</div></div>
          <div className="ad-chart-bars">{chart.map((item,index)=><div key={item.date}><i style={{height:`${item.height}%`}} className={index===chart.length-1?"current":""}/><span>{dayLabel(item.date)}</span></div>)}</div>
        </section>
      </main>
    </>
  );
}
