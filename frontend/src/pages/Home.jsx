import { useEffect, useRef, useState } from "react";
import { api, fmtDate, fmtTime } from "../api.js";
import DatePicker from "../components/DatePicker.jsx";
import Contact from "../components/Contact.jsx";
import Notifications from "../components/Notifications.jsx";
import { Link } from "react-router-dom";
import { useBrand } from "../components/BrandContext.jsx";

const STATUS = {
  confirmed: ["✅ Dalam senarai", "ok"], skipped: ["⏭️ Tak naik", "muted"],
  cancelled: ["❌ Dibatalkan", "bad"], ineligible: ["🚫 Terkecuali", "warn"],
};
const PAY = {
  unpaid: ["Belum bayar", "warn"], pending: ["Menunggu pengesahan", "warn"], paid: ["Dah bayar ✅", "ok"],
  rejected: ["Resit ditolak", "bad"], void: ["Tiada bayaran", "muted"],
};
const EVENT = { open: ["Menunggu pengesahan senarai", "warn"], finalised: ["Senarai disahkan", "ok"], cancelled: ["Dibatalkan", "bad"] };
const DIR = { going: "Pergi", returning: "Balik" };

function Badge({ map, k }) {
  const [text, cls] = map[k] || [k, "muted"];
  return <span className={`badge ${cls}`}>{text}</span>;
}

function PayBox({ info, day, busy, onFile }) {
  const fileRef = useRef();
  const [qr, setQr] = useState(null);
  useEffect(() => { if (info?.has_qr) api.blobUrl("/payment-info/qr").then(setQr).catch(() => {}); }, [info?.has_qr]);
  return (
    <div className="note" style={{ cursor: "default" }}>
      <div className="paynow">Perlu bayar <b>RM{day.payment.due.toFixed(2)}</b></div>
      Melalui pindahan bank / QR (tiada bayaran tunai, tiada pemulangan).
      {day.pay_deadline && <div className="small"><b>Bayar sebelum {new Date(day.pay_deadline).toLocaleString("ms-MY", { weekday: "long", day: "2-digit", month: "2-digit", hour: "numeric", minute: "2-digit" })}</b>; lewat dari itu menjadi tunggakan.</div>}
      {info && (info.pay_bank || info.pay_account_no) && (
        <div className="small">🏦 {info.pay_bank} · <b>{info.pay_account_no}</b><br />{info.pay_account_name}</div>
      )}
      {info?.pay_notes && <div className="small">{info.pay_notes}</div>}
      {qr && <div className="imgframe"><img src={qr} alt="QR bayaran" /></div>}
      <button className="btn wide" disabled={busy} onClick={() => fileRef.current.click()}>📤 Upload resit</button>
      <input ref={fileRef} type="file" accept="image/*,application/pdf" hidden onChange={onFile} />
    </div>
  );
}

