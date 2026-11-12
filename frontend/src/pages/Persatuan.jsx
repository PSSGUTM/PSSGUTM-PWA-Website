import { useEffect, useRef, useState } from "react";
import { api, fmtDate } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import { sendForm, imgUrl } from "../formapi.js";

const fail = (e) => alert(e.message);
const GENDER = { male: "Lelaki", female: "Perempuan" };
const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function useLoad(path, deps = []) {
  const [data, setData] = useState(null);
  const load = () => (path ? api.get(path).then(setData).catch(fail) : Promise.resolve());
  useEffect(() => { setData(null); load(); }, deps);
  return [data, load];
}

export default function Persatuan() {
  const [me, reload] = useLoad("/persatuan/me");
  const [tab, setTab] = useState(null);
  if (!me) return <p className="muted">Memuatkan…</p>;
  const p = me.perms;
  const tabs = [];
  if (p.admin) tabs.push(["ahli", "Ahli"], ["tamat", "Tamat"], ["import", "Import"], ["bengkung", "Bengkung"], ["biro", "Biro"], ["laman", "Laman"]);
  if (p.attendance) tabs.push(["hadir", "Kehadiran"]);
  if (p.inventory) tabs.push(["inv", "Inventori"]);
  if (tabs.length === 0) return <div className="note small">Bahagian ini untuk admin dan pemegang jawatan sahaja.</div>;
  const cur = tab && tabs.some(([k]) => k === tab) ? tab : tabs[0][0];
  return (
    <div>
      {tabs.length > 1 && (
        <div className="subtabs">{tabs.map(([k, l]) => <button key={k} className={cur === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      )}
      {cur === "ahli" && <Ahli />}
      {cur === "tamat" && <Tamat />}
      {cur === "import" && <Import onDone={reload} />}
      {cur === "bengkung" && <Bengkung />}
      {cur === "biro" && <Biro />}
      {cur === "laman" && <Laman />}
      {cur === "hadir" && <Kehadiran />}
      {cur === "inv" && <Inventori />}
    </div>
  );
}

/* ---------- Ahli (admin) ---------- */
const EMPTY = { name: "", email: "", phone: "", gender: "male", intake: "", kind: "SG", study_end: "", study_level: "", college: "", block: "", is_coach: false, belt_id: "", belt_date: "", note: "", active: true };

function Ahli() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [res, setRes] = useState(null);
  const [belts] = useLoad("/persatuan/belts");
  const [edit, setEdit] = useState(null);
  const load = () => api.get(`/persatuan/people?q=${encodeURIComponent(q)}&kind=${kind}`).then(setRes).catch(fail);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [q, kind]);
  return (
    <div>
      <div className="card">
        <input placeholder="Cari nama, emel atau no. ahli" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="seg" style={{ marginTop: 8 }}>
          {[["", "Semua"], ["SG", "Ahli (SG)"], ["SSG", "Alumni (SSG)"]].map(([k, l]) => <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{l}</button>)}
        </div>
        <p className="small muted">{res ? `${res.total} rekod, disusun A hingga Z` : "…"}</p>
        <button className="btn ghost" onClick={() => setEdit({ ...EMPTY })}>+ Tambah seorang</button>
      </div>
      {res?.items.map((p) => (
        <div className="card" key={p.id} onClick={() => setEdit({ ...EMPTY, ...p, belt_id: p.belt_id || "", study_end: p.study_end || "", belt_date: p.belt_date || "" })} style={{ cursor: "pointer" }}>
          <b>{p.name}</b> {p.due && <span className="badge bad">Tamat pengajian</span>}<br />
          <span className="small muted">{p.member_no} · {p.kind === "SG" ? `Ahli · ${p.belt || "tiada bengkung"}` : "Alumni"} · {p.email}</span>
        </div>
      ))}
      {edit && <PersonForm init={edit} belts={belts || []} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); toast("Disimpan"); }} />}
    </div>
  );
}

