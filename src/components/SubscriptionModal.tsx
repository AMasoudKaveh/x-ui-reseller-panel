import { Copy, Link2, LoaderCircle, QrCode, X } from "lucide-react";
import { useEffect, useState } from "react";
import { getUserAccess, type UserAccessInfo } from "../api/userActions";

type Props = {
  open: boolean;
  userId: number | null;
  username: string;
  onClose: () => void;
  onCopied?: (message: string) => void;
};

async function copyText(text: string) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
  document.body.appendChild(ta); ta.focus(); ta.select(); document.execCommand("copy"); ta.remove();
}

export default function SubscriptionModal({ open, userId, username, onClose, onCopied }: Props) {
  const [data, setData] = useState<UserAccessInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !userId) return;
    let alive = true;
    setLoading(true); setError(""); setData(null);
    getUserAccess(userId)
      .then(result => alive && setData(result))
      .catch(err => alive && setError(err instanceof Error ? err.message : "Unable to load subscription"))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [open, userId]);

  if (!open || !userId) return null;

  const copy = async (value: string, message: string) => {
    if (!value) return;
    await copyText(value); onCopied?.(message);
  };

  return <div className="sq-backdrop" onMouseDown={e=>e.target===e.currentTarget && onClose()}>
    <section className="sq-modal">
      <header className="sq-header"><div className="sq-title"><QrCode size={20}/><div><h2>Subscription</h2><div style={{marginTop:"4px",color:"var(--muted)",fontSize:"10px"}}>{username}</div></div></div><button type="button" className="sq-close" onClick={onClose}><X size={18}/></button></header>
      {loading ? <div className="sq-content" style={{display:"flex",minHeight:"420px",alignItems:"center",justifyContent:"center",color:"var(--muted)"}}><LoaderCircle size={21} className="xcu-spinner"/><span style={{marginLeft:"8px"}}>Loading subscription...</span></div>
      : error ? <div className="sq-content" style={{display:"flex",minHeight:"300px",alignItems:"center",justifyContent:"center",color:"#ef7676"}}>{error}</div>
      : data ? <div className="sq-content">
          <div className="sq-qr-column">
            <div className="sq-qr-frame">{data.qr_svg ? <div className="sq-qr-svg" dangerouslySetInnerHTML={{__html:data.qr_svg}}/> : <div style={{width:"260px",height:"260px",display:"grid",placeItems:"center",color:"#333"}}>QR unavailable</div>}</div>
            <div className="sq-qr-caption">This QR contains the full subscription URL and includes all attached configs.</div>
            <button type="button" className="sq-copy-all" style={{marginTop:"14px"}} onClick={()=>void copy(data.subscription_url,"Subscription copied")}><Link2 size={16}/>Copy Subscription</button>
          </div>
          <div className="sq-config-column">
            <div className="sq-config-heading"><h3>Configs</h3><button type="button" className="sq-copy-all" onClick={()=>void copy(data.links.join("\n"),"Configs copied")}><Copy size={16}/>Copy All</button></div>
            <div className="sq-config-list" style={{maxHeight:"430px",overflowY:"auto"}}>
              {data.configs.length ? data.configs.map((config,index)=><div className="sq-config-item" key={`${config.name}-${index}`}><div className="sq-config-copy"><strong>{config.name}</strong><span>{config.link}</span></div><div className="sq-config-actions"><button type="button" title="Copy" onClick={()=>void copy(config.link,"Config copied")}><Copy size={16}/></button></div></div>) : <div style={{minHeight:"160px",display:"grid",placeItems:"center",color:"var(--muted)",fontSize:"12px"}}>No config links returned by x-ui</div>}
            </div>
          </div>
        </div> : null}
    </section>
  </div>;
}
