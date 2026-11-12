import { useEffect, useRef, useState } from "react";
import { api, auth, fmtDate } from "../api.js";

const money = (n) => `RM${Number(n).toFixed(2)}`;
const fail = (e) => alert(e.message);

function useLoad(path, deps = []) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const load = () => (path ? api.get(path).then(setData).catch((e) => setErr(e.message)) : Promise.resolve());
  useEffect(() => { setData(null); load(); }, deps);
  return [data, load, err];
}

/* ---------- Pemantau aliran satu tarikh: prebet sahkan -> senarai -> resit ahli -> bayar prebet -> resit prebet ---------- */
export function Flow({ e, onChange }) {
  const f = e.flow;
  const [open, setOpen] = useState(false);
  if (!f) return null;
  const setAvail = (u, available) =>
    api.put("/admin/prebet/availability", { user_id: u.user_id, training_date: e.training_date, available })
      .then(onChange).catch(fail);
  return (
    <div className="note" style={{ cursor: "default" }}>
      <b>🧭 Aliran tarikh ini</b>
      <ol className="flow">
        {f.steps.map((s) => (
          <li key={s.key} className={s.done ? "done" : ""}>
            <span className="dot">{s.done ? "✓" : "•"}</span>
            <span><b>{s.label}</b><br /><span className="small muted">{s.detail}</span></span>
          </li>
        ))}
      </ol>
      {f.warnings.map((w) => <p className="error small" key={w}>⚠️ {w}</p>)}
      <button className="link" onClick={() => setOpen(!open)}>{open ? "Tutup senarai prebet" : `👥 Prebet (${f.prebet.length}) & nombor telefon`}</button>
      {open && f.prebet.length === 0 && <p className="small muted">Belum ada prebet berdaftar dengan kenderaan diluluskan.</p>}
      {open && f.prebet.map((u) => (
        <div className="row small" key={u.user_id}>
          <span>
            <b>{u.name}</b> {u.college && <span className="chip">{u.college}</span>}<br />
            <a href={`tel:${u.phone}`}>{u.phone}</a> · <a href={`https://wa.me/${(u.phone || "").replace(/\D/g, "").replace(/^0/, "60")}`} target="_blank" rel="noreferrer">WhatsApp</a>
            <br />{u.vehicles.map((v) => `${v.name} (${v.capacity})`).join(", ")}
          </span>
          <span className="seg">
            <button className={u.available === true ? "on" : ""} onClick={() => setAvail(u, true)}>Boleh</button>
            <button className={u.available === false ? "on bad" : ""} onClick={() => setAvail(u, false)}>Tak</button>
          </span>
        </div>
      ))}
      {open && <p className="small muted">Belum sahkan = tidak disusun. Tekan untuk sahkan bagi pihak prebet.</p>}
    </div>
  );
}

/* ---------- Cuti ---------- */
export function Holidays() {
  const [rows, load] = useLoad("/admin/holidays");
  const [f, setF] = useState({ training_date: "", note: "Cuti" });
  const add = async (ev) => {
    ev.preventDefault();
    if (!confirm(`Tandakan ${f.training_date} sebagai cuti? Tempahan pada tarikh itu dibatalkan dan ahli dimaklumkan.`)) return;
    try { await api.post("/admin/holidays", f); setF({ training_date: "", note: "Cuti" }); load(); } catch (e) { fail(e); }
  };
  const del = (h) => api.del(`/admin/holidays/${h.id}`).then(load).catch(fail);
  return (
    <section className="card">
      <h3>🏖️ Tarikh cuti</h3>
      <p className="small muted">Tiada pengangkutan pada tarikh cuti. Tarikh harian lain kekal seperti biasa.</p>
      {(rows || []).map((h) => (
        <div className="row" key={h.id}><span><b>{fmtDate(h.training_date)}</b> <span className="small muted">{h.note}</span></span>
          <button className="link" onClick={() => del(h)}>Buang</button></div>
      ))}
      {rows && rows.length === 0 && <p className="small muted">Tiada tarikh cuti.</p>}
      <form onSubmit={add}>
        <input type="date" value={f.training_date} onChange={(e) => setF({ ...f, training_date: e.target.value })} required />
        <input placeholder="Sebab (cth Cuti peristiwa)" maxLength={120} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        <button className="btn">Tandakan cuti</button>
      </form>
    </section>
  );
}

