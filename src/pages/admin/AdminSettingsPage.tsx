import {
  Check, CircleHelp, DatabaseBackup, Download, KeyRound, Laptop, Moon,
  Network, Palette, RefreshCcw, Save, Server, ShieldCheck, Sun, Trash2, Upload
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getLiveAdminInbounds, type LiveAdminInbound } from "../../api/adminInbounds";
import {
  downloadAdminBackup, getAdminSettings, inspectAdminBackup, removeConfigProxy, restoreAdminBackup,
  saveConfigProxy, saveSubscriptionProxy, updateAdminCredentials,
  type AdminSettingsData, type ConfigProxyOverride, type RestoreInspection
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
  subscription: {
    host: "", port: 0, detected_port: 0, effective_port: 0, fallback_port: 0,
    configured: false, certificate_path: "", key_path: ""
  },
  xui_connection: { base_url: "", auth_mode: "token" }
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
  const [subCertificatePath, setSubCertificatePath] = useState("");
  const [subKeyPath, setSubKeyPath] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [adminUsername, setAdminUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoreInspection, setRestoreInspection] = useState<RestoreInspection | null>(null);
  const [restoreConnectionMode, setRestoreConnectionMode] = useState<"backup" | "current" | "new">("current");
  const [restoreXuiUrl, setRestoreXuiUrl] = useState("");
  const [restoreXuiToken, setRestoreXuiToken] = useState("");
  const [restoreVerifyTls, setRestoreVerifyTls] = useState(false);
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
      setSubCertificatePath(data.subscription.certificate_path || "");
      setSubKeyPath(data.subscription.key_path || "");
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
    if (Boolean(subHost.trim()) !== Boolean(subPort)) {
      setError("Subscription proxy host and port are both required");
      return;
    }
    setBusy(true);
    try {
      await saveSubscriptionProxy({
        host: subHost.trim(),
        port: Math.max(0, Number(subPort || 0)),
        certificate_path: subCertificatePath.trim(),
        key_path: subKeyPath.trim()
      });
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
    setBusy(true);
    try {
      const inspected = await inspectAdminBackup(restoreFile);
      setRestoreInspection(inspected);
      setRestoreConnectionMode(inspected.has_backup_connection ? "backup" : "current");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backup inspection failed");
    } finally {
      setBusy(false);
    }
  };

  const applyRestore = async () => {
    if (!restoreInspection || busy) return;
    if (restoreConnectionMode === "new" && (!restoreXuiUrl.trim() || !restoreXuiToken.trim())) {
      setError("New X-UI URL and API token are required");
      return;
    }
    if (!window.confirm("Restore this backup now? Current local data will be replaced. A safety backup and automatic rollback are enabled.")) return;
    setBusy(true);
    try {
      await restoreAdminBackup({
        restore_token: restoreInspection.restore_token,
        connection_mode: restoreConnectionMode,
        connection: restoreConnectionMode === "new" ? {
          base_url: restoreXuiUrl.trim(), api_token: restoreXuiToken.trim(), verify_tls: restoreVerifyTls
        } : undefined
      });
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
          <div className="settings-section-title"><Network size={18}/><div><h2>Branded Subscription Proxy</h2><p>Serve reseller-branded subscriptions on a dedicated domain and free HTTPS port without changing x-ui.</p></div></div>
          <div className="admin-settings-card">
            <div className="admin-settings-grid two">
              <label><span>Public Domain</span><input value={subHost} onChange={e=>setSubHost(e.target.value)} placeholder="sub.example.com"/></label>
              <label><span>Public HTTPS Port</span><input inputMode="numeric" value={subPort} onChange={e=>setSubPort(e.target.value.replace(/\D/g,""))} placeholder="Enter a free port"/></label>
              <label><span>TLS Certificate Path</span><input value={subCertificatePath} onChange={e=>setSubCertificatePath(e.target.value)} placeholder="Blank = detect from x-ui"/></label>
              <label><span>TLS Private Key Path</span><input value={subKeyPath} onChange={e=>setSubKeyPath(e.target.value)} placeholder="Blank = detect from x-ui"/></label>
            </div>
            <div className="admin-settings-port-note">
              x-ui upstream port: <strong>{settings.subscription.detected_port || "not detected"}</strong>
              {settings.subscription.configured ? <> · Public proxy: <strong>{settings.subscription.host}:{settings.subscription.port}</strong></> : <> · Public proxy is not configured</>}
            </div>
            <div className="admin-settings-actions"><button className="admin-settings-primary" disabled={busy} onClick={()=>void saveSub()}><Save size={17}/>{subHost.trim() || subPort ? "Apply Subscription Proxy" : "Disable Subscription Proxy"}</button></div>
          </div>
          <div className="settings-note"><CircleHelp size={17}/><span>Choose any free port and allow it through the server firewall or cloud security group. Host and port are required together; no default port is used. TLS files are read from x-ui when available, otherwise enter local absolute paths. Clear both host and port to disable the branded proxy.</span></div>
        </section>
      </> : null}

      {!loading && tab === "backup" ? <section className="settings-section">
        <div className="settings-section-title"><DatabaseBackup size={18}/><div><h2>Backup & Restore</h2><p>Admin-only backup of the local panel database.</p></div></div>
        <div className="admin-settings-two-cards">
          <div className="admin-settings-card"><div className="admin-settings-card-title"><Download size={20}/><div><strong>Create Full Backup</strong><span>All local users, representatives, API keys, traffic/accounting state, settings and X-UI connection details.</span></div></div><button className="admin-settings-primary" disabled={busy} onClick={()=>void downloadAdminBackup().then(()=>showToast("Full backup downloaded")).catch(e=>setError(e instanceof Error?e.message:"Backup failed"))}><Download size={17}/>Download .xuibak</button></div>
          <div className="admin-settings-card"><div className="admin-settings-card-title"><Upload size={20}/><div><strong>Inspect & Restore</strong><span>Use after restoring the primary x-ui backup. Legacy SQLite backups are also accepted.</span></div></div><label className="admin-settings-file"><input type="file" accept=".xuibak,.sqlite,.sqlite3,.db,application/zip,application/vnd.sqlite3" onChange={e=>{setRestoreFile(e.target.files?.[0]||null);setRestoreInspection(null)}}/><span>{restoreFile?.name || "Choose backup file"}</span></label><button className="admin-settings-danger" disabled={busy||!restoreFile} onClick={()=>void restore()}><Upload size={17}/>Inspect Backup</button></div>
        </div>
        {restoreInspection ? <div className="admin-restore-confirm">
          <div className="admin-settings-card-title"><ShieldCheck size={20}/><div><strong>Backup verified — choose the X-UI connection</strong><span>Version {restoreInspection.app_version || "legacy"} · {restoreInspection.tables.length} tables · representatives {restoreInspection.row_counts.representatives || 0} · clients {restoreInspection.row_counts.clients || 0} · API keys {restoreInspection.row_counts.api_keys || 0}</span></div></div>
          <label className={`admin-restore-choice ${restoreConnectionMode==="backup"?"selected":""}`}><input type="radio" name="restore-connection" disabled={!restoreInspection.has_backup_connection} checked={restoreConnectionMode==="backup"} onChange={()=>setRestoreConnectionMode("backup")}/><span><strong>Use connection saved in backup</strong><small>{restoreInspection.has_backup_connection ? restoreInspection.backup_xui_url : "Not available in this legacy backup"}</small></span></label>
          <label className={`admin-restore-choice ${restoreConnectionMode==="current"?"selected":""}`}><input type="radio" name="restore-connection" checked={restoreConnectionMode==="current"} onChange={()=>setRestoreConnectionMode("current")}/><span><strong>Keep this server's current connection</strong><small>{settings.xui_connection.base_url || "Current X-UI URL is not configured"}</small></span></label>
          <label className={`admin-restore-choice ${restoreConnectionMode==="new"?"selected":""}`}><input type="radio" name="restore-connection" checked={restoreConnectionMode==="new"} onChange={()=>setRestoreConnectionMode("new")}/><span><strong>Use a new X-UI URL and API token</strong><small>The connection is validated before any data is replaced.</small></span></label>
          {restoreConnectionMode === "new" ? <div className="admin-settings-grid two admin-restore-fields"><label><span>Full X-UI URL</span><input value={restoreXuiUrl} onChange={e=>setRestoreXuiUrl(e.target.value)} placeholder="https://panel.example.com:2053/path"/></label><label><span>Admin API Token</span><input type="password" value={restoreXuiToken} onChange={e=>setRestoreXuiToken(e.target.value)} autoComplete="off"/></label><label className="admin-restore-tls"><input type="checkbox" checked={restoreVerifyTls} onChange={e=>setRestoreVerifyTls(e.target.checked)}/><span>Verify TLS certificate</span></label></div> : null}
          <div className="admin-settings-actions"><button className="admin-settings-primary" disabled={busy} onClick={()=>void applyRestore()}><ShieldCheck size={17}/>Confirm & Restore</button></div>
        </div> : null}
        <div className="settings-note"><ShieldCheck size={17}/><span>Restore validates the package and X-UI connection first, creates a safety backup, migrates old schemas, runs a final integrity check, logs out all sessions and automatically rolls back on failure. Full .xuibak files contain X-UI credentials; store and transfer them securely.</span></div>
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
