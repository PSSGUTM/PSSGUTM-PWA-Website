import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, fmtTime } from "../api.js";
import Notifications from "../components/Notifications.jsx";
import { useToast } from "../components/Toast.jsx";

const EVENT = { open: ["Senarai belum disahkan", "warn"], finalised: ["Senarai disahkan", "ok"], cancelled: ["Dibatalkan", "bad"] };

function Deadline({ o }) {
  if (o.available !== null) return null;
  const dl = new Date(o.deadline);
  const txt = dl.toLocaleString("ms-MY", { weekday: "short", day: "2-digit", month: "2-digit", hour: "numeric", minute: "2-digit" });
  return <p className={`small ${o.deadline_passed ? "error" : "muted"}`}>
    {o.deadline_passed ? "Waktu sahkan sudah tutup (5 petang hari latihan). Hubungi BKK." : `Sahkan sebelum ${txt}.`}
  </p>;
}

function DateCard({ o, onSet, onTick, busy, contact }) {
  const confirmed = o.available === true, declined = o.available === false;
  const multi = (o.vehicles || []).length > 1;
  const locked = o.deadline_passed;
  return (
    <section className="card">
      <div className="row">
        <h3>{fmtDate(o.training_date)}{o.past ? " · sudah lepas" : ""}</h3>
        <span className={`badge ${EVENT[o.event_status]?.[1] || "muted"}`}>{EVENT[o.event_status]?.[0] || o.event_status}</span>
      </div>
      <p className="muted small">
        {o.is_activity ? "📌 Aktiviti luar · " : ""}{o.session_name} · mula {fmtTime(o.start_time)} · pickup {o.pickup_window}
        {o.venue ? ` · 🏟️ ${o.venue}` : o.is_activity ? "" : " · tempat latihan belum ditetapkan"}
      </p>
      <div className="row">
        <b>Boleh bawa penumpang?</b>
        <div className="seg">
          <button disabled={busy || locked} className={confirmed ? "on" : ""} onClick={() => onSet(o, true)}>Boleh</button>
          <button disabled={busy || locked} className={declined ? "on bad" : ""} onClick={() => onSet(o, false)}>Tak boleh</button>
        </div>
      </div>
      {multi && (
        <label className="small" style={{ display: "block", marginTop: 6 }}>Kenderaan hari ini
          <select disabled={busy || locked} value={o.vehicle_id || ""} onChange={(e) => onSet(o, o.available !== false, Number(e.target.value))}>
            {o.vehicles.map((v) => <option key={v.id} value={v.id}>{v.desc}</option>)}
          </select>
        </label>
      )}
      <p className="small muted">Tak dapat bawa? Hubungi BKK{contact ? `: ${contact}` : ""}.</p>
      {o.by_admin && o.available !== null && <p className="small muted">Disahkan oleh BKK bagi pihak anda.</p>}
      <Deadline o={o} />
      {o.passengers > 0 && (
        <div className="note" style={{ cursor: "default" }}>
          <b>🚗 Tugasan anda: {o.passengers} penumpang</b>
          <div className="chiprow">
            {o.stops.map((st) => <span className="chip" key={st.college + st.checkpoint}>📍 {st.college} · {st.checkpoint} ({st.count})</span>)}
          </div>
          <div className="small">{o.task}{o.venue ? `Kemudian ke ${o.venue}.` : ""}</div>
          {o.event_status !== "finalised" && <div className="small muted">Senarai penumpang (nama, telefon, blok) dipaparkan di sini selepas BKK sahkan senarai.</div>}
          {o.pickups && o.pickups.length > 0 && (
            <ul className="pickups">
              {o.pickups.map((x, i) => (
                <li key={i}>
                  <b>{x.name}</b> · {x.college} · 📍 {x.places && x.places.going && x.places.returning && x.places.going !== x.places.returning ? `Pergi: ${x.places.going} · Balik: ${x.places.returning}` : x.checkpoint}{x.block ? ` · blok ${x.block}` : ""}
                  <br /><a href={`tel:${x.phone}`}>{x.phone}</a>{x.directions.length === 1 ? ` · ${x.directions[0] === "going" ? "pergi sahaja" : "balik sahaja"}` : ""}
                </li>
              ))}
            </ul>
          )}
          {o.ticks && (
            <div className="actions" style={{ marginTop: 8 }}>
              <button className={`btn ${o.ticks.arrived ? "" : "ghost"}`} disabled={busy} onClick={() => onTick(o, "arrived", !o.ticks.arrived)}>
                {o.ticks.arrived ? "✅ Dah sampai tempat latihan" : "☐ Dah sampai tempat latihan"}</button>
              <button className={`btn ${o.ticks.delivered ? "" : "ghost"}`} disabled={busy} onClick={() => onTick(o, "delivered", !o.ticks.delivered)}>
                {o.ticks.delivered ? "✅ Dah hantar semua" : "☐ Dah hantar semua (selepas latihan)"}</button>
            </div>
          )}
        </div>
      )}
      {o.passengers === 0 && o.task && <p className="small muted">{o.task}</p>}
    </section>
  );
}

