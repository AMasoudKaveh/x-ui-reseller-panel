import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Ban, CalendarDays, ChevronDown, Copy, Link2, MoreVertical, PencilLine,
  QrCode, RefreshCcw, RotateCcw, Search, SortAsc, Trash2, UserCheck,
  UsersRound, Wifi
} from "lucide-react";
import {
  getAdminClientAccess,
  getAdminClients,
  removeAdminClient,
  resetAdminClientUsage,
  revokeAdminClientSubscription,
  toggleAdminClient,
  type AdminClientAccess,
  type AdminClientRow,
  type AdminClientsSummary
} from "../../api/adminClients";
import AdminModifyUserModal from "../../components/AdminModifyUserModal";
import AdminSubscriptionModal from "../../components/AdminSubscriptionModal";

type SortKey = "created" | "username" | "owner";

const EMPTY_SUMMARY: AdminClientsSummary = {
  total: 0,
  active: 0,
  online: 0,
  disabled: 0,
  expired: 0
};

function formatBytes(value: number): string {
  const n = Math.max(0, Number(value || 0));
  if (n < 1024) return `${Math.round(n)} B`;
  const units = ["KB", "MB", "GB", "TB", "PB"];
  let v = n;
  let i = -1;
  do {
    v /= 1024;
    i += 1;
  } while (v >= 1024 && i < units.length - 1);
  const digits = v >= 100 ? 0 : v >= 10 ? 1 : 2;
  return `${v.toFixed(digits)} ${units[i]}`;
}

function expiryText(value: string): string {
  if (value === "∞") return "No expiry";
  if (value === "Expired") return "Expired";
  if (value.startsWith("After first use")) return value;
  return `Expires in ${value}`;
}

