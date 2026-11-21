import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { ExternalLink, MessageCircle, Map as MapIcon, Users, X, Smartphone } from "lucide-react";

const UA = typeof navigator === "undefined" ? "" : navigator.userAgent;
const IS_IOS = /iPhone|iPad|iPod/i.test(UA);
const IS_ANDROID = /Android/i.test(UA);
const IS_PHONE = IS_IOS || IS_ANDROID;

function phoneLink(b) {
  if (IS_IOS) return b.ios || b.web || b.android;
  return b.android || b.web || b.ios;
}

function Qr({ url, label }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    QRCode.toDataURL(url, { margin: 1, width: 168 }).then(setSrc).catch(() => setSrc(""));
  }, [url]);
  return (
    <figure className="qr-box">
      {src ? <img src={src} alt={`QR code: ${label}`} width={168} height={168}/> : <div className="qr-placeholder"/>}
      <figcaption>{label}</figcaption>
      <a href={url} target="_blank" rel="noopener noreferrer">open link</a>
    </figure>
  );
}

// On a laptop these apps can't be opened directly, so an app button shows QR codes to scan with your phone
// (Android and iPhone store pages, or the WhatsApp chat), plus the website when there is one.
function PhonePanel({ b, onClose }) {
  const codes = [];
  if (b.android) codes.push({ url: b.android, label: "Android (Google Play)" });
  if (b.ios) codes.push({ url: b.ios, label: "iPhone (App Store)" });
  if (!b.android && !b.ios && b.web) codes.push({ url: b.web, label: "Scan with your phone" });
  return (
    <div className="phone-panel" role="dialog" aria-label={`Open ${b.provider} on your phone`}>
      <div className="phone-panel-head">
        <strong><Smartphone size={16}/> {b.provider} on your phone</strong>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><X size={16}/></button>
      </div>
      <p className="muted">{b.purpose}. Scan with your phone's camera to open it there.</p>
      <div className="qr-row">{codes.map((c) => <Qr key={c.url} {...c}/>)}</div>
      {b.web && (b.android || b.ios) && (
        <a className="booking-web" href={b.web} target="_blank" rel="noopener noreferrer"><ExternalLink size={14}/> Or open the website</a>
      )}
      {b.note && <p className="booking-warn">{b.note}</p>}
    </div>
  );
}

// "Book or pay" buttons for each part of the selected journey (links come from the engine).
export default function BookingLinks({ option, goTo }) {
  const [open, setOpen] = useState(null);
  useEffect(() => { setOpen(null); }, [option?.id]);
  const links = option?.booking || [];
  if (!links.length) return null;
  const onlyMaps = links.every((b) => b.kind === "maps");
  return (
    <div className="booking-links">
      <h4>Book or pay</h4>
      <div className="booking-grid">
        {links.map((b, i) => {
          if (b.kind === "internal") {
            return (
              <button key={i} type="button" className="booking-btn" onClick={() => goTo?.(b.page)}>
                <Users size={16}/><span><strong>{b.purpose}</strong><small>{b.provider}</small></span>
              </button>
            );
          }
          const Icon = b.kind === "maps" ? MapIcon : b.provider.includes("WhatsApp") ? MessageCircle : ExternalLink;
          const body = <><Icon size={16}/><span><strong>{b.provider}</strong><small>{b.purpose}</small>{b.note && <em>{b.note}</em>}</span></>;
          // Maps and websites work anywhere; apps on a laptop go through the QR panel.
          if (b.kind === "maps" || IS_PHONE) {
            return <a key={i} className="booking-btn" href={b.kind === "maps" ? b.web : phoneLink(b)} target="_blank" rel="noopener noreferrer">{body}</a>;
          }
          return (
            <button key={i} type="button" className={`booking-btn ${open === i ? "active" : ""}`} onClick={() => setOpen(open === i ? null : i)}>
              {body}
            </button>
          );
        })}
      </div>
      {open !== null && links[open] && <PhonePanel b={links[open]} onClose={() => setOpen(null)}/>}
      <p className="muted booking-note">
        {onlyMaps
          ? "This option needs no ticket or booking. Pick a Metro, bus, train, auto or cab option to see where to book it."
          : IS_PHONE
            ? "These apps open at their home screen; enter the stops shown above. Google Maps opens with this route filled in. Fares in the app may differ from the estimate here."
            : "On a laptop, app buttons show a QR code to open the app on your phone. Google Maps opens here with this route filled in. Fares in the app may differ from the estimate here."}
      </p>
    </div>
  );
}
