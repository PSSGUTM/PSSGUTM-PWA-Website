import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, auth } from "./api.js";
import Auth from "./pages/Auth.jsx";
import Landing from "./pages/Landing.jsx";
import Home from "./pages/Home.jsx";
import Setup from "./pages/Setup.jsx";
import Admin, { Treasurer } from "./pages/Admin.jsx";
import Driver from "./pages/Driver.jsx";
import Prebet, { Pendapatan } from "./pages/Prebet.jsx";
import Bayaran from "./pages/Bayaran.jsx";
import Rules from "./pages/Rules.jsx";
import Forgot from "./pages/Forgot.jsx";
import Reset from "./pages/Reset.jsx";
import Notis from "./pages/Notis.jsx";
import Persatuan from "./pages/Persatuan.jsx";
import Hadir from "./pages/Hadir.jsx";
import FrontShell from "./components/FrontShell.jsx";
import Beranda from "./pages/Beranda.jsx";
import { NoticeList, NoticeDetail, TextPage, MaklumBalas, Simpanan } from "./pages/Laman.jsx";
import { Direktori, MTBiro } from "./pages/Direktori.jsx";
import { ProfilSaya, KehadiranSaya } from "./pages/ProfilSaya.jsx";
import KodQR from "./pages/KodQR.jsx";
import Pengangkutan from "./pages/Pengangkutan.jsx";
import { ToastProvider } from "./components/Toast.jsx";
import { BrandCtx } from "./components/BrandContext.jsx";
import { syncTheme } from "./components/Theme.jsx";
import { IconAdmin, IconBack, IconCar, IconCoin, IconHome, IconPeople, IconRules, IconUser } from "./components/Icons.jsx";

// Warna teks yang sesuai di atas warna latar (supaya boleh baca walau admin pilih warna cerah)
function readable(hex, light = "#ffffff", dark = "#16120a") {
  const n = parseInt(hex.replace("#", ""), 16);
  const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return lum > 0.62 ? dark : light;
}

export function applyBranding(b) {
  const r = document.documentElement.style;
  r.setProperty("--primary", b.brand_primary);
  r.setProperty("--accent", b.brand_accent);
  r.setProperty("--on-primary", readable(b.brand_primary));
  r.setProperty("--on-accent", readable(b.brand_accent));
  document.title = b.brand_name;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", b.brand_primary);
}

// Menu ikut peranan: setiap peranan ada "Utama" sendiri.
export function tabsFor(user) {
  const t = [];
  const prebet = user.role === "driver", admin = user.role === "admin";
  t.push(["/", "Beranda", IconHome, true]);
  t.push(["/transport", "Transport", admin ? IconAdmin : IconCar, true]);
  if (prebet) t.push(["/driver", "Driver", IconCar]);
  if (prebet) t.push(["/pendapatan", "Pendapatan", IconCoin]);
  if (admin || (prebet && user.passenger_ok)) t.push(["/penumpang", "Penumpang", IconPeople]);
  if (!prebet || user.passenger_ok) t.push(["/bayaran", "Bayaran", IconCoin]);
  if (user.is_treasurer && !admin) t.push(["/bendahari", "Bendahari", IconCoin]);
  t.push(["/profil", "Profil", IconUser]);
  t.push(["/rules", "Syarat", IconRules]);
  return t;
}

function Shell({ user, onLogout, onProfile, brand, children }) {
  const loc = useLocation();
  const [unread, setUnread] = useState(0);
  useEffect(() => { api.get("/notifications").then((n) => setUnread(n.filter((x) => !x.read || x.severity === "warning").length)).catch(() => {}); }, [loc.pathname]);
  // Segarkan peranan/kebenaran (cth admin lulus "jadi penumpang", atau lantik bendahari) tanpa perlu login semula
  useEffect(() => {
    api.get("/profile").then((p) => {
      if (p.theme) syncTheme(p.theme);
      if (p.role !== user.role || p.passenger_ok !== user.passenger_ok || p.is_treasurer !== user.is_treasurer) onProfile(p);
    }).catch(() => {});
  }, [loc.pathname]);
  const navigate = useNavigate();
  const canBack = (window.history.state?.idx ?? 0) > 0;
  return (
    <div className="app">
      <header className="top">
        <button className="fr-ico" aria-label="Kembali" onClick={() => (canBack ? navigate(-1) : navigate("/"))}><IconBack /></button>
        <span className="brand">
          <img src={brand?.has_logo ? brand.logo_url : "/icon-192.png"} alt="" onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = "/icon-192.png"; }} /> {brand?.brand_name || "PSSGUTM"}
        </span>
        <span className="top-actions">
          <Link to="/notis" className="bell" aria-label="Notifikasi">🔔{unread > 0 && <span className="badge-dot">{unread > 9 ? "9+" : unread}</span>}</Link>
          <button className="link light" onClick={onLogout}>Keluar</button>
        </span>
      </header>
      <div className="motif-strip" />
      <main className="content">{children}</main>
      <nav className="tabs">
        {tabsFor(user).map(([to, label, Icon, end]) => <NavLink key={to} to={to} end={end}><Icon /><small>{label}</small></NavLink>)}
      </nav>
    </div>
  );
}

// Imbas QR kehadiran semasa belum log masuk: simpan tujuan, hantar ke log masuk, kemudian kembali ke sini
function NextLogin() {
  try { sessionStorage.setItem("pssgutm_next", window.location.pathname); } catch { /* abaikan */ }
  return <Navigate to="/login" replace />;
}

