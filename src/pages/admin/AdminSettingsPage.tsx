import {
  Check, CircleHelp, DatabaseBackup, Download, KeyRound, Laptop, Moon,
  Network, Palette, RefreshCcw, Save, Server, ShieldCheck, Sun, Trash2, Upload
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getLiveAdminInbounds, type LiveAdminInbound } from "../../api/adminInbounds";
import {
  downloadAdminBackup, getAdminSettings, removeConfigProxy, restoreAdminBackup,
  saveConfigProxy, saveSubscriptionProxy, updateAdminCredentials,
  type AdminSettingsData, type ConfigProxyOverride
} from "../../api/adminSettings";
import {
  type AccentColor, type UiMode, useThemeSettings
} from "../../theme/ThemeProvider";

type Tab = "theme" | "proxy" | "backup" | "account";

const modes: Array<{ id: UiMode; title: string; description: string; icon: typeof Sun }> = [
  { id: "light", title: "Light", description: "Bright and clean", icon: Sun },
  { id: "dark", title: "Dark", description: "Easy on the eyes", icon: Moon },
  { id: "system", title: "System", description: "Matches your device", icon: Laptop }
];

const colors: Array<{ id: AccentColor; title: string; swatch: string }> = [
  { id: "default", title: "Default", swatch: "#4d82cf" },
  { id: "red", title: "Red", swatch: "#ef4444" },
  { id: "rose", title: "Rose", swatch: "#f43f5e" },
  { id: "orange", title: "Orange", swatch: "#f97316" },
  { id: "green", title: "Green", swatch: "#22c55e" },
  { id: "blue", title: "Blue", swatch: "#3b82f6" },
  { id: "yellow", title: "Yellow", swatch: "#eab308" },
  { id: "violet", title: "Violet", swatch: "#8b5cf6" }
];

const EMPTY_SETTINGS: AdminSettingsData = {
  username: "",
  config_overrides: [],
  subscription: { host: "", port: 0, detected_port: 0, effective_port: 2096, fallback_port: 2096 }
};

function inboundName(inbound: LiveAdminInbound | undefined, id: number): string {
  return String(inbound?.name || inbound?.label || `Inbound #${id}`);
}

