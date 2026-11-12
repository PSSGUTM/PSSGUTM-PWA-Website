import Contact from "../components/Contact.jsx";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { BrandMark } from "../components/Emblem.jsx";

const FALLBACK = {
  fees: { car: { dekat: 3, jauh: 4 }, motorcycle: { dekat: 1, jauh: 2 } },
  sessions: [
    { name: "Rabu", start: "9:00 PM", pickup: "8:30 PM – 8:50 PM", return: "11:00 PM" },
    { name: "Sabtu", start: "9:00 PM", pickup: "8:30 PM – 8:50 PM", return: "11:00 PM" },
  ],
};

import { DESTS } from "../components/FrontShell.jsx";
import { imgUrl } from "../formapi.js";

const byKey = (k) => DESTS.find((d) => d.key === k);
const CATS = [
  ["Transport", ["transport"]],
  ["Persatuan", ["kehadiran", "qr", "simpanan", "direktori", "alumni", "mtbiro"]],
  ["Maklumat", ["panduan", "hubungi", "maklum", "sokongan"]],
];
// Belum login: simpan tujuan, selepas login terus ke halaman itu
const go = (to) => () => { try { sessionStorage.setItem("pssgutm_next", to); } catch { /* abaikan */ } };
const TILES = ["transport", "kehadiran", "qr", "simpanan", "direktori", "mtbiro"];
const MONTHS = ["JAN", "FEB", "MAC", "APR", "MEI", "JUN", "JUL", "OGO", "SEP", "OKT", "NOV", "DIS"];

function nextTrainings(n = 4) {
  const out = [], d = new Date();
  d.setHours(0, 0, 0, 0);
  while (out.length < n) { if (d.getDay() === 3 || d.getDay() === 6) out.push(new Date(d)); d.setDate(d.getDate() + 1); }
  return out;
}
const DAYS = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu"];

