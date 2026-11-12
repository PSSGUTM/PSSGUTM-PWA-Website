import { useEffect, useState } from "react";
import { api, fmtDate } from "../api.js";
import { useToast } from "./Toast.jsx";

const DIRS = { going: "Pergi", returning: "Balik" };

// Cermin peraturan adab di backend (hanya untuk menandakan kerusi yang sesuai; pelayan tetap mengesahkan).
function violates(car, occ) {
  const seen = new Set();
  for (const o of occ) { const k = `${o.row}.${o.col}`; if (seen.has(k)) return true; seen.add(k); }
  if (car.type === "motorcycle") return occ.some((o) => o.gender !== car.driver_gender);
  if (car.driver_gender === "female") return occ.some((o) => o.gender !== "female");
  const rg = {};
  for (const o of occ) { if ((rg[o.row] ??= o.gender) !== o.gender) return true; }
  if (occ.some((o) => o.gender === "female" && o.row === 0)) return true;
  const m = Object.keys(rg).filter((r) => rg[r] === "male").map(Number);
  const f = Object.keys(rg).filter((r) => rg[r] !== "male").map(Number);
  return m.length > 0 && f.length > 0 && Math.max(...m) > Math.min(...f);
}

function Seat({ car, r, c, person, state, onPick, onDrop, onDragStart }) {
  const cls = ["seat", person ? (person.gender === "male" ? "m" : "f") : "empty", state].filter(Boolean).join(" ");
  return (
    <button type="button" className={cls} draggable={!!person}
            title={person ? `${person.name} (${person.college || "-"})` : "Kosong"}
            onClick={() => onPick(car, r, c, person)}
            onDragStart={(e) => { e.dataTransfer.setData("text/plain", String(person.user_id)); onDragStart(person); }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); onDrop(car, r, c); }}>
      {person ? <><b>{person.gender === "male" ? "L" : "P"} <i>{person.college || "-"}</i></b><small>{person.name.split(" ")[0].slice(0, 8)}</small></> : <small>·</small>}
    </button>
  );
}

