import { useEffect, useState } from "react";
import { api } from "../api.js";

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
  useEffect(() => { api.get(`/persatuan/structure?session=${ses}`).then(setD).catch(() => setD({ sessions: [], mt: [], biros: [] })); }, [ses]);
  if (!d) return <p className="muted">Memuatkan…</p>;
  return (
    <div>
      <div className="fr-chips">
        {d.sessions.map((s) => <button key={s} className={d.session === s ? "on" : ""} onClick={() => setSes(s)}>{s}</button>)}
      </div>
      {d.sessions.length === 0 && <p className="muted">Belum ada data jawatan. Admin boleh import melalui lembaran Jawatan.</p>}
      {d.mt.length > 0 && (
        <div className="fr-mt">
          <h3>Majlis Tertinggi (MT)</h3>
          {d.mt.map((x) => <div className="row small" key={x.title}><span>{x.title}</span><b>{x.names.join(", ")}</b></div>)}
        </div>
      )}
      {d.biros.length > 0 && <h3 style={{ margin: "1rem 0 .3rem" }}>Biro</h3>}
      {d.biros.map((b) => (
        <div className="card" key={b.name}>
          <b>{b.name}</b>
          {b.posts.map((x) => <div className="row small" key={x.title}><span className="muted">{x.title}</span><span>{x.names.join(", ")}</span></div>)}
        </div>
      ))}
    </div>
  );
}
