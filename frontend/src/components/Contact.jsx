import { useBrand } from "./BrandContext.jsx";

// Hubungi pentadbir website: WhatsApp dan emel (ditetapkan admin dalam Branding).
export default function Contact({ compact = false, light = false }) {
  const b = useBrand();
  const wa = b?.contact_whatsapp, em = b?.contact_email;
  if (!wa && !em) return null;
  const pretty = wa ? `+${wa.slice(0, 2)}${wa.slice(2, 4)}-${wa.slice(4)}` : "";
  return (
    <div className={`contact ${light ? "light" : ""}`}>
      {!compact && <p className="small muted" style={light ? { color: "rgba(255,255,255,.75)" } : undefined}>Ada masalah dengan website ini? Hubungi pentadbir:</p>}
      <div className="actions">
        {wa && <a className="btn ghost" href={`https://wa.me/${wa}?text=${encodeURIComponent("Salam, saya nak tanya/lapor tentang app prebet PSSGUTM: ")}`} target="_blank" rel="noreferrer">💬 WhatsApp {pretty}</a>}
        {em && <a className="btn ghost" href={`mailto:${em}?subject=${encodeURIComponent("Masalah app prebet PSSGUTM")}`}>✉️ {em}</a>}
      </div>
    </div>
  );
}