function PersonForm({ init, belts, onClose, onSaved }) {
  const [f, setF] = useState(init);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const save = (ev) => {
    ev.preventDefault();
    const body = { ...f, belt_id: f.belt_id ? Number(f.belt_id) : null, belt_date: f.belt_date || null, study_end: f.kind === "SG" ? (f.study_end || null) : null };
    (f.id ? api.put(`/persatuan/people/${f.id}`, body) : api.post("/persatuan/people", body)).then(onSaved).catch(fail);
  };
  return (
    <form className="card" onSubmit={save}>
      <h3>{f.id ? "Kemas kini rekod" : "Tambah rekod"}</h3>
      {f.member_no && <p className="small muted">No. ahli: <b>{f.member_no}</b> (dijana sistem)</p>}
      <label className="small">Nama penuh<input required value={f.name} onChange={set("name")} /></label>
      <label className="small">Emel Google<input required type="email" value={f.email} onChange={set("email")} /></label>
      <label className="small">No. telefon<input value={f.phone} onChange={set("phone")} /></label>
      <label className="small">Jantina
        <select value={f.gender || "male"} onChange={set("gender")}><option value="male">Lelaki</option><option value="female">Perempuan</option></select></label>
      <label className="small">Jenis
        <select value={f.kind} onChange={set("kind")}><option value="SG">Ahli semasa (SG)</option><option value="SSG">Alumni (SSG)</option></select></label>
      <label className="small">Sesi masuk (4 digit, cth 2425)<input required pattern="\d{4}" value={f.intake} onChange={set("intake")} /></label>
      {f.kind === "SG" && <>
        <label className="small">Tarikh tamat pengajian<input type="date" value={f.study_end} onChange={set("study_end")} /></label>
        <label className="small">Peringkat pengajian<input value={f.study_level} onChange={set("study_level")} /></label>
        <label className="small">Kolej<input value={f.college} onChange={set("college")} /></label>
        <label className="small">Blok<input value={f.block} onChange={set("block")} /></label>
      </>}
      {f.kind === "SG" && <>
        <label className="small">Bengkung semasa
          <select value={f.belt_id} onChange={set("belt_id")}><option value="">(tiada)</option>{belts.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <label className="small">Tarikh naik bengkung<input type="date" value={f.belt_date} onChange={set("belt_date")} /></label>
      </>}
      <label className="check"><input type="checkbox" checked={f.is_coach} onChange={set("is_coach")} /> Jurulatih</label>
      <label className="check"><input type="checkbox" checked={f.active} onChange={set("active")} /> Aktif</label>
      <label className="small">Catatan<input value={f.note} onChange={set("note")} /></label>
      <div className="actions"><button className="btn">Simpan</button><button type="button" className="btn ghost" onClick={onClose}>Batal</button></div>
    </form>
  );
}

/* ---------- Tamat pengajian: SG -> SSG ---------- */
function Tamat() {
  const [rows, load] = useLoad("/persatuan/conversions");
  const [ext, setExt] = useState({});
  const act = (id, body) => api.post(`/persatuan/conversions/${id}`, body).then(load).catch(fail);
  if (!rows) return <p className="muted">Memuatkan…</p>;
  return (
    <div>
      <div className="note"><b>Tarikh tamat pengajian sudah tiba</b><br /><span className="small">Sahkan sama ada sudah tamat. "Tamat" menukar SG kepada SSG (no. menjadi SSG + sesi masuk). "Belum" melanjutkan tarikh tamat.</span></div>
      {rows.length === 0 && <p className="muted">Tiada yang menunggu pengesahan.</p>}
      {rows.map((p) => (
        <div className="card" key={p.id}>
          <b>{p.name}</b><br /><span className="small muted">{p.member_no} · tamat {fmtDate(p.study_end)}</span>
          <div className="actions">
            <button className="btn" onClick={() => confirm(`Tukar ${p.name} kepada alumni (SSG${p.intake})?`) && act(p.id, { action: "convert" })}>Tamat → SSG</button>
            <input type="date" value={ext[p.id] || ""} onChange={(e) => setExt({ ...ext, [p.id]: e.target.value })} />
            <button className="btn ghost" disabled={!ext[p.id]} onClick={() => act(p.id, { action: "extend", new_end: ext[p.id] })}>Belum, lanjut</button>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Import Excel ---------- */
function Import({ onDone }) {
  const ref = useRef();
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = (dry) => {
    setBusy(true);
    api.upload("/persatuan/import", file, { dry_run: dry ? "true" : "false" }).then((r) => { setRes(r); if (!dry) { setFile(null); onDone?.(); } }).catch(fail).finally(() => setBusy(false));
  };
  return (
    <div className="card">
      <h3>Import ahli, alumni, bengkung dan jawatan</h3>
      <p className="small muted">Guna fail format rasmi. Import boleh diulang: rekod dipadankan melalui emel dan dikemas kini, bukan digandakan.</p>
      <p><a href="/format-import-PSSGUTM.xlsx" download>⬇️ Muat turun format import (.xlsx)</a></p>
      <input ref={ref} type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files[0]); setRes(null); }} />
      <div className="actions">
        <button className="btn ghost" disabled={!file || busy} onClick={() => run(true)}>1. Semak dahulu</button>
        <button className="btn" disabled={!file || busy || !res || !res.dry_run} onClick={() => run(false)}>2. Import</button>
      </div>
      {res && (
        <div className="note" style={{ cursor: "default" }}>
          <b>{res.dry_run ? "Semakan (belum disimpan)" : "Selesai diimport"}</b>
          <p className="small">Baharu {res.stats.people_new} · dikemas kini {res.stats.people_updated} · bengkung baharu {res.stats.belts_new + res.stats.belts_created_from_people} · jawatan baharu {res.stats.posts_new}</p>
          {res.error_count > 0 && <>
            <p className="error small">{res.error_count} baris bermasalah (baris ini dilangkau):</p>
            {res.errors.map((e, i) => <p className="small" key={i}>{e.sheet} baris {e.row}: {e.msg}</p>)}
          </>}
        </div>
      )}
    </div>
  );
}

/* ---------- Bengkung ---------- */
function Bengkung() {
  const [rows, load] = useLoad("/persatuan/belts");
  const [name, setName] = useState("");
  if (!rows) return <p className="muted">Memuatkan…</p>;
  const move = (i, d) => {
    const ids = rows.map((b) => b.id);
    const j = i + d;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    api.put("/persatuan/belts/order", ids).then(load).catch(fail);
  };
  return (
    <div className="card">
      <h3>Peringkat bengkung</h3>
      <p className="small muted">Dari paling bawah (atas senarai) ke paling atas.</p>
      {rows.map((b, i) => (
        <div className="row" key={b.id}>
          <span>{i + 1}. <b>{b.name}</b></span>
          <span className="seg">
            <button onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
            <button onClick={() => move(i, 1)} disabled={i === rows.length - 1}>↓</button>
            <button onClick={() => { const n = prompt("Nama baharu", b.name); if (n && n.trim()) api.put(`/persatuan/belts/${b.id}`, { name: n }).then(load).catch(fail); }}>Ubah</button>
            <button onClick={() => confirm(`Padam ${b.name}?`) && api.del(`/persatuan/belts/${b.id}`).then(load).catch(fail)}>Padam</button>
          </span>
        </div>
      ))}
      <form className="row" onSubmit={(e) => { e.preventDefault(); api.post("/persatuan/belts", { name }).then(() => { setName(""); load(); }).catch(fail); }}>
        <input placeholder="Bengkung baharu (di paling atas)" value={name} onChange={(e) => setName(e.target.value)} required />
        <button className="btn">Tambah</button>
      </form>
    </div>
  );
}

/* ---------- Biro, seki, jawatan ---------- */
function Biro() {
  const [biros, load] = useLoad("/persatuan/biros");
  const [f, setF] = useState({ name: "", parent_id: "" });
  if (!biros) return <p className="muted">Memuatkan…</p>;
  const tops = biros.filter((b) => !b.parent_id);
  const save = (b, patch) => api.put(`/persatuan/biros/${b.id}`, { name: b.name, parent_id: b.parent_id, can_attendance: b.can_attendance, can_inventory: b.can_inventory, ...patch }).then(load).catch(fail);
  return (
    <div>
      <div className="card">
        <h3>Biro dan sekretariat (seki)</h3>
        <p className="small muted">Pemegang jawatan semasa dalam biro (atau seki di bawahnya) yang diberi kebenaran boleh urus kehadiran atau inventori.</p>
        {biros.map((b) => (
          <div className="row small" key={b.id} style={b.parent_id ? { paddingLeft: 18 } : null}>
            <span><b>{b.name}</b>{b.parent_id ? ` (seki, ${biros.find((x) => x.id === b.parent_id)?.name || ""})` : ""}</span>
            <span className="seg">
              <button className={b.can_attendance ? "on" : ""} onClick={() => save(b, { can_attendance: !b.can_attendance })}>Kehadiran</button>
              <button className={b.can_inventory ? "on" : ""} onClick={() => save(b, { can_inventory: !b.can_inventory })}>Inventori</button>
              <button onClick={() => { const n = prompt("Nama baharu", b.name); if (n && n.trim()) save(b, { name: n }); }}>Ubah</button>
              <button onClick={() => confirm(`Padam ${b.name}?`) && api.del(`/persatuan/biros/${b.id}`).then(load).catch(fail)}>Padam</button>
            </span>
          </div>
        ))}
        <form className="row" onSubmit={(e) => { e.preventDefault(); api.post("/persatuan/biros", { name: f.name, parent_id: f.parent_id ? Number(f.parent_id) : null }).then(() => { setF({ name: "", parent_id: "" }); load(); }).catch(fail); }}>
          <input placeholder="Nama biro / seki" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
          <select value={f.parent_id} onChange={(e) => setF({ ...f, parent_id: e.target.value })}><option value="">Biro</option>{tops.map((b) => <option key={b.id} value={b.id}>Seki bawah {b.name}</option>)}</select>
          <button className="btn">Tambah</button>
        </form>
      </div>
      <PostAdd biros={biros} />
    </div>
  );
}

function PostAdd({ biros }) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [found, setFound] = useState([]);
  const [pick, setPick] = useState(null);
  const [posts, setPosts] = useState([]);
  const [f, setF] = useState({ session: "", level: "Biro", biro_id: "", title: "" });
  useEffect(() => { if (q.length < 2) return setFound([]); const t = setTimeout(() => api.get(`/persatuan/people?q=${encodeURIComponent(q)}&limit=8`).then((r) => setFound(r.items)).catch(() => {}), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { api.get("/persatuan/session").then((x) => setF((v) => (v.session ? v : { ...v, session: x.code }))).catch(() => {}); }, []);
  const loadPosts = (p) => api.get(`/persatuan/people/${p.id}`).then((r) => setPosts(r.posts));
  useEffect(() => { if (pick) loadPosts(pick); }, [pick]);
  const add = (e) => {
    e.preventDefault();
    api.post("/persatuan/posts", { person_id: pick.id, session: f.session, level: f.level, biro_id: f.biro_id ? Number(f.biro_id) : null, title: f.title })
      .then(() => { toast("Jawatan ditambah"); loadPosts(pick); }).catch(fail);
  };
  return (
    <div className="card">
      <h3>Jawatan seseorang</h3>
      {!pick ? <>
        <input placeholder="Cari nama" value={q} onChange={(e) => setQ(e.target.value)} />
        {found.map((p) => <div className="row small" key={p.id} onClick={() => setPick(p)} style={{ cursor: "pointer" }}><span>{p.name}</span><span className="muted">{p.member_no}</span></div>)}
      </> : <>
        <p><b>{pick.name}</b> <button className="link" onClick={() => { setPick(null); setPosts([]); }}>tukar</button></p>
        {posts.map((j) => (
          <div className="row small" key={j.id}>
            <span><b>{j.title}</b> · {j.seki ? `${j.seki} (${j.biro})` : j.biro} · {j.label}</span>
            <span className="seg">
              <button className={j.current ? "on" : ""} onClick={() => api.put(`/persatuan/posts/${j.id}?current=${!j.current}`).then(() => loadPosts(pick)).catch(fail)}>Semasa</button>
              <button onClick={() => api.del(`/persatuan/posts/${j.id}`).then(() => loadPosts(pick)).catch(fail)}>Padam</button>
            </span>
          </div>
        ))}
        <form onSubmit={add}>
          <label className="small">Sesi jawatan (cth 2425)<input required pattern="\d{4}" value={f.session} onChange={(e) => setF({ ...f, session: e.target.value })} /></label>
          <label className="small">Peringkat<select value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })}><option>MT</option><option>Biro</option><option>Sekretariat</option></select></label>
          <label className="small">Biro / seki<select value={f.biro_id} onChange={(e) => setF({ ...f, biro_id: e.target.value })}><option value="">(tiada)</option>{biros.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label className="small">Jawatan<input required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
          <button className="btn">Tambah jawatan</button>
        </form>
      </>}
    </div>
  );
}

/* ---------- Kehadiran (BLG / admin) ---------- */
function Kehadiran() {
  const toast = useToast();
  const [rows, load] = useLoad("/persatuan/attendances");
  const [sel, setSel] = useState(null);
  const [f, setF] = useState({ title: "Latihan", on_date: new Date().toISOString().slice(0, 10) });
  if (sel) return <KehadiranDetail id={sel} onBack={() => { setSel(null); load(); }} />;
  return (
    <div>
      <form className="card" onSubmit={(e) => { e.preventDefault(); api.post("/persatuan/attendances", f).then((a) => { toast("Dicipta"); setSel(a.id); }).catch(fail); }}>
        <h3>Kehadiran baharu</h3>
        <label className="small">Tajuk<input required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        <label className="small">Tarikh<input type="date" required value={f.on_date} onChange={(e) => setF({ ...f, on_date: e.target.value })} /></label>
        <button className="btn">Jana QR kehadiran</button>
      </form>
      {rows?.map((a) => (
        <div className="card" key={a.id} onClick={() => setSel(a.id)} style={{ cursor: "pointer" }}>
          <b>{a.title}</b> <span className={`badge ${a.open ? "ok" : ""}`}>{a.open ? "Dibuka" : "Ditutup"}</span><br />
          <span className="small muted">{fmtDate(a.date)} · {a.count} hadir</span>
        </div>
      ))}
    </div>
  );
}

function KehadiranDetail({ id, onBack }) {
  const [d, load] = useLoad(`/persatuan/attendances/${id}`, [id]);
  const [qr, setQr] = useState(null);
  const [q, setQ] = useState("");
  const [found, setFound] = useState([]);
  useEffect(() => { api.get(`/persatuan/attendances/${id}/qr?base=${encodeURIComponent(window.location.origin)}`).then(setQr).catch(() => {}); }, [id]);
  useEffect(() => { if (q.length < 2) return setFound([]); const t = setTimeout(() => api.get(`/persatuan/people/search?q=${encodeURIComponent(q)}`).then(setFound).catch(() => {}), 250); return () => clearTimeout(t); }, [q]);
  const csv = async () => { const u = await api.blobUrl(`/persatuan/attendances/${id}/csv`); const a = document.createElement("a"); a.href = u; a.download = "kehadiran.csv"; a.click(); };
  if (!d) return <p className="muted">Memuatkan…</p>;
  return (
    <div>
      <button className="link" onClick={onBack}>← Senarai</button>
      <div className="card" style={{ textAlign: "center" }}>
        <h3>{d.title}</h3>
        <p className="small muted">{fmtDate(d.date)} · {d.count} hadir</p>
        {qr?.image ? <img src={qr.image} alt="QR kehadiran" style={{ width: 240, maxWidth: "80%", background: "#fff", padding: 8, borderRadius: 8 }} /> : <p className="small muted">QR tak tersedia. Kongsi pautan di bawah.</p>}
        {qr && <p className="small" style={{ wordBreak: "break-all" }}>{qr.url}</p>}
        <div className="actions">
          <button className="btn ghost" onClick={() => api.put(`/persatuan/attendances/${id}/open?open=${!d.open}`).then(load).catch(fail)}>{d.open ? "Tutup kehadiran" : "Buka semula"}</button>
          <button className="btn ghost" onClick={csv}>Muat turun CSV</button>
          <button className="btn ghost" onClick={() => confirm("Padam kehadiran ini?") && api.del(`/persatuan/attendances/${id}`).then(onBack).catch(fail)}>Padam</button>
        </div>
      </div>
      <div className="card">
        <h3>Isi manual</h3>
        <input placeholder="Cari nama" value={q} onChange={(e) => setQ(e.target.value)} />
        {found.map((p) => <div className="row small" key={p.id}><span>{p.name} <span className="muted">{p.member_no}</span></span><button className="btn ghost" onClick={() => api.post(`/persatuan/attendances/${id}/add`, { person_id: p.id }).then(() => { setQ(""); load(); }).catch(fail)}>Hadir</button></div>)}
      </div>
      <div className="card">
        <h3>Senarai hadir ({d.records.length})</h3>
        {d.records.map((r, i) => <div className="row small" key={r.id}><span>{i + 1}. {r.name} <span className="muted">{r.member_no}{r.manual ? " · manual" : ""}</span></span><button className="link" onClick={() => api.del(`/persatuan/attendances/${id}/records/${r.id}`).then(load).catch(fail)}>buang</button></div>)}
      </div>
    </div>
  );
}

/* ---------- Inventori ---------- */
function Inventori() {
  const toast = useToast();
  const [items, loadItems] = useLoad("/persatuan/inventory/items");
  const [loans, loadLoans] = useLoad("/persatuan/inventory/loans?open_only=false");
  const [nf, setNf] = useState({ name: "", category: "", total: 1, note: "", active: true });
  const [lend, setLend] = useState(null);   // item
  const reload = () => { loadItems(); loadLoans(); };
  const photo = async (name) => window.open(await api.blobUrl(`/persatuan/inventory/photo/${name}`), "_blank");
  if (!items) return <p className="muted">Memuatkan…</p>;
  const open = (loans || []).filter((l) => !l.returned_at);
  return (
    <div>
      <div className="card">
        <h3>Barang</h3>
        {items.map((i) => (
          <div className="row small" key={i.id}>
            <span><b>{i.name}</b> {i.category && <span className="chip">{i.category}</span>}{!i.active && <span className="badge bad">Tidak aktif</span>}<br />Ada {i.available} / {i.total}</span>
            <span className="seg">
              <button disabled={!i.active || i.available < 1} onClick={() => setLend(i)}>Pinjam</button>
              <button onClick={() => { const t = prompt("Jumlah baharu", i.total); if (t !== null && !isNaN(+t)) api.put(`/persatuan/inventory/items/${i.id}`, { ...i, total: Number(t) }).then(reload).catch(fail); }}>Jumlah</button>
              <button onClick={() => api.put(`/persatuan/inventory/items/${i.id}`, { ...i, active: !i.active }).then(reload).catch(fail)}>{i.active ? "Henti" : "Aktif"}</button>
            </span>
          </div>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); api.post("/persatuan/inventory/items", { ...nf, total: Number(nf.total) }).then(() => { setNf({ name: "", category: "", total: 1, note: "", active: true }); reload(); toast("Barang ditambah"); }).catch(fail); }}>
          <input placeholder="Nama barang baharu" required value={nf.name} onChange={(e) => setNf({ ...nf, name: e.target.value })} />
          <input placeholder="Kategori (pilihan)" value={nf.category} onChange={(e) => setNf({ ...nf, category: e.target.value })} />
          <input type="number" min="0" value={nf.total} onChange={(e) => setNf({ ...nf, total: e.target.value })} />
          <button className="btn">Tambah barang</button>
        </form>
      </div>
      {lend && <LendForm item={lend} onClose={() => setLend(null)} onDone={() => { setLend(null); reload(); toast("Pinjaman direkodkan"); }} />}
      <div className="card">
        <h3>Sedang dipinjam ({open.length})</h3>
        {open.map((l) => <LoanRow key={l.id} l={l} photo={photo} onChange={reload} />)}
        {open.length === 0 && <p className="muted small">Tiada.</p>}
      </div>
      <div className="card">
        <h3>Sejarah pulangan</h3>
        {(loans || []).filter((l) => l.returned_at).slice(0, 40).map((l) => (
          <div className="row small" key={l.id}><span><b>{l.item}</b> ×{l.qty} · {l.person}<br /><span className="muted">{l.return_note || "tiada nota"}{l.return_photo && <> · <button className="link" onClick={() => photo(l.return_photo)}>gambar pulang</button></>}</span></span></div>
        ))}
      </div>
    </div>
  );
}

function LendForm({ item, onClose, onDone }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState([]);
  const [who, setWho] = useState(null);
  const [f, setF] = useState({ qty: 1, due_date: "", note: "" });
  const [file, setFile] = useState(null);
  useEffect(() => { if (q.length < 2) return setFound([]); const t = setTimeout(() => api.get(`/persatuan/people/search?q=${encodeURIComponent(q)}`).then(setFound).catch(() => {}), 250); return () => clearTimeout(t); }, [q]);
  const submit = (e) => {
    e.preventDefault();
    const form = new FormData();
    form.append("item_id", item.id); form.append("person_id", who.id); form.append("qty", f.qty);
    form.append("due_date", f.due_date); form.append("note", f.note);
    if (file) form.append("file", file);
    const a = JSON.parse(localStorage.getItem("pssgutm_auth"));
    fetch(`${BASE}/persatuan/inventory/loans`, { method: "POST", headers: { Authorization: `Bearer ${a.token}` }, body: form })
      .then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail || "Gagal"); onDone(); }).catch(fail);
  };
  return (
    <form className="card" onSubmit={submit}>
      <h3>Pinjam: {item.name}</h3>
      {!who ? <>
        <input placeholder="Cari nama peminjam" value={q} onChange={(e) => setQ(e.target.value)} />
        {found.map((p) => <div className="row small" key={p.id} onClick={() => setWho(p)} style={{ cursor: "pointer" }}><span>{p.name}</span><span className="muted">{p.member_no}</span></div>)}
      </> : <p><b>{who.name}</b> <button type="button" className="link" onClick={() => setWho(null)}>tukar</button></p>}
      <label className="small">Kuantiti (baki {item.available})<input type="number" min="1" max={item.available} value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} /></label>
      <label className="small">Tarikh pulang dijangka<input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></label>
      <label className="small">Keadaan barang semasa dipinjam<input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
      <label className="small">Gambar keadaan barang (pilihan)<input type="file" accept="image/*" onChange={(e) => setFile(e.target.files[0])} /></label>
      <div className="actions"><button className="btn" disabled={!who}>Rekod pinjaman</button><button type="button" className="btn ghost" onClick={onClose}>Batal</button></div>
    </form>
  );
}

