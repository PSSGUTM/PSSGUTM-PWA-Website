import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate } from "../api.js";
import { imgUrl } from "../formapi.js";

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
        {user.avatar ? (
          <img src={imgUrl(user.avatar)} className="fr-av big" alt={user.name} style={{ objectFit: "cover" }} />
        ) : (
          <span className="fr-av big">{initials(user.name)}</span>
        )}
        <div>
          <b>{user.name}</b>
          <small>No. ahli {p?.member_no || user.member_no}</small>
          <span>{p?.intake && <em>Sesi {p.intake}</em>}<em className="ok">{p?.active === false ? "Tidak aktif" : "Aktif"}</em>{p && <em>{p.kind === "SG" ? "Ahli" : "Alumni"}</em>}</span>
        </div>
        <Link to="/profil" className="btn ghost">Sunting</Link>
      </div>

      {/* Kad Pertanyaan & Pengesahan Nombor Ahli */}
      <div className="card" style={{
        background: "linear-gradient(135deg, rgba(107, 31, 31, 0.35), rgba(44, 24, 16, 0.6))",
        border: "1.5px solid var(--accent, #D4A94E)",
        borderRadius: 14,
        padding: "1rem 1.1rem",
        margin: "0.8rem 0 1rem"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
          <span style={{ fontSize: "1.25rem" }}>⚠️</span>
          <b style={{ color: "var(--accent, #D4A94E)", fontSize: "1.02rem" }}>
            Pengesahan Nombor Ahli: {p?.member_no || user.member_no}
          </b>
        </div>
        <p className="small" style={{ lineHeight: 1.6, margin: "0.3rem 0 0.8rem", color: "var(--text, #FDF8F0)" }}>
          Adakah nombor ahli <b>{p?.member_no || user.member_no}</b> ini milik asal anda?
          <br /><br />
          Jika nombor ini <b>bukan milik asal anda</b> (contohnya susunan nombor telah berubah):
          <br />
          Nombor ahli anda akan <b>dipindahkan ke nombor yang betul</b> mengikut senarai rasmi, dan <b>SEMUA maklumat anda</b> (sejarah jawatan biro/MT, rekod kehadiran latihan, bengkung, serta perkhidmatan pengangkutan) akan <b>dipindahkan secara automatik ke nombor baharu</b> tersebut tanpa sebarang rekod yang hilang.
        </p>
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
          <a
            href="https://docs.google.com/spreadsheets/d/1RkEQYsnG3n7-_fg98flrrQajSXWy2uYKXW2uVkC8xYE/edit?usp=sharing"
            target="_blank"
            rel="noopener noreferrer"
            className="btn small"
            style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.3rem", padding: ".45rem .85rem" }}
          >
            📋 Semak Senarai Rasmi Ahli
          </a>
          <a
            href={`https://wa.me/?text=${encodeURIComponent("Salam BKK PSSGUTM, saya (" + user.name + ", emel: " + (user.email || "") + ") ingin membuat pengesahan nombor ahli saya.")}`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn ghost small"
            style={{ textDecoration: "none", padding: ".45rem .85rem" }}
          >
            💬 Hubungi BKK
          </a>
        </div>
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
