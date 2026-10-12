import { FormEvent, useEffect, useMemo, useState } from "react";
import { Check, LoaderCircle, Search, Server, UsersRound, X } from "lucide-react";
import {
  createBulkXuiUsers,
  getXuiInbounds,
  type BulkCreateUserPayload,
  type XuiInbound,
} from "../api/createUser";
import { createAdminClientsBulk } from "../api/adminClients";
import {
  getAdminInbounds,
  getAdminRepresentatives,
  type AdminRepresentative,
} from "../api/adminRepresentatives";

type Props = {
  open: boolean;
  portal: "admin" | "reseller";
  onClose: () => void;
  onCreated: () => void | Promise<void>;
};

const INITIAL: BulkCreateUserPayload = {
  inbound_ids: [],
  method: "random",
  username_prefix: "user",
  number_of_clients: 1,
  subscription_id: "",
  group: "",
  hwid_limit: 0,
  comment: "",
  limit_ip: 0,
  traffic_gb: 0,
  start_after_first_use: false,
  duration_days: 0,
  auto_renew: 0,
  renew_on_day: 0,
  max_renewals: 0,
  traffic_reset: 0,
  enabled: true,
};

export default function BulkUserModal({ open, portal, onClose, onCreated }: Props) {
  const [form, setForm] = useState<BulkCreateUserPayload>(INITIAL);
  const [inbounds, setInbounds] = useState<XuiInbound[]>([]);
  const [representatives, setRepresentatives] = useState<AdminRepresentative[]>([]);
  const [ownerId, setOwnerId] = useState(0);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    setError("");
    const task = portal === "admin"
      ? Promise.all([getAdminInbounds(), getAdminRepresentatives()]).then(([items, reps]) => {
          if (!alive) return;
          setInbounds(items.map(item => ({ ...item, remark: item.name, enabled: item.enabled })));
          setRepresentatives(reps.representatives.filter(item => item.status === "Active"));
        })
      : getXuiInbounds().then(items => { if (alive) setInbounds(items); });
    task.catch(err => { if (alive) setError(err instanceof Error ? err.message : "Unable to load form data"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [open, portal]);

  const shown = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return inbounds;
    return inbounds.filter(item => [item.label, item.remark, item.protocol, item.port, item.id].join(" ").toLowerCase().includes(value));
  }, [inbounds, query]);

  if (!open) return null;

  const number = (key: keyof BulkCreateUserPayload, value: string) => {
    setForm(current => ({ ...current, [key]: Math.max(0, Number(value || 0)) }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.inbound_ids.length) return setError("Attached Inbounds is required");
    if (portal === "admin" && !ownerId) return setError("Representative Owner is required");
    setBusy(true);
    setError("");
    try {
      const result = portal === "admin"
        ? await createAdminClientsBulk({ ...form, owner_rep_id: ownerId })
        : await createBulkXuiUsers(form);
      if (result.errors.length) {
        setError(`${result.created.length} created, ${result.errors.length} failed: ${result.errors[0].detail}`);
        if (result.created.length) await onCreated();
        return;
      }
      await onCreated();
      setForm(INITIAL);
      setOwnerId(0);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk creation failed");
    } finally {
      setBusy(false);
    }
  };

  return <div className="bulk-backdrop" onMouseDown={onClose}>
    <form className="bulk-modal" onSubmit={submit} onMouseDown={event => event.stopPropagation()}>
      <header className="bulk-header">
        <div><UsersRound size={21}/><div><h2>Add Bulk</h2><p>Create multiple clients with shared settings</p></div></div>
        <button type="button" onClick={onClose} aria-label="Close"><X size={20}/></button>
      </header>

      <div className="bulk-body">
        {portal === "admin" ? <label className="bulk-field required">
          <span>Representative Owner</span>
          <select value={ownerId} onChange={event => setOwnerId(Number(event.target.value))}>
            <option value={0}>Select a representative</option>
            {representatives.map(item => <option key={item.id} value={item.id}>{item.username}</option>)}
          </select>
        </label> : null}

        <section className="bulk-inbounds">
          <div className="bulk-label required"><span>Attached Inbounds</span><div><button type="button" onClick={() => setForm(current => ({...current, inbound_ids: shown.map(item => item.id)}))}>Select all</button><button type="button" onClick={() => setForm(current => ({...current, inbound_ids: []}))}>Clear all</button></div></div>
          <div className="bulk-search"><Search size={17}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search inbounds"/></div>
          <div className="bulk-inbound-list">
            {shown.map(item => {
              const checked = form.inbound_ids.includes(item.id);
              return <button type="button" className={checked ? "selected" : ""} key={item.id} onClick={() => setForm(current => ({...current, inbound_ids: checked ? current.inbound_ids.filter(id => id !== item.id) : [...current.inbound_ids, item.id]}))}>
                <span className="bulk-check">{checked ? <Check size={13}/> : null}</span><Server size={16}/><span>{item.label || item.remark || `Inbound #${item.id}`}</span>
              </button>;
            })}
          </div>
        </section>

        <div className="bulk-grid">
          <label className="bulk-field required"><span>Method</span><select value={form.method} onChange={event => setForm({...form, method: event.target.value as "random"|"sequential"})}><option value="random">Random</option><option value="sequential">Sequential</option></select></label>
          <label className="bulk-field required"><span>Number of Clients</span><input type="number" min="1" max="100" value={form.number_of_clients} onChange={event => number("number_of_clients", event.target.value)}/></label>
          <label className="bulk-field"><span>Username Prefix</span><input value={form.username_prefix} onChange={event => setForm({...form, username_prefix:event.target.value})} placeholder="user"/></label>
          <label className="bulk-field"><span>Subscription ID</span><input value={form.subscription_id} onChange={event => setForm({...form, subscription_id:event.target.value})}/></label>
          <label className="bulk-field"><span>Group</span><input value={form.group} onChange={event => setForm({...form, group:event.target.value})} placeholder="e.g. customer-a"/></label>
          <label className="bulk-field"><span>HWID Limit</span><input type="number" min="0" value={form.hwid_limit} onChange={event => number("hwid_limit",event.target.value)}/></label>
          <label className="bulk-field bulk-wide"><span>Comment</span><input value={form.comment} onChange={event => setForm({...form, comment:event.target.value})}/></label>
          <label className="bulk-field"><span>IP Limit</span><input type="number" min="0" value={form.limit_ip} onChange={event => number("limit_ip",event.target.value)}/></label>
          <label className="bulk-field"><span>Traffic Limit (GB)</span><input type="number" min="0" step="0.1" value={form.traffic_gb} onChange={event => number("traffic_gb",event.target.value)}/></label>
          <label className="bulk-toggle"><span>Start After First Use</span><input type="checkbox" checked={form.start_after_first_use} onChange={event => setForm({...form,start_after_first_use:event.target.checked})}/></label>
          <label className="bulk-field"><span>Duration (days)</span><input type="number" min="0" value={form.duration_days} onChange={event => number("duration_days",event.target.value)}/></label>
          <label className="bulk-field"><span>Auto Renew</span><input type="number" min="0" value={form.auto_renew} onChange={event => number("auto_renew",event.target.value)}/></label>
          <label className="bulk-field"><span>Renew on day</span><input type="number" min="0" max="31" value={form.renew_on_day} onChange={event => number("renew_on_day",event.target.value)}/></label>
          <label className="bulk-field"><span>Max renewals</span><input type="number" min="0" value={form.max_renewals} onChange={event => number("max_renewals",event.target.value)}/></label>
          <label className="bulk-field"><span>Traffic Reset</span><select value={form.traffic_reset} onChange={event => number("traffic_reset",event.target.value)}><option value="0">Never</option><option value="1">Daily</option><option value="7">Weekly</option><option value="30">Monthly</option></select></label>
        </div>

        {loading ? <div className="bulk-message"><LoaderCircle className="spin" size={17}/>Loading...</div> : null}
        {error ? <div className="bulk-error" role="alert">{error}</div> : null}
      </div>

      <footer className="bulk-footer"><button type="button" onClick={onClose}>Close</button><button className="primary" type="submit" disabled={busy || loading}>{busy ? <LoaderCircle className="spin" size={17}/> : null}Create</button></footer>
    </form>
  </div>;
}
