import { useEffect, useState, useRef } from "react";
import { api, auth } from "../api.js";
import { imgUrl } from "../formapi.js";

const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

// Direktori ahli (SG) atau alumni (SSG): nama, sesi, kolej dan jawatan sahaja
export function Direktori({ kind }) {
  const [q, setQ] = useState("");
  const [ses, setSes] = useState("");
  const [res, setRes] = useState(null);
  useEffect(() => {
    const t = setTimeout(() => api.get(`/persatuan/directory?kind=${kind}&q=${encodeURIComponent(q)}&session=${ses}`).then(setRes).catch(() => setRes({ items: [], sessions: [], total: 0 })), 250);
    return () => clearTimeout(t);
  }, [kind, q, ses]);
  return (
    <div>
      <input className="fr-search" placeholder="Cari nama" value={q} onChange={(e) => setQ(e.target.value)} />
      {res && res.sessions.length > 0 && (
        <div className="fr-chips">
          <button className={!ses ? "on" : ""} onClick={() => setSes("")}>Semua</button>
          {res.sessions.slice(0, 14).map((s) => <button key={s} className={ses === s ? "on" : ""} onClick={() => setSes(s)}>{s}</button>)}
        </div>
      )}
      {res && <p className="small muted">{res.total} {kind === "SSG" ? "alumni" : "ahli"} · disusun A hingga Z</p>}
      {!res && <p className="muted">Memuatkan…</p>}
      {res?.items.map((p) => (
        <div className="fr-person" key={p.id}>
          <span className="fr-av">{initials(p.name)}</span>
          <div>
            <b>{p.name}</b>
            <small>Sesi {p.intake}{p.college ? ` · ${p.college}` : ""}</small>
            {p.posts?.length > 0 && <small className="fr-posts">{p.posts.join(", ")}</small>}
          </div>
          {p.is_coach && <em className="fr-tag">Jurulatih</em>}
        </div>
      ))}
    </div>
  );
}

export function MTBiro() {
  const [ses, setSes] = useState("");
  const [d, setD] = useState(null);
  const [chart, setChart] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);
  const [isAdmin, setIsAdmin] = useState(auth.get()?.user?.role === "admin");

  useEffect(() => {
    api.get("/persatuan/me").then((m) => {
      if (m?.perms?.admin) setIsAdmin(true);
    }).catch(() => {});
  }, []);

  const loadChart = () => api.get("/persatuan/org-chart").then((r) => setChart(r.image || "")).catch(() => {});

  useEffect(() => {
    api.get(`/persatuan/structure?session=${ses}`).then(setD).catch(() => setD({ sessions: [], mt: [], biros: [] }));
    loadChart();
  }, [ses]);

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const r = await api.upload("/persatuan/org-chart", f);
      setChart(r.image || "");
    } catch (err) {
      alert("Gagal muat naik: " + err.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onDeleteChart = async () => {
    if (!confirm("Padam gambar carta organisasi ini?")) return;
    try {
      await api.del("/persatuan/org-chart");
      setChart("");
    } catch (err) {
      alert("Gagal padam: " + err.message);
    }
  };

  if (!d) return <p className="muted">Memuatkan…</p>;
  return (
    <div>
      <div className="fr-chips">
        {d.sessions.map((s) => <button key={s} className={d.session === s ? "on" : ""} onClick={() => setSes(s)}>{s}</button>)}
      </div>

      {/* Carta Organisasi Infografik */}
      {chart && (
        <div className="card" style={{ padding: ".8rem", textAlign: "center", marginBottom: "1rem" }}>
          <h4 style={{ margin: "0 0 .5rem", color: "var(--accent)" }}>📊 Carta Organisasi Jawatankuasa</h4>
          <a href={imgUrl(chart)} target="_blank" rel="noopener noreferrer" title="Klik untuk lihat saiz penuh">
            <img src={imgUrl(chart)} alt="Carta Organisasi" style={{ maxWidth: "100%", maxHeight: 420, borderRadius: 10, objectFit: "contain", border: "1px solid var(--line)" }} />
          </a>
          <p className="small muted" style={{ margin: ".4rem 0 0" }}>Tekan gambar untuk lihat saiz penuh.</p>
          {isAdmin && (
            <div style={{ marginTop: ".6rem" }}>
              <button type="button" className="btn ghost danger small" onClick={onDeleteChart}>🗑️ Padam Carta</button>
            </div>
          )}
        </div>
      )}

      {isAdmin && !chart && (
        <div className="card" style={{ padding: ".8rem 1rem", marginBottom: "1rem", border: "1px dashed var(--accent)" }}>
          <b className="small">Carta Organisasi / Hierarki</b>
          <p className="small muted" style={{ margin: ".2rem 0 .5rem" }}>Muat naik gambar infografik carta jawatankuasa untuk dipaparkan kepada ahli.</p>
          <input type="file" accept="image/*" ref={fileRef} onChange={onUpload} style={{ display: "none" }} />
          <button type="button" className="btn small" disabled={uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? "Memuat naik…" : "📤 Muat naik Gambar Carta Organisasi"}
          </button>
        </div>
      )}

      {d.sessions.length === 0 && <p className="muted">Belum ada data jawatan. Admin boleh import melalui lembaran Jawatan.</p>}
      {d.mt.length > 0 && (
        <div className="fr-mt">
          <h3>Majlis Tertinggi (MT)</h3>
          {d.mt.map((x) => (
            <div className="row small mt-row" key={x.title}>
              <span className="mt-role">{x.title}</span>
              <b className="mt-name">{x.names.join(", ")}</b>
            </div>
          ))}
        </div>
      )}
      {d.biros.length > 0 && <h3 style={{ margin: "1rem 0 .3rem" }}>Biro</h3>}
      {d.biros.map((b) => (
        <div className="card fr-biro-card" key={b.name}>
          <b style={{ color: "var(--accent)" }}>{b.name}</b>
          {b.posts.map((x) => (
            <div className="row small mt-row" key={x.title}>
              <span className="muted mt-role">{x.title}</span>
              <span className="mt-name">{x.names.join(", ")}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