export default function App() {
  const [session, setSession] = useState(auth.get());
  const [brand, setBrand] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.publicGet("/branding").then((b) => {
      const base = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const full = { ...b, logo_url: `${base}/branding/logo?v=${Date.now()}` };
      applyBranding(full);
      setBrand(full);
    }).catch(() => {});
  }, []);

  const login = (data) => {
    const s = { token: data.access_token, user: data.user };
    auth.set(s);
    setSession(s);
    if (data.user?.theme) syncTheme(data.user.theme);
    let next = "/";
    try { next = sessionStorage.getItem("pssgutm_next") || "/"; sessionStorage.removeItem("pssgutm_next"); } catch { /* abaikan */ }
    navigate(next);
  };
  const logout = () => {
    auth.clear();
    setSession(null);
    navigate("/");
  };

  if (!session) {
    return (
      <BrandCtx.Provider value={brand}>
      <Routes>
        <Route path="/" element={<Landing brand={brand} />} />
        <Route path="/login" element={<Auth initialMode="login" onAuth={login} brand={brand} />} />
        <Route path="/daftar" element={<Auth initialMode="register" onAuth={login} brand={brand} />} />
        <Route path="/hadir/:token" element={<NextLogin />} />
        <Route path="/lupa" element={<Forgot brand={brand} />} />
        <Route path="/reset-password" element={<Reset brand={brand} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </BrandCtx.Provider>
    );
  }
  const user = session.user;
  const onProfile = (u) => { const n = { ...session, user: { ...session.user, ...u } }; auth.set(n); setSession(n); };
  const adminEl = <Admin brand={brand} onBrand={(b) => { applyBranding(b); setBrand({ ...brand, ...b, logo_url: `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/branding/logo?v=${Date.now()}` }); }} />;
  // Halaman muka depan baharu (header + menu sisi, tiada tab bawah)
  const F = (title, el, home = false) => <FrontShell user={user} brand={brand} onLogout={logout} title={title} home={home}>{el}</FrontShell>;
  return (
    <BrandCtx.Provider value={brand}>
    <ToastProvider>
      <Routes>
        <Route path="/" element={F("", <Beranda />, true)} />
        <Route path="/pengangkutan" element={F("Transport", <Pengangkutan user={user} />)} />
        <Route path="/kehadiran" element={F("Kehadiran", <KehadiranSaya />)} />
        <Route path="/kod-qr" element={F("Kod QR", <KodQR />)} />
        <Route path="/hadir/:token" element={F("Kehadiran", <Hadir />)} />
        <Route path="/simpanan" element={F("Simpanan Barang", <Simpanan />)} />
        <Route path="/direktori" element={F("Direktori Ahli", <Direktori kind="SG" />)} />
        <Route path="/alumni" element={F("Alumni", <Direktori kind="SSG" />)} />
        <Route path="/mt-biro" element={F("MT dan Biro", <MTBiro />)} />
        <Route path="/pengumuman" element={F("Pengumuman", <NoticeList kind="pengumuman" />)} />
        <Route path="/pengumuman/:id" element={F("Pengumuman", <NoticeDetail kind="pengumuman" />)} />
        <Route path="/kebajikan" element={F("Kebajikan", <NoticeList kind="kebajikan" />)} />
        <Route path="/kebajikan/:id" element={F("Kebajikan", <NoticeDetail kind="kebajikan" />)} />
        <Route path="/event" element={F("Event", <NoticeList kind="event" />)} />
        <Route path="/event/:id" element={F("Event", <NoticeDetail kind="event" />)} />
        <Route path="/panduan" element={F("Panduan", <TextPage pageKey="panduan" />)} />
        <Route path="/hubungi" element={F("Hubungi", <TextPage pageKey="hubungi" />)} />
        <Route path="/sokongan" element={F("Sokongan", <TextPage pageKey="sokongan" />)} />
        <Route path="/maklum-balas" element={F("Maklum Balas", <MaklumBalas />)} />
        <Route path="/profil-saya" element={F("Profil saya", <ProfilSaya user={user} />)} />
        <Route path="/persatuan" element={F("Pengurusan persatuan", <Persatuan />)} />
        <Route path="/*" element={
          <Shell user={user} onLogout={logout} onProfile={onProfile} brand={brand}>
            <Routes>
              <Route path="/transport" element={user.role === "driver" ? <Prebet user={user} /> : user.role === "admin" ? adminEl : <Home user={user} />} />
              <Route path="/penumpang" element={<Home user={user} />} />
              <Route path="/profil" element={<Setup onProfile={onProfile} />} />
              <Route path="/setup" element={<Navigate to="/profil" replace />} />
              <Route path="/driver" element={<Driver />} />
              <Route path="/prebet" element={<Navigate to="/transport" replace />} />
              <Route path="/pendapatan" element={<Pendapatan />} />
              <Route path="/bayaran" element={<Bayaran />} />
              <Route path="/rules" element={<Rules />} />
              <Route path="/notis" element={<Notis />} />
              <Route path="/reset-password" element={<Reset brand={brand} />} />
              {(user.role === "admin" || user.is_treasurer) && <Route path="/bendahari" element={<Treasurer />} />}
              {user.role === "admin" && <Route path="/admin" element={adminEl} />}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Shell>
        } />
      </Routes>
    </ToastProvider>
    </BrandCtx.Provider>
  );
}