export default function Prebet({ user }) {
  const toast = useToast();
  const [dates, setDates] = useState(null);
  const [notes, setNotes] = useState(null);
  const [docs, setDocs] = useState(null);
  const [veh, setVeh] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = () => Promise.all([api.get("/driver/dates"), api.get("/notifications"), api.get("/driver/docs"), api.get("/driver/vehicles")])
    .then(([d, n, c, v]) => { setDates(d); setNotes(n); setDocs(c); setVeh(v); })
    .catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const [contact, setContact] = useState("");
  useEffect(() => {
    api.get("/contacts").then((c) => setContact((c.duty.length ? c.duty : [c.fallback]).map((x) => `${x.name} ${x.phone}`).join(" / "))).catch(() => {});
  }, []);

  async function setTick(o, kind, on) {
    setBusy(true);
    try { setDates(await api.put("/driver/tick", { training_date: o.training_date, kind, on })); } catch (e) { toast(e.message, "bad"); } finally { setBusy(false); }
  }

  async function setAvail(o, available, vehicle_id) {
    setBusy(true);
    try {
      setDates(await api.put("/driver/availability", { training_date: o.training_date, available, vehicle_id: vehicle_id || o.vehicle_id || null }));
      toast(available ? `${fmtDate(o.training_date)}: boleh bawa ✅` : `${fmtDate(o.training_date)}: tak boleh`);
    } catch (e) { toast(e.message, "bad"); } finally { setBusy(false); }
  }

  const approved = veh?.vehicles.some((v) => v.approval === "approved" && v.active);
  const coming = dates ? dates.filter((d) => !d.past) : null;
  const next = coming && (coming.find((d) => d.passengers > 0) || coming.find((d) => d.available === true));
  const left = next ? Math.round((new Date(next.training_date + "T00:00:00") - new Date(new Date().toDateString())) / 864e5) : null;
  const todo = coming ? coming.filter((d) => d.available === null).length : 0;

  return (
    <>
      <div className="hero-card">
        <p className="eyebrow">Assalamualaikum, {user.short_name || user.name.split(" ")[0]} · Prebet</p>
        {next ? (
          <>
            <div className="big">{next.passengers > 0 ? "Tugasan" : "Sedia"} <span>{fmtDate(next.training_date)}</span></div>
            <div className="sub">{next.passengers > 0 ? `${next.passengers} penumpang · ${next.stops.map((s) => s.college).join(", ")}` : "Anda sudah sahkan boleh bawa."}</div>
            <span className="count">{left <= 0 ? "Hari ini" : left === 1 ? "Esok" : `${left} hari lagi`}</span>
          </>
        ) : (
          <>
            <div className="big">{todo ? <>Sahkan <span>{todo}</span> tarikh</> : <>Tiada <span>tugasan</span></>}</div>
            <div className="sub">{todo ? "Beritahu BKK tarikh yang anda boleh bawa penumpang." : "Anda akan dimaklumkan bila ada tugasan."}</div>
          </>
        )}
      </div>

      {docs && !docs.has_licence && <div className="note warnbox"><b>⚠️ Gambar lesen belum dimuat naik.</b> <Link to="/profil">Lengkapkan di Profil →</Link></div>}
      {veh && !approved && <div className="note warnbox"><b>🚗 Belum ada kenderaan yang diluluskan.</b> {veh.vehicles.length ? "Menunggu kelulusan BKK." : <Link to="/driver">Daftar kenderaan →</Link>}</div>}

      <Notifications warningsOnly notes={notes} setNotes={setNotes} />
      {err && <p className="error">{err}</p>}
      {!dates && !err && <><div className="skel" /><div className="skel" /></>}
      {dates && dates.length === 0 && <p className="muted">Tiada latihan akan datang. Tarikh cuti tidak dipaparkan.</p>}
      {dates && dates.map((o) => <DateCard key={o.training_date + o.session_name} o={o} onSet={setAvail} onTick={setTick} busy={busy || !approved} contact={contact} />)}
      {dates && dates.length > 0 && !approved && <p className="small muted">Butang sahkan aktif selepas kenderaan anda diluluskan.</p>}
    </>
  );
}

