import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtDate } from "../api.js";
import { imgUrl } from "../formapi.js";
import { useToast } from "../components/Toast.jsx";

const fail = (e) => alert(e.message);

// Senarai + butiran pengumuman atau kebajikan
export function NoticeList({ kind }) {
  const [rows, setRows] = useState(null);
  const [title, setTitle] = useState("");
  useEffect(() => {
    api.get(`/laman/notices?kind=${kind}`).then(setRows).catch(() => setRows([]));
    api.get("/laman/home").then((h) => setTitle(h.titles?.[kind] || "")).catch(() => {});
  }, [kind]);
  if (!rows) return <p className="muted">Memuatkan…</p>;
  const head = title ? <h2 style={{ margin: ".2rem 0 .6rem" }}>{title}</h2> : null;
  if (rows.length === 0) return <>{head}<p className="muted">Belum ada kandungan.</p></>;
  return <>{head}{rows.map((a) => (
    <Link to={`/${kind}/${a.id}`} className="fr-news" key={a.id}>
      <div className="fr-news-img" style={a.image ? { backgroundImage: `url(${imgUrl(a.image)})` } : null}>{!a.image && <small>PSSGUTM</small>}</div>
      <div><b>{a.title}</b><small>{fmtDate(a.date)}</small><span className="muted small">{a.body}</span></div>
    </Link>
  ))}</>;
}

export function NoticeDetail({ kind }) {
  const { id } = useParams();
  const [n, setN] = useState(undefined);
  useEffect(() => { api.get(`/laman/notices?kind=${kind}`).then((r) => setN(r.find((x) => String(x.id) === id) || null)).catch(() => setN(null)); }, [kind, id]);
  if (n === undefined) return <p className="muted">Memuatkan…</p>;
  if (n === null) return <p className="muted">Tidak ditemui.</p>;
  return (
    <article className="card">
      {n.image && <img className="fr-hero" src={imgUrl(n.image)} alt="" />}
      <h2>{n.title}</h2>
      <p className="small muted">{fmtDate(n.date)}</p>
      <p style={{ whiteSpace: "pre-wrap" }}>{n.body}</p>
      {n.link && <p><a href={n.link} target="_blank" rel="noreferrer">Buka pautan</a></p>}
    </article>
  );
}

// Panduan, Hubungi, Sokongan: teks yang admin edit
export function TextPage({ pageKey }) {
  const [p, setP] = useState(null);
  useEffect(() => { api.get(`/laman/page/${pageKey}`).then(setP).catch(() => setP({ body: "" })); }, [pageKey]);
  if (!p) return <p className="muted">Memuatkan…</p>;
  return <div className="card"><p style={{ whiteSpace: "pre-wrap" }}>{p.body}</p></div>;
}

export function MaklumBalas() {
  const toast = useToast();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const send = (e) => {
    e.preventDefault();
    setBusy(true);
    api.post("/laman/feedback", { message: msg }).then(() => { setMsg(""); toast("Maklum balas dihantar. Terima kasih."); }).catch(fail).finally(() => setBusy(false));
  };
  return (
    <form className="card" onSubmit={send}>
      <p className="small muted">Cadangan, aduan atau masalah app. Pentadbir akan membacanya.</p>
      <textarea rows={6} required minLength={3} maxLength={1500} placeholder="Tulis di sini…" value={msg} onChange={(e) => setMsg(e.target.value)} />
      <button className="btn wide" disabled={busy}>Hantar</button>
    </form>
  );
}

export function Simpanan() {
  const [rows, setRows] = useState(null);
  const [canManage, setCan] = useState(false);
  useEffect(() => {
    api.get("/persatuan/inventory/list").then(setRows).catch(() => setRows([]));
    api.get("/persatuan/me").then((m) => setCan(!!(m.perms.inventory || m.perms.admin))).catch(() => {});
  }, []);
  if (!rows) return <p className="muted">Memuatkan…</p>;
  return (
    <div>
      <div className="note small">Untuk meminjam barang, hubungi pengurus inventori persatuan.{canManage && <> <Link to="/persatuan">Urus inventori</Link></>}</div>
      {rows.length === 0 && <p className="muted">Belum ada barang didaftarkan.</p>}
      {rows.map((i) => (
        <div className="card" key={i.id}>
          <b>{i.name}</b> {i.category && <span className="chip">{i.category}</span>}<br />
          <span className="small muted">Ada {i.available} daripada {i.total}{i.note ? ` · ${i.note}` : ""}</span>
        </div>
      ))}
    </div>
  );
}
