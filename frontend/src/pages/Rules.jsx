import { useEffect, useState } from "react";
import { api, fmtDate } from "../api.js";

const G = { male: "Lelaki", female: "Perempuan", any: "Semua" };

export default function Rules() {
  const [r, setR] = useState(null);
  const [cols, setCols] = useState([]);
  useEffect(() => { api.publicGet("/rules").then(setR); api.publicGet("/colleges").then(setCols); }, []);
  if (!r) return <p className="muted">Memuatkan...</p>;
  return (
    <>
      <h2>Syarat kemudahan</h2>
      {r.custom_rules ? (
        <section className="card small">
          <ul>{r.custom_rules.split("\n").map((l) => l.trim()).filter(Boolean).map((l, i) => <li key={i}>{l}</li>)}</ul>
        </section>
      ) : (
      <section className="card small">
        <ul>{(r.default_rules || []).map((l, i) => <li key={i}>{l}</li>)}</ul>
      </section>
      )}
      <section className="card small">
        <h3>Masa</h3>
        {r.sessions.map((s) => <div key={s.name}>{s.name}: latihan {s.start} · pickup {s.pickup} (bersedia 5 minit awal) · balik dari {s.return}</div>)}
        {(r.activities || []).map((a) => <div key={a.name + a.date}>📌 {a.name} · {fmtDate(a.date)} · {a.fee > 0 ? `RM${a.fee.toFixed(2)} seorang` : "percuma"} (terbuka untuk semua ahli)</div>)}
      </section>
      <section className="card small">
        <h3>Tempat berkumpul</h3>
        {r.checkpoints.map((c, i) => <div key={i}>{c.college} ({G[c.gender]}): {c.name}</div>)}
        <p className="muted">Kolej tanpa checkpoint: {cols.filter((c) => !c.transport_available).map((c) => c.code).join(", ") || "-"}</p>
      </section>
      <section className="card small">
        <h3>Kolej terkecuali ikut tempat latihan</h3>
        {r.venues.map((v) => <div key={v.name}>{v.name}: {v.excluded.join(" & ") || "-"}</div>)}
      </section>
    </>
  );
}