export function Pendapatan() {
  const toast = useToast();
  const [rows, setRows] = useState(null);
  const [inc, setInc] = useState(null);
  const [err, setErr] = useState("");
  const load = () => Promise.all([api.get("/driver/payouts"), api.get("/driver/income")])
    .then(([r, i]) => { setRows(r); setInc(i); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const view = async (r) => {
    try { window.open(await api.blobUrl(`/driver/payouts/${r.id}/receipt`), "_blank"); } catch (e) { toast(e.message, "bad"); }
  };
  const got = async (r) => {
    try { await api.post(`/driver/payouts/${r.id}/received`); toast("Terima kasih, ditandakan diterima ✅"); load(); } catch (e) { toast(e.message, "bad"); }
  };
  return (
    <>
      <h2>Pendapatan</h2>
      <p className="muted small">Bayaran tetap setiap hari latihan yang anda beroperasi. Bendahari membayar anda {inc ? `(${inc.mode_label.toLowerCase()})` : ""} dan memuat naik satu resit. Isi akaun bank / QR anda di tab Driver.</p>
      {!rows && !err && <div className="skel" />}
      {err && <p className="error">{err}</p>}
      {inc && inc.pending.length > 0 && (
        <section className="card">
          <div className="row"><h3>Belum dibayar: RM{inc.pending_total.toFixed(2)}</h3><span className="badge warn">Menunggu bendahari</span></div>
          <p className="small">{inc.note}</p>
          {inc.pending.map((p) => (
            <div key={p.training_date + p.vehicle} className="small muted">{fmtDate(p.training_date)} · {p.vehicle} · RM{p.amount.toFixed(2)}
              {p.overdue ? " · lewat tarikh akhir" : ""}</div>
          ))}
        </section>
      )}
      {rows && rows.length === 0 && (!inc || inc.pending.length === 0) && <p className="muted">Belum ada bayaran.</p>}
      {(rows || []).map((r) => (
        <section className="card" key={r.id}>
          <div className="row"><h3>RM{r.amount.toFixed(2)}</h3>
            <span className={`badge ${r.received ? "ok" : "warn"}`}>{r.received ? "Diterima ✅" : "Menunggu pengesahan anda"}</span></div>
          <p className="muted small">{r.note}</p>
          <div className="actions">
            {r.has_receipt && <button className="btn ghost" onClick={() => view(r)}>🧾 Lihat resit</button>}
            {!r.received && <button className="btn" onClick={() => got(r)}>✔ Diterima</button>}
          </div>
        </section>
      ))}
    </>
  );
}