export default function AdminClientsPage() {
  const [rows, setRows] = useState<AdminClientRow[]>([]);
  const [summary, setSummary] = useState<AdminClientsSummary>(EMPTY_SUMMARY);
  const [search, setSearch] = useState("");
  const [sortOpen, setSortOpen] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("created");
  const [modify, setModify] = useState<number | null>(null);
  const [qrAccess, setQrAccess] = useState<AdminClientAccess | null>(null);
  const [menuFor, setMenuFor] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(true);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 1800);
  }, []);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const result = await getAdminClients();
      setRows(result.clients || []);
      setSummary(result.summary || EMPTY_SUMMARY);
    } catch (err) {
      if (!silent) showToast(err instanceof Error ? err.message : "Unable to load clients");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    let alive = true;
    void load(false);

    const refresh = () => {
      if (alive) void load(true);
    };
    const timer = window.setInterval(refresh, 3000);
    window.addEventListener("focus", refresh);

    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [load]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = !q
      ? rows
      : rows.filter(c => [c.username, c.owner, c.inbound, c.status, c.disable_reason]
          .join(" ").toLowerCase().includes(q));

    return [...filtered].sort((a, b) => {
      if (sortKey === "username") return a.username.localeCompare(b.username);
      if (sortKey === "owner") return a.owner.localeCompare(b.owner);
      return b.id - a.id;
    });
  }, [rows, search, sortKey]);

  const copy = async (text: string, msg: string) => {
    if (!text) {
      showToast("No link returned");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      showToast(msg);
    } catch {
      showToast("Clipboard unavailable");
    }
  };

  const withAccess = async (client: AdminClientRow, mode: "subscription" | "configs" | "qr") => {
    try {
      const access = await getAdminClientAccess(client.id);
      if (mode === "subscription") {
        await copy(access.subscription_url, "Subscription Link Copied");
      } else if (mode === "configs") {
        await copy((access.links || []).join("\n"), "All Links Copied");
      } else {
        setQrAccess(access);
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Unable to load client access");
    }
  };

  const toggle = async (client: AdminClientRow) => {
    setMenuFor(null);
    try {
      await toggleAdminClient(client.id, !client.enabled);
      showToast(client.enabled ? "Client Disabled" : "Client Enabled");
      await load(true);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Status update failed");
    }
  };

  const resetUsage = async (client: AdminClientRow) => {
    setMenuFor(null);
    if (!window.confirm(`Reset x-ui traffic for ${client.username}? Representative cumulative usage will be preserved.`)) return;
    try {
      await resetAdminClientUsage(client.id);
      showToast("Usage Reset");
      await load(true);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Reset failed");
    }
  };

  const revoke = async (client: AdminClientRow) => {
    setMenuFor(null);
    if (!window.confirm(`Revoke subscription for ${client.username}? UUID will be preserved.`)) return;
    try {
      await revokeAdminClientSubscription(client.id);
      showToast("Subscription Revoked");
      await load(true);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Revoke failed");
    }
  };

  const remove = async (client: AdminClientRow) => {
    setMenuFor(null);
    if (!window.confirm(`Remove ${client.username} from x-ui and this panel? Historical representative usage will be preserved.`)) return;
    try {
      await removeAdminClient(client.id);
      showToast("Client Removed");
      await load(true);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Remove failed");
    }
  };

  return <>
    <header className="page-header users-header"><div><div className="page-title-row"><h1>Clients</h1><span className="help-chip">?</span></div><p>View all clients created by representatives</p></div></header>

    <main className="up-page" onClick={()=>{setSortOpen(false);setMenuFor(null)}}>
      <section className="up-stats-grid">
        <section className="up-stat-card"><div className="up-stat-left"><UsersRound size={23}/><span>Clients</span></div><strong>{loading ? "…" : summary.total}</strong></section>
        <section className="up-stat-card"><div className="up-stat-left"><Wifi size={23}/><span>Online</span></div><strong>{loading ? "…" : summary.online}</strong></section>
        <section className="up-stat-card"><div className="up-stat-left"><UserCheck size={23}/><span>Active</span></div><strong>{loading ? "…" : summary.active}</strong></section>
      </section>

      <section className="up-toolbar">
        <div className="up-search-box"><Search size={18}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search client, representative or inbound"/></div>
        <div className="up-sort-wrap">
          <button className={`up-tool-button ${sortOpen?"active":""}`} onClick={e=>{e.stopPropagation();setSortOpen(v=>!v)}}><SortAsc size={19}/></button>
          {sortOpen&&<div className="up-sort-menu ac-sort" onClick={e=>e.stopPropagation()}>
            <div className="up-sort-title">Sort Options</div>
            <button className={`rp-sort-option ${sortKey==="created"?"active":""}`} onClick={()=>{setSortKey("created");setSortOpen(false)}}><CalendarDays size={16}/>Created at</button>
            <button className={`rp-sort-option ${sortKey==="username"?"active":""}`} onClick={()=>{setSortKey("username");setSortOpen(false)}}><UsersRound size={16}/>Username</button>
            <button className={`rp-sort-option ${sortKey==="owner"?"active":""}`} onClick={()=>{setSortKey("owner");setSortOpen(false)}}><UserCheck size={16}/>Owner</button>
          </div>}
        </div>
      </section>

      <section className="ac-table-card">
        <div className="ac-table-head"><div>Client</div><div>Owner</div><div>Status / Expire</div><div>Inbound</div><div>Data Usage</div><div/></div>
        {visible.map(c=>{
          const percent = c.limit_bytes > 0 ? Math.min(100, c.usage_percent) : 0;
          return <div className="ac-row" key={c.id}>
            <div className="up-name-cell"><span className={`up-presence ${c.online?"online":""}`}/><div className="up-username-line"><strong>{c.username}</strong><span>#{c.id}</span><span>{c.age}</span></div></div>
            <div><span className="ac-owner-chip">{c.owner}</span></div>
            <div className="up-status-cell"><span className={c.status==="Active"?"up-active-pill":"ac-disabled-pill"}><Wifi size={14}/>{c.status}</span><span className="up-expiry">{expiryText(c.expires_in)}</span></div>
            <div className="ac-inbound">{c.inbound}</div>
            <div className="up-usage-cell"><div className="up-usage-progress"><div className="up-usage-fill" style={{width:`${percent}%`}}/></div><div className="up-usage-line"><span>{formatBytes(c.used_bytes)} / {c.limit_bytes ? formatBytes(c.limit_bytes) : "∞"}</span><span>Total: {formatBytes(c.used_bytes)}</span></div></div>
            <div className="up-actions" onClick={e=>e.stopPropagation()}>
              <button title="Copy Subscription" onClick={()=>void withAccess(c,"subscription")}><Link2 size={18}/></button>
              <button title="Copy Configs" onClick={()=>void withAccess(c,"configs")}><Copy size={18}/></button>
              <button title="QR" onClick={()=>void withAccess(c,"qr")}><QrCode size={18}/></button>
              <button title="Modify" onClick={()=>setModify(c.id)}><PencilLine size={18}/></button>
              <div className="ua-action-wrap">
                <button title="More" onClick={()=>setMenuFor(menuFor===c.id?null:c.id)}><MoreVertical size={18}/></button>
                {menuFor===c.id&&<div className="ua-more-menu rp-more-menu">
                  <button type="button" onClick={()=>{setModify(c.id);setMenuFor(null)}}><PencilLine size={18}/><span>Modify</span></button>
                  <button type="button" onClick={()=>void revoke(c)}><RotateCcw size={18}/><span>Revoke Subscription</span></button>
                  <button type="button" onClick={()=>void resetUsage(c)}><RefreshCcw size={18}/><span>Reset Usage</span></button>
                  <div className="ua-menu-divider"/>
                  <button type="button" className="ua-warning" onClick={()=>void toggle(c)}><Ban size={18}/><span>{c.enabled?"Disable":"Enable"}</span></button>
                  <button type="button" className="ua-danger" onClick={()=>void remove(c)}><Trash2 size={18}/><span>Remove</span></button>
                </div>}
              </div>
            </div>
          </div>;
        })}
        {!loading && !visible.length ? <div style={{padding:"24px",color:"var(--muted)",fontSize:"11px"}}>No clients found.</div> : null}
      </section>
    </main>

    {toast&&<div className="ua-global-toast">{toast}</div>}
    <AdminModifyUserModal open={Boolean(modify)} userId={modify} onClose={()=>setModify(null)} onSaved={()=>load(true)}/>
    <AdminSubscriptionModal open={Boolean(qrAccess)} access={qrAccess} onClose={()=>setQrAccess(null)} onCopy={(text,msg)=>void copy(text,msg)}/>
  </>;
}