function LoanRow({ l, photo, onChange }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [file, setFile] = useState(null);
  const back = (e) => {
    e.preventDefault();
    const form = new FormData();
    form.append("note", note);
    if (file) form.append("file", file);
    const a = JSON.parse(localStorage.getItem("pssgutm_auth"));
    fetch(`${BASE}/persatuan/inventory/loans/${l.id}/return`, { method: "POST", headers: { Authorization: `Bearer ${a.token}` }, body: form })
      .then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail || "Gagal"); onChange(); }).catch(fail);
  };
  return (
    <div className="row small" style={{ display: "block" }}>
      <b>{l.item}</b> ×{l.qty} · {l.person} {l.overdue && <span className="badge bad">Lewat</span>}<br />
      <span className="muted">Dipinjam {fmtDate(l.taken_at.slice(0, 10))}{l.due_date ? ` · pulang ${fmtDate(l.due_date)}` : ""}{l.taken_note ? ` · ${l.taken_note}` : ""}{l.taken_photo && <> · <button className="link" onClick={() => photo(l.taken_photo)}>gambar pinjam</button></>}</span>
      {!open ? <div><button className="btn ghost" onClick={() => setOpen(true)}>Rekod pulang</button></div> : (
        <form onSubmit={back}>
          <input placeholder="Keadaan barang semasa dipulangkan" value={note} onChange={(e) => setNote(e.target.value)} />
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files[0])} />
          <div className="actions"><button className="btn">Sahkan pulang</button><button type="button" className="btn ghost" onClick={() => setOpen(false)}>Batal</button></div>
        </form>
      )}
    </div>
  );
}


