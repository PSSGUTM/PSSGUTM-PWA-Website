import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, auth, fmtDate } from "../api.js";
import { DESTS, FavPicker, loadFav } from "../components/FrontShell.jsx";
import { imgUrl } from "../formapi.js";

const GRID = ["notifikasi", "direktori", "alumni", "mtbiro", "panduan", "hubungi", "maklum", "sokongan"];

export default function Beranda() {
  const [fav, setFav] = useState(loadFav());
  const [data, setData] = useState(null);
  const [unread, setUnread] = useState(0);
  const [profile, setProfile] = useState(auth.get()?.user);

  useEffect(() => {
    api.get("/profile").then((p) => {
      const cur = auth.get();
      if (cur) auth.set({ ...cur, user: { ...cur.user, ...p } });
      setProfile(p);
    }).catch(() => {});
  }, []);

  const isIncomplete = (u) => {
    if (!u || u.role === "admin") return false;
    const noPhone = !u.phone || u.phone.trim() === "" || u.phone === "0000000000";
    const noCollege = !u.college_id && !u.college_other;
    const noBlock = u.college_id && (!u.block || u.block.trim() === "");
    return noPhone || noCollege || noBlock;
  };
  const incomplete = isIncomplete(profile);

  useEffect(() => {
    const f = () => setFav(loadFav());
    window.addEventListener("pssgutm-fav", f);
    return () => window.removeEventListener("pssgutm-fav", f);
  }, []);
  useEffect(() => {
    api.get("/laman/home").then(setData).catch(() => setData({ announcements: [], welfare: [] }));
    api.get("/notifications").then((n) => setUnread(n.filter((x) => !x.read || x.severity === "warning").length)).catch(() => {});
  }, []);
  const byKey = (k) => DESTS.find((d) => d.key === k);
  const ann = data?.announcements || [];
  const wel = data?.welfare?.[0];
  return (
    <div className="fr-home">
      {incomplete && (
        <div className="note" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(212, 169, 78, 0.15)", border: "1px solid var(--accent)", borderRadius: 12, padding: ".8rem 1rem", margin: "0 0 1rem", gap: "1rem" }}>
          <div>
            <b style={{ color: "var(--accent)" }}>⚠️ Profil Anda Belum Lengkap</b>
            <p className="small muted" style={{ margin: ".2rem 0 0" }}>Sila lengkapkan nombor telefon, kolej dan nombor bilik untuk membuka akses perkhidmatan penuh.</p>
          </div>
          <Link to="/profil" className="btn small" style={{ flex: "none", margin: 0, padding: ".4rem .8rem" }}>Lengkapkan</Link>
        </div>
      )}

      <div className="fr-quick">
        {fav.map((k) => { const d = byKey(k); return <Link to={d.to} key={k}><span><d.Icon /></span><small>{d.label}</small></Link>; })}
      </div>

      <section>
        <div className="fr-sec-head">
          <div><h2>Pengumuman</h2><p className="small muted">Maklumat terkini daripada pengurusan</p></div>
          <Link className="btn ghost" to="/pengumuman">Lihat semua</Link>
        </div>
        {data && ann.length === 0 && <p className="muted small">Belum ada pengumuman.</p>}
        {ann.map((a) => (
          <Link to={`/pengumuman/${a.id}`} className="fr-news" key={a.id}>
            <div className="fr-news-img" style={a.image ? { backgroundImage: `url(${imgUrl(a.image)})` } : null}>{!a.image && <small>PSSGUTM</small>}</div>
            <div><b>{a.title}</b><small>{fmtDate(a.date)}</small></div>
          </Link>
        ))}
      </section>

      <div className="fr-grid">
        {GRID.map((k) => { const d = byKey(k); return (
          <Link to={d.to} key={k}><span><d.Icon />{k === "notifikasi" && unread > 0 && <i className="fr-dot">{unread > 9 ? "9+" : unread}</i>}</span><small>{d.label}</small></Link>
        ); })}
      </div>

      <section>
        <div className="fr-sec-head">
          <div><h2>{data?.titles?.kebajikan || "News"}</h2><p className="small muted">Terkini</p></div>
          <Link className="btn ghost" to="/kebajikan">Lihat semua</Link>
        </div>
        {wel ? (
          <Link to={`/kebajikan/${wel.id}`} className="fr-banner" style={wel.image ? { backgroundImage: `linear-gradient(rgba(0,0,0,.35),rgba(0,0,0,.35)),url(${imgUrl(wel.image)})` } : null}>
            <b>{wel.title}</b>
          </Link>
        ) : <div className="fr-banner empty">{data ? "Belum ada kempen kebajikan." : ""}</div>}
      </section>
    </div>
  );
}