export default function AdminSettingsPage() {
  const { mode, accent, setMode, setAccent } = useThemeSettings();
  const [tab, setTab] = useState<Tab>("theme");
  const [settings, setSettings] = useState<AdminSettingsData>(EMPTY_SETTINGS);
  const [inbounds, setInbounds] = useState<LiveAdminInbound[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const themeReady = useRef(false);

  const [selectedInbound, setSelectedInbound] = useState(0);
  const [proxyHost, setProxyHost] = useState("");
  const [proxyPort, setProxyPort] = useState("");
  const [proxySid, setProxySid] = useState("");
  const [subHost, setSubHost] = useState("");
  const [subPort, setSubPort] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [adminUsername, setAdminUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 1800);
  };

  const loadSettings = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await getAdminSettings();
      setSettings(data);
      setAdminUsername(data.username || "");
      setSubHost(data.subscription.host || "");
      setSubPort(data.subscription.port ? String(data.subscription.port) : "");
      setError("");
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Unable to load admin settings");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const loadInbounds = async () => {
    try {
      const rows = await getLiveAdminInbounds();
      setInbounds(rows);
      setSelectedInbound(current => current || rows[0]?.id || 0);
    } catch {
      // Keep last good snapshot.
    }
  };

  useEffect(() => {
    void loadSettings(false);
    void loadInbounds();
    const timer = window.setInterval(() => void loadInbounds(), 3000);
    const focus = () => void loadInbounds();
    window.addEventListener("focus", focus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", focus);
    };
  }, []);

  useEffect(() => {
    if (!themeReady.current) {
      themeReady.current = true;
      return;
    }
    showToast("Theme changed successfully");
  }, [mode, accent]);

  const overrideMap = useMemo(() => new Map(settings.config_overrides.map(item => [item.inbound_id, item])), [settings.config_overrides]);

  useEffect(() => {
    const current = overrideMap.get(selectedInbound);
    setProxyHost(current?.host || "");
    setProxyPort(current?.port ? String(current.port) : "");
    setProxySid(current?.reality_sid || "");
  }, [selectedInbound, overrideMap]);

  const saveProxy = async () => {
    if (!selectedInbound) return;
    setBusy(true);
    try {
      await saveConfigProxy({
        inbound_id: selectedInbound,
        host: proxyHost.trim(),
        port: Math.max(0, Number(proxyPort || 0)),
        reality_sid: proxySid.trim()
      });
      await loadSettings(true);
      showToast(proxyHost.trim() ? "External proxy saved" : "External proxy cleared");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save proxy");
    } finally { setBusy(false); }
  };

  const removeProxy = async (id: number) => {
    setBusy(true);
    try {
      await removeConfigProxy(id);
      await loadSettings(true);
      showToast("External proxy removed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove proxy");
    } finally { setBusy(false); }
  };

  const saveSub = async () => {
    setBusy(true);
    try {
      await saveSubscriptionProxy(subHost.trim(), Math.max(0, Number(subPort || 0)));
      await loadSettings(true);
      showToast("Subscription proxy saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save subscription proxy");
    } finally { setBusy(false); }
  };

  const changeCredentials = async () => {
    if (!currentPassword) { setError("Current password is required"); return; }
    if (newPassword !== confirmPassword) { setError("New passwords do not match"); return; }
    setBusy(true);
    try {
      await updateAdminCredentials({
        current_password: currentPassword,
        username: adminUsername.trim(),
        new_password: newPassword
      });
      showToast("Admin credentials updated");
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      window.setTimeout(() => window.location.reload(), 650);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update credentials");
    } finally { setBusy(false); }
  };

  const restore = async () => {
    if (!restoreFile || busy) return;
    if (!window.confirm("Restore this backup? Current local panel data will be replaced and all sessions will be logged out.")) return;
    setBusy(true);
    try {
      await restoreAdminBackup(restoreFile);
      showToast("Backup restored. Sign in again.");
      window.setTimeout(() => {
        window.location.hash = "#/admin/login";
        window.location.reload();
      }, 900);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restore failed");
      setBusy(false);
    }
  };

  return <>
    <header className="page-header settings-header">
      <div><div className="page-title-row"><h1>Settings</h1><span className="help-chip">?</span></div><p>Admin-only panel settings and generated-link controls</p></div>
    </header>

    <main className="settings-page admin-settings-page">
      <div className="settings-tab-row admin-settings-tabs">
        <button className={`settings-tab ${tab === "theme" ? "active" : ""}`} onClick={()=>setTab("theme")}><Palette size={17}/><span>Theme</span></button>
        <button className={`settings-tab ${tab === "proxy" ? "active" : ""}`} onClick={()=>setTab("proxy")}><Network size={17}/><span>External Proxy</span></button>
        <button className={`settings-tab ${tab === "backup" ? "active" : ""}`} onClick={()=>setTab("backup")}><DatabaseBackup size={17}/><span>Backup</span></button>
        <button className={`settings-tab ${tab === "account" ? "active" : ""}`} onClick={()=>setTab("account")}><KeyRound size={17}/><span>Admin Account</span></button>
      </div>

      {error ? <div className="admin-settings-error">{error}<button onClick={()=>setError("")}>×</button></div> : null}
      {loading ? <div className="admin-settings-loading"><RefreshCcw size={17}/>Loading settings...</div> : null}

      {!loading && tab === "theme" ? <>
        <section className="settings-section">
          <div className="settings-section-title"><Sun size={18}/><div><h2>Mode</h2><p>Choose how the interface should appear</p></div></div>
          <div className="mode-grid">{modes.map(item=>{const Icon=item.icon;const selected=item.id===mode;return <button key={item.id} className={`mode-card ${selected?"selected":""}`} onClick={()=>setMode(item.id)}><div className="mode-icon"><Icon size={19}/></div><div className="mode-copy"><strong>{item.title}</strong><span>{item.description}</span></div>{selected?<span className="settings-check"><Check size={12}/></span>:null}</button>})}</div>
        </section>
        <section className="settings-section settings-color-section">
          <div className="settings-section-title"><Palette size={18}/><div><h2>Color</h2><p>Select your preferred color scheme</p></div></div>
          <div className="color-grid">{colors.map(item=>{const selected=item.id===accent;return <button key={item.id} className={`color-card ${selected?"selected":""}`} onClick={()=>setAccent(item.id)}><span className="color-swatch" style={{backgroundColor:item.swatch}}/><strong>{item.title}</strong>{selected?<span className="settings-check"><Check size={12}/></span>:null}</button>})}</div>
        </section>
        <div className="settings-note"><CircleHelp size={17}/><span>Theme settings are visual only. They do not change x-ui or reseller access.</span></div>
      </> : null}

      {!loading && tab === "proxy" ? <>
        <section className="settings-section">
          <div className="settings-section-title"><Server size={18}/><div><h2>Configuration External Proxy</h2><p>Rewrite generated config host per inbound. x-ui itself stays read-only.</p></div></div>
          <div className="admin-settings-card">
            <div className="admin-settings-grid four">
              <label><span>Inbound</span><select value={selectedInbound || ""} onChange={e=>setSelectedInbound(Number(e.target.value))}>{inbounds.map(i=><option key={i.id} value={i.id}>{inboundName(i,i.id)} · #{i.id} · :{i.port}</option>)}</select></label>
              <label><span>External Host</span><input value={proxyHost} onChange={e=>setProxyHost(e.target.value)} placeholder="proxy.example.com"/></label>
              <label><span>External Port</span><input inputMode="numeric" value={proxyPort} onChange={e=>setProxyPort(e.target.value.replace(/\D/g,""))} placeholder="Blank = inbound port"/></label>
              <label><span>Reality SID</span><input value={proxySid} onChange={e=>setProxySid(e.target.value)} placeholder="Blank = x-ui SID"/></label>
            </div>
            <div className="admin-settings-actions"><button className="admin-settings-primary" disabled={busy||!selectedInbound} onClick={()=>void saveProxy()}><Save size={17}/>Save External Proxy</button></div>
          </div>

          <div className="admin-settings-list">
            {settings.config_overrides.map(item=>{const ib=inbounds.find(x=>x.id===item.inbound_id);return <div className="admin-settings-list-row" key={item.inbound_id}><div><strong>{inboundName(ib,item.inbound_id)}</strong><span>#{item.inbound_id} · {item.host}{item.port?`:${item.port}`:" · original port"}{item.reality_sid?` · SID ${item.reality_sid}`:""}</span></div><button onClick={()=>void removeProxy(item.inbound_id)} title="Remove override"><Trash2 size={17}/></button></div>})}
            {!settings.config_overrides.length?<div className="admin-settings-empty">No config overrides. Generated links remain exactly as x-ui returns them.</div>:null}
          </div>
        </section>

        <section className="settings-section">
          <div className="settings-section-title"><Network size={18}/><div><h2>Subscription External Proxy</h2><p>External public host and subscription port used for generated subscription links.</p></div></div>
          <div className="admin-settings-card">
            <div className="admin-settings-grid two">
              <label><span>Subscription Host</span><input value={subHost} onChange={e=>setSubHost(e.target.value)} placeholder="proxy.example.com"/></label>
              <label><span>Subscription Port</span><input inputMode="numeric" value={subPort} onChange={e=>setSubPort(e.target.value.replace(/\D/g,""))} placeholder={String(settings.subscription.effective_port || 2096)}/></label>
            </div>
            <div className="admin-settings-port-note">{settings.subscription.detected_port ? `Detected from x-ui: ${settings.subscription.detected_port}` : `x-ui subscription port was not detected · fallback: ${settings.subscription.fallback_port || 2096}`} · Effective: <strong>{settings.subscription.port || settings.subscription.effective_port || 2096}</strong></div>
            <div className="admin-settings-actions"><button className="admin-settings-primary" disabled={busy} onClick={()=>void saveSub()}><Save size={17}/>Save Subscription Proxy</button></div>
          </div>
          <div className="settings-note"><CircleHelp size={17}/><span>Leave a host empty to use the original x-ui output. Per-inbound External Port and Reality SID are optional; blank values keep the original config values.</span></div>
        </section>
      </> : null}

      {!loading && tab === "backup" ? <section className="settings-section">
        <div className="settings-section-title"><DatabaseBackup size={18}/><div><h2>Backup & Restore</h2><p>Admin-only backup of the local panel database.</p></div></div>
        <div className="admin-settings-two-cards">
          <div className="admin-settings-card"><div className="admin-settings-card-title"><Download size={20}/><div><strong>Create Backup</strong><span>Representatives, client mappings, traffic ledger, admin settings and local state.</span></div></div><button className="admin-settings-primary" disabled={busy} onClick={()=>void downloadAdminBackup().then(()=>showToast("Backup downloaded")).catch(e=>setError(e instanceof Error?e.message:"Backup failed"))}><Download size={17}/>Download Backup</button></div>
          <div className="admin-settings-card"><div className="admin-settings-card-title"><Upload size={20}/><div><strong>Restore Backup</strong><span>Restores the local panel DB. The primary x-ui database is not modified.</span></div></div><label className="admin-settings-file"><input type="file" accept=".sqlite,.sqlite3,.db,application/vnd.sqlite3" onChange={e=>setRestoreFile(e.target.files?.[0]||null)}/><span>{restoreFile?.name || "Choose backup file"}</span></label><button className="admin-settings-danger" disabled={busy||!restoreFile} onClick={()=>void restore()}><Upload size={17}/>Restore Backup</button></div>
        </div>
        <div className="settings-note"><ShieldCheck size={17}/><span>Before every restore, the backend automatically creates a safety backup of the current local database. Restore logs out all sessions.</span></div>
      </section> : null}

      {!loading && tab === "account" ? <section className="settings-section">
        <div className="settings-section-title"><KeyRound size={18}/><div><h2>Admin Credentials</h2><p>Change the Super Admin username or password.</p></div></div>
        <div className="admin-settings-card admin-settings-account">
          <div className="admin-settings-grid two">
            <label><span>Username</span><input value={adminUsername} onChange={e=>setAdminUsername(e.target.value)}/></label>
            <label><span>Current Password</span><input type="password" value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} autoComplete="current-password"/></label>
            <label><span>New Password</span><input type="password" value={newPassword} onChange={e=>setNewPassword(e.target.value)} placeholder="Leave blank to keep current" autoComplete="new-password"/></label>
            <label><span>Confirm New Password</span><input type="password" value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} autoComplete="new-password"/></label>
          </div>
          <div className="admin-settings-actions"><button className="admin-settings-primary" disabled={busy||!adminUsername.trim()||!currentPassword} onClick={()=>void changeCredentials()}><Save size={17}/>Save Credentials</button></div>
        </div>
      </section> : null}
    </main>

    {toast?<div className="theme-toast"><span className="theme-toast-icon"><Check size={13}/></span><div><strong>Success</strong><span>{toast}</span></div></div>:null}
  </>;
}