export default function Landing({ brand }) {
  const [r, setR] = useState(FALLBACK);
  const [h, setH] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.publicGet("/rules").then(setR).catch(() => {});
    api.publicGet("/laman/public").then(setH).catch(() => {});
  }, []);
  const f = r.fees;
  const sesi = h?.session?.label ? h.session.label.replace(/\/(\d\d)$/, "/20$1") : "";
  const t = h?.titles || {};
  const design = h?.design || {};
  const found = q.trim() ? DESTS.filter((d) => d.label.toLowerCase().includes(q.trim().toLowerCase())) : [];
  const useImg = design.mode === "gambar" && design.bg;
  const heroStyle = useImg ? { backgroundImage: `linear-gradient(rgba(0,0,0,.45),rgba(0,0,0,.55)),url(${imgUrl(design.bg)})` } : null;
  const pat = useImg ? "none" : design.pattern || "batik";
  const trainings = useMemo(() => nextTrainings(), []);

  return (
    <div className="lp">
      <section className={`lp-hero p-${pat}`} style={heroStyle}>
        <div className="lp-top">
          <span className="brand"><img src={brand?.has_logo ? brand.logo_url : "/icon-192.png"} alt="" onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = "/icon-192.png"; }} /> {brand?.brand_name || "PSSGUTM"}</span>
          <Link className="btn ghost-light" to="/login">Login</Link>
        </div>
        <BrandMark brand={brand} size={104} />
        <h1>Persatuan Silat Seni Gayong <span>UTM</span></h1>
        <p className="lp-tag">Portal ahli PSSGUTM · Sesi {sesi}</p>
        <div className="lp-find">
          <input placeholder="Cari sistem atau modul…" value={q} onChange={(e) => setQ(e.target.value)} />
          {q.trim() && (
            <div className="lp-res">
              {found.length === 0 && <span className="muted small">Tiada padanan.</span>}
              {found.map((d) => <Link key={d.key} to="/login" onClick={go(d.to)}>{d.label}</Link>)}
            </div>
          )}
        </div>
        <div className="lp-tiles">
          {TILES.map((k) => { const d = byKey(k); return <Link to="/login" key={k} onClick={go(d.to)}><d.Icon /><span>{d.label}</span></Link>; })}
        </div>
        <div className="lp-cta">
          <Link className="btn" to="/daftar">Daftar sekarang</Link>
          <Link className="btn ghost-light" to="/login">Dah ada akaun? Login</Link>
        </div>
      </section>
      <div className="motif-strip" />

      <div className="lp-body">
        <section className="lp-card">
          <h2>{t.sistem || "Sistem & Aplikasi"}</h2>
          <p className="small muted">Log masuk untuk guna</p>
          {CATS.map(([name, keys], i) => (
            <details key={name} open={i === 0}>
              <summary>{name}</summary>
              {keys.map((k) => { const d = byKey(k); return <Link key={k} to="/login" onClick={go(d.to)}>{d.label}</Link>; })}
            </details>
          ))}
        </section>

        <div className="lp-stack">
          <section className="lp-card">
            <div className="lp-head"><h2>{t.pengumuman || "Pengumuman"}</h2></div>
            {h && h.announcements.length === 0 && <p className="muted small">Belum ada pengumuman.</p>}
            {h?.announcements.map((a) => (
              <div className="lp-item" key={a.id}>
                <div><b>{a.title}</b><small>{a.body}</small></div>
              </div>
            ))}
          </section>
          <section className="lp-card">
            <h2>{t.event || "Event"}</h2>
            {h && h.events.length === 0 && <p className="muted small">Belum ada event.</p>}
            {h?.events.map((e) => { const d = new Date(e.date + "T00:00:00"); return (
              <div className="lp-item" key={e.id}>
                <span className="lp-date"><b>{d.getDate()}</b><small style={{ color: "#fff" }}>{MONTHS[d.getMonth()]}</small></span>
                <div><b>{e.title}</b>{e.body && <small>{e.body}</small>}</div>
              </div>
            ); })}
          </section>
        </div>

        <div className="lp-stack">
          <section className="lp-card">
            <h2>{t.jadual || "Jadual Latihan"}</h2>
            <p className="small muted">{r.sessions.map((s) => `${s.name} ${s.start}`).join(" · ")}</p>
            {trainings.map((d, i) => (
              <div className="lp-slot" key={d.toISOString()}><b>{DAYS[d.getDay()]}, {d.getDate()} {MONTHS[d.getMonth()]}</b><span className="muted small">{i === 0 ? "Seterusnya" : ""}</span></div>
            ))}
            <p className="small muted" style={{ marginTop: ".6rem" }}>Transport prebet: kereta RM{f.car.dekat}/RM{f.car.jauh}, motosikal RM{f.motorcycle.dekat}/RM{f.motorcycle.jauh} seorang (kolej dekat/jauh).</p>
          </section>
          {design.poster && <img className="lp-poster" src={imgUrl(design.poster)} alt="" />}
        </div>
      </div>

      <section className="lp-bottom">
        <h2>{t.kebajikan || "News"}</h2>
        {h && h.welfare.length === 0 && <p className="muted small">Belum ada kandungan.</p>}
        <div className="lp-slider">
          {h?.welfare.map((w) => (
            <div className="lp-banner" key={w.id}
              style={w.image ? { backgroundImage: `linear-gradient(rgba(0,0,0,.3),rgba(0,0,0,.45)),url(${imgUrl(w.image)})` } : null}>{w.title}</div>
          ))}
        </div>
      </section>

      <section className="lp-band">
        <h2>Ada kereta atau motor?</h2>
        <p>Daftar sebagai prebet, isi kenderaan anda, dan persatuan akan bayar anda untuk setiap trip.</p>
        <Link className="btn" to="/daftar?driver=1">Daftar sebagai prebet</Link>
      </section>

      <footer className="land-foot">
        <div className="motif-strip" />
        <p>PSSGUTM · Sesi {sesi}</p>
        <Link className="link light" to="/login">Login ahli / admin</Link>
        <div style={{ padding: "0 1.25rem" }}><Contact light /></div>
      </footer>
    </div>
  );
}