function Day({ day, reload, info }) {
  const brand = useBrand();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const open = day.event_status === "open";
  const hasConfirmed = day.trips.some((t) => t.status === "confirmed");
  const allSkipped = day.trips.every((t) => t.status === "skipped");
  const allIneligible = day.trips.every((t) => t.status === "ineligible");

  async function run(fn) {
    setBusy(true); setErr("");
    try { await fn(); await reload(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  const skip = (s) => run(() => api.post("/bookings/skip", { training_date: day.training_date, skip: s }));
  const upload = (e) => {
    const file = e.target.files[0];
    if (file) run(() => api.upload(`/payments/${day.payment.id}/receipt`, file));
    e.target.value = "";
  };
  const pay = day.payment;

  return (
    <section className="card">
      <div className="row">
        <h3>{fmtDate(day.training_date)}</h3>
        <Badge map={EVENT} k={day.event_status} />
      </div>
      {day.is_activity
        ? <p className="muted">📌 Aktiviti luar jadual</p>
        : <p className="muted">Latihan {fmtTime(day.start_time)} – {fmtTime(day.end_time)}{day.venue ? ` · ${day.venue}` : " · tempat akan dimaklumkan"}</p>}

      {hasConfirmed && (
        <div className="stepper">
          {[["Dalam senarai", true], ["Senarai disahkan", day.event_status === "finalised"], ["Kenderaan", !!day.car || day.trips.some((t) => t.ehailing)], ["Bayar", day.payment?.status === "paid" || day.payment?.status === "void"]]
            .map(([l, ok], i, a) => <div key={l} className={`st ${ok ? "done" : a.slice(0, i).every((x) => x[1]) ? "now" : ""}`}><i>{ok ? "✓" : i + 1}</i>{l}</div>)}
        </div>
      )}
      {!day.is_activity && allIneligible && <p className="error small">Kolej anda tidak dapat kemudahan pengangkutan untuk latihan di {day.venue}.</p>}
      {day.event_status === "cancelled" && <p className="small muted">Latihan dibatalkan. Bayaran yang dah dibuat dibawa ke latihan seterusnya.</p>}

      {day.trips.map((t) => (
        <div className="row" key={t.id}>
          <div>
            <b>{DIR[t.direction]}</b>
            {t.status === "confirmed" && (
              <div className="muted small">
                📍 {t.checkpoint || "-"}{t.block ? ` · blok ${t.block}` : ""}<br />
                {t.ehailing && <><b>🚕 E-hailing (diuruskan BKK)</b>{t.ehailing_note ? ` · ${t.ehailing_note}` : ""}<br /></>}
                🕘 {t.direction === "going" ? `Sampai di checkpoint ${day.arrive_by} (prebet ambil ${day.pickup_window})` : `Bermula ${day.return_time}, kereta yang sama`}
              </div>
            )}
          </div>
          <Badge map={STATUS} k={t.status} />
        </div>
      ))}

      {day.car ? (
        <div className="note" style={{ cursor: "default" }}>
          {day.car.vehicle_type === "motorcycle" ? "🏍️" : "🚗"} Naik: <b>{day.car.driver_name || day.car.name} ({day.car.desc})</b>
          {day.car.driver_name && <div className="small">Prebet: {day.car.driver_name} · <a href={`tel:${day.car.driver_phone}`}>{day.car.driver_phone}</a></div>}
        </div>
      ) : (hasConfirmed && day.event_status === "finalised" && !day.trips.some((t) => t.ehailing) &&
        <p className="small error">Belum ada prebet untuk anda. BKK akan maklumkan jika ada tempat kosong atau uruskan e-hailing.</p>)}
      {!day.car && day.trips.some((t) => t.ehailing) &&
        <div className="note" style={{ cursor: "default" }}>🚕 <b>E-hailing diuruskan BKK</b><div className="small">Tiada prebet untuk trip ini. Sila pantau group WhatsApp BKK untuk butiran e-hailing. {brand?.wa_group_link && <a href={brand.wa_group_link} target="_blank" rel="noreferrer">Buka group WhatsApp →</a>}</div></div>}
      {hasConfirmed && open && <p className="small muted">Kenderaan, driver dan jumlah yuran muktamad dimaklumkan selepas senarai disahkan.</p>}

      {pay && pay.status !== "void" && (
        <div className="row">
          <div><b>Yuran</b> <span className="muted">RM{pay.amount.toFixed(2)}{open ? " (anggaran)" : ""}{pay.credit_applied > 0 ? ` (kredit −RM${pay.credit_applied.toFixed(2)})` : ""}</span></div>
          <Badge map={PAY} k={pay.status} />
        </div>
      )}
      {pay?.can_pay && <PayBox info={info} day={day} busy={busy} onFile={upload} />}
      {pay && pay.status === "unpaid" && !pay.can_pay && hasConfirmed && open &&
        <p className="small muted">Bayaran dibuka selepas BKK sahkan senarai (atau disahkan automatik sebelum latihan). Jangan bayar dahulu; maklumat akaun dipaparkan bila dibuka.</p>}

      {err && <p className="error">{err}</p>}
      <div className="actions">
        {hasConfirmed && open && !day.closed && <button className="btn ghost" disabled={busy} onClick={() => skip(true)}>❌ Tak naik</button>}
        {!hasConfirmed && allSkipped && open && !day.closed && <button className="btn" disabled={busy} onClick={() => skip(false)}>↩️ Nak naik semula</button>}
      </div>
      {day.closed && hasConfirmed && <p className="small muted">Pilihan ditutup pada {day.cutoff} hari latihan. Hubungi BKK jika ada perubahan.</p>}
    </section>
  );
}

function FeedbackBox() {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ kind: "cadangan", message: "" });
  const [m, setM] = useState("");
  async function send(e) {
    e.preventDefault(); setM("");
    try { await api.post("/feedback", f); setF({ kind: "cadangan", message: "" }); setM("Terima kasih! Cadangan anda dah dihantar kepada BKK ✅"); }
    catch (e2) { setM(e2.message); }
  }
  if (!open) return <button className="btn ghost wide" onClick={() => setOpen(true)}>💬 Cadangan / masalah website</button>;
  return (
    <form className="card" onSubmit={send}>
      <h3>💬 Cadangan & maklum balas</h3>
      <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
        <option value="cadangan">Cadangan penambahbaikan</option>
        <option value="masalah">Lapor masalah / bug</option>
        <option value="lain">Lain-lain</option>
      </select>
      <textarea rows={4} maxLength={1000} minLength={5} required placeholder="Tulis cadangan atau masalah anda..." value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} />
      {m && <p className="small">{m}</p>}
      <Contact />
      <button className="btn wide">Hantar</button>
    </form>
  );
}