/* ---------- Laman: pengumuman, kebajikan, teks halaman, maklum balas (admin) ---------- */
function Laman() {
  const [sec, setSec] = useState("pengumuman");
  const [titles, setTitles] = useState({});
  useEffect(() => { api.get("/laman/home").then((h) => setTitles(h.titles || {})).catch(() => {}); }, [sec]);
  return (
    <div>
      <div className="seg" style={{ marginBottom: ".6rem", flexWrap: "wrap" }}>
        {[["pengumuman", titles.pengumuman || "Pengumuman"], ["event", titles.event || "Event"], ["kebajikan", titles.kebajikan || "News"], ["teks", "Teks halaman"], ["rekaan", "Rekaan & nama"], ["maklum", "Maklum balas"]].map(([k, l]) => <button key={k} className={sec === k ? "on" : ""} onClick={() => setSec(k)}>{l}</button>)}
      </div>
      {["pengumuman", "event", "kebajikan"].includes(sec) && <Notices key={sec} kind={sec} label={titles[sec]} />}
      {sec === "rekaan" && <Rekaan />}
      {sec === "teks" && <Texts />}
      {sec === "maklum" && <Feedbacks />}
    </div>
  );
}

function Notices({ kind, label }) {
  const toast = useToast();
  const [rows, load] = useLoad(`/laman/notices?kind=${kind}&all=true`, [kind]);
  const [f, setF] = useState(null);
  const open = (n) => setF(n ? { ...n, on_date: n.date, file: null } : { title: "", body: "", link: "", on_date: "", active: true, file: null });
  const save = (e) => {
    e.preventDefault();
    const form = new FormData();
    form.append("kind", kind); form.append("title", f.title); form.append("body", f.body || ""); form.append("link", f.link || "");
    form.append("on_date", f.on_date || ""); form.append("active", f.active ? "true" : "false");
    if (f.remove_image) form.append("remove_image", "true");
    if (f.file) form.append("file", f.file);
    sendForm(f.id ? "PUT" : "POST", f.id ? `/laman/notices/${f.id}` : "/laman/notices", form)
      .then(() => { setF(null); load(); toast("Disimpan"); }).catch(fail);
  };
  return (
    <div>
      {!f && <button className="btn" onClick={() => open(null)}>+ {label || kind} baharu</button>}
      {f && (
        <form className="card" onSubmit={save}>
          <label className="small">Tajuk<input required maxLength={160} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
          <label className="small">Isi<textarea rows={5} value={f.body || ""} onChange={(e) => setF({ ...f, body: e.target.value })} /></label>
          <label className="small">Tarikh<input type="date" value={f.on_date || ""} onChange={(e) => setF({ ...f, on_date: e.target.value })} /></label>
          <label className="small">Pautan (pilihan)<input value={f.link || ""} onChange={(e) => setF({ ...f, link: e.target.value })} /></label>
          <label className="small">Gambar (pilihan, JPG/PNG)<input type="file" accept="image/*" onChange={(e) => setF({ ...f, file: e.target.files[0] })} /></label>
          {f.image && !f.file && <label className="check"><input type="checkbox" checked={!!f.remove_image} onChange={(e) => setF({ ...f, remove_image: e.target.checked })} /> Buang gambar sedia ada</label>}
          <label className="check"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Dipaparkan kepada ahli</label>
          <div className="actions"><button className="btn">Simpan</button><button type="button" className="btn ghost" onClick={() => setF(null)}>Batal</button></div>
        </form>
      )}
      {rows?.map((n) => (
        <div className="card row" key={n.id}>
          <span>{n.image && <img src={imgUrl(n.image)} alt="" style={{ width: 44, height: 44, objectFit: "cover", borderRadius: 8, marginRight: 8, verticalAlign: "middle" }} />}<b>{n.title}</b> {!n.active && <span className="badge bad">Disorok</span>}<br /><small className="muted">{fmtDate(n.date)}</small></span>
          <span className="seg"><button onClick={() => open(n)}>Ubah</button><button onClick={() => confirm("Padam?") && api.del(`/laman/notices/${n.id}`).then(load).catch(fail)}>Padam</button></span>
        </div>
      ))}
    </div>
  );
}