export default function SeatMap() {
  const toast = useToast();
  const [events, setEvents] = useState(null);
  const [eid, setEid] = useState("");
  const [map, setMap] = useState(null);
  const [dir, setDir] = useState("going");
  const [sel, setSel] = useState(null);       // { user_id, gender, name, fromVehicle }
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/admin/dashboard").then((e) => {
      const ok = e.filter((x) => x.status !== "cancelled");
      setEvents(ok);
      if (ok[0]) setEid(String(ok[0].event_id));
    }).catch((e) => toast(e.message, "bad"));
  }, []);
  const load = () => eid && api.get(`/admin/events/${eid}/seatmap`).then(setMap).catch((e) => toast(e.message, "bad"));
  useEffect(() => { setMap(null); setSel(null); load(); }, [eid]);

  async function move(person, vehicle_id, row, col) {
    setBusy(true);
    try {
      const body = { user_id: person.user_id, vehicle_id, direction: dir, row, col };
      setMap(await api.put(`/admin/events/${eid}/seat`, body));
      toast(vehicle_id ? "Tempat dikemas kini ✅" : "Dikeluarkan daripada kenderaan");
    } catch (e) { toast(e.message, "bad"); }
    finally { setBusy(false); setSel(null); }
  }
  async function regenerate() {
    if (!confirm("Susun semula kenderaan secara automatik? Kerusi pilihan anda dikekalkan jika masih sah.")) return;
    setBusy(true);
    try { await api.post(`/admin/events/${eid}/reassign`); await load(); toast("Disusun semula ✅"); }
    catch (e) { toast(e.message, "bad"); } finally { setBusy(false); }
  }

  // Tandakan kerusi kosong yang sesuai untuk orang terpilih
  function seatState(car, r, c, person) {
    if (!sel) return "";
    if (person && person.user_id === sel.user_id) return "sel";
    const seated = car.directions[dir].seated;
    const mine = seated.find((p) => p.user_id === sel.user_id);
    let occ = seated.filter((p) => p.user_id !== sel.user_id && !(person && p.user_id === person.user_id));
    occ = occ.map((p) => ({ row: p.row, col: p.col, gender: p.gender }));
    occ.push({ row: r, col: c, gender: sel.gender });
    if (person) {                       // tukar tempat (hanya jika orang terpilih sudah dalam kenderaan ini)
      if (!mine) return "no";
      occ.push({ row: mine.row, col: mine.col, gender: person.gender });
    }
    return violates(car, occ) ? "no" : "ok";
  }
  function pick(car, r, c, person) {
    if (busy) return;
    if (!sel) { if (person) setSel({ ...person, fromVehicle: car.vehicle_id }); return; }
    if (person && person.user_id === sel.user_id) return setSel(null);
    move(sel, car.vehicle_id, r, c);
  }
  const drop = (car, r, c) => { if (sel && !busy) move(sel, car.vehicle_id, r, c); };

  if (!events) return <div className="skel" />;
  if (!events.length) return <p className="muted">Tiada latihan dalam tempoh terdekat.</p>;
  const ev = events.find((e) => String(e.event_id) === eid);

  return (
    <>
      <section className="card">
        <h3>💺 Susunan kerusi</h3>
        <select value={eid} onChange={(e) => setEid(e.target.value)}>
          {events.map((e) => <option key={e.event_id} value={e.event_id}>{fmtDate(e.training_date)} · {e.session_name}</option>)}
        </select>
        <div className="actions">
          <div className="seg">{Object.entries(DIRS).map(([k, l]) => <button key={k} className={dir === k ? "on" : ""} onClick={() => setDir(k)}>{l}</button>)}</div>
          <button className="btn ghost" disabled={busy} onClick={regenerate}>🔄 Jana automatik</button>
        </div>
        <p className="small muted">Tekan atau seret orang ke kerusi lain. <span className="legend m">L</span> lelaki <span className="legend f">P</span> perempuan. Hijau = boleh, merah = langgar peraturan adab. Pergi dan balik naik kenderaan yang sama, kerusi boleh berbeza.{ev?.status === "finalised" ? " Senarai sudah disahkan; perubahan dimaklumkan kepada ahli." : ""}</p>
        {sel && (
          <div className="note" style={{ cursor: "default" }}>
            Dipilih: <b>{sel.name}</b> ({sel.gender === "male" ? "L" : "P"}). Pilih kerusi.
            <div className="actions">
              {sel.fromVehicle && <button className="btn ghost" onClick={() => move(sel, null)}>Keluarkan dari kenderaan</button>}
              <button className="btn ghost" onClick={() => setSel(null)}>Batal</button>
            </div>
          </div>
        )}
      </section>

      {!map && <div className="skel" />}
      {map && map.cars.map((car) => {
        const d = car.directions[dir];
        const at = (r, c) => d.seated.find((p) => p.row === r && p.col === c);
        return (
          <section className="card" key={car.vehicle_id}>
            <div className="row">
              <b>{car.type === "motorcycle" ? "🏍️" : "🚗"} {car.name}</b>
              <span className="chiprow"><span className={`badge ${car.driver_gender === "male" ? "ok" : "warn"}`}>{(car.type === "motorcycle" ? "Motor " : "Kereta ") + (car.driver_gender === "male" ? "lelaki" : "perempuan")}</span>{car.driver_college && <span className="badge muted">{car.driver_college}</span>}{car.category && <span className={`badge ${car.category === "jauh" ? "warn" : "ok"}`}>Kolej {car.category}</span>}</span>
            </div>
            <div className="row">
              <span className="small muted">{car.plate_no} · {car.driver_name || "tiada driver"} ({car.driver_gender === "male" ? "L" : "P"}) · {d.seated.length}/{car.rows.reduce((a, b) => a + b, 0)}</span>
            </div>
            <div className="carbody">
              <div className="carfront">
                {Array.from({ length: car.rows[0] }, (_, c) => {
                  const p = at(0, c);
                  return <Seat key={c} car={car} r={0} c={c} person={p} state={seatState(car, 0, c, p)} onPick={pick} onDrop={drop} onDragStart={(x) => setSel({ ...x, fromVehicle: car.vehicle_id })} />;
                })}
                <span className="seat wheel" title="Tempat duduk driver (kanan)">⚙️<small>Driver ({car.driver_gender === "male" ? "L" : "P"})</small></span>
              </div>
              {car.rows.slice(1).map((n, i) => (
                <div className="carrow" key={i}>
                  {Array.from({ length: n }, (_, c) => {
                    const p = at(i + 1, c);
                    return <Seat key={c} car={car} r={i + 1} c={c} person={p} state={seatState(car, i + 1, c, p)} onPick={pick} onDrop={drop} onDragStart={(x) => setSel({ ...x, fromVehicle: car.vehicle_id })} />;
                  })}
                </div>
              ))}
            </div>
            {d.loose.length > 0 && <p className="small error">Tak muat ikut peraturan: {d.loose.map((p) => p.name).join(", ")}. Pindahkan ke kenderaan lain.</p>}
          </section>
        );
      })}

      {map && map.unassigned.length > 0 && (
        <section className="card">
          <h3>⚠️ Belum ada kenderaan ({map.unassigned.length})</h3>
          <p className="small muted">Tekan nama, kemudian tekan kerusi kosong dalam kenderaan.</p>
          <div className="chiprow">
            {map.unassigned.map((p) => (
              <button key={p.user_id} type="button" className={`chip pickchip ${sel?.user_id === p.user_id ? "on" : ""}`}
                      onClick={() => setSel(sel?.user_id === p.user_id ? null : { ...p, fromVehicle: null })}
                      draggable onDragStart={() => setSel({ ...p, fromVehicle: null })}>
                {p.gender === "male" ? "L" : "P"} · {p.name} ({p.college || "-"})
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
