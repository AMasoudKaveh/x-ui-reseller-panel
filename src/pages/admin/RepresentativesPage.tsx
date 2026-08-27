import { useEffect, useMemo, useState } from "react";
import {
  Ban,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  MoreVertical,
  PencilLine,
  Plus,
  RefreshCcw,
  Search,
  Server,
  ShieldCheck,
  SortAsc,
  Trash2,
  UserCheck,
  UsersRound,
  Wifi,
  X
} from "lucide-react";
import {
  createAdminRepresentative,
  deleteAdminRepresentative,
  getAdminInbounds,
  getAdminRepresentatives,
  resetAdminRepresentativeUsage,
  setAdminRepresentativeStatus,
  updateAdminRepresentative,
  type AdminInbound,
  type AdminRepresentative,
  type AdminRepresentativeStatus,
} from "../../api/adminRepresentatives";

type SortKey = "username" | "created" | "updated" | "usage" | "users";

const GB = 1024 ** 3;

function bytesToGB(value: number): number {
  return Number(value || 0) / GB;
}

function protocolLabel(item: AdminInbound): string {
  return [
    item.protocol,
    item.network,
    item.security,
  ]
    .filter(Boolean)
    .join(" · ")
    .toUpperCase();
}

export default function RepresentativesPage() {
  const [rows, setRows] = useState<AdminRepresentative[]>([]);
  const [inbounds, setInbounds] = useState<AdminInbound[]>([]);
  const [search, setSearch] = useState("");
  const [sortOpen, setSortOpen] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("updated");
  const [createOpen, setCreateOpen] = useState(false);
  const [modify, setModify] = useState<AdminRepresentative | null>(null);
  const [details, setDetails] = useState<AdminRepresentative | null>(null);
  const [menuFor, setMenuFor] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(true);
  const [archivedUsedBytes, setArchivedUsedBytes] = useState(0);

  const showToast = (message:string) => {
    setToast(message);
    window.setTimeout(()=>setToast(""),1600);
  };

  const loadRows = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const result = await getAdminRepresentatives();
      setRows(result.representatives);
      setArchivedUsedBytes(result.archived_used_bytes);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Unable to load representatives");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const loadInbounds = async (silent = false) => {
    try {
      setInbounds(await getAdminInbounds());
    } catch (error) {
      if (!silent) {
        showToast(error instanceof Error ? error.message : "Unable to load inbounds");
      }
    }
  };

  useEffect(() => {
    // ADMIN_STEP2_LIVE_INBOUND_POLL
    void loadRows();
    void loadInbounds();

    const timer = window.setInterval(() => {
      void loadInbounds(true);
    }, 3000);

    const refresh = () => void loadInbounds(true);
    const visibility = () => {
      if (document.visibilityState === "visible") refresh();
    };

    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", visibility);

    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);

  const visible = useMemo(() => {
    const filtered = rows.filter(r => r.username.toLowerCase().includes(search.toLowerCase()));
    return [...filtered].sort((a,b) => {
      if(sortKey === "username") return a.username.localeCompare(b.username);
      if(sortKey === "created") return b.created_at.localeCompare(a.created_at);
      if(sortKey === "updated") return b.updated_at.localeCompare(a.updated_at);
      if(sortKey === "usage") return b.used_bytes-a.used_bytes;
      return b.users-a.users;
    });
  }, [rows,search,sortKey]);

  const active = rows.filter(r=>r.status==="Active").length;
  const totalUsed = rows.reduce((s,r)=>s+r.used_bytes,0) + archivedUsedBytes;

  const updateStatus = async (rep: AdminRepresentative) => {
    try {
      const nextStatus: AdminRepresentativeStatus = rep.status === "Active" ? "Suspended" : "Active";
      await setAdminRepresentativeStatus(rep.id, nextStatus);
      await loadRows(true);
      showToast(nextStatus === "Active" ? "Representative Activated" : "Representative Suspended");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Status update failed");
    }
  };

  const remove = async (rep: AdminRepresentative) => {
    try {
      await deleteAdminRepresentative(rep.id);
      await loadRows(true);
      showToast("Representative Removed");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Remove failed");
    }
  };

  const resetUsage = async (rep: AdminRepresentative) => {
    try {
      await resetAdminRepresentativeUsage(rep.id);
      await loadRows(true);
      showToast("Usage Reset");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Usage reset failed");
    }
  };

  return (
    <>
      <header className="page-header users-header">
        <div><div className="page-title-row"><h1>Representatives</h1><span className="help-chip">?</span></div><p>Manage reseller accounts, quota and inbound access</p></div>
        <button className="up-create-button" type="button" onClick={()=>setCreateOpen(true)}><Plus size={20}/>Create Representative</button>
      </header>

      <main className="rp-page" onClick={()=>{setMenuFor(null);setSortOpen(false)}}>
        <section className="up-stats-grid">
          <RepStat icon={UsersRound} label="Representatives" value={rows.length}/>
          <RepStat icon={UserCheck} label="Active" value={active}/>
          <RepStat icon={Database} label="Consumed Traffic" value={`${bytesToGB(totalUsed).toFixed(1)} GB`}/>
        </section>

        <section className="up-toolbar">
          <div className="up-search-box"><Search size={18}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search representatives"/></div>
          <div className="up-sort-wrap">
            <button className={`up-tool-button ${sortOpen?"active":""}`} type="button" onClick={e=>{e.stopPropagation();setSortOpen(v=>!v)}}><SortAsc size={19}/></button>
            {sortOpen&&<div className="up-sort-menu rp-sort" onClick={e=>e.stopPropagation()}>
              <div className="up-sort-title">Sort Options</div>
              {([['username','Username',UsersRound],['created','Created at',CalendarDays],['updated','Edited at',PencilLine],['usage','Data Usage',Database],['users','Users',UsersRound]] as const).map(([key,label,Icon])=><button key={key} className={`rp-sort-option ${sortKey===key?"active":""}`} onClick={()=>{setSortKey(key);setSortOpen(false)}}><Icon size={16}/><span>{label}</span></button>)}
            </div>}
          </div>
        </section>

        <section className="rp-table-card">
          <div className="rp-table-head"><div>Representative</div><div>Status</div><div>Traffic Usage</div><div>Users</div><div>Allowed Inbounds</div><div/></div>
          {visible.map(rep => {
            const usedGB = bytesToGB(rep.used_bytes);
            const quotaGB = bytesToGB(rep.quota_bytes);
            const pct = quotaGB > 0 ? Math.min(100, usedGB / quotaGB * 100) : 0;
            return <div className="rp-row" key={rep.id}>
              <div className="rp-name"><span className={`rp-presence ${rep.status==="Active"?"active":""}`}/><div><strong>{rep.username}</strong><span>R-{rep.id} · {rep.created_at}</span></div></div>
              <div><span className={`rp-status-pill ${rep.status==="Active"?"active":"suspended"}`}>{rep.status==="Active"?<Wifi size={13}/>:<Ban size={13}/>} {rep.status}</span></div>
              <div className="rp-usage"><div className="up-usage-progress"><div className="up-usage-fill" style={{width:`${pct}%`}}/></div><div className="up-usage-line"><span>{usedGB.toFixed(1)} / {quotaGB.toFixed(1)} GB</span><span>{pct.toFixed(0)}%</span></div></div>
              <div className="rp-users"><strong>{rep.users}</strong><span>{rep.online} online</span></div>
              <div className="rp-inbounds"><Server size={15}/><strong>{rep.inbound_ids.length}</strong><span>assigned</span></div>
              <div className="up-actions" onClick={e=>e.stopPropagation()}>
                <button type="button" title="Details" onClick={()=>setDetails(rep)}><Eye size={18}/></button>
                <div className="ua-action-wrap"><button type="button" onClick={()=>setMenuFor(menuFor===rep.id?null:rep.id)}><MoreVertical size={18}/></button>
                  {menuFor===rep.id&&<div className="ua-more-menu rp-more-menu">
                    <button type="button" onClick={()=>{setModify(rep);setMenuFor(null)}}><PencilLine size={18}/><span>Modify</span></button>
                    <button type="button" onClick={()=>{setMenuFor(null);void resetUsage(rep)}}><RefreshCcw size={18}/><span>Reset Usage</span></button>
                    <div className="ua-menu-divider"/>
                    <button type="button" className="ua-warning" onClick={()=>{setMenuFor(null);void updateStatus(rep)}}><Ban size={18}/><span>{rep.status==="Active"?"Suspend":"Activate"}</span></button>
                    <button type="button" className="ua-danger" onClick={()=>{setMenuFor(null);void remove(rep)}}><Trash2 size={18}/><span>Remove</span></button>
                  </div>}
                </div>
              </div>
            </div>;
          })}
          {loading && rows.length === 0 ? <div className="rp-row"><div className="muted">Loading representatives...</div></div> : null}
        </section>

        <section className="up-pagination"><div className="up-items-per-page"><button type="button">10 <ChevronDown size={16}/></button><span>Items per page</span></div><div className="up-pagination-right"><button><ChevronLeft size={18}/>Previous</button><button className="up-current-page">1</button><button>Next<ChevronRight size={18}/></button></div></section>
      </main>

      {toast&&<div className="ua-global-toast">{toast}</div>}
      <RepresentativeModal
        open={createOpen}
        mode="create"
        inbounds={inbounds}
        onClose={()=>setCreateOpen(false)}
        onSubmit={async(input)=>{
          try {
            await createAdminRepresentative({
              ...input,
              password: input.password || "",
            });
            setCreateOpen(false);
            await loadRows(true);
            showToast("Representative Created");
          } catch (error) {
            showToast(error instanceof Error ? error.message : "Create failed");
            throw error;
          }
        }}
      />
      <RepresentativeModal
        open={Boolean(modify)}
        mode="modify"
        initial={modify??undefined}
        inbounds={inbounds}
        onClose={()=>setModify(null)}
        onSubmit={async(input)=>{
          if (!modify) return;
          try {
            await updateAdminRepresentative(modify.id, input);
            setModify(null);
            await loadRows(true);
            showToast("Representative Updated");
          } catch (error) {
            showToast(error instanceof Error ? error.message : "Update failed");
            throw error;
          }
        }}
      />
      <RepresentativeDetails open={Boolean(details)} rep={details} inbounds={inbounds} onClose={()=>setDetails(null)}/>
    </>
  );
}

