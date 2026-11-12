import SeatMap from "../components/SeatMap.jsx";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, fmtDate } from "../api.js";
import { Arrears, EventMoney, DutyRoster, Flow, Holidays, PaxRequests, PayDrivers, PayoutReceipt, BackupBox, Profit, Rates, ResetBox } from "./AdminExtra.jsx";

const DIR = { going: "Pergi", returning: "Balik" };
const DAYS = { 0: "Isn", 1: "Sel", 2: "Rab", 3: "Kha", 4: "Jum", 5: "Sab", 6: "Aha" };
const EVENT = { open: ["Belum disahkan", "warn"], finalised: ["Disahkan", "ok"], cancelled: ["Dibatalkan", "bad"] };
const G = { male: "Lelaki", female: "Perempuan", any: "Semua" };
const money = (n) => `RM${Number(n).toFixed(2)}`;

function useLoad(path, deps = []) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const load = () => (path ? api.get(path).then(setData).catch((e) => setErr(e.message)) : Promise.resolve());
  useEffect(() => { setData(null); load(); }, deps);
  return [data, load, err];
}
const fail = (e) => alert(e.message);

/* ---------- Manifest kenderaan ---------- */
function Manifest({ date, onChange }) {
  const [m, load, err] = useLoad(`/admin/manifest?training_date=${date}`, [date]);
  const [vs] = useLoad("/admin/vehicles");
  if (!m) return <p className="muted small">{err || "Memuatkan..."}</p>;
  const assign = async (user_id, vehicle_id) => {
    try { await api.post("/admin/bookings/assign", { user_id, training_date: date, vehicle_id: vehicle_id ? Number(vehicle_id) : null }); load(); onChange?.(); }
    catch (e) { fail(e); }
  };
  const usable = (vs || []).filter((v) => v.approval === "approved" && v.active);
  return (
    <div>
      {m.cars.map((c) => (
        <div className="note" key={c.vehicle_id} style={{ cursor: "default" }}>
          <b>{c.vehicle_type === "motorcycle" ? "🏍️" : "🚗"} {c.name}</b> {c.plate_no} · {c.passengers.length}/{c.capacity} ({c.male}L {c.female}P)
          {c.driver && <span className="small"> · {c.driver.name} ({c.driver_college || "-"}{c.category ? `, kolej ${c.category}` : ""}) <a href={`tel:${c.driver.phone}`}>{c.driver.phone}</a></span>}
          <div className="small">{c.desc}</div>
          {c.passengers.map((p) => (
            <div className="small" key={p.user_id}>{p.full_name || p.name} <span className="muted">({p.short_name})</span> ({p.college}) · 📍 {p.checkpoint}{p.block ? ` · blok ${p.block}` : ""} · {p.directions.map((d) => DIR[d]).join("+")} · <a href={`tel:${p.phone}`}>{p.phone}</a></div>
          ))}
        </div>
      ))}
      {m.unassigned.length > 0 && (
        <div className="note mf-warn" style={{ cursor: "default" }}>
          <b>⚠️ Belum ada kenderaan ({m.unassigned.length})</b>
          {m.unassigned.map((p) => (
            <div className="row small" key={p.user_id}>
              <span>{p.name} ({p.college}, {p.gender === "male" ? "L" : "P"})</span>
              <select defaultValue="" onChange={(e) => e.target.value && assign(p.user_id, e.target.value)} style={{ width: "auto" }}>
                <option value="">Tetapkan kenderaan…</option>
                {usable.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Statistik keseluruhan ---------- */
function Stats() {
  const [s, , err] = useLoad("/admin/stats");
  if (!s) return err ? <p className="error">{err}</p> : null;
  const box = (n, label) => <div className="stat"><b>{n}</b><span>{label}</span></div>;
  return (
    <section className="card">
      <h3>📊 Gambaran keseluruhan</h3>
      <div className="stats">
        {box(s.roster_total, "Ahli sah")}{box(s.registered, "Dah daftar")}{box(s.roster_not_registered, "Belum daftar")}
        {box(s.active_riders, "Penumpang aktif")}{box(s.drivers, "Prebet")}
        {box(`${s.vehicles_approved}${s.vehicles_pending ? ` (+${s.vehicles_pending})` : ""}`, "Kenderaan")}
      </div>
      <p className="small muted">Lelaki {s.male} · Perempuan {s.female}</p>
      {s.by_college.length > 0 && (
        <>
          <p className="small muted" style={{ marginBottom: 4 }}>Ikut kolej (aktif / daftar):</p>
          <div className="chiprow">{s.by_college.map((c) => <span className="chip" key={c.college}>{c.college} {c.active_riders}/{c.registered}</span>)}</div>
        </>
      )}
      {s.other_colleges.length > 0 && <p className="small muted">Lain-lain: {s.other_colleges.map((o) => `${o.name} (${o.count})`).join(", ")}</p>}
    </section>
  );
}

/* ---------- Ringkasan ---------- */
function Summary() {
  const [events, load, err] = useLoad("/admin/dashboard");
  const [venues] = useLoad("/admin/venues");
  const [show, setShow] = useState({});
  if (!events) return <p className="muted">{err || "Memuatkan..."}</p>;

  const act = async (fn, confirmMsg) => {
    if (confirmMsg && !confirm(confirmMsg)) return;
    try { await fn(); await load(); } catch (e) { fail(e); }
  };
  return (
    <>
      <Stats />
      <button className="btn ghost" onClick={() => act(() => api.post("/admin/generate"))}>🔄 Jana booking & semak pengesahan auto</button>
      {events.length === 0 && <p className="muted">Tiada latihan dalam tempoh terdekat.</p>}
      {events.map((e) => (
        <section className="card" key={e.event_id}>
          <div className="row">
            <h3>{fmtDate(e.training_date)}{e.is_activity ? ` · 📌 ${e.session_name}` : ""}</h3>
            <span className={`badge ${EVENT[e.status][1]}`}>{EVENT[e.status][0]}</span>
          </div>
          {e.is_activity && <p className="small muted">Aktiviti luar jadual: tiada tempat latihan, tiada kolej terkecuali.</p>}
          {e.status !== "cancelled" && !e.is_activity && (
            <select value={e.venue?.id ?? ""} onChange={(ev) => act(() => api.put(`/admin/events/${e.event_id}/venue`, { venue_id: ev.target.value ? Number(ev.target.value) : null }))}>
              <option value="">Tempat latihan belum ditetapkan</option>
              {(venues || []).filter((v) => v.active).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          )}
          {e.venue && <p className="small muted">Terkecuali: {e.venue.excluded || "-"}{e.ineligible_members > 0 ? ` (${e.ineligible_members} ahli terkesan)` : ""}</p>}
          {e.warnings.map((w) => <p className="error small" key={w}>⚠️ {w}</p>)}
          {e.by_college && Object.keys(e.by_college).length > 0 && (
            <div className="chiprow">{Object.entries(e.by_college).map(([k, v]) => <span className="chip" key={k}>{k} {v}</span>)}</div>
          )}
          {[["Pergi", e.going], ["Balik", e.returning]].map(([label, t]) => (
            <div className="row" key={label}><b>{label}</b><span>👥 {t.passengers} · 🚗 {t.assigned} · 🚕 {t.ehailing} · ⚠️ {t.unassigned}</span></div>
          ))}
          {e.skipped && e.skipped.length > 0 && <p className="small muted">⏭️ Tak naik ({e.skipped.length}): {e.skipped.join(", ")}</p>}
          {e.status !== "cancelled" && <NeedTransport e={e} onChange={load} />}
          {e.status !== "cancelled" && <Flow e={e} onChange={load} />}
          <p className="muted small">👥 ahli · 🚗 dapat prebet · 🚕 e-hailing (BKK uruskan) · ⚠️ belum ada kenderaan. Kenderaan digunakan: {e.vehicles_used}/{e.vehicles_available}</p>
          <div className="row"><span>💰 Kutipan {money(e.payments.collected)} / {money(e.payments.expected)}</span>
            <span className="muted small">{e.payments.pending_verify} tunggu verify · {e.payments.unpaid} belum bayar</span></div>
          {e.status === "finalised" && (
            <div className="moneybox">
              <div><span className="small">Ahli perlu bayar (persatuan kutip)</span><b>RM{(e.payments.to_collect ?? 0).toFixed(2)}</b><span className="small muted">{e.payments.members} ahli · dah masuk RM{e.payments.collected.toFixed(2)}</span></div>
              <div><span className="small">Bendahari perlu bayar prebet</span><b>RM{(e.payout_due ?? 0).toFixed(2)}</b><span className="small muted">bayaran tetap ikut kenderaan</span></div>
            </div>
          )}
          {e.status === "open" && <p className="small muted">Sahkan senarai dahulu supaya ahli boleh bayar dan bendahari boleh bayar prebet. Jika anda tak sahkan, sistem sahkan automatik pada waktu yang ditetapkan{e.auto_off ? " (DIMATIKAN untuk latihan ini: anda mesti sahkan sendiri)" : ""}.</p>}
          <div className="actions">
            <button className="btn ghost" onClick={() => setShow({ ...show, [e.event_id]: !show[e.event_id] })}>{show[e.event_id] ? "Tutup" : "Lihat kenderaan"}</button>
            {e.status === "finalised" && <button className="btn ghost" onClick={() => act(() => api.post(`/admin/events/${e.event_id}/unfinalise`),
              "Batalkan pengesahan senarai? Ahli dimaklumkan jangan bayar dahulu, bayaran ditutup semula dan auto-sah dimatikan untuk latihan ini. Anda sahkan semula bila siap.")}>↩️ Batalkan pengesahan</button>}
            {e.status !== "cancelled" && <button className="btn ghost" onClick={() => act(() => api.post(`/admin/events/${e.event_id}/reassign`))}>🔄 Susun kenderaan</button>}
            {e.status === "open" && <button className="btn" onClick={() => act(() => api.post(`/admin/events/${e.event_id}/finalise`),
              "Sahkan senarai? Kenderaan dikunci, ahli dimaklumkan dan bayaran dibuka.")}>✅ Sahkan senarai</button>}
            {e.status === "cancelled" && e.training_date >= new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Kuala_Lumpur" }) && (
              <button className="btn" onClick={() => act(() => api.post(`/admin/events/${e.event_id}/reactivate`),
                "Aktifkan semula latihan ini? Ahli yang ditempah sebelum dibatalkan dipulihkan (yang batal sendiri tidak), cuti pada tarikh ini dibuang, ahli dimaklumkan dan kredit bayaran digunakan semasa senarai disahkan.")}>♻️ Aktifkan semula latihan</button>)}
            {e.status !== "cancelled" && <button className="btn ghost" onClick={() => act(() => api.post(`/admin/events/${e.event_id}/cancel`),
              "Batalkan latihan ini? Bayaran yang dah dibuat akan dibawa ke latihan seterusnya sebagai kredit.")}>🚫 Batalkan latihan</button>}
          </div>
          {show[e.event_id] && <Manifest date={e.training_date} onChange={load} />}
        </section>
      ))}
    </>
  );
}

function NeedTransport({ e, onChange }) {
  const [rows, load] = useLoad(`/admin/events/${e.event_id}/needs-transport`, [e.event_id, e.going.unassigned, e.returning.unassigned, e.going.ehailing, e.returning.ehailing]);
  const [note, setNote] = useState("");
  const DIRN = { going: "Pergi", returning: "Balik" };
  const call = (body) => api.post(`/admin/events/${e.event_id}/ehailing`, body).then(() => { onChange(); load(); }).catch(fail);
  if (!rows || rows.length === 0) return null;
  const copyWa = () => {
    const eh = rows.filter((r) => r.ehailing);
    const lines = [`🚕 *E-hailing ${fmtDate(e.training_date)}*`, "Tiada prebet untuk trip berikut. Sila tempah & bayar e-hailing sendiri; geraksekali supaya kos lebih jimat."];
    ["going", "returning"].forEach((d) => {
      const g = eh.filter((r) => r.direction === d);
      if (!g.length) return;
      lines.push("", `*${DIRN[d]}* (${g.length} orang):`);
      g.forEach((r, i) => lines.push(`${i + 1}. ${r.name}${r.college ? ` (${r.college})` : ""}`));
    });
    const text = lines.join("\n");
    (navigator.clipboard?.writeText(text) || Promise.reject()).then(() => alert("Mesej disalin ✅")).catch(() => window.prompt("Salin mesej:", text));
  };
  return (
    <div className="note" style={{ cursor: "default" }}>
      <b>🚕 Tiada prebet / e-hailing</b>
      <div className="small muted">BKK tempah e-hailing, isi nota (nama driver, plat, masa) kemudian tandakan. Ahli dimaklumkan dalam app.</div>
      <input placeholder="Nota untuk ahli (cth Grab, plat ABC1234, 8:40 malam)" value={note} maxLength={250} onChange={(ev) => setNote(ev.target.value)} />
      {rows.map((r) => (
        <div className="row" key={r.booking_id}>
          <span>{r.name} <span className="small muted">· {DIRN[r.direction]} · {r.phone}</span>{r.ehailing && <span className="badge ok">🚕 e-hailing{r.note ? `: ${r.note}` : ""}</span>}</span>
          <button className="link" onClick={() => call({ direction: r.direction, user_ids: [r.user_id], note, on: !r.ehailing })}>{r.ehailing ? "Batal" : "🚕 Tandakan"}</button>
        </div>
      ))}
      <div className="actions">
        {rows.some((r) => r.ehailing) && <button className="btn ghost" onClick={copyWa}>📋 Salin mesej WhatsApp</button>}
        {["going", "returning"].map((d) => rows.some((r) => r.direction === d && !r.ehailing) &&
          <button key={d} className="btn ghost" onClick={() => call({ direction: d, note, on: true })}>🚕 Semua {DIRN[d]} → e-hailing</button>)}
      </div>
    </div>
  );
}

/* ---------- Penumpang ---------- */
function Passengers() {
  const [dates, , derr] = useLoad("/admin/dashboard");
  const [sel, setSel] = useState("");
  const [rows, load, err] = useLoad(sel ? `/admin/passengers?training_date=${sel}` : null, [sel]);
  useEffect(() => { if (dates && !sel && dates[0]) setSel(dates[0].training_date); }, [dates]);
  if (!dates) return <p className="muted">{derr || "Memuatkan..."}</p>;
  const cancel = async (user_id, name) => {
    if (!confirm(`Batalkan semua trip ${name}? Bayaran yang dah dibuat dibawa sebagai kredit.`)) return;
    await api.post("/admin/bookings/cancel", { user_id, training_date: sel }).catch(fail);
    load();
  };
  const isAct = !!(dates.find((d) => d.training_date === sel) || {}).is_activity;
  const changePlace = async (r) => {
    const arah = r.direction === "returning" ? "hantar (balik)" : "ambil (pergi)";
    const v = prompt(`Tempat ${arah} ${r.name} (kosong = kembali ke checkpoint kolej)`, r.pickup_place || "");
    if (v === null) return;
    try { await api.put("/admin/bookings/pickup", { user_id: r.user_id, training_date: sel, place: v.trim(), direction: r.direction }); load(); } catch (e2) { fail(e2); }
  };
  const seen = new Set();
  const conf = (rows || []).filter((r) => r.status === "confirmed");
  const uniq = new Map(conf.map((r) => [r.user_id, r]));
  const people = [...uniq.values()];
  const cnt = (fn) => people.filter(fn).length;
  const byCollege = {};
  people.forEach((p) => { byCollege[p.college || "-"] = (byCollege[p.college || "-"] || 0) + 1; });
  const dirCount = (d) => conf.filter((r) => r.direction === d).length;
  return (
    <>
      <select value={sel} onChange={(e) => setSel(e.target.value)}>
        {dates.map((d) => <option key={d.training_date} value={d.training_date}>{fmtDate(d.training_date)}</option>)}
      </select>
      {rows && (
        <section className="card">
          <h3>Jumlah penumpang: {people.length} orang</h3>
          <div className="stats">
            <div className="stat"><b>{cnt((p) => p.gender === "male")}</b><span>Lelaki</span></div>
            <div className="stat"><b>{cnt((p) => p.gender === "female")}</b><span>Perempuan</span></div>
            <div className="stat"><b>{cnt((p) => !p.vehicle_id)}</b><span>Belum ada kenderaan</span></div>
          </div>
          <div className="stats">
            <div className="stat"><b>{cnt((p) => p.category === "dekat")}</b><span>Kolej dekat</span></div>
            <div className="stat"><b>{cnt((p) => p.category === "jauh")}</b><span>Kolej jauh</span></div>
            <div className="stat"><b>{dirCount("going")} / {dirCount("returning")}</b><span>Pergi / Balik</span></div>
          </div>
          <div className="chiprow">{Object.entries(byCollege).sort().map(([k, v]) => <span className="chip" key={k}>{k} {v}</span>)}</div>
          <p className="small muted">Dikira daripada tempahan yang sah sahaja (tak termasuk yang tak naik atau terkecuali).</p>
        </section>
      )}
      {err && <p className="error">{err}</p>}
      {rows && rows.length === 0 && <p className="muted">Tiada penumpang.</p>}
      {rows && rows.map((r) => {
        const first = !seen.has(r.user_id); seen.add(r.user_id);
        return (
          <div className="card" key={r.booking_id}>
            <div className="row"><b>{r.name}</b><span className={`badge ${r.status === "confirmed" ? "ok" : "muted"}`}>{DIR[r.direction]} · {r.status}</span></div>
            <div className="small muted">{r.college} · 📍 {r.checkpoint || "-"} · {r.vehicle_type === "motorcycle" ? "🏍️" : "🚗"} {r.vehicle || "belum ada kenderaan"}</div>
            <div className="small"><a href={`tel:${r.phone}`}>📞 {r.phone}</a> · {r.member_no}
              {r.status === "confirmed" && isAct && <button className="link" onClick={() => changePlace(r)}> Tukar tempat {r.direction === "returning" ? "balik" : "pergi"}</button>}
              {first && r.status === "confirmed" && <button className="link" onClick={() => cancel(r.user_id, r.name)}> Batalkan</button>}</div>
          </div>
        );
      })}
    </>
  );
}

/* ---------- Bayaran ---------- */
function DriverBank() {
  const [rows] = useLoad("/admin/finance/drivers");
  const [qr, setQr] = useState(null);
  const showQr = async (id, slot = 1) => { try { setQr(await api.blobUrl(`/admin/drivers/${id}/payout-qr?slot=${slot}`)); } catch (e) { fail(e); } };
  return (
    <section className="card">
      <h3>🏦 Bank / QR driver</h3>
      <p className="muted small">Siapa pemilik setiap akaun bank atau QR untuk bayar driver (nampak kepada admin dan bendahari sahaja).</p>
      {rows && rows.length === 0 && <p className="muted small">Belum ada driver.</p>}
      {(rows || []).map((r) => (
        <div className="note" style={{ cursor: "default" }} key={r.id}>
          <b>{r.name}</b> <span className="small muted">· {r.member_no} · {r.phone}</span>
          {r.account_no || r.has_qr || r.has_qr2
            ? <div className="small">🏦 {r.bank || "-"} · <b>{r.account_no || "-"}</b> · {r.account_name || "-"}
                {r.has_qr && <button className="link" onClick={() => showQr(r.id, 1)}>QR bank</button>}{r.has_qr2 && <button className="link" onClick={() => showQr(r.id, 2)}>QR e-wallet</button>}</div>
            : <div className="small error">⚠️ Belum isi maklumat bayaran</div>}
          <div className="small muted">{r.vehicles.map((v) => `${TYPE[v.type]} ${v.name} (${v.plate_no})${v.approval !== "approved" ? ` · ${v.approval}` : ""}`).join(" · ")}</div>
        </div>
      ))}
      {qr && <div><span className="imgframe"><img src={qr} alt="QR driver" style={{ width: "100%", maxWidth: 240 }} /></span><button className="link" onClick={() => setQr(null)}>Tutup</button></div>}
    </section>
  );
}

function Payments() {
  const [rows, load, err] = useLoad("/admin/payments");
  const [filter, setFilter] = useState("pending");
  if (!rows) return <p className="muted">{err || "Memuatkan..."}</p>;
  const act = async (id, what, body) => { await api.post(`/admin/payments/${id}/${what}`, body).catch(fail); load(); };
  const verify = (p) => {
    const v = window.prompt(`Jumlah sebenar pada resit (RM)?\nPerlu bayar: ${money(p.due)}. Jika lebih, lebihan jadi kredit ahli untuk latihan seterusnya.`, String(p.due));
    if (v === null) return;
    const n = Number(String(v).replace(",", "."));
    if (!isFinite(n) || n < 0) return alert("Jumlah tak sah");
    act(p.id, "verify", { amount_paid: n });
  };
  const shown = rows.filter((p) => filter === "all" || p.status === filter);
  return (
    <>
      <EventMoney />
      <Arrears />
      <select value={filter} onChange={(e) => setFilter(e.target.value)}>
        <option value="pending">Menunggu pengesahan</option><option value="unpaid">Belum bayar</option>
        <option value="paid">Dah bayar</option><option value="all">Semua</option>
      </select>
      <p className="muted small">Bayaran tunai tidak diterima; hanya bayaran dengan resit boleh disahkan.</p>
      <PayDrivers />
      <DriverBank />
      {shown.length === 0 && <p className="muted">Tiada rekod.</p>}
      {shown.map((p) => (
        <div className="card" key={p.id}>
          <div className="row"><b>{p.name}</b><span>{money(p.due)}</span></div>
          <div className="small muted">{fmtDate(p.training_date)} · {p.status}{p.due < p.amount ? ` · kredit −${money(p.amount - p.due)}` : ""}</div>
          <div className="actions">
            {p.has_receipt && <button className="btn ghost" onClick={() => api.openReceipt(p.id).catch(fail)}>🧾 Resit</button>}
            {p.status === "pending" && <>
              <button className="btn" onClick={() => verify(p)}>✔ Sahkan</button>
              <button className="btn ghost" onClick={() => act(p.id, "reject")}>✖ Tolak</button>
            </>}
          </div>
        </div>
      ))}
    </>
  );
}

/* ---------- Kenderaan ---------- */
const TYPE = { car: "🚗", motorcycle: "🏍️" };
const LAYOUTS = { "1,3": "Kereta 5 seat", "1,3,2": "Kereta 7 seat" };

function Vehicles() {
  const [vs, load, err] = useLoad("/admin/vehicles");
  const [users] = useLoad("/admin/users");
  const [f, setF] = useState({ name: "", plate_no: "", vehicle_type: "car", seat_rows: "1,3", driver_id: "", driver_gender: "male", days: [2, 5], kind_id: "" });
  const [kinds] = useLoad("/admin/vehicle-kinds");
  if (!vs) return <p className="muted">{err || "Memuatkan..."}</p>;
  const body = (v) => ({ name: v.name, plate_no: v.plate_no || "", vehicle_type: v.vehicle_type, seat_rows: v.seat_rows,
    driver_id: v.driver_id ? Number(v.driver_id) : null, driver_gender: v.driver_gender, available_days: v.available_days, active: v.active, category: v.category ?? "", kind_id: v.kind_id ? Number(v.kind_id) : null });
  async function add(e) {
    e.preventDefault();
    try { await api.post("/admin/vehicles", body({ ...f, available_days: f.days.join(","), active: true })); setF({ ...f, name: "", plate_no: "" }); load(); }
    catch (e2) { fail(e2); }
  }
  const toggle = (v) => api.put(`/admin/vehicles/${v.id}`, body({ ...v, active: !v.active })).then(load).catch(fail);
  const decide = (v, what) => api.post(`/admin/vehicles/${v.id}/${what}`).then(load).catch(fail);
  const del = (v) => confirm(`Padam kenderaan ${v.name} (${v.plate_no})? Tak boleh diundur.`) && api.del(`/admin/vehicles/${v.id}`).then(load).catch(fail);
  const toggleDay = (d) => setF({ ...f, days: f.days.includes(d) ? f.days.filter((x) => x !== d) : [...f.days, d] });
  const pending = vs.filter((v) => v.approval === "pending");
  const chosen = (users || []).find((u) => String(u.id) === String(f.driver_id));

  return (
    <>
      {pending.length > 0 && <h3>Menunggu kelulusan ({pending.length})</h3>}
      {pending.map((v) => (
        <div className="card" key={v.id}>
          <b>{TYPE[v.vehicle_type]} {v.name}</b> {v.plate_no} · {v.capacity} penumpang · driver {v.driver_gender === "male" ? "lelaki" : "perempuan"}<br />
          <span className="small muted">{v.driver_name} · {v.driver_phone} · {v.available_days.split(",").map((d) => DAYS[d]).join("/")}</span>
          {!v.payout_ok && <div className="small error">⚠️ Belum isi maklumat bayaran (bank/QR)</div>}
          <div className="actions">
            <button className="btn" onClick={() => decide(v, "approve")}>✔ Lulus</button>
            <button className="btn ghost" onClick={() => decide(v, "reject")}>✖ Tolak</button>
            <button className="btn ghost" onClick={() => del(v)}>🗑️ Padam</button>
          </div>
        </div>
      ))}

      <form className="card" onSubmit={add}>
        <h3>Tambah kenderaan (admin)</h3>
        {(kinds || []).length > 0 ? (
          <select value={f.kind_id} onChange={(e) => setF({ ...f, kind_id: e.target.value })} required>
            <option value="">Pilih jenis kenderaan</option>
            {kinds.filter((k) => k.active).map((k) => <option key={k.id} value={k.id}>{k.name} ({k.capacity} penumpang)</option>)}
          </select>
        ) : (
          <select value={f.vehicle_type} onChange={(e) => setF({ ...f, vehicle_type: e.target.value })}>
            <option value="car">Kereta</option><option value="motorcycle">Motosikal</option>
          </select>
        )}
        <input placeholder="Nama (cth: Myvi Ali)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
        <input placeholder="No. plat" value={f.plate_no} onChange={(e) => setF({ ...f, plate_no: e.target.value })} />
        <select value={f.driver_id} onChange={(e) => setF({ ...f, driver_id: e.target.value })}>
          <option value="">Driver (pilih pengguna)</option>
          {(users || []).map((u) => <option key={u.id} value={u.id}>{u.name} ({u.member_no})</option>)}
        </select>
        {(!chosen || !chosen.gender) && (
          <select value={f.driver_gender} onChange={(e) => setF({ ...f, driver_gender: e.target.value })}>
            <option value="male">Driver lelaki</option><option value="female">Driver perempuan</option>
          </select>
        )}
        <div className="chips">{[2, 5].map((d) => <label key={d} className="check"><input type="checkbox" checked={f.days.includes(d)} onChange={() => toggleDay(d)} /> {DAYS[d]}</label>)}</div>
        <button className="btn">Tambah</button>
      </form>

      {vs.filter((v) => v.approval !== "pending").map((v) => (
        <div className="card row" key={v.id}>
          <div><b>{TYPE[v.vehicle_type]} {v.name}</b> <span className="muted small">{v.plate_no} · {v.kind_name ? `${v.kind_name} · ` : ""}{v.capacity} penumpang · driver {v.driver_gender === "male" ? "L" : "P"} · {v.available_days.split(",").map((d) => DAYS[d]).join("/")}<br />
            {v.driver_name || "tiada driver"} · {v.approval}{!v.safety_confirmed ? " · akuan keselamatan belum" : ""}{v.driver_id && !v.payout_ok ? " · bayaran belum diisi" : ""}</span></div>
          <span>
            <select value={v.category || ""} style={{ width: "auto", marginTop: 0 }} title="Kategori kolej"
                    onChange={(e) => api.put(`/admin/vehicles/${v.id}`, body({ ...v, category: e.target.value })).then(load).catch(fail)}>
              <option value="">Auto ({v.category_effective || "-"})</option><option value="dekat">Dekat</option><option value="jauh">Jauh</option>
            </select>{" "}
            <button className="btn ghost" onClick={() => toggle(v)}>{v.active ? "Aktif" : "Nyahaktif"}</button>{" "}
            <button className="link" onClick={() => del(v)}>Padam</button>
          </span>
        </div>
      ))}
      <Kinds />
    </>
  );
}

function Kinds() {
  const [ks, load] = useLoad("/admin/vehicle-kinds");
  const [f, setF] = useState({ name: "", base: "car", seat_rows: "1,3" });
  const add = async (e) => {
    e.preventDefault();
    try { await api.post("/admin/vehicle-kinds", f); setF({ name: "", base: "car", seat_rows: "1,3" }); load(); } catch (e2) { fail(e2); }
  };
  const edit = (k) => {
    const name = prompt("Nama jenis:", k.name); if (name === null) return;
    const seat_rows = k.base === "motorcycle" ? "1" : prompt("Susun atur penumpang dari hadapan (cth 1,3 atau 1,2,2,2):", k.seat_rows);
    if (seat_rows === null) return;
    api.put(`/admin/vehicle-kinds/${k.id}`, { name, base: k.base, seat_rows, active: k.active }).then(load).catch(fail);
  };
  return (
    <section className="card">
      <h3>🧩 Jenis kenderaan</h3>
      <p className="small muted">Jenis yang boleh dipilih driver. Susun atur = bilangan penumpang setiap baris dari hadapan; baris pertama sebelah driver. Cth Myvi: 1,3. Van 7 penumpang: 1,2,2,2. Mengubah jenis tidak mengubah kenderaan yang sudah didaftar.</p>
      {(ks || []).map((k) => (
        <div className="row small" key={k.id}>
          <span className={k.active ? "" : "muted"}><b>{k.name}</b> · {k.base === "car" ? "kereta" : "motosikal"} · {k.capacity} penumpang ({k.seat_rows})</span>
          <span>
            <button className="link" onClick={() => edit(k)}>Ubah</button>
            <button className="link" onClick={() => api.put(`/admin/vehicle-kinds/${k.id}`, { name: k.name, base: k.base, seat_rows: k.seat_rows, active: !k.active }).then(load).catch(fail)}>{k.active ? "Nyahaktif" : "Aktifkan"}</button>
            <button className="link" onClick={() => confirm(`Padam jenis ${k.name}?`) && api.del(`/admin/vehicle-kinds/${k.id}`).then(load).catch(fail)}>Padam</button>
          </span>
        </div>
      ))}
      <form onSubmit={add}>
        <input placeholder="Nama jenis baru (cth: Van 9 penumpang)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
        <select value={f.base} onChange={(e) => setF({ ...f, base: e.target.value, seat_rows: e.target.value === "car" ? "1,3" : "1" })}>
          <option value="car">Kereta / van (yuran kereta)</option><option value="motorcycle">Motosikal</option>
        </select>
        {f.base === "car" && <input placeholder="Susun atur, cth 1,2,2,2" value={f.seat_rows} onChange={(e) => setF({ ...f, seat_rows: e.target.value })} required />}
        <button className="btn">Tambah jenis</button>
      </form>
    </section>
  );
}

/* ---------- Bayar driver ---------- */
function Payouts() {
  const [dates] = useLoad("/admin/dashboard");
  const [sel, setSel] = useState("");
  const [rows, load, err] = useLoad(sel ? `/admin/payouts?training_date=${sel}` : null, [sel]);
  useEffect(() => { if (dates && !sel && dates[0]) setSel(dates[0].training_date); }, [dates]);
  const [qr, setQr] = useState(null);
  const mark = async (r) => {
    if (!confirm(`Tandakan RM${r.outstanding.toFixed(2)} telah dibayar kepada ${r.driver?.name}?`)) return;
    try { await api.post("/admin/payouts", { vehicle_id: r.vehicle_id, training_date: sel }); load(); } catch (e) { fail(e); }
  };
  const showQr = async (id, slot = 1) => { try { setQr(await api.blobUrl(`/admin/drivers/${id}/payout-qr?slot=${slot}`)); } catch (e) { fail(e); } };
  if (!dates) return null;
  return (
    <section className="card">
      <h3>🚗 Bayar driver</h3>
      <p className="muted small">Ahli bayar kepada persatuan; persatuan bayar driver. Jumlah = kadar prebet (Lagi › Jadual harga) bagi ahli yang sudah bayar. Muat naik resit supaya prebet nampak dan tanda diterima.</p>
      <select value={sel} onChange={(e) => setSel(e.target.value)}>
        {dates.map((d) => <option key={d.training_date} value={d.training_date}>{fmtDate(d.training_date)}</option>)}
      </select>
      {err && <p className="error">{err}</p>}
      {rows && rows.length === 0 && <p className="muted small">Tiada kenderaan bertugas.</p>}
      {(rows || []).map((r) => (
        <div className="note" key={r.vehicle_id} style={{ cursor: "default" }}>
          <div className="row"><b>{TYPE[r.vehicle_type]} {r.vehicle}</b><span>{r.passengers} penumpang</span></div>
          <div className="small">{r.driver ? `${r.driver.name} · ${r.driver.phone}` : "Tiada driver"}</div>
          {r.driver && (r.driver.account_no || r.driver.has_qr || r.driver.has_qr2)
            ? <div className="small">🏦 {r.driver.bank} · <b>{r.driver.account_no}</b> {r.driver.account_name}
                {r.driver.has_qr && <button className="link" onClick={() => showQr(r.driver.id, 1)}>QR bank</button>}{r.driver.has_qr2 && <button className="link" onClick={() => showQr(r.driver.id, 2)}>QR e-wallet</button>}</div>
            : <div className="small error">⚠️ Maklumat bayaran driver belum diisi</div>}
          <div className="small">Terkumpul {money(r.collected)} / {money(r.expected)} · patut dibayar {money(r.owed)} · dibayar {money(r.paid_out)} · <b>tertunggak {money(r.outstanding)}</b></div>
          <PayoutReceipt r={r} date={sel} onDone={load} />
        </div>
      ))}
      {qr && <div><span className="imgframe"><img src={qr} alt="QR driver" style={{ width: "100%", maxWidth: 240 }} /></span><button className="link" onClick={() => setQr(null)}>Tutup</button></div>}
    </section>
  );
}

/* ---------- Tetapan lain ---------- */
function PaymentInfo() {
  const [d, load] = useLoad("/admin/settings/payment");
  const [f, setF] = useState(null);
  useEffect(() => { if (d) setF(d); }, [d]);
  if (!f) return null;
  const save = (e) => { e.preventDefault(); api.put("/admin/settings/payment", f).then(() => { alert("Disimpan"); load(); }).catch(fail); };
  const qr = (e) => { const file = e.target.files[0]; if (file) api.upload("/admin/settings/payment-qr", file).then(() => { alert("QR dimuat naik"); load(); }).catch(fail); };
  return (
    <form className="card" onSubmit={save}>
      <h3>💳 Maklumat bayaran</h3>
      <input placeholder="Nama bank" value={f.pay_bank} onChange={(e) => setF({ ...f, pay_bank: e.target.value })} />
      <input placeholder="No. akaun" value={f.pay_account_no} onChange={(e) => setF({ ...f, pay_account_no: e.target.value })} />
      <input placeholder="Nama akaun" value={f.pay_account_name} onChange={(e) => setF({ ...f, pay_account_name: e.target.value })} />
      <textarea placeholder="Nota (cth: letak nama + no. ahli pada rujukan)" rows={2} value={f.pay_notes} onChange={(e) => setF({ ...f, pay_notes: e.target.value })} />
      <button className="btn">Simpan</button>
      <label className="small muted" style={{ display: "block", marginTop: 8 }}>QR {f.has_qr ? "(dah ada; muat naik untuk ganti)" : ""}
        <input type="file" accept="image/png,image/jpeg" onChange={qr} /></label>
    </form>
  );
}

function RulesEditor() {
  const [d, load] = useLoad("/admin/settings/rules");
  const [t, setT] = useState("");
  useEffect(() => { if (d) setT(d.text); }, [d]);
  const save = (text) => api.put("/admin/settings/rules", { text }).then(() => { alert(text ? "Syarat disimpan" : "Guna syarat asal"); load(); }).catch(fail);
  const loadDefault = () => api.publicGet("/rules").then((r) => setT((r.default_rules || []).join("\n"))).catch(fail);
  return (
    <section className="card">
      <h3>📋 Teks syarat kemudahan</h3>
      <p className="small muted">Satu baris = satu syarat, dipaparkan di halaman Syarat. Syarat auto sentiasa dikemas kini mengikut harga & tetapan semasa. Tekan "Muat syarat asal" untuk salin ke sini dan ubah sendiri; "Guna syarat auto" untuk kembali ke versi auto. Peraturan susunan kerusi (adab) kekal berjalan walaupun teks diubah.</p>
      <textarea rows={8} value={t} onChange={(e) => setT(e.target.value)} placeholder="Kosong = syarat asal sistem" />
      <div className="actions">
        <button className="btn" onClick={() => save(t)}>Simpan</button>
        <button className="btn ghost" onClick={loadDefault}>Muat syarat asal (untuk edit)</button>
        <button className="btn ghost" onClick={() => { setT(""); save(""); }}>Guna syarat auto</button>
      </div>
    </section>
  );
}

function Venues() {
  const [vs, load] = useLoad("/admin/venues");
  const [cols] = useLoad("/admin/colleges");
  const [f, setF] = useState({ name: "", college_code: "", excluded_codes: [] });
  const [editId, setEditId] = useState(null);
  const reset = () => { setEditId(null); setF({ name: "", college_code: "", excluded_codes: [] }); };
  const add = async (e) => {
    e.preventDefault();
    try {
      if (editId) await api.put(`/admin/venues/${editId}`, { ...f, active: vs.find((v) => v.id === editId)?.active ?? true });
      else await api.post("/admin/venues", { ...f, active: true });
      reset(); load();
    } catch (e2) { fail(e2); }
  };
  const edit = (v) => { setEditId(v.id); setF({ name: v.name, college_code: v.college_code || "", excluded_codes: v.excluded_codes }); };
  const del = (v) => confirm(`Padam ${v.name}?`) && api.del(`/admin/venues/${v.id}`).then(() => { if (editId === v.id) reset(); load(); }).catch(fail);
  const toggleCode = (c) => setF({ ...f, excluded_codes: f.excluded_codes.includes(c) ? f.excluded_codes.filter((x) => x !== c) : [...f.excluded_codes, c] });
  const toggleActive = (v) => api.put(`/admin/venues/${v.id}`, { name: v.name, college_code: v.college_code || "", excluded_codes: v.excluded_codes, active: !v.active }).then(load).catch(fail);
  return (
    <section className="card">
      <h3>🏟️ Tempat latihan & kolej terkecuali</h3>
      {(vs || []).map((v) => (
        <div className="row" key={v.id}>
          <span className={v.active ? "" : "muted"}>{v.name}{v.college_code ? ` (kolej ${v.college_code})` : ""}<br /><span className="small muted">Terkecuali / berjalan kaki: {v.excluded_codes.join(", ") || "-"}</span></span>
          <span>
            <button className="link" onClick={() => edit(v)}>Edit</button>{" "}
            <button className="link" onClick={() => toggleActive(v)}>{v.active ? "Nyahaktif" : "Aktifkan"}</button>{" "}
            <button className="link" onClick={() => del(v)}>Padam</button>
          </span>
        </div>
      ))}
      <form onSubmit={add}>
        <select value={f.college_code} onChange={(e) => {
          const c = e.target.value;
          setF({ ...f, college_code: c, excluded_codes: c && !f.excluded_codes.includes(c) ? [...f.excluded_codes, c] : f.excluded_codes });
        }}>
          <option value="">Tempat bukan kolej (taip nama di bawah)</option>
          {(cols || []).map((c) => <option key={c.code} value={c.code}>Kolej {c.code}: ahli {c.code} berjalan kaki</option>)}
        </select>
        <input placeholder={f.college_code ? `Nama tempat (kosong = Dewan ${f.college_code})` : "Nama tempat, cth L50"} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required={!f.college_code} />
        <p className="small muted">Pilih kolej jika latihan di kolej itu: ahli kolej sama tak perlu prebet. Tempat bukan kolej (cth L50) tak kecualikan sesiapa melainkan ditanda di bawah.</p>
        <div className="chips" style={{ flexWrap: "wrap", gap: ".5rem" }}>
          {(cols || []).map((c) => <label key={c.code} className="check small"><input type="checkbox" checked={f.excluded_codes.includes(c.code)} onChange={() => toggleCode(c.code)} />{c.code}</label>)}
        </div>
        <button className="btn">{editId ? "Simpan perubahan" : "Tambah"}</button>
        {editId && <button type="button" className="btn ghost" onClick={reset}>Batal edit</button>}
      </form>
    </section>
  );
}

function Colleges() {
  const [cols, load] = useLoad("/admin/colleges");
  const [pts, loadP] = useLoad("/admin/pickup-points");
  const [f, setF] = useState({ name: "", college_id: "", gender: "any" });
  const put = (c, patch) => api.put(`/admin/colleges/${c.id}`, { name: c.name, category: c.category, transport_available: c.transport_available, ...patch }).then(load).catch(fail);
  const addPt = async (e) => { e.preventDefault(); try { await api.post("/admin/pickup-points", { ...f, college_id: Number(f.college_id), active: true }); setF({ name: "", college_id: "", gender: "any" }); loadP(); } catch (e2) { fail(e2); } };
  const delPt = async (p) => {
    if (!confirm(`Padam checkpoint "${p.name}"?`)) return;
    try { await api.del(`/admin/pickup-points/${p.id}`); loadP(); return; } catch (e) {
      if (!/masih guna/.test(e.message)) return fail(e);
      const others = (pts || []).filter((x) => x.college_id === p.college_id && x.id !== p.id);
      if (!others.length) return alert(`${e.message}\n\nTiada checkpoint lain untuk kolej ini. Tambah satu dahulu.`);
      const pick = prompt(`${e.message}\n\nTaip nombor checkpoint destinasi:\n` + others.map((x, i) => `${i + 1}. ${x.name}`).join("\n"));
      const t = others[Number(pick) - 1];
      if (!t) return;
      try { const r = await api.del(`/admin/pickup-points/${p.id}?move_to=${t.id}`); alert(`Dipadam. ${r.moved_users} ahli dipindahkan ke "${t.name}".`); loadP(); } catch (e2) { fail(e2); }
    }
  };
  const togglePt = (p) => api.put(`/admin/pickup-points/${p.id}`, { name: p.name, college_id: p.college_id, gender: p.gender, active: !p.active }).then(loadP).catch(fail);
  return (
    <>
      <section className="card">
        <h3>🏫 Kolej</h3>
        {(cols || []).map((c) => (
          <div className="row small" key={c.id}>
            <span><b>{c.code}</b> {c.category}</span>
            <span>
              <button className="link" onClick={() => put(c, { category: c.category === "dekat" ? "jauh" : "dekat" })}>tukar kategori</button>
              <button className="link" onClick={() => put(c, { transport_available: !c.transport_available })}>{c.transport_available ? "✅ ada perkhidmatan" : "🚫 tiada"}</button>
            </span>
          </div>
        ))}
      </section>
      <section className="card">
        <h3>📍 Checkpoint</h3>
        {(pts || []).map((p) => (
          <div className="row small" key={p.id}>
            <span className={p.active ? "" : "muted"}>{p.college} ({G[p.gender]}): {p.name}</span>
            <button className="link" onClick={() => togglePt(p)}>{p.active ? "Nyahaktif" : "Aktifkan"}</button>
            <button className="link" onClick={() => delPt(p)}>Padam</button>
          </div>
        ))}
        <form onSubmit={addPt}>
          <select value={f.college_id} onChange={(e) => setF({ ...f, college_id: e.target.value })} required>
            <option value="">Kolej</option>{(cols || []).map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
          </select>
          <select value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}>
            <option value="any">Semua</option><option value="male">Lelaki</option><option value="female">Perempuan</option>
          </select>
          <input placeholder="Tempat berkumpul" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
          <button className="btn">Tambah</button>
        </form>
      </section>
    </>
  );
}

function Sessions() {
  const [ss] = useLoad("/admin/sessions");
  const save = (s) => api.put(`/admin/sessions/${s.id}`, { start_time: s.start_time, end_time: s.end_time, pickup_start: s.pickup_start, pickup_end: s.pickup_end, active: s.active })
    .then(() => alert("Disimpan")).catch(fail);
  return (
    <section className="card">
      <h3>🕘 Masa</h3>
      {(ss || []).map((s, i) => (
        <div key={s.id} className="sess">
          <b>{s.name}</b>
          {[["start_time", "Mula latihan"], ["end_time", "Balik bermula"], ["pickup_start", "Pickup dari"], ["pickup_end", "Pickup hingga"]].map(([k, label]) => (
            <label className="small muted" key={k}>{label}<input type="time" defaultValue={s[k]} onChange={(e) => (ss[i][k] = e.target.value)} /></label>
          ))}
          <button className="btn ghost" onClick={() => save(ss[i])}>Simpan {s.name}</button>
        </div>
      ))}
    </section>
  );
}

function Eligibility() {
  const [d, load] = useLoad("/admin/settings/eligibility");
  const [extra, setExtra] = useState("");
  const [sel, setSel] = useState(null);
  const chosen = sel ?? (d ? d.years : []);
  const all = [...new Set([...(d ? d.available : []), ...chosen])].sort();
  const toggle = (y) => setSel(chosen.includes(y) ? chosen.filter((x) => x !== y) : [...chosen, y]);
  const addYear = () => {
    const y = extra.trim();
    if (!/^\d{4}$/.test(y)) return alert("Isi 4 digit, cth 2728");
    if (!chosen.includes(y)) setSel([...chosen, y]);
    setExtra("");
  };
  const save = () => api.put("/admin/settings/eligibility", { years: chosen })
    .then(() => { setSel(null); load(); alert("Disimpan. Tempahan latihan biasa ahli luar sesi ini dibatalkan automatik."); }).catch(fail);
  const lab = (y) => `${y.slice(0, 2)}/${y.slice(2)}`;
  return (
    <section className="card">
      <h3>🎓 Sesi ahli yang boleh tempah prebet (latihan biasa)</h3>
      <p className="small muted">Tick satu atau lebih sesi (4 digit selepas "SG" pada no. ahli; 2627 = sesi 26/27). Tahun baru: tambah 2728 dan nyahtick 2627. Ahli lain masih boleh daftar &amp; masuk tetapi tak boleh tick tempah latihan biasa. Aktiviti luar jadual terbuka untuk semua ahli.</p>
      {all.map((y) => (
        <label className="check" key={y}>
          <input type="checkbox" checked={chosen.includes(y)} onChange={() => toggle(y)} /> Sesi {lab(y)} <span className="muted small">(SG{y}XXX)</span>
        </label>
      ))}
      <div className="row">
        <input placeholder="Tambah sesi lain, cth 2728" value={extra} maxLength={4} onChange={(e) => setExtra(e.target.value)} />
        <button type="button" className="btn ghost" onClick={addYear}>Tambah</button>
      </div>
      <button className="btn" disabled={chosen.length === 0} onClick={save}>Simpan</button>
    </section>
  );
}

function Activities() {
  const [rows, load] = useLoad("/admin/activities");
  const blank = { name: "", go_date: "", return_date: "", pickup_start: "20:30", pickup_end: "20:45", return_time: "23:00", fee: "0", km: "", motor_max_km: "10", car_price: "", motor_price: "3", pickup_mode: "kedua", gather_place: "", return_place: "", return_same: false, fee_by_assoc: false };
  const [f, setF] = useState(blank);
  const add = async (e) => {
    e.preventDefault();
    const num = (v) => (v === "" || v == null ? null : Number(v));
    try { await api.post("/admin/activities", { ...f, return_date: f.return_date || null, fee: Number(f.fee || 0), km: num(f.km), motor_max_km: num(f.motor_max_km), car_price: num(f.car_price), motor_price: num(f.motor_price) }); setF(blank); load(); } catch (e2) { fail(e2); }
  };
  const del = (a) => confirm(`Padam ${a.name}?`) && api.del(`/admin/activities/${a.id}`).then(load).catch(fail);
  const MODES = [["kedua", "Ahli pilih kolej atau tempat lain"], ["rumah", "Ahli ambil dari rumah / tempat sendiri"], ["kolej", "Ambil dari kolej sahaja"]];
  const setPickup = (a) => {
    const go = prompt("Tempat PERGI tetap, semua ahli wajib ikut (kosong = ahli pilih sendiri)", a.gather_place || "");
    if (go === null) return;
    let back = "", same = false;
    const b = prompt("Tempat BALIK tetap (kosong = ahli pilih sendiri; taip = jika sama dengan tempat pergi)",
      a.return_same ? "=" : (a.return_place || ""));
    if (b === null) return;
    if (b.trim() === "=") same = true; else back = b;
    let mode = a.pickup_mode === "kumpul" ? "kedua" : a.pickup_mode;
    if (!go.trim() || (!same && !back.trim())) {
      const ans = prompt(`Bagi arah yang ahli pilih sendiri:\n${MODES.map((m, i) => `${i + 1} = ${m[1]}`).join("\n")}`, String(Math.max(0, MODES.findIndex((m) => m[0] === mode)) + 1));
      if (ans === null) return;
      const m = MODES[Number(ans) - 1];
      if (!m) { alert("Pilih nombor 1 hingga 3"); return; }
      mode = m[0];
    }
    api.put(`/admin/activities/${a.id}/pickup`, { pickup_mode: mode, gather_place: go, return_place: back, return_same: same }).then(load).catch(fail);
  };
  const setFunding = (a, by, settled) => api.put(`/admin/activities/${a.id}/funding`, {
    ...(by !== undefined ? { fee_by_assoc: by } : {}), ...(settled !== undefined ? { assoc_settled: settled } : {}) }).then(load).catch(fail);
  const toggleAssoc = (a) => {
    const to = !a.fee_by_assoc;
    if (confirm(to ? "Persatuan tanggung yuran ahli untuk aktiviti ini? Ahli tak perlu bayar; persatuan serah kepada BKK kemudian."
                   : "Ahli bayar semula (lalai)?")) setFunding(a, to);
  };
  const setFee = (a) => {
    const ask = (label, cur) => { const v = prompt(label, cur ?? ""); return v === null ? undefined : v.trim() === "" ? null : Number(v); };
    const car = ask(`Harga SEKENDERAAN kereta untuk ${a.name} (RM; kosong = guna yuran tetap)`, a.car_price); if (car === undefined) return;
    const motor = ask("Harga motosikal seorang (RM; lalai 3)", a.motor_price ?? 3); if (motor === undefined) return;
    const km = ask("Jarak aktiviti (km; kosong = tak dihad)", a.km); if (km === undefined) return;
    const mmax = ask("Motosikal dibenarkan jika jarak tak melebihi (km; lalai 10)", a.motor_max_km ?? 10); if (mmax === undefined) return;
    const fee = ask("Yuran tetap seorang jika harga sekenderaan kosong (RM; 0 = percuma)", a.fee); if (fee === undefined) return;
    api.put(`/admin/activities/${a.id}/fee`, { fee: fee ?? 0, km, motor_max_km: mmax, car_price: car, motor_price: motor }).then(load).catch(fail);
  };
  return (
    <section className="card">
      <h3>📌 Aktiviti luar jadual</h3>
      <p className="small muted">Terbuka untuk semua ahli, tiada tempat latihan. Kalau tarikh balik berbeza, pergi dan balik jadi dua senarai berasingan (yuran dikira setiap tarikh). Ahli tick sendiri dalam Tetapan. Elak tarikh yang sama dengan latihan Rabu/Sabtu.</p>
      {(rows || []).map((a) => (
        <div className="row" key={a.id}>
          <div><b>{a.name}</b>
            <div className="small muted">Pergi {a.go_date} (pickup {a.pickup_start}–{a.pickup_end}) · Balik {a.return_date} dari {a.return_time}</div>
            <div className="small">📍 Pergi: {a.gather_place || "ahli pilih"} · Balik: {a.return_same ? (a.gather_place || "sama") : (a.return_place || "ahli pilih")}</div>
            <div className="small">💸 {a.fee_by_assoc
              ? <>Ditanggung persatuan{a.assoc_owed ? ` · persatuan perlu serah RM${a.assoc_owed.toFixed(2)} kepada BKK` : " · jumlah dikira selepas senarai disahkan"} · {a.assoc_settled ? "✅ sudah diserah" : "belum diserah"}{" "}
                <button className="link" onClick={() => setFunding(a, undefined, !a.assoc_settled)}>{a.assoc_settled ? "Batal tanda" : "Tandakan sudah diserah"}</button></>
              : "Ahli bayar kepada BKK"}</div>
            <div className="small">{a.car_price != null ? `💰 Kereta RM${Number(a.car_price).toFixed(2)} sekenderaan (÷ kapasiti) · motosikal RM${Number(a.motor_price ?? 3).toFixed(2)}${a.km != null ? ` · ${a.km} km${a.km > (a.motor_max_km ?? 10) ? " (tiada motosikal)" : ""}` : ""}` : a.fee > 0 ? `💰 RM${a.fee.toFixed(2)} seorang setiap tarikh (persatuan kutip, bayar driver)` : "🆓 Percuma (tiada bayaran, tiada bayaran driver)"}</div></div>
          <span><button className="link" onClick={() => setPickup(a)}>Tempat</button>{" "}<button className="link" onClick={() => toggleAssoc(a)}>{a.fee_by_assoc ? "Ahli bayar" : "Persatuan tanggung"}</button>{" "}<button className="link" onClick={() => setFee(a)}>Yuran</button>{" "}<button className="link" onClick={() => del(a)}>Padam</button></span>
        </div>
      ))}
      <form onSubmit={add}>
        <input placeholder="Nama aktiviti" maxLength={40} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
        <label className="small muted">Tarikh pergi<input type="date" value={f.go_date} onChange={(e) => setF({ ...f, go_date: e.target.value })} required /></label>
        <label className="small muted">Tarikh balik (kosong atau sama dengan tarikh pergi = pergi & balik hari yang sama)<input type="date" value={f.return_date} min={f.go_date || undefined} onChange={(e) => setF({ ...f, return_date: e.target.value })} /></label>
        <input placeholder="Tempat pergi tetap (kosong = ahli pilih)" maxLength={120} value={f.gather_place} onChange={(e) => setF({ ...f, gather_place: e.target.value })} />
        <label className="small"><input type="checkbox" checked={f.return_same} onChange={(e) => setF({ ...f, return_same: e.target.checked })} /> Balik ke tempat pergi yang sama</label>
        {!f.return_same && <input placeholder="Tempat balik tetap (kosong = ahli pilih)" maxLength={120} value={f.return_place} onChange={(e) => setF({ ...f, return_place: e.target.value })} />}
        <label className="small muted">Jika ahli pilih sendiri
          <select value={f.pickup_mode} onChange={(e) => setF({ ...f, pickup_mode: e.target.value })}>
            {MODES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select></label>
        <label className="small"><input type="checkbox" checked={f.fee_by_assoc} onChange={(e) => setF({ ...f, fee_by_assoc: e.target.checked })} /> Persatuan tanggung yuran pengangkutan (ahli tak bayar)</label>
        {[["pickup_start", "Pickup pergi dari"], ["pickup_end", "Pickup pergi hingga"], ["return_time", "Balik bermula"]].map(([k, label]) => (
          <label className="small muted" key={k}>{label}<input type="time" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} required /></label>
        ))}
        <label className="small muted">Jarak aktiviti (km)
          <input type="number" min="0" step="0.1" value={f.km} onChange={(e) => setF({ ...f, km: e.target.value })} /></label>
        <label className="small muted">Harga SEKENDERAAN kereta (RM). Yuran penumpang = harga ÷ kapasiti kereta (cth RM40 ÷ 4 = RM10 seorang, walaupun hanya 2 naik; persatuan tanggung kekurangan). Kosong = guna yuran tetap di bawah.
          <input type="number" min="0" step="0.5" value={f.car_price} onChange={(e) => setF({ ...f, car_price: e.target.value })} /></label>
        <label className="small muted">Motosikal dibenarkan jika jarak tak melebihi (km). Lalai 10
          <input type="number" min="0" step="0.5" value={f.motor_max_km} onChange={(e) => setF({ ...f, motor_max_km: e.target.value })} /></label>
        <label className="small muted">Harga motosikal seorang (RM). Lalai RM3
          <input type="number" min="0" step="0.5" value={f.motor_price} onChange={(e) => setF({ ...f, motor_price: e.target.value })} /></label>
        <label className="small muted">Yuran tetap seorang (RM), kaedah ringkas bila harga sekenderaan kosong. 0 = percuma (jika harga kenderaan juga kosong).
          <input type="number" min="0" max="200" step="0.5" value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} /></label>
        <button className="btn">Tambah aktiviti</button>
      </form>
    </section>
  );
}

function Feedback() {
  const [rows, load] = useLoad("/admin/feedback");
  const KIND = { cadangan: "💡 Cadangan", masalah: "🐞 Masalah", lain: "💬 Lain-lain" };
  const setSt = (r, status) => api.put(`/admin/feedback/${r.id}`, { status }).then(load).catch(fail);
  const del = (r) => confirm("Padam maklum balas ini?") && api.del(`/admin/feedback/${r.id}`).then(load).catch(fail);
  const baru = (rows || []).filter((r) => r.status === "baru").length;
  return (
    <section className="card">
      <h3>💬 Maklum balas ahli {baru > 0 && <span className="badge warn">{baru} baru</span>}</h3>
      {rows && rows.length === 0 && <p className="muted small">Belum ada maklum balas.</p>}
      {(rows || []).map((r) => (
        <div className="note" style={{ cursor: "default" }} key={r.id}>
          <b>{KIND[r.kind]}</b> <span className="small muted">· {r.from ? `${r.from.name} (${r.from.member_no})` : "—"} · {r.created_at.slice(0, 10)} · {r.status}</span>
          <div className="small">{r.message}</div>
          <div className="actions">
            {r.status !== "selesai" && <button className="link" onClick={() => setSt(r, "selesai")}>✅ Selesai</button>}
            {r.status === "baru" && <button className="link" onClick={() => setSt(r, "dibaca")}>👁️ Dibaca</button>}
            <button className="link" onClick={() => del(r)}>Padam</button>
          </div>
        </div>
      ))}
    </section>
  );
}

function Users() {
  const [users, load] = useLoad("/admin/users");
  const setRole = (u, role) => api.put(`/admin/users/${u.id}/role`, { role }).then(load).catch(fail);
  const toggle = (u) => api.put(`/admin/users/${u.id}`, { active: !u.active }).then(load).catch(fail);
  const [q, setQ] = useState("");
  const setTreasurer = (u) => api.put(`/admin/users/${u.id}/treasurer`, { on: !u.is_treasurer }).then(load).catch(fail);
  const delUser = async (u) => {
    if (!confirm(`Padam akaun ${u.name} (${u.member_no})? Tak boleh diundur.`)) return;
    try { await api.del(`/admin/users/${u.id}`); load(); }
    catch (e) {
      if (/paksa/i.test(e.message) && confirm(`${u.name} ada tempahan/bayaran/kenderaan.\n\nPadam paksa? SEMUA data akaun ini (tempahan, bayaran, kenderaan) turut dipadam. Sesuai untuk akaun ujian sahaja.`)) {
        api.del(`/admin/users/${u.id}?force=true`).then(load).catch(fail);
      } else if (!/paksa/i.test(e.message)) fail(e);
    }
  };
  const [col, setCol] = useState("");
  const [sortBy, setSortBy] = useState("name");
  const cols = [...new Set((users || []).map((u) => u.college).filter(Boolean))].sort();
  const list = (users || [])
    .filter((u) => !q || `${u.name} ${u.member_no} ${u.email} ${u.block || ""}`.toLowerCase().includes(q.toLowerCase()))
    .filter((u) => !col || u.college === col)
    .sort((a, b) => sortBy === "block"
      ? `${a.college || "~"} ${a.block || "~"} ${a.name}`.localeCompare(`${b.college || "~"} ${b.block || "~"} ${b.name}`, "ms", { numeric: true })
      : 0);
  const reset = async (u) => {
    if (!confirm(`Tetapkan kata laluan sementara untuk ${u.name}?`)) return;
    try { const r = await api.post(`/admin/users/${u.id}/reset-password`); alert(`Kata laluan sementara untuk ${u.name}:\n\n${r.temporary_password}\n\nMaklumkan kepada ahli; minta tukar selepas login.`);
      const ph = (u.phone || "").replace(/\D/g, "").replace(/^0/, "60");
      if (ph && confirm("Buka WhatsApp dengan mesej siap untuk ahli ini?"))
        window.open(`https://wa.me/${ph}?text=${encodeURIComponent(`Salam ${u.name}, kata laluan sementara anda untuk app prebet PSSGUTM: ${r.temporary_password}\nSila login dan tukar di Tetapan.`)}`, "_blank"); }
    catch (e) { fail(e); }
  };
  return (
    <section className="card">
      <h3>👥 Pengguna</h3>
      <input placeholder="Cari nama / no. ahli / emel / blok" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="row" style={{ gap: 8 }}>
        <select value={col} onChange={(e) => setCol(e.target.value)} aria-label="Tapis kolej">
          <option value="">Semua kolej</option>
          {cols.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="Susun">
          <option value="name">Susun: nama</option><option value="block">Susun: kolej dan blok</option>
        </select>
      </div>
      <p className="small muted">{list.length} orang. Bendahari boleh urus bayaran ahli dan bayar driver sahaja. Pengguna perlu log keluar dan masuk semula selepas peranan ditukar.</p>
      {list.map((u) => (
        <div className="row" key={u.id}>
          <span className={u.active ? "" : "muted"}>{u.name}<br /><span className="small muted">{u.member_no} · {u.college || "-"}{u.block ? ` · blok ${u.block}` : ""}{u.checkpoint ? ` · 📍 ${u.checkpoint}` : ""} · <a href={`tel:${u.phone}`}>{u.phone}</a> · <a href={`https://wa.me/${(u.phone || "").replace(/\D/g, "").replace(/^0/, "60")}`} target="_blank" rel="noreferrer">WhatsApp</a>{u.credit_balance > 0 ? ` · kredit ${money(u.credit_balance)}` : ""}</span></span>
          <span>
            <select value={u.role} onChange={(e) => setRole(u, e.target.value)} style={{ width: "auto" }}>
              <option value="member">Ahli</option><option value="driver">Driver</option><option value="admin">Admin</option>
            </select>
            <button className="link" onClick={() => toggle(u)}>{u.active ? "Nyahaktif" : "Aktifkan"}</button>
            <button className="link" onClick={() => reset(u)}>Reset</button>
            <button className="link" onClick={() => setTreasurer(u)}>{u.is_treasurer ? "✓ Bendahari" : "Jadi bendahari"}</button>
            <button className="link" onClick={() => delUser(u)}>Padam</button>
          </span>
        </div>
      ))}
    </section>
  );
}

function Roster() {
  const [rows, load, err] = useLoad("/admin/roster");
  const [f, setF] = useState({ member_no: "", name: "", gender: "", college_code: "" });
  const [cols] = useLoad("/admin/colleges");
  const [res, setRes] = useState(null);
  const [q, setQ] = useState("");
  const csv = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try { setRes(await api.upload("/admin/roster/import", file)); load(); } catch (e2) { fail(e2); }
    e.target.value = "";
  };
  const add = async (e) => {
    e.preventDefault();
    try { await api.post("/admin/roster", { member_no: f.member_no, name: f.name, gender: f.gender || null, college_code: f.college_code || null }); setF({ member_no: "", name: "", gender: "", college_code: "" }); load(); }
    catch (e2) { fail(e2); }
  };
  const toggle = (r) => api.put(`/admin/roster/${r.id}?active=${!r.active}`).then(load).catch(fail);
  const shown = (rows || []).filter((r) => !q || (r.member_no + r.name).toLowerCase().includes(q.toLowerCase())).slice(0, 60);
  return (
    <section className="card">
      <h3>📋 Senarai ahli sah</h3>
      <p className="muted small">Hanya no. ahli dalam senarai ini boleh mendaftar. Import CSV dengan kolum: no ahli, nama, jantina (L/P), kolej (kod, cth KTF). Hanya no. ahli wajib. Format no. ahli: SG + 7 digit (cth SG2627001). No. ahli berulang dalam fail ditolak (semua barisnya); lajur tambahan (IC, alamat dll) diabaikan. Boleh import semula untuk kemas kini; no. lama yang tiada dalam fail kekal.</p>
      <input type="file" accept=".csv,text/csv,text/plain" onChange={csv} />
      {res && <p className="small okmsg">Ditambah {res.added}, dikemas kini {res.updated}{res.error_count ? `, ${res.error_count} ralat` : ""}{res.errors.map((x) => <span key={x} className="error" style={{ display: "block" }}>{x}</span>)}</p>}
      <form onSubmit={add}>
        <input placeholder="No. ahli" value={f.member_no} onChange={(e) => setF({ ...f, member_no: e.target.value })} required />
        <input placeholder="Nama (pilihan)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <div className="row">
          <select value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}><option value="">Jantina</option><option value="male">Lelaki</option><option value="female">Perempuan</option></select>
          <select value={f.college_code} onChange={(e) => setF({ ...f, college_code: e.target.value })}><option value="">Kolej</option>{(cols || []).map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}</select>
        </div>
        <button className="btn">Tambah ahli</button>
      </form>
      <input placeholder={`Cari (${(rows || []).length} ahli)`} value={q} onChange={(e) => setQ(e.target.value)} />
      {err && <p className="error">{err}</p>}
      {shown.map((r) => (
        <div className="row small" key={r.id}>
          <span className={r.active ? "" : "muted"}>{r.member_no} {r.name}<br /><span className="muted">{r.college || "-"} · {r.gender || "-"} · {r.registered ? "dah daftar" : "belum daftar"}</span></span>
          <button className="link" onClick={() => toggle(r)}>{r.active ? "Nyahaktif" : "Aktifkan"}</button>
        </div>
      ))}
    </section>
  );
}

function Branding({ brand, onBrand }) {
  const [f, setF] = useState(null);
  useEffect(() => { if (brand) setF({ brand_name: brand.brand_name, brand_primary: brand.brand_primary, brand_accent: brand.brand_accent, contact_whatsapp: brand.contact_whatsapp || "", contact_email: brand.contact_email || "", wa_group_link: brand.wa_group_link || "" }); }, [brand?.brand_name, brand?.brand_primary, brand?.brand_accent, brand?.contact_whatsapp, brand?.contact_email, brand?.wa_group_link]);
  if (!f) return null;
  const save = async (e) => {
    e.preventDefault();
    try { onBrand(await api.put("/admin/branding", f)); alert("Disimpan"); } catch (e2) { fail(e2); }
  };
  const logo = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try { onBrand(await api.upload("/admin/branding/logo", file)); alert("Logo dikemas kini"); } catch (e2) { fail(e2); }
  };
  const resetColours = async () => {
    if (!confirm("Set semula warna utama dan warna butang ke lalai (merah naga + emas)? Nama dan maklumat lain tak berubah.")) return;
    try { onBrand(await api.post("/admin/branding/reset-colours")); alert("Warna dikembalikan ke lalai"); } catch (e2) { fail(e2); }
  };
  return (
    <form className="card" onSubmit={save}>
      <h3>🎨 Branding</h3>
      <input placeholder="Nama app" value={f.brand_name} onChange={(e) => setF({ ...f, brand_name: e.target.value })} required />
      <label className="small muted">Warna utama<input className="swatch" type="color" value={f.brand_primary} onChange={(e) => setF({ ...f, brand_primary: e.target.value })} /></label>
      <label className="small muted">Warna butang<input className="swatch" type="color" value={f.brand_accent} onChange={(e) => setF({ ...f, brand_accent: e.target.value })} /></label>
      <label className="small muted">No. WhatsApp pentadbir (untuk masalah website)<input placeholder="cth 60192278390" value={f.contact_whatsapp} onChange={(e) => setF({ ...f, contact_whatsapp: e.target.value })} /></label>
      <label className="small muted">Emel pentadbir<input type="email" placeholder="nama@gmail.com" value={f.contact_email} onChange={(e) => setF({ ...f, contact_email: e.target.value })} /></label>
      <label className="small muted">Pautan kumpulan WhatsApp BKK (untuk ahli e-hailing)<input placeholder="https://chat.whatsapp.com/..." value={f.wa_group_link} onChange={(e) => setF({ ...f, wa_group_link: e.target.value })} /></label>
      <button className="btn">Simpan</button>
      <button type="button" className="btn ghost" onClick={resetColours}>↩️ Set semula warna ke lalai</button>
      <label className="small muted" style={{ display: "block", marginTop: 8 }}>Logo (PNG/JPG){brand?.has_logo ? " (dah ada; muat naik untuk ganti)" : ""}
        <input type="file" accept="image/png,image/jpeg" onChange={logo} /></label>
      <p className="small muted">Ikon app pada skrin utama telefon tidak berubah automatik; pasang semula app selepas logo baru.</p>
    </form>
  );
}

function More({ brand, onBrand }) {
  const [a, setA] = useState({ title: "", body: "" });
  const announce = async (e) => { e.preventDefault(); try { await api.post("/admin/announce", a); setA({ title: "", body: "" }); alert("Pengumuman dihantar"); } catch (e2) { fail(e2); } };
  return (
    <>
      <form className="card" onSubmit={announce}>
        <h3>📢 Pengumuman</h3>
        <input placeholder="Tajuk" value={a.title} onChange={(e) => setA({ ...a, title: e.target.value })} required />
        <textarea placeholder="Butiran (pilihan)" rows={3} maxLength={500} value={a.body} onChange={(e) => setA({ ...a, body: e.target.value })} />
        <button className="btn">Hantar kepada semua ahli</button>
      </form>
      <Branding brand={brand} onBrand={onBrand} /><DutyRoster /><Profit /><Holidays /><Rates /><PaymentInfo /><RulesEditor /><Feedback /><Eligibility /><Activities /><Roster /><Venues /><Colleges /><Sessions /><PaxRequests /><Users /><BackupBox /><ResetBox />
    </>
  );
}

const TABS = [["summary", "Ringkasan", Summary], ["pax", "Penumpang", Passengers], ["pay", "Bayaran", Payments],
  ["seat", "Kerusi", SeatMap], ["veh", "Kenderaan", Vehicles], ["more", "Lagi", More]];

/* Halaman Bendahari: bayaran ahli, bayar driver, bank/QR driver dan maklumat akaun persatuan */
export function Treasurer() {
  return (
    <>
      <h2>Bendahari</h2>
      <Payments />
      <PaymentInfo />
    </>
  );
}

export default function Admin({ brand, onBrand }) {
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") || "summary");
  useEffect(() => { const t = params.get("tab"); if (t && TABS.some((x) => x[0] === t)) setTab(t); }, [params]);
  const Cmp = (TABS.find((t) => t[0] === tab) || TABS[0])[2];
  return (
    <>
      <h2>Panel BKK</h2>
      <div className="subtabs">
        {TABS.map(([k, label]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      <Cmp brand={brand} onBrand={onBrand} />
    </>
  );
}
