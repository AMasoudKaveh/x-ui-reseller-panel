import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Check, ChevronDown, LoaderCircle, LockKeyhole, Plus,
  Search, Server, SlidersHorizontal, UserRoundPen, X
} from "lucide-react";
import { getXuiInbounds, type XuiInbound } from "../api/createUser";
import { getUserDetail, modifyUser } from "../api/userActions";

type Props = {
  open: boolean;
  userId: number | null;
  onClose: () => void;
  onSaved?: () => void | Promise<void>;
};

export default function ModifyUserModal({ open, userId, onClose, onSaved }: Props) {
  const [username, setUsername] = useState("");
  const [traffic, setTraffic] = useState("");
  const [expiry, setExpiry] = useState("");
  const [startAfterFirstUse, setStartAfterFirstUse] = useState(false);
  const [startAfterDays, setStartAfterDays] = useState("30");
  const [enabled, setEnabled] = useState(true);
  const [comment, setComment] = useState("");
  const [limitIp, setLimitIp] = useState("0");
  const [telegramId, setTelegramId] = useState("");
  const [uuid, setUuid] = useState("");
  const [subId, setSubId] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [inbounds, setInbounds] = useState<XuiInbound[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!open || !userId) return;
    let alive = true;
    setLoading(true); setError(""); setSuccess(""); setSearch("");
    Promise.all([getUserDetail(userId), getXuiInbounds()])
      .then(([detail, rows]) => {
        if (!alive) return;
        setUsername(detail.username);
        setTraffic(detail.traffic_gb > 0 ? String(detail.traffic_gb) : "");
        setExpiry(detail.expiry_date || "");
        setStartAfterFirstUse(Boolean(detail.start_after_first_use));
        setStartAfterDays(String(detail.start_after_days || 30));
        setEnabled(detail.enabled);
        setComment(detail.comment || "");
        setLimitIp(String(detail.limit_ip || 0));
        setTelegramId(detail.telegram_user_id || "");
        setUuid(detail.uuid || "");
        setSubId(detail.sub_id || "");
        setInbounds(rows);
        setSelected(detail.inbound_ids || []);
        if (!detail.panel_connected && detail.panel_error) {
          setError("x-ui client data could not be fully loaded: " + detail.panel_error);
        }
      })
      .catch(err => alive && setError(err instanceof Error ? err.message : "Unable to load user"))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [open, userId]);

  useEffect(() => {
    // ADMIN_STEP2_MODIFY_MODAL_INBOUND_POLL
    if (!open || !userId) return;
    let alive = true;

    const refresh = async () => {
      try {
        const rows = await getXuiInbounds();
        if (!alive) return;
        setInbounds(rows);
        setSelected(current => current.filter(id => rows.some(item => item.id === id)));
      } catch {
        // Preserve the last successful list on a temporary x-ui error.
      }
    };

    const timer = window.setInterval(() => void refresh(), 3000);
    const focus = () => void refresh();
    window.addEventListener("focus", focus);

    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", focus);
    };
  }, [open, userId]);

  const visibleInbounds = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return inbounds;
    return inbounds.filter(item => [item.label, item.remark, item.protocol, item.network, item.security, item.port, item.id]
      .join(" ").toLowerCase().includes(q));
  }, [inbounds, search]);

  if (!open || !userId) return null;

  const toggleInbound = (id: number) => {
    setSelected(current => current.includes(id) ? current.filter(x => x !== id) : [...current, id]);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || loading) return;
    if (!selected.length) { setError("Select at least one inbound"); return; }
    setSaving(true); setError(""); setSuccess("");
    try {
      await modifyUser(userId, {
        traffic_gb: Math.max(0, Number(traffic || 0)),
        expiry_date: expiry,
        start_after_first_use: startAfterFirstUse,
        start_after_days: startAfterFirstUse ? Math.max(1, Number(startAfterDays || 0)) : 0,
        enabled,
        comment: comment.trim(),
        inbound_ids: selected,
        limit_ip: Math.max(0, Number(limitIp || 0)),
        telegram_user_id: telegramId.trim()
      });
      setSuccess(`${username} updated successfully`);
      await new Promise(resolve => window.setTimeout(resolve, 450));
      if (onSaved) await onSaved(); else onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update user failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="xcu-backdrop" onMouseDown={e => e.target === e.currentTarget && !saving && onClose()}>
      <form className="xcu-modal" onSubmit={submit}>
        <header className="xcu-header">
          <div className="xcu-title"><UserRoundPen size={21}/><div><h2>Modify User</h2><p>Update the existing x-ui client</p></div></div>
          <button type="button" className="xcu-icon-btn" onClick={onClose} disabled={saving}><X size={20}/></button>
        </header>

        <div className="xcu-content">
          <section className="xcu-main">
            {error ? <div className="xcu-message error">{error}</div> : null}
            {success ? <div className="xcu-message success"><Check size={16}/>{success}</div> : null}
            {loading ? <div className="xcu-loading"><LoaderCircle size={19} className="xcu-spinner"/>Loading user from x-ui...</div> : <>
              <div className="xcu-grid">
                <label className="xcu-field"><span>Username</span><div className="xcu-input-action"><input value={username} readOnly/><button type="button" disabled><LockKeyhole size={16}/></button></div></label>
                <label className="xcu-field"><span>Traffic Limit (GB)</span><input type="number" min="0" step="0.01" value={traffic} onChange={e=>setTraffic(e.target.value)} placeholder="0 = unlimited" disabled={saving}/></label>
                <label className="xcu-field"><span>Expiry</span><input type="date" value={expiry} onChange={e=>setExpiry(e.target.value)} disabled={saving || startAfterFirstUse}/></label>
                <label className="xcu-field"><span>Status</span><select value={enabled ? "enabled" : "disabled"} onChange={e=>setEnabled(e.target.value === "enabled")} disabled={saving}><option value="enabled">Enabled</option><option value="disabled">Disabled</option></select></label>
                <label className="xcu-field xcu-full"><span>Comment</span><textarea value={comment} onChange={e=>setComment(e.target.value)} placeholder="Optional note for this user ..." disabled={saving}/></label>
              </div>

              <section className="xcu-advanced">
                <button type="button" className="xcu-advanced-head" onClick={()=>setAdvancedOpen(v=>!v)}><span><SlidersHorizontal size={17}/>Advanced Options</span><ChevronDown size={17} className={advancedOpen ? "open" : ""}/></button>
                {advancedOpen ? <div className="xcu-advanced-body">
                  <label className="xcu-field"><span>IP Limit</span><input type="number" min="0" step="1" value={limitIp} onChange={e=>setLimitIp(e.target.value)} disabled={saving}/><small>0 = unlimited</small></label>
                  <label className="xcu-field"><span>Telegram User ID</span><input value={telegramId} onChange={e=>setTelegramId(e.target.value)} placeholder="Optional" disabled={saving}/></label>
                  <label className="xcu-field"><span>Start After First Use</span><select value={startAfterFirstUse ? "on" : "off"} onChange={e=>{const on=e.target.value==="on";setStartAfterFirstUse(on);if(on)setExpiry("");}} disabled={saving}><option value="off">Off</option><option value="on">On</option></select><small>Expiry timer starts after first traffic.</small></label>
                  {startAfterFirstUse ? <label className="xcu-field"><span>Duration (days)</span><input type="number" min="1" max="3650" step="1" value={startAfterDays} onChange={e=>setStartAfterDays(e.target.value)} disabled={saving}/></label> : null}
                  <div className="xcu-option-row"><span>Auto Renew</span><strong>Off</strong></div>
                </div> : null}
              </section>
              <div className="xcu-info"><Plus size={15}/>UUID and Subscription ID are preserved.</div>
              {uuid ? <div style={{marginTop:"8px",color:"var(--muted)",fontSize:"9px"}}>UUID: {uuid}</div> : null}
              {subId ? <div style={{marginTop:"4px",color:"var(--muted)",fontSize:"9px"}}>Subscription ID: {subId}</div> : null}
            </>}
          </section>

          <aside className="xcu-inbounds">
            <div className="xcu-inbound-title"><div><Server size={18}/><strong>Attached Inbounds</strong></div><span>{selected.length} selected</span></div>
            <div className="xcu-search"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search inbounds"/></div>
            <button type="button" className="xcu-select-all" onClick={()=>setSelected(selected.length === inbounds.length ? [] : inbounds.map(x=>x.id))} disabled={loading || saving}>
              <span className={`xcu-checkbox ${selected.length > 0 && selected.length === inbounds.length ? "checked" : ""}`}>{selected.length > 0 && selected.length === inbounds.length ? <Check size={13}/> : null}</span>Select all
            </button>
            <div className="xcu-inbound-list">
              {loading ? <div className="xcu-loading"><LoaderCircle size={19} className="xcu-spinner"/>Loading...</div> : visibleInbounds.map(inbound => {
                const checked = selected.includes(inbound.id);
                const details = [inbound.protocol?.toUpperCase(), inbound.network?.toUpperCase(), inbound.security?.toUpperCase()].filter(Boolean).join(" · ");
                return <button type="button" key={inbound.id} className={`xcu-inbound-item ${checked ? "selected" : ""}`} onClick={()=>toggleInbound(inbound.id)}>
                  <span className={`xcu-checkbox ${checked ? "checked" : ""}`}>{checked ? <Check size={13}/> : null}</span>
                  <div><strong>{inbound.label}</strong><small>{details}</small></div><span className="xcu-inbound-id">#{inbound.id}</span>
                </button>;
              })}
            </div>
          </aside>
        </div>

        <footer className="xcu-footer"><div/><div className="xcu-footer-actions">
          <button type="button" className="xcu-cancel" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="xcu-submit" disabled={saving || loading}>{saving ? <LoaderCircle size={17} className="xcu-spinner"/> : <UserRoundPen size={17}/>} {saving ? "Saving..." : "Save Changes"}</button>
        </div></footer>
      </form>
    </div>
  );
}
