import { Activity, Network, Search, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  getLiveAdminInbounds,
  type LiveAdminInbound,
} from "../../api/adminInbounds";

const LIVE_REFRESH_MS = 3000;

function formatBytes(value: number): string {
  const bytes = Math.max(0, Number(value || 0));
  if (bytes < 1024) return `${bytes.toFixed(0)} B`;
  const units = ["KB", "MB", "GB", "TB", "PB"];
  let current = bytes / 1024;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024;
    index += 1;
  }
  const digits = current >= 100 ? 0 : current >= 10 ? 1 : 2;
  return `${current.toFixed(digits)} ${units[index]}`;
}

function formatSpeed(value: number): string {
  const bps = Math.max(0, Number(value || 0));
  return bps > 0 ? `${formatBytes(bps)}/s` : "—";
}

function protocolText(item: LiveAdminInbound): string {
  return [item.protocol, item.network, item.security]
    .filter(Boolean)
    .join(" · ")
    .toUpperCase();
}

export default function InboundsPage() {
  const [search, setSearch] = useState("");
  const [inbounds, setInbounds] = useState<LiveAdminInbound[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    const load = async (silent = false) => {
      if (!silent && alive) setLoading(true);
      try {
        const rows = await getLiveAdminInbounds();
        if (!alive) return;
        setInbounds(rows);
        setError("");
      } catch (err) {
        if (!alive) return;
        if (!silent) {
          setError(err instanceof Error ? err.message : "Unable to load inbounds");
        }
      } finally {
        if (!silent && alive) setLoading(false);
      }
    };

    void load(false);

    const timer = window.setInterval(() => {
      void load(true);
    }, LIVE_REFRESH_MS);

    const onFocus = () => void load(true);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void load(true);
    };

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const visible = useMemo(
    () =>
      inbounds.filter((item) =>
        [
          item.name,
          item.node,
          item.protocol,
          item.network,
          item.security,
          item.port,
          item.id,
        ]
          .join(" ")
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [inbounds, search],
  );

  return (
    <>
      <header className="page-header">
        <div>
          <div className="page-title-row">
            <h1>Inbounds</h1>
            <span className="help-chip">?</span>
          </div>
          <p>Live read-only inbound monitoring</p>
        </div>
      </header>

      <main className="ad-page">
        <section className="up-stats-grid">
          <section className="up-stat-card">
            <div className="up-stat-left"><Network size={23}/><span>Inbounds</span></div>
            <strong>{loading && inbounds.length === 0 ? "..." : inbounds.length}</strong>
          </section>
          <section className="up-stat-card">
            <div className="up-stat-left"><Activity size={23}/><span>Online</span></div>
            <strong>{loading && inbounds.length === 0 ? "..." : inbounds.filter((x) => x.enabled).length}</strong>
          </section>
          <section className="up-stat-card">
            <div className="up-stat-left"><UsersRound size={23}/><span>Clients</span></div>
            <strong>{loading && inbounds.length === 0 ? "..." : inbounds.reduce((sum, x) => sum + x.clients, 0).toLocaleString()}</strong>
          </section>
        </section>

        <section className="up-toolbar">
          <div className="up-search-box">
            <Search size={18}/>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search inbound"/>
          </div>
        </section>

        <section className="ib-table-card">
          <div className="ib-table-head">
            <div>Status</div><div>Inbound</div><div>Node</div><div>Port</div><div>Protocol</div><div>Clients / Online</div><div>Traffic</div><div>Speed</div>
          </div>

          {visible.map((item) => (
            <div className="ib-row" key={item.id}>
              <div>
                <span className="ib-online-pill"><span/>{item.enabled ? "Online" : "Disabled"}</span>
              </div>
              <div className="ib-name"><strong>{item.name}</strong><span>#{item.id}</span></div>
              <div>{item.node || "Local panel"}</div>
              <div>{item.port}</div>
              <div><span className="ib-protocol">{protocolText(item) || "—"}</span></div>
              <div className="ib-users"><strong>{item.clients.toLocaleString()}</strong><span>{item.online} online</span></div>
              <div>{formatBytes(item.traffic_bytes)}</div>
              <div>{formatSpeed(item.speed_bps)}</div>
            </div>
          ))}

          {!loading && visible.length === 0 ? (
            <div className="ib-row"><div>{error || "No inbounds found"}</div></div>
          ) : null}
        </section>

        <div className="ib-note">Inbound configuration is intentionally read-only in this panel. Changes remain in the primary x-ui panel.</div>
      </main>
    </>
  );
}