const PATS = [["batik", "Batik"], ["kawung", "Kawung"], ["sisik", "Sisik naga"], ["tumpal", "Tumpal"], ["luk", "Luk"], ["polos", "Polos"]];
const TITLE_KEYS = [["sistem", "Sistem & Aplikasi"], ["pengumuman", "Pengumuman"], ["event", "Event"], ["jadual", "Jadual Latihan"], ["kebajikan", "Bahagian bawah (asal: News)"]];

function SesiForm() {
  const toast = useToast();
  const [s, setS] = useState(null);
  const [code, setCode] = useState("");
  const load = () => api.get("/persatuan/session").then((x) => { setS(x); setCode(x.code); }).catch(fail);
  useEffect(() => { load(); }, []);
  if (!s) return null;
  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); api.put("/persatuan/session", { code }).then(() => { load(); toast("Sesi dikemas kini"); }).catch(fail); }}>
      <h3>Sesi semasa</h3>
      <p className="small muted">Sekarang: <b>{s.label}</b>. Bila intake baharu masuk, tukar kepada sesi baharu (cth 2728 = 2027/28). Laman depan, kehadiran dan sesi layak transport akan ikut.</p>
      <label className="small">Kod sesi (4 digit)<input required pattern="\d{4}" value={code} onChange={(e) => setCode(e.target.value)} /></label>
      <div className="actions"><button className="btn">Simpan sesi</button></div>
    </form>
  );
}

