import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { BrandMark } from "../components/Emblem.jsx";
import PasswordInput from "../components/PasswordInput.jsx";

export default function Reset({ brand }) {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const nav = useNavigate();
  async function submit(e) {
    e.preventDefault(); setErr("");
    if (pw !== pw2) return setErr("Kata laluan tidak sama");
    try { await api.post("/auth/reset", { token, new_password: pw }); setDone(true); setTimeout(() => nav("/login"), 1800); }
    catch (e2) { setErr(e2.message); }
  }
  return (
    <div className="auth-page">
      <div className="auth-hero">
        <BrandMark brand={brand} size={72} />
        <h1>Kata laluan baru</h1>
      </div>
      <div className="motif-strip" />
      <form className="card auth-card" onSubmit={submit}>
        {!token && <p className="error">Pautan tidak sah. <Link to="/lupa">Minta pautan baru</Link></p>}
        {done ? <p className="okmsg">Berjaya ✅ Mengalihkan ke login...</p> : (
          <>
            <PasswordInput placeholder="Kata laluan baru (min 8)" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" minLength={8} required />
            <PasswordInput placeholder="Sahkan kata laluan baru" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" minLength={8} required />
            {err && <p className="error">{err}</p>}
            <button className="btn wide" disabled={!token}>Simpan</button>
          </>
        )}
      </form>
    </div>
  );
}
