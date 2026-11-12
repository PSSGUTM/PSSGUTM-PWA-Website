import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate } from "../api.js";

const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

export function ProfilSaya({ user }) {
  const [me, setMe] = useState(null);
  const [att, setAtt] = useState(null);
  useEffect(() => {
    api.get("/persatuan/me").then(setMe).catch(() => setMe({ person: null, posts: [] }));
    api.get("/persatuan/me/attendance").then(setAtt).catch(() => {});
  }, []);
  if (!me) return <p className="muted">Memuatkan…</p>;
  const p = me.person;
  const pct = att && att.total ? Math.round((100 * att.present) / att.total) : 0;
  return (
    <div>
      <div className="fr-profile">
        <span className="fr-av big">{initials(user.name)}</span>
        <div>
          <b>{user.name}</b>
          <small>No. ahli {p?.member_no || user.member_no}</small>
          <span>{p?.intake && <em>Sesi {p.intake}</em>}<em className="ok">{p?.active === false ? "Tidak aktif" : "Aktif"}</em>{p && <em>{p.kind === "SG" ? "Ahli" : "Alumni"}</em>}</span>
        </div>
        <Link to="/profil" className="btn ghost">Sunting</Link>
      </div>
      <div className="card">
        {p?.kind === "SG" && p.belt && <div className="row"><span className="muted">Bengkung</span><b>{p.belt}</b></div>}
        <div className="row"><span className="muted">Kolej</span><b>{p?.college || user.college || "–"}</b></div>
        {p?.study_level && <div className="row"><span className="muted">Peringkat pengajian</span><b>{p.study_level}</b></div>}
        <div className="row"><span className="muted">Telefon</span><b>{user.phone || p?.phone || "–"}</b></div>
        {p?.kind === "SG" && p.study_end && <div className="row"><span className="muted">Jangkaan tamat pengajian</span><b>{fmtDate(p.study_end)}</b></div>}
      </div>
      {!p && <div className="note small">Emel anda belum ada dalam senarai ahli/alumni. Hubungi pentadbir supaya bengkung, jawatan dan kehadiran dipaparkan.</div>}
      {me.posts?.length > 0 && (
        <div className="card"><h3>Sejarah jawatan</h3>
          {me.posts.map((j) => (
            <div className="row small" key={j.id}>
              <span><em className="chip">{j.session}</em> {j.title}{j.seki || j.biro ? `, ${j.seki || j.biro}` : ""}</span>
              {j.current && <span className="badge ok">semasa</span>}
            </div>
          ))}
        </div>
      )}
      {att && att.linked && (
        <Link to="/kehadiran" className="card fr-att">
          <div className="row"><b>Kehadiran sesi ini</b><span>{att.present} daripada {att.total}</span></div>
          <div className="fr-bar"><i style={{ width: `${pct}%` }} /></div>
        </Link>
      )}
    </div>
  );
}

export function KehadiranSaya() {
  const [att, setAtt] = useState(null);
  useEffect(() => { api.get("/persatuan/me/attendance").then(setAtt).catch(() => setAtt({ items: [], total: 0, present: 0, linked: false })); }, []);
  if (!att) return <p className="muted">Memuatkan…</p>;
  if (!att.linked) return <div className="note small">Emel anda belum ada dalam senarai ahli/alumni, jadi kehadiran belum direkodkan. Hubungi pentadbir.</div>;
  const pct = att.total ? Math.round((100 * att.present) / att.total) : 0;
  return (
    <div>
      <div className="card">
        <div className="row"><b>Sesi {att.label}</b><span>{att.present} daripada {att.total}</span></div>
        <div className="fr-bar"><i style={{ width: `${pct}%` }} /></div>
        <Link className="btn wide" to="/kod-qr" style={{ marginTop: ".8rem" }}>Imbas kod kehadiran</Link>
      </div>
      {att.items.length === 0 && <p className="muted">Belum ada kehadiran sesi ini.</p>}
      {att.items.map((a) => (
        <div className="card row" key={a.id}>
          <span><b>{a.title}</b><br /><small className="muted">{fmtDate(a.date)}</small></span>
          <span className={`badge ${a.present ? "ok" : "bad"}`}>{a.present ? "Hadir" : "Tidak hadir"}</span>
        </div>
      ))}
    </div>
  );
}