function Rekaan() {
  const toast = useToast();
  const [d, setD] = useState(null);
  const [titles, setTitles] = useState(null);
  const [bg, setBg] = useState(null);
  const [poster, setPoster] = useState(null);
  const [rmBg, setRmBg] = useState(false);
  const [rmPoster, setRmPoster] = useState(false);
  const load = () => api.get("/laman/home").then((h) => { setD(h.design); setTitles(h.titles); }).catch(fail);
  useEffect(() => { load(); }, []);
  if (!d || !titles) return <p className="muted">Memuatkan…</p>;
  const saveDesign = (e) => {
    e.preventDefault();
    const form = new FormData();
    form.append("mode", d.mode); form.append("pattern", d.pattern);
    form.append("remove_bg", rmBg ? "true" : "false"); form.append("remove_poster", rmPoster ? "true" : "false");
    if (bg) form.append("bg", bg);
    if (poster) form.append("poster", poster);
    sendForm("PUT", "/laman/design", form).then(() => { setBg(null); setPoster(null); setRmBg(false); setRmPoster(false); load(); toast("Disimpan"); }).catch(fail);
  };
  return (
    <div>
      <SesiForm />
      <form className="card" onSubmit={saveDesign}>
        <h3>Rekaan muka depan</h3>
        <div className="seg">
          <button type="button" className={d.mode === "corak" ? "on" : ""} onClick={() => setD({ ...d, mode: "corak" })}>Corak</button>
          <button type="button" className={d.mode === "gambar" ? "on" : ""} onClick={() => setD({ ...d, mode: "gambar" })}>Gambar</button>
        </div>
        {d.mode === "corak" && (
          <div className="seg" style={{ flexWrap: "wrap", marginTop: ".5rem" }}>
            {PATS.map(([k, l]) => <button type="button" key={k} className={d.pattern === k ? "on" : ""} onClick={() => setD({ ...d, pattern: k })}>{l}</button>)}
          </div>
        )}
        {d.mode === "gambar" && (
          <>
            <label className="small">Gambar latar (JPG/PNG)<input type="file" accept="image/*" onChange={(e) => setBg(e.target.files[0])} /></label>
            {d.bg && !bg && <label className="check"><input type="checkbox" checked={rmBg} onChange={(e) => setRmBg(e.target.checked)} /> Buang gambar sedia ada</label>}
          </>
        )}
        <label className="small">Gambar poster (pilihan, dipaparkan di bawah jadual)<input type="file" accept="image/*" onChange={(e) => setPoster(e.target.files[0])} /></label>
        {d.poster && !poster && <label className="check"><input type="checkbox" checked={rmPoster} onChange={(e) => setRmPoster(e.target.checked)} /> Buang poster sedia ada</label>}
        <div className="actions"><button className="btn">Simpan rekaan</button></div>
      </form>
      <form className="card" onSubmit={(e) => { e.preventDefault(); api.put("/laman/titles", { titles }).then(() => { load(); toast("Disimpan"); }).catch(fail); }}>
        <h3>Nama bahagian</h3>
        {TITLE_KEYS.map(([k, l]) => (
          <label className="small" key={k}>{l}<input maxLength={40} value={titles[k] || ""} onChange={(e) => setTitles({ ...titles, [k]: e.target.value })} /></label>
        ))}
        <div className="actions"><button className="btn">Simpan nama</button></div>
      </form>
    </div>
  );
}