function RepStat({icon:Icon,label,value}:{icon:any;label:string;value:string|number}) { return <section className="up-stat-card"><div className="up-stat-left"><Icon size={23}/><span>{label}</span></div><strong>{value}</strong></section> }

type ModalSubmit = {
  username: string;
  password?: string;
  quota_bytes: number;
  status: AdminRepresentativeStatus;
  inbound_ids: number[];
};

function RepresentativeModal({open,mode,initial,inbounds,onClose,onSubmit}:{open:boolean;mode:"create"|"modify";initial?:AdminRepresentative;inbounds:AdminInbound[];onClose:()=>void;onSubmit:(input:ModalSubmit)=>Promise<void>}) {
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [quota,setQuota]=useState("500");
  const [status,setStatus]=useState<AdminRepresentativeStatus>("Active");
  const [selected,setSelected]=useState<number[]>([]);
  const [query,setQuery]=useState("");
  const [submitting,setSubmitting]=useState(false);
  const [formError,setFormError]=useState("");

  useEffect(()=>{
    if(!open) return;
    setUsername(initial?.username??"");
    setPassword("");
    setQuota(String(initial ? bytesToGB(initial.quota_bytes) : 500));
    setStatus(initial?.status??"Active");
    setSelected(initial?.inbound_ids??[]);
    setQuery("");
    setFormError("");
  },[open,mode,initial]);

  if(!open) return null;
  const shown=inbounds.filter(i=>i.name.toLowerCase().includes(query.toLowerCase()));
  const submit=async()=>{
    if (submitting) return;

    const cleanUsername = username.trim();
    const quotaNumber = Number(quota);

    if (!/^[A-Za-z0-9_.@-]{3,64}$/.test(cleanUsername)) {
      setFormError("Username must be 3-64 characters and contain only letters, numbers, . _ @ -");
      return;
    }

    if (mode === "create" && password.length < 8) {
      setFormError("Password must be at least 8 characters");
      return;
    }

    if (mode === "modify" && password && password.length < 8) {
      setFormError("New password must be at least 8 characters");
      return;
    }

    if (!Number.isFinite(quotaNumber) || quotaNumber < 0) {
      setFormError("Traffic quota must be zero or a positive number");
      return;
    }

    setFormError("");
    setSubmitting(true);
    try {
      await onSubmit({
        username:cleanUsername,
        password,
        quota_bytes:Math.max(0,Math.round(quotaNumber*GB)),
        status,
        inbound_ids:selected,
      });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : (mode === "create" ? "Create failed" : "Update failed"));
    } finally {
      setSubmitting(false);
    }
  };
  return <div className="cu-backdrop admin-rep-backdrop" onMouseDown={onClose}><section className="cu-modal rp-modal" onMouseDown={e=>e.stopPropagation()}>
    <header className="cu-header"><div className="cu-title-wrap"><ShieldCheck size={24}/><div><h2>{mode==="create"?"Create Representative":"Modify Representative"}</h2><p>{mode==="create"?"Create panel credentials and assign traffic quota.":`Update ${initial?.username} account limits and access.`}</p></div></div><button className="cu-close" onClick={onClose}><X size={21}/></button></header>
    <div className="cu-body">
      <div className="cu-form-column">
        <div className="cu-grid-two"><label className="cu-field"><span>Username <b>*</b></span><input value={username} onChange={e=>setUsername(e.target.value)} placeholder="Representative username"/></label><label className="cu-field"><span>{mode==="create"?"Password *":"New Password"}</span><input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder={mode==="create"?"Login password":"Leave empty to keep current"}/></label></div>
        <div className="cu-grid-two"><label className="cu-field"><span>Traffic Quota (GB)</span><input inputMode="decimal" value={quota} onChange={e=>setQuota(e.target.value)}/></label><label className="cu-field"><span>Status</span><button className="cu-select" type="button" onClick={()=>setStatus(status==="Active"?"Suspended":"Active")}><span className={`cu-status-dot ${status==="Active"?"on":"off"}`}/><span>{status}</span><ChevronDown size={17}/></button></label></div>
        {mode==="modify"&&<div className="rp-usage-preview"><div><span>Consumed Traffic</span><strong>{bytesToGB(initial?.used_bytes??0).toFixed(1)} GB</strong></div><div><span>Remaining</span><strong>{Math.max(0,(Number(quota)||0)-bytesToGB(initial?.used_bytes??0)).toFixed(1)} GB</strong></div><div><span>Users</span><strong>{initial?.users}</strong></div></div>}
        <div className="cu-auto-note"><Database size={18}/><span>Representative quota is based on real traffic usage, not the sum of client limits.</span></div>
        {formError ? <div className="rp-form-error" role="alert">{formError}</div> : null}
      </div>
      <aside className="cu-inbounds-column"><div className="cu-inbounds-title"><div><Server size={20}/><strong>Allowed Inbounds</strong></div><span>{selected.length} selected</span></div><div className="cu-inbound-search"><Search size={18}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search inbounds"/></div><button className="cu-select-all" type="button" onClick={()=>{const ids=shown.map(x=>x.id);const all=ids.every(id=>selected.includes(id));setSelected(current=>all?current.filter(x=>!ids.includes(x)):Array.from(new Set([...current,...ids])))}}><span className="cu-check"/>Select all</button><div className="cu-inbound-list">{shown.map(item=>{const active=selected.includes(item.id);return <button className={`cu-inbound-item ${active?"selected":""}`} key={item.id} onClick={()=>setSelected(current=>active?current.filter(x=>x!==item.id):[...current,item.id])}><span className={`cu-check ${active?"checked":""}`}>{active?"✓":""}</span><span className="cu-inbound-copy"><strong>{item.name}</strong><small>{protocolLabel(item)}</small></span><span className="cu-inbound-id">#{item.id}</span></button>})}</div></aside>
    </div>
    <footer className="cu-footer"><button className="cu-secondary" onClick={onClose}>Cancel</button><button className="cu-primary" disabled={submitting} onClick={()=>void submit()}><ShieldCheck size={18}/>{mode==="create"?"Create Representative":"Save Changes"}</button></footer>
  </section></div>;
}

