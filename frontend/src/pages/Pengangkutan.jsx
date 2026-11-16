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

  const isIncomplete = (u) => {
    if (!u || u.role === "admin") return false;
    const noPhone = !u.phone || u.phone.trim() === "" || u.phone === "0000000000";
    const noCollege = !u.college_id && !u.college_other;
    if (u.role === "driver") {
      return noPhone || noCollege;
    }
    const noBlock = u.college_id && (!u.block || u.block.trim() === "");
    return noPhone || noCollege || noBlock;
  };
  const incomplete = isIncomplete(user);
  const incompleteMsg = (u) => {
    if (!u) return "";
    const noPhone = !u.phone || u.phone.trim() === "" || u.phone === "0000000000";
    const noCollege = !u.college_id && !u.college_other;
    const isDriver = u.role === "driver";
    const noBlock = !isDriver && u.college_id && (!u.block || u.block.trim() === "");
    const parts = [];
    if (noPhone) parts.push("nombor telefon");
    if (noCollege) parts.push("kolej kediaman");
    if (noBlock) parts.push("nombor bilik");
    return `Sila lengkapkan ${parts.join(", ")} anda sebelum menempah atau menjadi prebet.`;
  };

  return (
    <div>
      {incomplete && (
        <div className="note" style={{ background: "rgba(212, 169, 78, 0.15)", border: "1px solid var(--accent)", borderRadius: 12, padding: ".8rem 1rem", marginBottom: "1rem" }}>
          <b style={{ color: "var(--accent)" }}>⚠️ Profil Belum Lengkap</b>
          <p className="small muted" style={{ margin: ".3rem 0 .5rem" }}>{incompleteMsg(user)}</p>
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
