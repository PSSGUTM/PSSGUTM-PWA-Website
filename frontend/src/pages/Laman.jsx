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
  const [bitPhone, setBitPhone] = useState("0192278390");
  const [canManage, setCan] = useState(false);
  useEffect(() => {
    api.get("/persatuan/inventory/list").then((res) => {
      if (Array.isArray(res)) {
        setRows(res);
      } else {
        setRows(res.items || []);
        if (res.bit_phone) setBitPhone(res.bit_phone);
      }
    }).catch(() => setRows([]));
    api.get("/persatuan/me").then((m) => setCan(!!(m.perms.inventory || m.perms.admin))).catch(() => {});
  }, []);
  if (!rows) return <p className="muted">Memuatkan…</p>;
  const cleanBitPhone = (bitPhone || "0192278390").replace(/\D/g, "").replace(/^6/, "");
  return (
    <div>
      <div className="card" style={{ background: "rgba(212,169,78,0.08)", border: "1px solid rgba(212,169,78,0.3)", marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: ".6rem" }}>
          <div>
            <b style={{ color: "var(--primary)" }}>📞 Hubungi BIT / Logistik untuk Pinjam Barang</b><br />
            <span className="small muted">Untuk urusan pinjaman barang persatuan, sila hubungi wakil BIT: <b>{bitPhone}</b></span>
          </div>
          <a
            className="btn small"
            href={`https://wa.me/6${cleanBitPhone}?text=${encodeURIComponent("Salam BIT PSSGUTM, saya ingin meminjam barang persatuan.")}`}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: "none" }}
          >
            💬 WhatsApp BIT
          </a>
        </div>
      </div>

      <div className="note small" style={{ marginBottom: "1rem" }}>
        Senarai alatan dan stok simpanan persatuan.{canManage && <> <Link to="/persatuan">Urus inventori</Link></>}
      </div>
      {rows.length === 0 && <p className="muted">Belum ada barang didaftarkan.</p>}
      {rows.map((i) => (
        <div className="card" key={i.id} style={{ display: "flex", gap: ".8rem", alignItems: "center" }}>
          {i.image ? (
            <img src={imgUrl(i.image)} alt={i.name} style={{ width: 60, height: 60, borderRadius: 10, objectFit: "cover", flexShrink: 0, border: "1px solid var(--line)" }} />
          ) : (
            <div style={{ width: 60, height: 60, borderRadius: 10, background: "rgba(212,169,78,0.1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.5rem", flexShrink: 0 }}>📦</div>
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <b>{i.name}</b> {i.category && <span className="chip">{i.category}</span>}<br />
            <span className="small muted">Ada {i.available} daripada {i.total}{i.note ? ` · ${i.note}` : ""}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function MerchandiseBKU() {
  const [data, setData] = useState(null);
  const [category, setCategory] = useState("");
  useEffect(() => {
    api.get("/persatuan/bku/merchandise").then(setData).catch(() => setData({ items: [], can_manage: false, default_phone: "0192278390" }));
  }, []);

  if (!data) return <p className="muted">Memuatkan katalog merchandise…</p>;
  const items = data.items || [];
  const categories = ["Semua", ...Array.from(new Set(items.map((x) => x.category).filter(Boolean)))];
  const filtered = category && category !== "Semua" ? items.filter((x) => x.category === category) : items;

  return (
    <div>
      <div className="card" style={{ background: "rgba(212,169,78,0.08)", border: "1px solid rgba(212,169,78,0.3)", marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: ".6rem" }}>
          <div>
            <h3 style={{ margin: 0, color: "var(--primary)" }}>🛒 Merchandise & Jual Beli BKU</h3>
            <span className="small muted">Dapatkan barangan rasmi PSSGUTM (pakaian, tanjak, sticker, cenderamata).</span>
          </div>
          {data.can_manage && (
            <Link to="/persatuan" className="btn ghost small">⚙️ Urus Produk (BKU)</Link>
          )}
        </div>
      </div>

      {categories.length > 2 && (
        <div className="seg" style={{ marginBottom: "1rem", flexWrap: "wrap" }}>
          {categories.map((c) => (
            <button key={c} className={(!category && c === "Semua") || category === c ? "on" : ""} onClick={() => setCategory(c === "Semua" ? "" : c)}>
              {c}
            </button>
          ))}
        </div>
      )}

      {filtered.length === 0 && <p className="muted">Belum ada produk merchandise didaftarkan.</p>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem" }}>
        {filtered.map((item) => {
          const phone = (item.contact_phone || data.default_phone || "0192278390").replace(/\D/g, "").replace(/^6/, "");
          const waUrl = `https://wa.me/6${phone}?text=${encodeURIComponent(`Salam BKU PSSGUTM, saya berminat untuk membeli: ${item.name} (RM${item.price.toFixed(2)}). Adakah stok masih ada?`)}`;
          return (
            <div className="card" key={item.id} style={{ display: "flex", flexDirection: "column", height: "100%", margin: 0 }}>
              {item.image ? (
                <img src={imgUrl(item.image)} alt={item.name} style={{ width: "100%", height: 180, objectFit: "cover", borderRadius: 10, border: "1px solid var(--line)", marginBottom: ".8rem" }} />
              ) : (
                <div style={{ width: "100%", height: 140, borderRadius: 10, background: "rgba(255,255,255,0.03)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "2.5rem", marginBottom: ".8rem" }}>
                  🥋
                </div>
              )}
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: ".5rem" }}>
                  <b style={{ fontSize: "1.05rem" }}>{item.name}</b>
                  <b style={{ color: "var(--primary)", fontSize: "1.1rem" }}>RM{Number(item.price || 0).toFixed(2)}</b>
                </div>
                {item.category && <span className="chip" style={{ marginTop: ".3rem" }}>{item.category}</span>}
                {item.description && <p className="small muted" style={{ whiteSpace: "pre-wrap", margin: ".6rem 0" }}>{item.description}</p>}
                <div className="small muted" style={{ marginTop: ".4rem" }}>
                  Baki stok: <b>{item.stock > 0 ? `${item.stock} unit` : <span style={{ color: "#e74c3c" }}>Habis</span>}</b>
                </div>
              </div>
              <div style={{ marginTop: "1rem" }}>
                <a className="btn wide" href={waUrl} target="_blank" rel="noreferrer" style={{ textAlign: "center", textDecoration: "none" }}>
                  💬 Tempah via WhatsApp
                </a>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