function Texts() {
  const toast = useToast();
  const [key, setKey] = useState("panduan");
  const [body, setBody] = useState("");
  useEffect(() => { api.get(`/laman/page/${key}`).then((p) => setBody(p.body)).catch(fail); }, [key]);
  return (
    <div className="card">
      <div className="seg">{[["panduan", "Panduan"], ["hubungi", "Hubungi"], ["sokongan", "Sokongan"]].map(([k, l]) => <button key={k} className={key === k ? "on" : ""} onClick={() => setKey(k)}>{l}</button>)}</div>
      <textarea rows={10} maxLength={8000} value={body} onChange={(e) => setBody(e.target.value)} />
      <button className="btn" onClick={() => api.put(`/laman/page/${key}`, { body }).then(() => toast("Disimpan")).catch(fail)}>Simpan</button>
    </div>
  );
}

function Feedbacks() {
  const [rows, load] = useLoad("/laman/feedback");
  if (!rows) return <p className="muted">Memuatkan…</p>;
  return (
    <div>
      {rows.length === 0 && <p className="muted">Tiada maklum balas.</p>}
      {rows.map((f) => (
        <div className="card" key={f.id} style={f.read ? { opacity: .65 } : null}>
          <b>{f.name}</b> <span className="small muted">{f.member_no} · {fmtDate(f.at.slice(0, 10))}</span>
          <p style={{ whiteSpace: "pre-wrap" }}>{f.message}</p>
          <button className="link" onClick={() => api.put(`/laman/feedback/${f.id}?read=${!f.read}`).then(load).catch(fail)}>{f.read ? "Tandakan belum dibaca" : "Tandakan dibaca"}</button>
        </div>
      ))}
    </div>
  );
}
