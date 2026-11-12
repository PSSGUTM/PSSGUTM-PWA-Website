import { useEffect, useState } from "react";
import { api } from "../api.js";
import PasswordInput from "../components/PasswordInput.jsx";
import { ThemeSwitch } from "../components/Theme.jsx";
import { useRef } from "react";

function PasswordBox() {
  const [f, setF] = useState({ current_password: "", new_password: "" });
  const [again, setAgain] = useState("");
  const [m, setM] = useState("");
  async function change() {
    setM("");
    if (f.new_password.length < 8) return setM("Kata laluan baru mesti sekurang-kurangnya 8 aksara");
    if (f.new_password !== again) return setM("Kata laluan baru tak sama");
    try { await api.put("/auth/password", f); setF({ current_password: "", new_password: "" }); setAgain(""); setM("Kata laluan ditukar ✅"); }
    catch (e) { setM(e.message); }
  }
  return (
    <section className="card">
      <h3>Tukar kata laluan</h3>
      <PasswordInput placeholder="Kata laluan semasa" value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} />
      <PasswordInput placeholder="Kata laluan baru (min 8)" value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} autoComplete="new-password" />
      <PasswordInput placeholder="Sahkan kata laluan baru" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" />
      <button type="button" className="btn ghost" onClick={change}>Tukar</button>
      {m && <p className="small">{m}</p>}
    </section>
  );
}

function DocsBox() {
  const [d, setD] = useState(null);
  const [exp, setExp] = useState("");
  const [msg, setMsg] = useState("");
  const lic = useRef(), ins = useRef();
  const load = () => api.get("/driver/docs").then((x) => { setD(x); setExp(x.licence_expiry || ""); });
  useEffect(() => { load(); }, []);
  if (!d) return null;
  const run = async (fn, ok) => { setMsg(""); try { await fn(); await load(); setMsg(ok); } catch (e) { setMsg(e.message); } };
  const view = async (kind) => { try { window.open(await api.blobUrl(`/driver/docs/${kind}`), "_blank"); } catch (e) { setMsg(e.message); } };
  const up = (kind, ref) => (e) => {
    const f = e.target.files[0]; e.target.value = "";
    if (f) run(() => api.upload(`/driver/docs/${kind}`, f), kind === "licence" ? "Gambar lesen disimpan ✅" : "Gambar insurans disimpan ✅");
  };
  return (
    <section className="card">
      <h3>🪪 Dokumen prebet</h3>
      <p className="muted small">Gambar lesen dan tarikh tamat diperlukan sebelum mendaftar kenderaan. Anda akan diingatkan sebelum lesen tamat. Insurans pilihan.</p>
      <div className="row"><b>Gambar lesen</b><span className={`badge ${d.has_licence ? "ok" : "bad"}`}>{d.has_licence ? "Ada" : "Wajib"}</span></div>
      <div className="actions">
        <button type="button" className="btn ghost" onClick={() => lic.current.click()}>{d.has_licence ? "Ganti gambar" : "Muat naik gambar lesen"}</button>
        {d.has_licence && <button type="button" className="btn ghost" onClick={() => view("licence")}>Lihat</button>}
      </div>
      <input ref={lic} type="file" accept="image/png,image/jpeg" hidden onChange={up("licence")} />
      <label className="small muted">Tarikh tamat lesen
        <input type="date" value={exp} onChange={(e) => setExp(e.target.value)} />
      </label>
      <button type="button" className="btn ghost" disabled={!exp} onClick={() => run(() => api.put("/driver/docs/licence-expiry", { licence_expiry: exp }), "Tarikh tamat disimpan ✅")}>Simpan tarikh tamat</button>
      <div className="row" style={{ marginTop: 10 }}><b>Gambar insurans</b><span className="badge muted">Pilihan</span></div>
      <div className="actions">
        <button type="button" className="btn ghost" onClick={() => ins.current.click()}>{d.has_insurance ? "Ganti gambar" : "Muat naik gambar insurans"}</button>
        {d.has_insurance && <button type="button" className="btn ghost" onClick={() => view("insurance")}>Lihat</button>}
        {d.has_insurance && <button type="button" className="btn ghost danger" onClick={() => run(() => api.del("/driver/docs/insurance"), "Dipadam")}>Padam</button>}
      </div>
      <input ref={ins} type="file" accept="image/png,image/jpeg" hidden onChange={up("insurance")} />
      {msg && <p className="small">{msg}</p>}
    </section>
  );
}

