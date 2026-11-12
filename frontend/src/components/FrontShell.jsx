import { useEffect, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { IconAdmin, IconBack, IconBell, IconBook, IconBox, IconBuilding, IconCar, IconChat, IconClock, IconGrad, IconHeart, IconHelp,
  IconHome, IconLogout, IconMenu, IconPeople, IconPhone, IconQR, IconStar, IconUser } from "./Icons.jsx";

// Semua destinasi muka depan. Empat pertama (lalai) atau pilihan ahli jadi "ikon kegemaran" di atas.
export const DESTS = [
  { key: "transport", label: "Transport", to: "/pengangkutan", Icon: IconCar },
  { key: "kehadiran", label: "Kehadiran", to: "/kehadiran", Icon: IconClock },
  { key: "qr", label: "Kod QR", to: "/kod-qr", Icon: IconQR },
  { key: "simpanan", label: "Simpanan Barang", to: "/simpanan", Icon: IconBox },
  { key: "notifikasi", label: "Notifikasi", to: "/notis", Icon: IconBell },
  { key: "direktori", label: "Direktori Ahli", to: "/direktori", Icon: IconPeople },
  { key: "alumni", label: "Alumni", to: "/alumni", Icon: IconGrad },
  { key: "mtbiro", label: "MT dan Biro", to: "/mt-biro", Icon: IconBuilding },
  { key: "panduan", label: "Panduan", to: "/panduan", Icon: IconBook },
  { key: "hubungi", label: "Hubungi", to: "/hubungi", Icon: IconPhone },
  { key: "maklum", label: "Maklum Balas", to: "/maklum-balas", Icon: IconChat },
  { key: "sokongan", label: "Sokongan", to: "/sokongan", Icon: IconHelp },
];
export const DEFAULT_FAV = ["transport", "kehadiran", "qr", "simpanan"];

export function loadFav() {
  try {
    const v = JSON.parse(localStorage.getItem("pssgutm_fav") || "null");
    if (Array.isArray(v) && v.length === 4 && v.every((k) => DESTS.some((d) => d.key === k))) return v;
  } catch { /* abaikan */ }
  return DEFAULT_FAV;
}
export function saveFav(v) {
  try { localStorage.setItem("pssgutm_fav", JSON.stringify(v)); } catch { /* abaikan */ }
  window.dispatchEvent(new Event("pssgutm-fav"));
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Selamat pagi" : h < 15 ? "Selamat tengah hari" : h < 19 ? "Selamat petang" : "Selamat malam";
}

export function FavPicker({ onClose }) {
  const [fav, setFav] = useState(loadFav());
  const toggle = (k) => setFav((f) => (f.includes(k) ? f.filter((x) => x !== k) : f.length < 4 ? [...f, k] : f));
  return (
    <div className="fr-sheet" role="dialog">
      <div className="fr-sheet-card">
        <h3>Ikon kegemaran</h3>
        <p className="small muted">Pilih tepat 4 ikon untuk bahagian atas muka depan ({fav.length}/4).</p>
        <div className="fr-pick">
          {DESTS.map((d) => <button key={d.key} className={fav.includes(d.key) ? "on" : ""} onClick={() => toggle(d.key)}><d.Icon />{d.label}</button>)}
        </div>
        <div className="actions">
          <button className="btn" disabled={fav.length !== 4} onClick={() => { saveFav(fav); onClose(true); }}>Simpan</button>
          <button className="btn ghost" onClick={() => onClose(false)}>Batal</button>
        </div>
      </div>
    </div>
  );
}

export default function FrontShell({ user, brand, onLogout, children, home = false, title = "" }) {
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState(false);
  const [perms, setPerms] = useState(null);
  const [me, setMe] = useState(null);
  const [fav, setFav] = useState(loadFav());
  const navigate = useNavigate();
  useEffect(() => { api.get("/persatuan/me").then((m) => { setPerms(m.perms); setMe(m.person); }).catch(() => {}); }, []);
  const logo = brand?.has_logo ? brand.logo_url : "/icon-192.png";
  const manage = perms && (perms.admin || perms.attendance || perms.inventory);
  const links = fav.map((k) => DESTS.find((d) => d.key === k)).concat(DESTS.filter((d) => !fav.includes(d.key) && ["direktori", "alumni", "mtbiro", "panduan"].includes(d.key)));
  const go = (to) => { setOpen(false); navigate(to); };
  return (
    <div className="app fr">
      <header className="top fr-top">
        {home ? (
          <button className="fr-ico" aria-label="Menu" onClick={() => setOpen(true)}><IconMenu /></button>
        ) : (
          <button className="fr-ico" aria-label="Kembali" onClick={() => navigate(-1)}><IconBack /></button>
        )}
        {home ? (
          <span className="fr-brand">
            <b>{brand?.brand_name || "PSSGUTM"}</b>
            {brand?.tagline && <small>{brand.tagline}</small>}
          </span>
        ) : <b className="fr-title">{title}</b>}
        {home ? <Link to="/profil-saya" className="fr-ico" aria-label="Profil saya"><IconUser /></Link>
          : <Link to="/" className="fr-ico" aria-label="Utama"><IconHome /></Link>}
      </header>
      <main className="content fr-content">{children}</main>

      {open && <div className="fr-scrim" onClick={() => setOpen(false)} />}
      <aside className={`fr-drawer ${open ? "open" : ""}`} aria-hidden={!open}>
        <div className="fr-drawer-head">
          <img src={logo} alt="" onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = "/icon-192.png"; }} />
          <small>{greeting()},</small>
          <b>{user.name}</b>
          <span>
            {me?.intake_label && <em>Sesi {me.intake}</em>}
            <em className="ok">{me ? (me.active ? "Aktif" : "Tidak aktif") : "Aktif"}</em>
          </span>
        </div>
        <nav>
          <NavLink to="/" end onClick={() => setOpen(false)}><IconHome /> Utama</NavLink>
          <button onClick={() => { setOpen(false); setPick(true); }}><IconStar /> Ikon Kegemaran</button>
          {links.map((d) => <NavLink key={d.key} to={d.to} onClick={() => setOpen(false)}><d.Icon /> {d.label}</NavLink>)}
          <NavLink to="/profil-saya" onClick={() => setOpen(false)}><IconUser /> Profil saya</NavLink>
          {manage && <NavLink to="/persatuan" onClick={() => setOpen(false)}><IconAdmin /> Pengurusan persatuan</NavLink>}
          {user.role === "admin" && <NavLink to="/admin" onClick={() => setOpen(false)}><IconAdmin /> Admin transport</NavLink>}
        </nav>
        <button className="fr-out" onClick={() => { setOpen(false); onLogout(); }}><IconLogout /> Log keluar</button>
      </aside>
      {pick && <FavPicker onClose={(saved) => { setPick(false); if (saved) { setFav(loadFav()); go("/"); } }} />}
    </div>
  );
}
