import { AlertTriangle, Trash2, UserX, X } from "lucide-react";
import { useEffect, useState } from "react";
import { executeDisabledCleanup, previewDisabledCleanup, type DisabledCleanupMode, type DisabledCleanupPreview } from "../api/userActions";

export default function DisabledCleanupModal({open,onClose,onCompleted,onToast}:{open:boolean;onClose:()=>void;onCompleted:()=>Promise<void>;onToast:(message:string)=>void}) {
  const [mode,setMode]=useState<DisabledCleanupMode>("all");
  const [days,setDays]=useState(30);
  const [preview,setPreview]=useState<DisabledCleanupPreview|null>(null);
  const [loading,setLoading]=useState(false);
  const [deleting,setDeleting]=useState(false);
  const [confirmed,setConfirmed]=useState(false);

  const loadPreview=async(nextMode=mode,nextDays=days)=>{
    setLoading(true); setConfirmed(false);
    try { setPreview(await previewDisabledCleanup(nextMode,nextDays)); }
    catch(error){ onToast(error instanceof Error?error.message:"Unable to preview disabled users"); }
    finally { setLoading(false); }
  };
  useEffect(()=>{if(open){setMode("all");setDays(30);setPreview(null);setConfirmed(false);void loadPreview("all",30)}},[open]);
  if(!open)return null;
  const remove=async()=>{
    if(!preview?.count||!confirmed)return;
    setDeleting(true);
    try{
      const result=await executeDisabledCleanup(mode,days);
      onToast(result.errors.length?`${result.deleted.length} removed, ${result.errors.length} failed`:`${result.deleted.length} disabled users removed`);
      await onCompleted(); onClose();
    }catch(error){onToast(error instanceof Error?error.message:"Cleanup failed")}
    finally{setDeleting(false)}
  };
  return <div className="cu-backdrop disabled-cleanup-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!deleting)onClose()}}>
    <section className="cu-modal disabled-cleanup-modal" role="dialog" aria-modal="true">
      <header className="cu-header"><div className="cu-header-icon"><UserX size={22}/></div><div><h2>Remove Disabled Users</h2><p>Preview and permanently remove disabled users from x-ui</p></div><button type="button" onClick={onClose} disabled={deleting}><X/></button></header>
      <div className="disabled-cleanup-body">
        <div className="disabled-cleanup-modes">
          <label className={mode==="all"?"active":""}><input type="radio" checked={mode==="all"} onChange={()=>{setMode("all");void loadPreview("all",days)}}/><span><strong>All disabled users</strong><small>Remove every independently disabled user</small></span></label>
          <label className={mode==="older_than"?"active":""}><input type="radio" checked={mode==="older_than"} onChange={()=>{setMode("older_than");void loadPreview("older_than",days)}}/><span><strong>Disabled longer than</strong><small>Only users disabled before the selected age</small></span></label>
        </div>
        {mode==="older_than"?<label className="cu-field"><span>Number of days</span><input type="number" min={1} max={3650} value={days} onChange={event=>setDays(Math.max(1,Number(event.target.value)||1))} onBlur={()=>void loadPreview("older_than",days)}/></label>:null}
        <div className="disabled-cleanup-summary"><Trash2 size={20}/><div><strong>{loading?"Checking…":`${preview?.count||0} users will be removed`}</strong><span>Quota-held users are excluded to prevent accidental deletion.</span></div></div>
        {preview?.users.length?<div className="disabled-cleanup-list">{preview.users.map(user=><div key={user.id}><span><strong>{user.email}</strong><small>{user.disable_reason||user.status} · disabled {user.disabled_at||"unknown"}</small></span><b>#{user.id}</b></div>)}</div>:null}
        {preview?.truncated?<p className="disabled-cleanup-note">Showing the first 250 users. All {preview.count} matching users will be processed.</p>:null}
        <label className="disabled-cleanup-confirm"><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}/><span><AlertTriangle size={17}/>I understand these users and their x-ui accounts will be permanently deleted.</span></label>
      </div>
      <footer className="cu-footer"><button type="button" className="cu-cancel" onClick={onClose} disabled={deleting}>Cancel</button><button type="button" className="cu-danger" disabled={!confirmed||!preview?.count||loading||deleting} onClick={()=>void remove()}>{deleting?"Removing…":`Remove ${preview?.count||0} users`}</button></footer>
    </section>
  </div>;
}
