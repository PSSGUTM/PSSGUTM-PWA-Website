import { useEffect, useState } from "react";
import { api, fmtDate } from "../api.js";
import { useToast } from "./Toast.jsx";

// Pilih tarikh latihan: Pergi / Balik untuk setiap tarikh akan datang.
export default function DatePicker({ onChange }) {
  const [opts, setOpts] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [pick, setPick] = useState({});
  const toast = useToast();

  useEffect(() => { api.get("/transport/dates").then(setOpts).catch((e) => setErr(e.message)); }, []);

  // Tempat ambil (pergi) dan hantar (balik) untuk aktiviti luar. Pilihan setempat, atau yang sedia ada pada tempahan.
  const key = (o) => o.training_date + o.session_id;
  const dflt = (o, dir) => {
    const m = o.my_places && o.my_places[dir];
    return m ? { kind: m.kind, place: m.kind === "tempat" ? m.place : "" } : { kind: o.can_kolej ? "kolej" : "tempat", place: "" };
  };
  const pk = (o) => {
    const v = pick[key(o)] || {};
    const go = v.go || dflt(o, "going");
    const same = !o.fixed_go && (v.same ?? !(o.my_places && o.my_places.returning && o.my_places.going
      && JSON.stringify(o.my_places.returning) !== JSON.stringify(o.my_places.going)));
    const ret = same ? go : (v.ret || dflt(o, "returning"));
    return { go, ret, same };
  };
  const setPk = (o, patch) => {
    const cur = pk(o);
    setPick({ ...pick, [key(o)]: { go: cur.go, ret: cur.ret, same: cur.same, ...patch } });
  };

  async function save(o, patch) {
    const next = { going: o.going, returning: o.returning, ...patch };
    const k = key(o);
    const goFree = o.is_activity && o.pickup_mode && !o.fixed_go;     // pergi dipilih ahli
    const retFree = o.is_activity && o.pickup_mode && !o.fixed_return; // balik dipilih ahli
    const choose = (goFree && next.going) || (retFree && next.returning);
    const c = pk(o);
    if (choose) {
      const bad = [["Pergi", c.go, next.going && goFree], ["Balik", c.ret, next.returning && retFree]]
        .find(([, x, on]) => on && x.kind === "tempat" && !x.place.trim());
      if (bad) { toast(`Isi nama tempat ${bad[0].toLowerCase()} dahulu`, "bad"); return; }
    }
    setBusy(k);
    try {
      const d = await api.put("/transport/dates", {
        training_date: o.training_date, session_id: o.session_id, going: next.going, returning: next.returning,
        ...(choose ? {
          ...(goFree ? { pickup: c.go.kind, place: c.go.kind === "tempat" ? c.go.place.trim() : "" } : {}),
          ...(retFree && (!c.same || !goFree)
            ? { return_pickup: c.ret.kind, return_place: c.ret.kind === "tempat" ? c.ret.place.trim() : "" } : {}) } : {}) });
      toast(next.going || next.returning ? `${fmtDate(o.training_date)} disimpan` : `${fmtDate(o.training_date)} dibuang`);
      setOpts(Array.isArray(d) ? d : opts);
      onChange?.();
    } catch (e) { toast(e.message, "bad"); }
    finally { setBusy(""); }
  }

  const Choice = ({ o, dir, label, value }) => (
    <div>
      <div className="small muted">{label}</div>
      {o.can_kolej && (
        <label className="small"><input type="radio" name={`pk${key(o)}${dir}`} checked={value.kind === "kolej"}
          onChange={() => setPk(o, { [dir]: { kind: "kolej", place: "" } })} /> Kolej saya{o.college_point ? ` (${o.college_point})` : ""}</label>)}
      {o.can_tempat && (
        <label className="small"><input type="radio" name={`pk${key(o)}${dir}`} checked={value.kind === "tempat"}
          onChange={() => setPk(o, { [dir]: { kind: "tempat", place: value.place } })} /> Tempat lain (rumah, rumah sewa atau lokasi lain)</label>)}
      {value.kind === "tempat" && (
        <input placeholder="Nama tempat / alamat ringkas" maxLength={120} value={value.place}
          onChange={(e) => setPk(o, { [dir]: { kind: "tempat", place: e.target.value } })} />)}
    </div>
  );

  if (err) return <p className="error">{err}</p>;
  if (!opts) return <div className="skel" />;
  if (!opts.length) return <p className="muted small">Tiada tarikh latihan akan datang.</p>;
  return (
    <div>
      {opts.map((o) => (
        <div key={o.training_date + o.session_id}>
          <div className={`dp-row ${busy === key(o) ? "busy" : ""}`}>
            <div className="dp-date"><b>{fmtDate(o.training_date)}</b><span>{o.session_name || ""}</span></div>
            <div className="seg">
              <button className={o.going ? "on" : ""} disabled={!o.eligible || o.walk || !!o.holiday} onClick={() => save(o, { going: !o.going })}>Pergi</button>
              <button className={o.returning ? "on" : ""} disabled={!o.eligible || o.walk || !!o.holiday} onClick={() => save(o, { returning: !o.returning })}>Balik</button>
            </div>
          </div>
          {o.is_activity && o.eligible && !o.holiday && !o.walk && o.assoc_pays &&
            <p className="dp-note">💚 Yuran pengangkutan ditanggung persatuan. Tiada bayaran untuk anda.</p>}
          {o.is_activity && o.eligible && !o.holiday && !o.walk && o.pickup_mode && (
            <div className="dp-note">
              {o.fixed_go
                ? <p className="small">📍 Pergi: kami ambil di <b>{o.fixed_go}</b> (ditetapkan BKK)</p>
                : <Choice o={o} dir="go" label="📍 Pergi: di mana kami ambil anda?" value={pk(o).go} />}
              {!o.fixed_go && !o.fixed_return &&
                <label className="small"><input type="checkbox" checked={pk(o).same} onChange={(e) => setPk(o, { same: e.target.checked })} /> Hantar balik ke tempat yang sama</label>}
              {o.fixed_return
                ? <p className="small">📍 Balik: kami hantar ke <b>{o.fixed_return}</b> (ditetapkan BKK)</p>
                : (!pk(o).same || o.fixed_go) && <Choice o={o} dir="ret" label="📍 Balik: hantar ke mana?" value={pk(o).ret} />}
              {(!o.fixed_go || !o.fixed_return) && (o.going || o.returning) && (
                <button className="link" disabled={busy === key(o)} onClick={() => save(o, {})}>Simpan tempat</button>)}
            </div>
          )}
          {o.holiday && <p className="dp-note warn">🏖️ Cuti ({o.holiday}): tiada pengangkutan.</p>}
          {o.note && !o.holiday && <p className={`dp-note ${!o.eligible || o.excluded || o.walk ? "warn" : ""}`}>{o.note}</p>}
        </div>
      ))}
    </div>
  );
}