function PassengerRequest({ profile, onChange }) {
  const [msg, setMsg] = useState("");
  if (profile.role !== "driver") return null;
  if (profile.passenger_ok) return <p className="okmsg small">✅ Anda dibenarkan menempah sebagai penumpang (tab Penumpang).</p>;
  const ask = async () => { try { await api.post("/driver/request-passenger"); setMsg("Permohonan dihantar kepada BKK."); onChange(); } catch (e) { setMsg(e.message); } };
  return (
    <section className="card">
      <h3>🙋 Jadi penumpang juga?</h3>
      <p className="muted small">Akaun prebet tidak menempah sebagai penumpang. Jika anda perlu naik prebet pada hari lain, mohon kebenaran BKK.</p>
      {profile.passenger_request
        ? <p className="small"><b>Permohonan anda sedang menunggu kelulusan BKK.</b></p>
        : <button type="button" className="btn ghost" onClick={ask}>Mohon jadi penumpang</button>}
      {msg && <p className="small">{msg}</p>}
    </section>
  );
}

function PrebetRequest({ profile, onChange }) {
  const [msg, setMsg] = useState("");
  if (profile.role !== "member") return null;
  const ask = async () => {
    if (!confirm("Mohon jadi prebet? Anda mesti ada kenderaan, dan BKK perlu meluluskan.")) return;
    try { await api.post("/profile/prebet-request"); setMsg("Permohonan dihantar kepada BKK."); onChange(); } catch (e) { setMsg(e.message); }
  };
  const cancel = async () => { try { await api.del("/profile/prebet-request"); onChange(); } catch (e) { setMsg(e.message); } };
  return (
    <section className="card">
      <h3>🚗 Ada kenderaan? Jadi prebet</h3>
      <p className="muted small">Jika anda ada kereta atau motosikal dan sudi menghantar ahli lain, mohon jadi prebet. Perlu kelulusan BKK. Selepas lulus anda muat naik lesen dan daftar kenderaan; anda masih boleh menempah sebagai penumpang.</p>
      {profile.prebet_request
        ? <p className="small"><b>Permohonan anda sedang menunggu kelulusan BKK.</b> <button type="button" className="link" onClick={cancel}>Batal permohonan</button></p>
        : <button type="button" className="btn ghost" onClick={ask}>Mohon jadi prebet</button>}
      {msg && <p className="small">{msg}</p>}
    </section>
  );
}

