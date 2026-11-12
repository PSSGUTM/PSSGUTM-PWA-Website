import { useEffect, useRef, useState } from "react";
import { api, fmtDate } from "../api.js";

const APPROVAL = { pending: ["Menunggu kelulusan BKK", "warn"], approved: ["Diluluskan ✅", "ok"], rejected: ["Ditolak", "bad"] };
const DAYS = { 2: "Rabu", 5: "Sabtu" };
const DIR = { going: "Pergi", returning: "Balik" };
const TYPE = { car: "🚗 Kereta", motorcycle: "🏍️ Motosikal" };

function VehicleForm({ initial, onSaved, onCancel }) {
  const [f, setF] = useState(initial || { brand: "", colour: "", name: "", plate_no: "", vehicle_type: "car", seats: 5, days: [2, 5], kind_id: "" });
  const [kinds, setKinds] = useState([]);
  useEffect(() => { api.get("/driver/kinds").then((k) => {
    setKinds(k);
    setF((x) => x.kind_id ? x : { ...x, kind_id: (k.find((y) => y.name === x.kind_name) || (x.id ? null : k[0]))?.id ?? "" });
  }).catch(() => {}); }, []);
  const kind = kinds.find((k) => k.id === Number(f.kind_id));
  const [err, setErr] = useState("");
  const toggle = (d) => setF({ ...f, days: f.days.includes(d) ? f.days.filter((x) => x !== d) : [...f.days, d] });
  async function save(e) {
    e.preventDefault(); setErr("");
    const body = { name: f.brand, brand: f.brand, colour: f.colour, plate_no: f.plate_no, vehicle_type: kind ? kind.base : f.vehicle_type, seats: Number(f.seats),
      kind_id: kind ? kind.id : null, available_days: f.days.join(",") };
    try {
      if (f.id) await api.put(`/driver/vehicles/${f.id}`, body); else await api.post("/driver/vehicles", body);
      onSaved();
    } catch (e2) { setErr(e2.message); }
  }
  return (
    <form className="card" onSubmit={save}>
      <h3>{f.id ? "Kemas kini kenderaan" : "Daftar kenderaan"}</h3>
      {kinds.length > 0 ? (
        <>
          <select value={f.kind_id} onChange={(e) => setF({ ...f, kind_id: e.target.value })}>
            {kinds.map((k) => <option key={k.id} value={k.id}>{k.name} (maks {k.capacity} penumpang)</option>)}
          </select>
          {kind?.base === "motorcycle" && <p className="muted small">Motosikal bawa 1 penumpang, sama jantina.</p>}
        </>
      ) : (
        <select value={f.vehicle_type} onChange={(e) => setF({ ...f, vehicle_type: e.target.value })}>
          <option value="car">Kereta</option><option value="motorcycle">Motosikal (bawa 1 penumpang, sama jantina)</option>
        </select>
      )}
      <input placeholder="JENAMA (cth Saga)" maxLength={40} value={f.brand} onChange={(e) => setF({ ...f, brand: e.target.value })} required />
      <input placeholder="WARNA (cth Silver)" maxLength={30} value={f.colour} onChange={(e) => setF({ ...f, colour: e.target.value })} required />
      <input placeholder="NO. PLAT (cth ABC123)" value={f.plate_no} onChange={(e) => setF({ ...f, plate_no: e.target.value })} required />
      <p className="muted small">Penumpang akan nampak: nama anda ({f.brand || "Saga"}, {f.colour || "silver"} &amp; {f.plate_no || "ABC123"}) supaya tahu kenderaan mana untuk dinaiki.</p>
      <div className="chips">{[2, 5].map((d) => <label key={d} className="check"><input type="checkbox" checked={f.days.includes(d)} onChange={() => toggle(d)} /> {DAYS[d]}</label>)}</div>
      {err && <p className="error">{err}</p>}
      <div className="actions"><button className="btn">Hantar</button>{onCancel && <button type="button" className="btn ghost" onClick={onCancel}>Batal</button>}</div>
    </form>
  );
}

function QrSlot({ slot, title, has, onChange }) {
  const ref = useRef();
  const [img, setImg] = useState(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (has) api.blobUrl(`/driver/payout-qr?slot=${slot}`).then(setImg).catch(() => setImg(null)); else setImg(null);
  }, [has]);
  const up = async (e) => {
    const file = e.target.files[0]; e.target.value = "";
    if (!file) return;
    try { onChange(await api.upload(`/driver/payout-qr?slot=${slot}`, file)); setMsg("Dimuat naik ✅"); } catch (e2) { setMsg(e2.message); }
  };
  const del = async () => {
    if (!confirm(`Padam ${title}?`)) return;
    try { onChange(await api.del(`/driver/payout-qr?slot=${slot}`)); setMsg("Dipadam"); } catch (e2) { setMsg(e2.message); }
  };
  return (
    <section className="card">
      <h3>{title} <span className="muted small">(pilihan)</span></h3>
      {img && <div className="imgframe"><img className="qrimg" src={img} alt={title} /></div>}
      <div className="actions">
        <button type="button" className="btn ghost" onClick={() => ref.current.click()}>{has ? "Ganti gambar" : "Muat naik gambar QR"}</button>
        {has && <button type="button" className="btn ghost danger" onClick={del}>Padam</button>}
      </div>
      <input ref={ref} type="file" accept="image/png,image/jpeg" hidden onChange={up} />
      {msg && <p className="small muted">{msg}</p>}
    </section>
  );
}

