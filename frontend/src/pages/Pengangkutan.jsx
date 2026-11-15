import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate } from "../api.js";

// Pembungkus muka depan untuk Transport. Halaman Transport sedia ada tidak diubah.
export default function Pengangkutan({ user }) {
  const [days, setDays] = useState(null);
  useEffect(() => { api.get("/bookings").then(setDays).catch(() => setDays([])); }, []);
  const next = (days || []).find((d) => !d.past);
  const st = !next ? null : next.event_status === "finalised" ? "Senarai disahkan" : "Senarai belum disahkan";
  const mine = next ? next.trips.filter((t) => t.status === "confirmed").length : 0;
  const incomplete = user && (!user.phone || user.phone === "0000000000" || !user.college_id || !user.block);

  return (
    <div>
      {incomplete && (
        <div className="note" style={{ background: "rgba(212, 169, 78, 0.15)", border: "1px solid var(--accent)", borderRadius: 12, padding: ".8rem 1rem", marginBottom: "1rem" }}>
          <b style={{ color: "var(--accent)" }}>⚠️ Profil Belum Lengkap</b>
          <p className="small muted" style={{ margin: ".3rem 0 .5rem" }}>Sila lengkapkan nombor telefon, kolej kediaman dan nombor bilik anda sebelum menempah atau menjadi prebet.</p>
          <Link to="/profil" className="btn small" style={{ display: "inline-block" }}>Lengkapkan Profil</Link>
        </div>
      )}
      <div className="card">
        <small className="muted">Latihan seterusnya</small>
        {days === null ? <p className="muted">Memuatkan…</p> : next ? (
          <>
            <h3 style={{ margin: ".2rem 0" }}>{fmtDate(next.training_date)}</h3>
            <p className="small">{next.start_time} – {next.end_time}{next.venue ? ` · ${next.venue}` : ""}</p>
            <p><span className="badge">{st}</span> <span className={`badge ${mine ? "ok" : ""}`}>{mine ? "Anda dalam senarai" : "Anda belum dalam senarai"}</span></p>
          </>
        ) : <p className="muted">Tiada latihan akan datang yang anda daftar. Buka Transport untuk memilih tarikh.</p>}
      </div>
      <Link to="/transport" className="btn wide">Buka Transport</Link>
      <div className="card fr-links">
        <Link to="/bayaran"><span>Bayaran saya</span><i>›</i></Link>
        {user.role !== "driver" && <Link to="/driver"><span>Jadi prebet</span><i>›</i></Link>}
        <Link to="/rules"><span>Panduan transport</span><i>›</i></Link>
      </div>
    </div>
  );
}
