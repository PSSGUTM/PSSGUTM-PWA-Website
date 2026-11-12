import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { useColleges } from "../colleges.js";
import { BrandMark } from "../components/Emblem.jsx";
import GoogleButton from "../components/GoogleButton.jsx";
import Contact from "../components/Contact.jsx";
import PasswordInput from "../components/PasswordInput.jsx";

const PHONE_RE = /^(\+?60|0)1\d{8,9}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

// Medan dengan contoh format dan ralat segera (selepas pengguna tinggalkan medan)
function Field({ error, hint, children }) {
  return (
    <div className={`fld ${error ? "bad" : ""}`}>
      {children}
      {error ? <p className="fld-msg err">⚠️ {error}</p> : hint ? <p className="fld-msg">{hint}</p> : null}
    </div>
  );
}

export default function Auth({ onAuth, brand, initialMode = "login" }) {
  const [params] = useSearchParams();
  const [mode, setMode] = useState(initialMode);
  const { colleges, error: collegeErr } = useColleges();
  const [f, setF] = useState({
    name: "", short_name: "", block: "", point: "", member_no: "", phone: "", email: "", identifier: "", password: "", password2: "", gender: "",
    college: "", college_other: "", is_driver: params.get("driver") === "1", agree: false, privacy: false,
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState({});
  const [g, setG] = useState(null);   // Google: { credential, email } semasa melengkapkan pendaftaran kali pertama
  const [fmt, setFmt] = useState({ member_no_pattern: "^SG\\d{7}$", member_no_example: "SG2627001" });
  useEffect(() => { api.publicGet("/auth/formats").then(setFmt).catch(() => {}); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const blur = (k) => () => setTouched((t) => ({ ...t, [k]: true }));

  let memberRe;
  try { memberRe = new RegExp(fmt.member_no_pattern); } catch { memberRe = /^SG\d{7}$/; }
  const phoneClean = f.phone.replace(/[\s-]/g, "");
  const errors = {};
  if (mode === "register") {
    if (f.name.trim().length < 2) errors.name = "Tulis nama penuh anda";
    if (f.short_name.trim().length < 2) errors.short_name = "Tulis nama pendek (cth Amir). Ini yang dilihat ahli & prebet lain";
    if (!f.is_driver && f.college && f.college !== "__other" && f.block.trim().length < 1) errors.block = "Tulis blok anda (cth B-12)";
    if (!memberRe.test(f.member_no.trim().toUpperCase())) errors.member_no = `Format tak betul. Contoh: ${fmt.member_no_example} (huruf SG + 7 digit)`;
    if (!PHONE_RE.test(phoneClean)) errors.phone = "Format tak betul. Contoh: 0123456789 atau +60123456789";
    if (!g && !EMAIL_RE.test(f.email.trim())) errors.email = "Format emel tak betul. Contoh: nama@gmail.com";
    if (!g && f.password.length < 8) errors.password = "Kata laluan mesti sekurang-kurangnya 8 aksara";
    if (!g && f.password2 !== f.password) errors.password2 = "Kata laluan tak sama";
  } else if (!f.identifier.trim()) errors.identifier = "Tulis no. ahli atau emel anda";
  const col = colleges.find((c) => c.code === f.college);
  const pts = (col?.points || []).filter((p) => !f.gender || p.gender === "any" || p.gender === f.gender);
  const needPoint = !f.is_driver && f.college !== "__other" && pts.length > 1;
  if (mode === "register" && needPoint && !f.point) errors.point = "Pilih checkpoint (bus stop) anda";
  const show = (k) => (touched[k] || touched.__submit) && errors[k];

  async function google(credential) {
    setErr(""); setBusy(true);
    try {
      const r = await api.post("/auth/google", { credential });
      if (r.needs_registration) {
        setG({ credential, email: r.email });
        setMode("register");
        setF((x) => ({ ...x, name: x.name || r.name || "", email: r.email }));
      } else onAuth(r);
    } catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setTouched((t) => ({ ...t, __submit: true }));
    if (Object.keys(errors).length) return setErr("Sila betulkan medan yang ditanda merah.");
    if (mode === "register") {
      if (!f.privacy) return setErr("Sila setuju maklumat anda disimpan oleh BKK");
      if (!f.is_driver && !f.agree) return setErr("Sila setuju dengan syarat kemudahan");
      if (f.college === "__other" && !f.college_other.trim()) return setErr("Sila tulis nama kolej / tempat tinggal anda");
    }
    setBusy(true);
    try {
      const data = g && mode === "register"
        ? await api.post("/auth/google", {
            credential: g.credential, name: f.name, member_no: f.member_no, phone: phoneClean, gender: f.gender || null,
            college_code: f.college && f.college !== "__other" ? f.college : null,
            college_other: f.college === "__other" ? f.college_other.trim() : null, is_driver: f.is_driver,
            short_name: f.short_name.trim(), block: f.block.trim(), pickup_point_id: f.point ? Number(f.point) : null,
          })
        : mode === "login"
        ? await api.post("/auth/login", { identifier: f.identifier, password: f.password })
        : await api.post("/auth/register", {
            name: f.name, member_no: f.member_no, phone: phoneClean, email: f.email.trim(), password: f.password,
            gender: f.gender || null,
            college_code: f.college && f.college !== "__other" ? f.college : null,
            college_other: f.college === "__other" ? f.college_other.trim() : null,
            is_driver: f.is_driver, short_name: f.short_name.trim(), block: f.block.trim(),
            pickup_point_id: f.point ? Number(f.point) : null,
          });
      onAuth(data);
    } catch (e2) {
      setErr(e2.message === "Failed to fetch" ? "Tidak dapat sambung ke server. Pastikan backend sedang berjalan." : e2.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="auth-page">
      <div className="auth-hero">
        <Link to="/" className="back">← Laman utama</Link>
        <BrandMark brand={brand} size={84} />
        <h1>{brand?.brand_name || "PSSGUTM Transport"}</h1>
        <p>{mode === "login" ? "Selamat kembali ke gelanggang." : "Daftar sekali, urusan pengangkutan kami uruskan."}</p>
      </div>
      <div className="motif-strip" />

      <form onSubmit={submit} className="card auth-card" noValidate>
        {!g && <GoogleButton onCredential={google} text={mode === "login" ? "signin_with" : "signup_with"} />}
        {g && <p className="okmsg small">✅ Emel Google disahkan: <b>{g.email}</b>. Lengkapkan maklumat ahli di bawah (tiada kata laluan diperlukan).</p>}
        {mode === "register" ? (
          <>
            <label className="check">
              <input type="checkbox" checked={f.is_driver} onChange={set("is_driver")} />
              Saya prebet (ada kereta / motosikal, nak tolong hantar)
            </label>
            <Field error={show("name")}>
              <input placeholder="Nama penuh" value={f.name} onChange={set("name")} onBlur={blur("name")} autoComplete="name" />
            </Field>
            <Field error={show("short_name")} hint="Nama pendek / panggilan. Ahli & prebet lain hanya nampak nama ini (admin nampak kedua-duanya).">
              <input placeholder="Nama pendek (cth Amir)" maxLength={40} value={f.short_name} onChange={set("short_name")} onBlur={blur("short_name")} />
            </Field>
            <Field error={show("member_no")} hint={`No. ahli, contoh: ${fmt.member_no_example}`}>
              <input placeholder={`No. ahli (cth ${fmt.member_no_example})`} value={f.member_no} onChange={set("member_no")} onBlur={blur("member_no")} autoCapitalize="characters" />
            </Field>
            <p className="muted small">Hanya ahli PSSGUTM yang sah (ada dalam senarai persatuan) boleh mendaftar. Jantina & kolej diisi automatik jika ada dalam senarai.</p>
            <select value={f.gender} onChange={set("gender")}>
              <option value="">Jantina</option><option value="male">Lelaki</option><option value="female">Perempuan</option>
            </select>
            <p className="small muted" style={{ margin: ".2rem 0 0" }}>Pilih jantina anda dengan betul (menentukan susunan tempat duduk). Jika tersilap kemudian, tukar perlu kelulusan BKK.</p>
            <select value={f.college} onChange={set("college")}>
              <option value="">Pilih kolej</option>
              {colleges.map((c) => {
                const off = !f.is_driver && c.transport_available === false;
                const noPt = !f.is_driver && c.points && c.points.length === 0;
                return <option key={c.code} value={c.code} disabled={off}>{c.code} · {c.name}{off ? " (tiada perkhidmatan)" : noPt ? " (belum ada bus stop)" : ""}</option>;
              })}
              <option value="__other">Lain-lain (tulis sendiri)</option>
            </select>
            {f.college === "__other" && (
              <input placeholder="Nama kolej / tempat tinggal" maxLength={60} value={f.college_other} onChange={set("college_other")} />
            )}
            {f.college && f.college !== "__other" && !f.is_driver && (
              <>
                {col && col.points && col.points.length === 0 && <p className="small muted">Bus stop {f.college} belum ditetapkan BKK. Anda boleh daftar; tempahan dibuka selepas bus stop ditambah.</p>}
                {needPoint && (
                  <Field error={show("point")}>
                    <select value={f.point} onChange={set("point")} onBlur={blur("point")}>
                      <option value="">Pilih checkpoint (bus stop) anda</option>
                      {pts.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </Field>
                )}
                {!needPoint && pts.length === 1 && <p className="small muted">📍 Checkpoint: {pts[0].name}</p>}
                <Field error={show("block")} hint="Supaya prebet senang cari anda">
                  <input placeholder="Blok / bilik (cth B-12-3)" maxLength={40} value={f.block} onChange={set("block")} onBlur={blur("block")} />
                </Field>
              </>
            )}
            {collegeErr && <p className="small error">Senarai kolej dari server tak dapat dimuat (guna senarai asal). Pastikan backend berjalan.</p>}
            <Field error={show("phone")} hint="Contoh: 0123456789">
              <input placeholder="No. telefon (cth 0123456789)" type="tel" inputMode="tel" value={f.phone} onChange={set("phone")} onBlur={blur("phone")} autoComplete="tel" />
            </Field>
            <Field error={show("email")} hint={g ? "" : "Contoh: nama@gmail.com"}>
              <input placeholder="Emel (cth nama@gmail.com)" type="email" value={f.email} onChange={set("email")} onBlur={blur("email")} disabled={!!g} autoComplete="email" />
            </Field>
          </>
        ) : (
          <Field error={show("identifier")}>
            <input placeholder="No. ahli atau emel" value={f.identifier} onChange={set("identifier")} onBlur={blur("identifier")} autoComplete="username" />
          </Field>
        )}
        {!g && (
          <Field error={show("password")} hint={mode === "register" ? "Sekurang-kurangnya 8 aksara" : ""}>
            <PasswordInput placeholder={mode === "register" ? "Kata laluan (min 8 aksara)" : "Kata laluan"} value={f.password} onChange={set("password")} onBlur={blur("password")}
                           autoComplete={mode === "register" ? "new-password" : "current-password"} />
          </Field>
        )}
        {mode === "register" && !g && (
          <Field error={show("password2")}>
            <PasswordInput placeholder="Sahkan kata laluan" value={f.password2} onChange={set("password2")} onBlur={blur("password2")} autoComplete="new-password" />
          </Field>
        )}
        {mode === "register" && (
          <label className="check small">
            <input type="checkbox" checked={f.privacy} onChange={set("privacy")} />
            <span>Saya setuju maklumat saya (nama, no. ahli, telefon, emel, kolej, blok; prebet: kenderaan, lesen &amp; akaun bank) disimpan oleh BKK PSSGUTM untuk urusan pengangkutan latihan sahaja, dan tidak dikongsi dengan pihak luar.</span>
          </label>
        )}
        {mode === "register" && !f.is_driver && (
          <label className="check small">
            <input type="checkbox" checked={f.agree} onChange={set("agree")} />
            <span>Saya ahli sah PSSGUTM, tiada pengangkutan sendiri, dan setuju: bayar kepada persatuan melalui website (tiada tunai), tiada pemulangan wang, dan naik kenderaan yang sama pergi & balik.</span>
          </label>
        )}
        {mode === "login" && <p className="small" style={{ textAlign: "right", margin: 0 }}><Link to="/lupa">Lupa kata laluan?</Link></p>}
        {err && <p className="error">{err}</p>}
        <button className="btn wide" disabled={busy}>{busy ? "Sekejap..." : mode === "login" ? "Login" : "Daftar"}</button>
      </form>
      <p className="auth-switch">
        <button className="link" onClick={() => { setErr(""); setG(null); setTouched({}); setMode(mode === "login" ? "register" : "login"); }}>
          {mode === "login" ? "Belum daftar? Daftar di sini" : "Dah ada akaun? Login"}
        </button>
      </p>
      <div className="auth-card" style={{ textAlign: "center" }}><Contact /></div>
    </div>
  );
}