/* ---------- Jadual harga: penumpang & bayaran prebet ---------- */
const VT = { car: "🚗 Kereta", motorcycle: "🏍️ Motosikal" };
export function Rates() {
  const [d, load] = useLoad("/admin/settings/rates");
  const [f, setF] = useState(null);
  useEffect(() => { if (d) setF(JSON.parse(JSON.stringify(d))); }, [d]);
  if (!f) return null;
  const set = (tbl, vt, cat, v) => setF({ ...f, [tbl]: { ...f[tbl], [vt]: { ...f[tbl][vt], [cat]: v === "" ? null : Number(v) } } });
  const save = (e) => {
    e.preventDefault();
    api.put("/admin/settings/rates", f).then(() => { alert("Harga disimpan. Bayaran yang belum dibayar dikemas kini."); load(); }).catch(fail);
  };
  const Table = ({ tbl, hint }) => (
    <table className="rates">
      <thead><tr><th></th><th>Kolej dekat</th><th>Kolej jauh</th></tr></thead>
      <tbody>
        {["car", "motorcycle"].map((vt) => (
          <tr key={vt}><td>{VT[vt]}</td>
            {["dekat", "jauh"].map((c) => (
              <td key={c}><input type="number" min="0" max="500" step="0.5" placeholder={hint}
                value={f[tbl][vt][c] ?? ""} onChange={(e) => set(tbl, vt, c, e.target.value)} /></td>
            ))}</tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <form className="card" onSubmit={save}>
      <h3>💰 Jadual harga</h3>
      <b className="small">Yuran penumpang bayar (RM seorang)</b>
      <Table tbl="fees" hint="" />
      <b className="small">Bayaran TETAP kepada prebet (RM sehari latihan, ikut kolej prebet)</b>
      <p className="small muted">Satu jumlah tetap setiap hari latihan yang prebet beroperasi (bukan ikut bilangan penumpang). Tidak beroperasi = tiada bayaran. Hanya admin boleh ubah. Kosong = nilai asal (kereta jauh RM14, dekat RM10; motosikal jauh RM2, dekat RM1).</p>
      <Table tbl="payouts" hint="asal" />
      <button className="btn">Simpan harga</button>
    </form>
  );
}

/* ---------- Tunggakan ahli (bendahari & admin) ---------- */
export function Arrears() {
  const [rows] = useLoad("/admin/arrears");
  if (!rows) return null;
  const total = rows.reduce((a, r) => a + r.total, 0);
  return (
    <section className="card">
      <h3>📒 Tunggakan ahli {rows.length > 0 && <span className="badge warn">{rows.length} orang · {money(total)}</span>}</h3>
      <p className="small muted">Ahli yang belum bayar masih boleh naik. Disekat hanya jika bayaran tertua melebihi 6 bulan.</p>
      {rows.length === 0 && <p className="small muted">Tiada tunggakan. 🎉</p>}
      {rows.map((r) => (
        <div className="row" key={r.user_id}>
          <span><b>{r.name}</b> <span className="small muted">{r.member_no}</span><br />
            <span className="small muted">{r.count} bayaran · tertua {r.oldest ? fmtDate(r.oldest) : "-"} · <a href={`https://wa.me/${(r.phone || "").replace(/\D/g, "").replace(/^0/, "60")}`} target="_blank" rel="noreferrer">WhatsApp</a></span></span>
          <span>{money(r.total)} {r.blocked && <span className="badge bad">Disekat</span>}</span>
        </div>
      ))}
    </section>
  );
}

/* ---------- Bayar prebet + muat naik resit ---------- */
export function PayoutReceipt({ r, date, onDone }) {
  const ref = useRef();
  const [busy, setBusy] = useState(false);
  const pick = (e) => {
    const f = e.target.files[0]; e.target.value = "";
    if (!f) return;
    if (!confirm(`Tandakan ${money(r.outstanding)} telah dibayar kepada ${r.driver?.name} dan hantar resit?`)) return;
    setBusy(true);
    api.upload("/admin/payouts/receipt", f, { vehicle_id: r.vehicle_id, training_date: date })
      .then(onDone).catch(fail).finally(() => setBusy(false));
  };
  const view = async (p) => { try { window.open(await api.blobUrl(`/admin/payouts/${p.id}/receipt`), "_blank"); } catch (e) { fail(e); } };
  return (
    <>
      {r.payouts.map((p) => (
        <div className="small" key={p.id}>🧾 {money(p.amount)} {p.has_receipt && <button className="link" onClick={() => view(p)}>Lihat resit</button>} · {p.received ? "✅ prebet sahkan terima" : "menunggu prebet sahkan"}</div>
      ))}
      {r.outstanding > 0 && (
        <>
          <button className="btn" disabled={busy} onClick={() => ref.current.click()}>📤 Dah bayar: muat naik resit ({money(r.outstanding)})</button>
          <input ref={ref} type="file" accept="image/*,application/pdf" hidden onChange={pick} />
        </>
      )}
    </>
  );
}

/* ---------- Permohonan prebet jadi penumpang & dokumen ---------- */
export function PaxRequests() {
  const [users, load] = useLoad("/admin/users");
  const reqs = (users || []).filter((u) => u.passenger_request);
  const greqs = (users || []).filter((u) => u.gender_request);
  const preqs = (users || []).filter((u) => u.prebet_request);
  const decideP = (u, approve) => api.put(`/admin/users/${u.id}/prebet-request`, { approve }).then(load).catch(fail);
  const decideG = (u, approve) => {
    if (approve && !confirm(`Lulus tukar jantina ${u.name}? Jangan lupa betulkan fail CSV sumber juga.`)) return;
    api.put(`/admin/users/${u.id}/gender-request`, { approve }).then(load).catch(fail);
  };
  const L = { male: "Lelaki", female: "Perempuan" };
  const act = (u, approve) => api.put(`/admin/users/${u.id}/passenger`, { approve }).then(load).catch(fail);
  const drivers = (users || []).filter((u) => u.role === "driver");
  const viewDoc = async (u, kind) => { try { window.open(await api.blobUrl(`/admin/users/${u.id}/${kind}`), "_blank"); } catch (e) { fail(e); } };
  const today = new Date().toISOString().slice(0, 10);
  return (
    <section className="card">
      <h3>🙋 Prebet: penumpang & dokumen {reqs.length > 0 && <span className="badge warn">{reqs.length} permohonan</span>}</h3>
      {preqs.length > 0 && <b className="small">🚗 Mohon jadi prebet <span className="badge warn">{preqs.length}</span></b>}
      {preqs.map((u) => (
        <div className="row" key={`p${u.id}`}><span><b>{u.name}</b> <span className="small muted">{u.member_no} · <a href={`tel:${u.phone}`}>{u.phone}</a> · ada kenderaan, mohon jadi prebet</span></span>
          <span><button className="btn" onClick={() => decideP(u, true)}>Lulus</button> <button className="link" onClick={() => decideP(u, false)}>Tolak</button></span></div>
      ))}
      {greqs.length > 0 && <b className="small">⚧ Permohonan tukar jantina <span className="badge warn">{greqs.length}</span></b>}
      {greqs.map((u) => (
        <div className="row" key={`g${u.id}`}><span><b>{u.name}</b> <span className="small muted">{u.member_no}: {L[u.gender]} → {L[u.gender_request]}</span></span>
          <span><button className="btn" onClick={() => decideG(u, true)}>Lulus</button> <button className="link" onClick={() => decideG(u, false)}>Tolak</button></span></div>
      ))}
      {reqs.map((u) => (
        <div className="row" key={u.id}><span><b>{u.name}</b> <span className="small muted">mohon jadi penumpang</span></span>
          <span><button className="btn" onClick={() => act(u, true)}>Lulus</button> <button className="link" onClick={() => act(u, false)}>Tolak</button></span></div>
      ))}
      {drivers.map((u) => (
        <div className="small" key={u.id} style={{ marginTop: 6 }}>
          <b>{u.name}</b> · <a href={`tel:${u.phone}`}>{u.phone}</a>{" "}
          {u.has_licence ? <button className="link" onClick={() => viewDoc(u, "licence")}>🪪 lesen</button> : <span className="badge bad">tiada lesen</span>}
          {u.licence_expiry && <span className={u.licence_expiry < today ? "error" : "muted"}> tamat {u.licence_expiry}</span>}
          {u.has_insurance && <button className="link" onClick={() => viewDoc(u, "insurance")}>📄 insurans</button>}
          {" "}{u.passenger_ok ? <button className="link" onClick={() => act(u, false)}>Tarik balik kebenaran penumpang</button> : null}
        </div>
      ))}
      {drivers.length === 0 && <p className="small muted">Belum ada akaun prebet.</p>}
    </section>
  );
}

/* ---------- Reset data ujian ---------- */
export function ResetBox() {
  const [st] = useLoad("/admin/reset/status");
  const [t, setT] = useState("");
  if (!st) return null;
  const go = async () => {
    if (!confirm("PADAM SEMUA data ujian? Semua pengguna lain, tempahan, bayaran, kenderaan, fail dimuat naik dan tetapan akan dipadam. Tak boleh diundur.")) return;
    try {
      const r = await api.post("/admin/reset", { confirm: t });
      alert(`Siap. ${r.files_removed} fail dipadam. Sistem kini bersih.`);
      location.href = "/";
    } catch (e) { fail(e); }
  };
  return (
    <section className="card danger-zone">
      <h3>⚠️ Zon bahaya: reset data ujian</h3>
      <p className="small muted">Memadam semua pengguna (kecuali akaun admin anda), tempahan, bayaran, kenderaan, gambar/resit/QR dan tetapan, supaya sistem nampak baharu. Senarai ahli sah, kolej, checkpoint, tempat latihan dan jadual Rabu/Sabtu kekal.</p>
      {!st.allowed ? <p className="small"><b>Dimatikan.</b> Set <code>ALLOW_RESET=true</code> pada server (Render) jika perlu, dan matikan semula selepas ujian.</p> : (
        <>
          <input placeholder="Taip RESET untuk mengesahkan" value={t} onChange={(e) => setT(e.target.value)} />
          <button className="btn danger" disabled={t.trim() !== "RESET"} onClick={go}>Reset semua data ujian</button>
        </>
      )}
    </section>
  );
}


/* ---------- Bayar prebet: satu kad seorang prebet, baki digabung, satu resit ---------- */
const MODES = { latihan: "Per latihan", mingguan: "Mingguan", bulanan: "Bulanan" };

export function PayDrivers() {
  const isAdmin = auth.get()?.user?.role === "admin";
  const [ov, load, err] = useLoad("/admin/payouts/overview");
  const [hist, loadHist] = useLoad("/admin/payouts/history");
  const [qr, setQr] = useState(null);
  const [busy, setBusy] = useState(0);
  const refs = useRef({});
  const reloadAll = () => { load(); loadHist(); };
  const showQr = async (id, slot) => { try { setQr(await api.blobUrl(`/admin/drivers/${id}/payout-qr?slot=${slot}`)); } catch (e) { fail(e); } };
  const setMode = (mode) => api.put("/admin/settings/payout-mode", { mode }).then(() => { alert("Kaedah bayaran ditukar. Prebet & bendahari dimaklumkan."); load(); }).catch(fail);
  const pick = (g) => (e) => {
    const f = e.target.files[0]; e.target.value = "";
    if (!f) return;
    if (!confirm(`Tandakan ${money(g.total)} telah dibayar kepada ${g.driver.name} dan hantar resit?`)) return;
    setBusy(g.driver.id);
    api.upload("/admin/payouts/driver", f, { driver_id: g.driver.id }).then(reloadAll).catch(fail).finally(() => setBusy(0));
  };
  const viewReceipt = async (h) => { try { window.open(await api.blobUrl(`/admin/payouts/${h.id}/receipt`), "_blank"); } catch (e) { fail(e); } };
  return (
    <section className="card">
      <h3>🚗 Bayar prebet</h3>
      {ov && <div className="moneybox"><div><span className="small">Jumlah perlu dibayar kepada prebet sekarang</span><b>RM{ov.total.toFixed(2)}</b><span className="small muted">{ov.drivers.length} prebet · hanya latihan yang telah disahkan</span></div></div>}
      <p className="muted small">Bayaran tetap setiap hari latihan yang prebet beroperasi. Satu bayaran = satu prebet = satu resit. Baki yang belum dibayar digabung dengan yang seterusnya (butiran tarikh dipaparkan).</p>
      {ov && (
        <div className="row">
          <span className="small">Kaedah: <b>{ov.mode_label}</b></span>
          {isAdmin && (
            <select value={ov.mode} onChange={(e) => setMode(e.target.value)} style={{ width: "auto" }}>
              {Object.entries(MODES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </div>
      )}
      {err && <p className="error">{err}</p>}
      {ov && ov.drivers.length === 0 && <p className="muted small">Tiada baki bayaran prebet. 🎉</p>}
      {(ov?.drivers || []).map((g) => (
        <div className="note" key={g.driver.id} style={{ cursor: "default" }}>
          <div className="row"><b>{g.driver.name}</b><span><b>{money(g.total)}</b> {g.overdue && <span className="badge bad">Lewat</span>}</span></div>
          <div className="small">{g.driver.phone}</div>
          {g.driver.account_no || g.driver.has_qr || g.driver.has_qr2 ? (
            <div className="small">🏦 {g.driver.bank} · <b>{g.driver.account_no}</b> {g.driver.account_name}
              {g.driver.has_qr && <button type="button" className="link" onClick={() => showQr(g.driver.id, 1)}>QR bank</button>}
              {g.driver.has_qr2 && <button type="button" className="link" onClick={() => showQr(g.driver.id, 2)}>QR e-wallet</button>}</div>
          ) : <div className="small error">⚠️ Maklumat bayaran prebet belum diisi</div>}
          <div className="small"><b>{g.note}</b></div>
          {g.items.map((i) => (
            <div className="small muted" key={i.training_date + i.vehicle_id}>
              {fmtDate(i.training_date)} · {i.vehicle} · {money(i.amount)}{i.complete ? "" : " · tempoh belum tamat"}
              {i.overdue ? " · lewat" : ""} · {i.arrived ? "✅" : "⚠️"} sampai · {i.delivered ? "✅" : "⚠️"} hantar
            </div>
          ))}
          {g.missing_ticks > 0 && <div className="small muted">⚠️ Ada tanda 'sampai/hantar' yang belum diisi prebet (amaran sahaja; prebet tetap dibayar).</div>}
          <button type="button" className="btn" disabled={busy === g.driver.id} onClick={() => refs.current[g.driver.id].click()}>📤 Dah bayar {money(g.total)}: muat naik resit</button>
          <input ref={(el) => { refs.current[g.driver.id] = el; }} type="file" accept="image/*,application/pdf" hidden onChange={pick(g)} />
        </div>
      ))}
      {qr && <div><span className="imgframe"><img src={qr} alt="QR prebet" style={{ width: "100%", maxWidth: 240 }} /></span> <button type="button" className="link" onClick={() => setQr(null)}>Tutup</button></div>}
      {hist && hist.length > 0 && (
        <>
          <b className="small">Bayaran terdahulu</b>
          {hist.slice(0, 15).map((h) => (
            <div className="small" key={h.id}>🧾 {h.driver} · {money(h.amount)} · {h.note} {h.has_receipt && <button type="button" className="link" onClick={() => viewReceipt(h)}>Resit</button>} · {h.received ? "✅ diterima" : "menunggu prebet sahkan"}</div>
          ))}
        </>
      )}
    </section>
  );
}

/* ---------- Sandaran: muat turun zip CSV (admin sahaja) ---------- */
export function BackupBox() {
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      const url = await api.blobUrl("/admin/export");
      const a = document.createElement("a");
      a.href = url; a.download = `sandaran-pssgutm-${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <section className="card">
      <h3>💾 Sandaran data</h3>
      <p className="small muted">Muat turun fail zip (CSV): ahli &amp; prebet, kenderaan, tempahan, bayaran ahli, bayaran prebet. Simpan dalam folder Drive BKK yang peribadi (2–3 orang sahaja). Tidak termasuk kata laluan, gambar lesen/resit/QR dan no. akaun bank penuh (hanya 4 digit akhir). Disyorkan sebulan sekali dan sebelum reset tahunan.</p>
      <button className="btn" disabled={busy} onClick={go}>{busy ? "Menyediakan…" : "⬇️ Muat turun sandaran"}</button>
    </section>
  );
}

/* ---------- Jumlah perlu dikutip / dibayar bagi setiap latihan yang telah disahkan ---------- */
export function EventMoney() {
  const [evs] = useLoad("/admin/dashboard");
  const fin = (evs || []).filter((e) => e.status === "finalised");
  if (!evs) return null;
  return (
    <section className="card">
      <h3>💰 Jumlah ikut latihan</h3>
      <p className="small muted">Dipaparkan selepas senarai disahkan (BKK atau auto). Sebelum itu ahli belum boleh bayar dan bendahari belum boleh bayar prebet.</p>
      {fin.length === 0 && <p className="small">Tiada latihan yang telah disahkan lagi.</p>}
      {fin.map((e) => (
        <div className="moneybox" key={e.event_id}>
          <div><span className="small"><b>{fmtDate(e.training_date)}</b> · ahli perlu bayar</span><b>RM{(e.payments.to_collect ?? 0).toFixed(2)}</b><span className="small muted">{e.payments.members} ahli · masuk RM{e.payments.collected.toFixed(2)}</span></div>
          <div><span className="small">Bayar prebet</span><b>RM{(e.payout_due ?? 0).toFixed(2)}</b><span className="small muted">tetap ikut kenderaan</span></div>
        </div>
      ))}
    </section>
  );
}

/* ---------- Penyata untung rugi (admin sahaja) ---------- */
export function Profit() {
  const [month, setMonth] = useState("");
  const [d] = useLoad(`/admin/profit${month ? `?month=${month}` : ""}`, [month]);
  if (!d) return null;
  const cls = (n) => (n < 0 ? "error" : "okmsg");
  return (
    <section className="card">
      <h3>📊 Untung / rugi (admin sahaja)</h3>
      <p className="small muted">Kutipan ahli tolak bayaran prebet. Boleh negatif (persatuan tanggung demi kebajikan ahli). <b>Bersih</b> = kutipan − patut dibayar prebet; <b>Tunai sebenar</b> = kutipan − yang sudah dibayar.</p>
      <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
      <div className="row small"><b>Jumlah</b><span>Kutip {money(d.total.collected)} · Prebet {money(d.total.owed)} · <b className={cls(d.total.net)}>Bersih {money(d.total.net)}</b> · tunai {money(d.total.realised)}</span></div>
      {d.months.map((m) => (
        <div className="row small" key={m.month}><span><b>{m.month}</b> ({m.trainings} latihan)</span>
          <span>Kutip {money(m.collected)} · Prebet {money(m.owed)} · <b className={cls(m.net)}>{money(m.net)}</b></span></div>
      ))}
      {d.days.length === 0 && <p className="small muted">Belum ada latihan disahkan.</p>}
      {d.days.map((r) => (
        <div className="row small muted" key={r.training_date}><span>{r.label}</span>
          <span>kutip {money(r.collected)}/{money(r.expected)} · prebet {money(r.owed)} (dibayar {money(r.paid_out)}) · <b className={cls(r.net)}>{money(r.net)}</b></span></div>
      ))}
    </section>
  );
}

/* ---------- Admin bertugas ikut bulan ---------- */
const WD = ["Isn", "Sel", "Rab", "Kha", "Jum", "Sab", "Aha"];
export function DutyRoster() {
  const me = auth.get()?.user;
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [d, load] = useLoad(`/admin/duty?month=${month}`, [month]);
  const [f, setF] = useState(null);
  useEffect(() => {
    if (d) { const mine = d.admins.find((a) => a.user_id === me?.id); setF(mine ? { weekdays: mine.weekdays, phone: mine.phone || mine.profile_phone || "" } : null); }
  }, [d]);
  const save = (e) => {
    e.preventDefault();
    api.put("/admin/duty", { month, weekdays: f.weekdays, phone: f.phone }).then(() => { alert("Disimpan"); load(); }).catch(fail);
  };
  const tg = (i) => setF({ ...f, weekdays: f.weekdays.includes(i) ? f.weekdays.filter((x) => x !== i) : [...f.weekdays, i] });
  if (!d) return null;
  return (
    <section className="card">
      <h3>🧑‍💼 Admin bertugas</h3>
      <p className="small muted">Setiap admin pilih hari bertugas dalam bulan itu dan nombor untuk dihubungi (lalai: nombor profil). Prebet/ahli nampak admin bertugas hari itu; jika tiada, nombor pentadbir laman web ({d.site.phone}).</p>
      <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
      {d.admins.map((a) => (
        <div className="small" key={a.user_id}><b>{a.short_name}</b>: {a.weekdays.length ? a.weekdays.map((i) => WD[i]).join(", ") : "belum set"} · {a.phone || a.profile_phone}</div>
      ))}
      {f && (
        <form onSubmit={save}>
          <b className="small">Tetapan saya ({month})</b>
          <div className="chips" style={{ flexWrap: "wrap" }}>
            {WD.map((l, i) => <label key={i} className="check small"><input type="checkbox" checked={f.weekdays.includes(i)} onChange={() => tg(i)} />{l}</label>)}
          </div>
          <input placeholder="No. untuk dihubungi" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
          <button className="btn">Simpan</button>
        </form>
      )}
    </section>
  );
}