export default function Home({ user }) {
  const [days, setDays] = useState(null);
  const [notes, setNotes] = useState(null);
  const [info, setInfo] = useState(null);
  const [profile, setProfile] = useState(null);
  const [arrears, setArrears] = useState(null);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const [d, n, i, p, a] = await Promise.all([api.get("/bookings"), api.get("/notifications"),
        api.get("/payment-info"), api.get("/profile"), api.get("/payments/summary")]);
      setDays(d); setNotes(n); setInfo(i); setProfile(p); setArrears(a);
    } catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, []);

  const next = days && days.find((d) => !d.past && d.trips.some((t) => t.status === "confirmed"));
  const daysLeft = next ? Math.round((new Date(next.training_date + "T00:00:00") - new Date(new Date().toDateString())) / 864e5) : null;

  return (
    <>
      <div className="hero-card">
        <p className="eyebrow">Assalamualaikum, {user.short_name || user.name.split(" ")[0]}</p>
        {next ? (
          <>
            <div className="big">Latihan <span>{fmtDate(next.training_date)}</span></div>
            <div className="sub">{next.trips.filter((t) => t.status === "confirmed").map((t) => DIR[t.direction]).join(" & ")}{next.car ? ` · ${next.car.name}` : ""}</div>
            <span className="count">{daysLeft <= 0 ? "Hari ini" : daysLeft === 1 ? "Esok" : `${daysLeft} hari lagi`}</span>
          </>
        ) : (
          <>
            <div className="big">Belum ada <span>trip</span></div>
            <div className="sub">Pilih tarikh latihan di bawah untuk naik prebet.</div>
          </>
        )}
      </div>
      {profile?.credit_balance > 0 && <p className="okmsg small">💳 Kredit anda: RM{profile.credit_balance.toFixed(2)} (digunakan automatik)</p>}
      {arrears && arrears.total > 0 && (
        <Link to="/bayaran" className="note warnbox" style={{ display: "block", textDecoration: "none", color: "inherit" }}>
          💳 <b>Tunggakan RM{arrears.total.toFixed(2)}</b> ({arrears.count} bayaran). Tekan untuk bayar →
        </Link>
      )}
      <Notifications warningsOnly notes={notes} setNotes={setNotes} />
      {err && <p className="error">{err}</p>}
      {!days && !err && <><div className="skel" /><div className="skel" /></>}
      <section className="card">
        <h3>📅 Pilih tarikh</h3>
        <p className="muted small">Tekan Pergi / Balik untuk tarikh yang anda nak naik. <b>Pilih atau batal sebelum 5 petang hari latihan</b>; selepas itu ditutup (hubungi BKK). Tiada yang dimasukkan automatik.</p>
        <DatePicker onChange={load} />
      </section>
      {days && days.map((d) => <Day key={d.training_date} day={d} reload={load} info={info} />)}
      <FeedbackBox />
    </>
  );
}