function RepresentativeDetails({open,rep,inbounds,onClose}:{open:boolean;rep:AdminRepresentative|null;inbounds:AdminInbound[];onClose:()=>void}) {
  if(!open||!rep) return null;
  const usedGB=bytesToGB(rep.used_bytes);
  const quotaGB=bytesToGB(rep.quota_bytes);
  const pct=quotaGB>0?Math.min(100,usedGB/quotaGB*100):0;
  return <div className="cu-backdrop admin-rep-backdrop" onMouseDown={onClose}><section className="rp-detail-modal" onMouseDown={e=>e.stopPropagation()}>
    <header className="cu-header"><div className="cu-title-wrap"><Eye size={24}/><div><h2>{rep.username}</h2><p>Representative usage and account overview</p></div></div><button className="cu-close" onClick={onClose}><X size={21}/></button></header>
    <div className="rp-detail-body"><div className="rp-detail-stats"><div><Database/><span>Traffic</span><strong>{usedGB.toFixed(1)} / {quotaGB.toFixed(1)} GB</strong></div><div><UsersRound/><span>Users</span><strong>{rep.users}</strong></div><div><Wifi/><span>Online</span><strong>{rep.online}</strong></div></div><section><div className="rp-detail-head"><h3>Traffic Consumption</h3><strong>{pct.toFixed(1)}%</strong></div><div className="ad-master-progress"><i style={{width:`${pct}%`}}/></div><div className="ad-master-meta"><span>Used {usedGB.toFixed(1)} GB</span><span>Remaining {Math.max(0,quotaGB-usedGB).toFixed(1)} GB</span></div></section><section><h3>Allowed Inbounds</h3><div className="rp-tag-list">{rep.inbound_ids.map(id=>{const i=inbounds.find(x=>x.id===id);return <span key={id}>{i?.name??`#${id}`}</span>})}</div></section></div><footer className="cu-footer"><button className="cu-secondary" onClick={onClose}>Close</button></footer>
  </section></div>;
}
