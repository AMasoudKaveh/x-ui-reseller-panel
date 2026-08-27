import { Copy, QrCode, X, ChevronLeft, ChevronRight } from "lucide-react";
import type { AdminClientAccess } from "../api/adminClients";

import { createPortal } from "react-dom";

type Props = {
  open: boolean;
  access: AdminClientAccess | null;
  onClose: () => void;
  onCopy: (text: string, message: string) => void;
};

function hostFromLink(link: string): string {
  try {
    const normalized = link.replace(/^[a-z0-9+.-]+:\/\//i, "http://");
    return new URL(normalized).host || "Configuration";
  } catch {
    return "Configuration";
  }
}

export default function AdminSubscriptionModal({ open, access, onClose, onCopy }: Props) {
  if (!open || !access) return null;

  const configurations = access.configs || [];

  // ADMIN_MODAL_BODY_PORTAL
  return createPortal(
    <div className="sq-backdrop" onMouseDown={onClose}>
      <section className="sq-modal" onMouseDown={(e) => e.stopPropagation()}>
        <header className="sq-header">
          <div className="sq-title">
            <QrCode size={23} strokeWidth={1.9} />
            <h2>{access.username}&apos;s Subscription</h2>
          </div>
          <button className="sq-close" type="button" onClick={onClose} aria-label="Close">
            <X size={21} />
          </button>
        </header>

        <div className="sq-content">
          <div className="sq-qr-column">
            <div className="sq-qr-frame">
              {access.qr_svg ? (
                <div
                  style={{ width: "304px", maxWidth: "100%" }}
                  dangerouslySetInnerHTML={{ __html: access.qr_svg }}
                />
              ) : (
                <div style={{width:"304px",height:"304px",display:"grid",placeItems:"center",color:"var(--muted)"}}>
                  QR unavailable
                </div>
              )}
            </div>
            <div className="sq-qr-caption">One QR contains all configurations in the subscription.</div>
          </div>

          <div className="sq-config-column">
            <div className="sq-config-heading">
              <h3>Configurations</h3>
              <button
                className="sq-copy-all"
                type="button"
                onClick={() => onCopy(configurations.map((item) => item.link).join("\n"), "All Links Copied")}
                disabled={!configurations.length}
              >
                <Copy size={18} />
                Copy All
              </button>
            </div>

            <div className="sq-config-list">
              {configurations.map((item, index) => (
                <div className="sq-config-item" key={`${item.name}-${index}`}>
                  <div className="sq-config-copy">
                    <strong>{item.name}</strong>
                    <span>{hostFromLink(item.link)}</span>
                  </div>
                  <div className="sq-config-actions">
                    <button type="button" title="Copy link" onClick={() => onCopy(item.link, "Configuration Link Copied")}>
                      <Copy size={18} />
                    </button>
                    <button type="button" title="QR preview">
                      <QrCode size={18} />
                    </button>
                  </div>
                </div>
              ))}
              {!configurations.length ? <div className="muted">No configuration links returned.</div> : null}
            </div>

            <div className="sq-pager">
              <button type="button"><ChevronLeft size={17} /></button>
              <span>1 / 1</span>
              <button type="button"><ChevronRight size={17} /></button>
            </div>
          </div>
        </div>
      </section>
    </div>
  , document.body);
}