function PayoutForm({ onSaved }) {
  const [f, setF] = useState(null);
  const [msg, setMsg] = useState("");
  useEffect(() => { api.get("/driver/payout").then(setF); }, []);
  if (!f) return null;
  const touched = f.payout_bank || f.payout_account_no || f.payout_account_name;
  const merge = (d) => { setF((x) => ({ ...x, has_qr: d.has_qr, has_qr2: d.has_qr2 })); onSaved?.(); };
  const save = async (e) => {
    e.preventDefault(); setMsg("");
    if (!f.payout_bank.trim() || !f.payout_account_no.trim()) return setMsg("Isi nama bank dan no. akaun.");
    if (!/^[0-9 -]{6,30}$/.test(f.payout_account_no.trim())) return setMsg("No. akaun hanya nombor (cth 1234567890).");
    try { const d = await api.put("/driver/payout", f); setF({ ...f, ...d }); setMsg("Akaun bank disimpan ✅"); onSaved?.(); } catch (e2) { setMsg(e2.message); }
  };
  const delBank = async () => {
    if (!confirm("Padam maklumat akaun bank?")) return;
    try { const d = await api.del("/driver/payout-bank"); setF({ ...f, ...d }); setMsg("Akaun bank dipadam"); onSaved?.(); } catch (e2) { setMsg(e2.message); }
  };
  return (
    <>
      <div className="note" style={{ cursor: "default" }}>
        💳 <b>Maklumat bayaran anda.</b> Isi sekurang-kurangnya satu: akaun bank, atau QR. Setiap bahagian disimpan dan dipadam sendiri; menukar satu tidak mengubah yang lain. Hanya BKK dan bendahari nampak.
      </div>
      <form className="card" onSubmit={save}>
        <h3>🏦 Akaun bank</h3>
        <input placeholder="Nama bank (cth Maybank)" value={f.payout_bank} onChange={(e) => setF({ ...f, payout_bank: e.target.value })} />
        <input placeholder="No. akaun (cth 1234567890)" inputMode="numeric" value={f.payout_account_no} onChange={(e) => setF({ ...f, payout_account_no: e.target.value })} />
        <input placeholder="Nama pemilik akaun" value={f.payout_account_name} onChange={(e) => setF({ ...f, payout_account_name: e.target.value })} />
        <div className="actions">
          <button className="btn">Simpan bank</button>
          {touched && <button type="button" className="btn ghost danger" onClick={delBank}>Padam bank</button>}
        </div>
        {msg && <p className="small">{msg}</p>}
      </form>
      <QrSlot slot={1} title="QR bank" has={f.has_qr} onChange={merge} />
      <QrSlot slot={2} title="QR Touch 'n Go / e-wallet" has={f.has_qr2} onChange={merge} />
    </>
  );
}

export default function Driver() {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);
  const [err, setErr] = useState("");
  const load = () => api.get("/driver/vehicles").then(setData).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const safety = (v, confirmed) => api.post(`/driver/vehicles/${v.id}/safety`, { confirmed }).then(load).catch((e) => alert(e.message));
  if (!data) return <p className="muted">{err || "Memuatkan..."}</p>;

  return (
    <>
      <h2>Driver / Rider</h2>
      <p className="muted">Daftar kenderaan anda; BKK akan luluskan. Anda boleh daftar <b>lebih daripada satu kenderaan</b> dan pilih yang digunakan pada setiap tarikh di tab Utama. Senarai penumpang dan butang sahkan ada di Utama. Bayaran anda tetap setiap hari latihan.</p>
      {!data.payout_ok && <p className="error small">⚠️ Sila isi maklumat bayaran (bank atau QR) supaya persatuan boleh bayar anda.</p>}
      {data.vehicles.map((v) => (
        editing?.id === v.id ? (
          <VehicleForm key={v.id} initial={{ id: v.id, name: v.name, brand: v.brand || v.name, colour: v.colour || "", plate_no: v.plate_no, vehicle_type: v.vehicle_type, seats: v.vehicle_type === "car" ? v.capacity + 1 : 5, days: v.available_days.split(",").map(Number) }}
                       onSaved={() => { setEditing(null); load(); }} onCancel={() => setEditing(null)} />
        ) : (
          <section className="card" key={v.id}>
            <div className="row"><h3>{v.desc || v.name}</h3>
              <span className={`badge ${APPROVAL[v.approval][1]}`}>{APPROVAL[v.approval][0]}</span></div>
            <p className="muted small">{TYPE[v.vehicle_type]} · {v.capacity} penumpang · {v.available_days.split(",").map((d) => DAYS[d]).join(" / ")}</p>
            <label className="check small">
              <input type="checkbox" checked={v.safety_confirmed} onChange={(e) => safety(v, e.target.checked)} />
              <span>Saya ada {v.vehicle_type === "motorcycle" ? "lesen menunggang sah, insurans dan akan pastikan penumpang memakai helmet" : "lesen memandu sah dan insurans"}. {!v.safety_confirmed && <b>(Belum diisi, sila lengkapkan)</b>}</span>
            </label>
            <button className="link" onClick={() => setEditing(v)}>{v.approval === "approved" ? "Ubah hari" : "Ubah maklumat"}</button>
          </section>
        )
      ))}
      {!editing && <VehicleForm onSaved={load} />}
      <PayoutForm onSaved={load} />
    </>
  );
}