export default function Setup({ onProfile }) {
  const [data, setData] = useState(null);
  const [colleges, setColleges] = useState([]);
  const [profile, setProfile] = useState(null);
  const [pickGender, setPickGender] = useState(false);   // jantina belum ditetapkan: benarkan pilih
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [cp, setCp] = useState({ current: null, points: [] });

  const load = () => Promise.all([api.get("/transport/preferences"), api.publicGet("/colleges"), api.get("/profile"), api.get("/checkpoints")])
    .then(([a, b, c, k]) => { setData(a); setColleges(b); setProfile({ ...c, pickup_point_id: k.current }); setCp(k); setPickGender(!c.gender); })
    .catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function askGender() {
    const to = profile.gender === "male" ? "female" : "male";
    if (!confirm(`Mohon tukar jantina kepada ${to === "male" ? "Lelaki" : "Perempuan"}? Perlu kelulusan BKK.`)) return;
    try { await api.post("/profile/gender-request", { gender: to }); setMsg("Permohonan dihantar kepada BKK ✅"); load(); } catch (e2) { setErr(e2.message); }
  }
  async function cancelGenderReq() {
    try { await api.del("/profile/gender-request"); load(); } catch (e2) { setErr(e2.message); }
  }

  async function save(e) {
    e.preventDefault();
    setErr(""); setMsg("");
    try {
      const u = await api.put("/profile", { name: profile.name, phone: profile.phone, gender: profile.gender || null, college_id: profile.college_id, college_other: profile.college_id ? null : (profile.college_other || null),
        short_name: profile.short_name || "", block: profile.block || "", pickup_point_id: profile.pickup_point_id || null });
      onProfile?.(u);
      setMsg("Disimpan ✅");
    } catch (e2) { setErr(e2.message); }
  }

  if (!data || !profile) return <p className="muted">{err || "Memuatkan..."}</p>;
  const el = data.eligibility;

  return (
    <form onSubmit={save}>
      <h2>Profil</h2>
      {profile.role === "driver" && !profile.passenger_ok ? null : el.eligible ? (
        <div className="note" style={{ cursor: "default" }}>
          📍 Checkpoint anda: <b>{el.pickup_point}</b><br />
          💰 Yuran ({el.category === "dekat" ? "kolej dekat" : "kolej jauh"}): kereta <b>RM{el.fee_car.toFixed(2)}</b>, motosikal <b>RM{el.fee_motorcycle.toFixed(2)}</b> seorang.
          Sama untuk pergi/balik atau sehala. Sistem isi kereta dahulu, baru motosikal; jumlah muktamad selepas senarai disahkan.
        </div>
      ) : <p className="error">{el.reason}</p>}

      <section className="card">
        <h3>Profil</h3>
        <input placeholder="Nama penuh" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} required />
        <input placeholder="Nama pendek (dilihat ahli & prebet lain)" maxLength={40} value={profile.short_name || ""} onChange={(e) => setProfile({ ...profile, short_name: e.target.value })} required />
        <input value={profile.phone} type="tel" onChange={(e) => setProfile({ ...profile, phone: e.target.value })} required />
        {!pickGender && profile.gender && (
          <div className="small">
            Jantina: <b>{profile.gender === "male" ? "Lelaki" : "Perempuan"}</b>
            {profile.gender_request
              ? <> · <span className="badge warn">Menunggu kelulusan BKK: {profile.gender_request === "male" ? "Lelaki" : "Perempuan"}</span> <button type="button" className="link" onClick={cancelGenderReq}>Batal permohonan</button></>
              : <> · <button type="button" className="link" onClick={askGender}>Tersilap? Mohon tukar (perlu kelulusan BKK)</button></>}
          </div>
        )}
        {pickGender && (
          <select value={profile.gender || ""} onChange={(e) => setProfile({ ...profile, gender: e.target.value || null })}>
            <option value="">Pilih jantina (selepas ini, tukar perlu kelulusan BKK)</option>
            <option value="male">Lelaki</option><option value="female">Perempuan</option>
          </select>
        )}
        <select value={profile.college_id ?? "__other"}
                onChange={(e) => e.target.value === "__other"
                  ? setProfile({ ...profile, college_id: null })
                  : setProfile({ ...profile, college_id: Number(e.target.value), college_other: "" })}>
          {colleges.map((c) => <option key={c.id} value={c.id} disabled={!c.transport_available && profile.role !== "driver"}>{c.code} · {c.name}</option>)}
          <option value="__other">Lain-lain (tulis sendiri)</option>
        </select>
        {!profile.college_id && (
          <input placeholder="Nama kolej / tempat tinggal" maxLength={60} value={profile.college_other || ""}
                 onChange={(e) => setProfile({ ...profile, college_other: e.target.value })} />
        )}
        {profile.role !== "driver" || profile.passenger_ok ? (
          <>
            {cp.points.length > 1 && (
              <select value={profile.pickup_point_id || ""} onChange={(e) => setProfile({ ...profile, pickup_point_id: Number(e.target.value) })}>
                {cp.points.map((p) => <option key={p.id} value={p.id}>📍 {p.name}</option>)}
              </select>
            )}
            <input placeholder="Blok / bilik (cth B-12-3)" maxLength={40} value={profile.block || ""} onChange={(e) => setProfile({ ...profile, block: e.target.value })} />
          </>
        ) : null}
        <p className="muted small">{profile.member_no} · {profile.email}</p>
        {profile.credit_balance > 0 && <p className="okmsg small">Kredit anda: RM{profile.credit_balance.toFixed(2)} (digunakan automatik pada latihan seterusnya)</p>}
      </section>
      {err && <p className="error">{err}</p>}
      {msg && <p className="okmsg">{msg}</p>}
      <button className="btn wide">Simpan</button>
      {profile.role === "driver" && <DocsBox />}
      <PassengerRequest profile={profile} onChange={load} />
      <PrebetRequest profile={profile} onChange={load} />
      <section className="card">
        <h3>🌗 Paparan</h3>
        <p className="muted small">Ikut tetapan telefon anda, atau pilih sendiri.</p>
        <ThemeSwitch />
      </section>
      <PasswordBox />
    </form>
  );
}
