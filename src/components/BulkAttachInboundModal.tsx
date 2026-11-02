import { Search, Server, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

export type BulkInboundOption = {
  id: number;
  label: string;
  detail?: string;
};

export default function BulkAttachInboundModal({
  open, count, inbounds, busy, onClose, onConfirm,
}: {
  open: boolean;
  count: number;
  inbounds: BulkInboundOption[];
  busy: boolean;
  onClose: () => void;
  onConfirm: (inboundId: number) => void | Promise<void>;
}) {
  const [selected, setSelected] = useState(0);
  const [query, setQuery] = useState("");
  useEffect(() => { if (open) { setSelected(0); setQuery(""); } }, [open]);
  const shown = useMemo(() => inbounds.filter(item => `${item.label} ${item.detail || ""} ${item.id}`.toLowerCase().includes(query.toLowerCase())), [inbounds, query]);
  if (!open) return null;

  return <div className="cu-backdrop bulk-inbound-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section className="cu-modal bulk-inbound-modal" role="dialog" aria-modal="true">
      <header className="cu-header">
        <div className="cu-header-icon"><Server size={22}/></div>
        <div><h2>Add Inbound</h2><p>Add one inbound to {count.toLocaleString()} selected item{count === 1 ? "" : "s"}</p></div>
        <button type="button" onClick={onClose} disabled={busy} aria-label="Close"><X/></button>
      </header>
      <div className="bulk-inbound-body">
        <label className="cu-inbound-search"><Search size={18}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search inbounds"/></label>
        <div className="cu-inbound-list">
          {shown.map(item => <button type="button" key={item.id} className={`cu-inbound-item ${selected === item.id ? "selected" : ""}`} onClick={() => setSelected(item.id)}>
            <span className={`cu-check ${selected === item.id ? "checked" : ""}`}>{selected === item.id ? "✓" : ""}</span>
            <span className="cu-inbound-copy"><strong>{item.label}</strong><small>{item.detail || "Inbound"}</small></span>
            <span className="cu-inbound-id">#{item.id}</span>
          </button>)}
          {!shown.length ? <div className="bulk-inbound-empty">No inbounds found.</div> : null}
        </div>
      </div>
      <footer className="cu-footer"><button type="button" className="cu-cancel" onClick={onClose} disabled={busy}>Cancel</button><button type="button" className="cu-submit" disabled={!selected || busy} onClick={() => void onConfirm(selected)}>{busy ? "Applying…" : `Add to ${count.toLocaleString()}`}</button></footer>
    </section>
  </div>;
}
