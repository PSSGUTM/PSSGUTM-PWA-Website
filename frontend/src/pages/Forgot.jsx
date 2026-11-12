import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { BrandMark } from "../components/Emblem.jsx";

export default function Forgot({ brand }) {
  const [id, setId] = useState("");
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault(); setErr(""); setBusy(true);
    try { setRes(await api.post("/auth/forgot", { identifier: id })); }
    catch (e2) { setErr(e2.message); }
    finally { setBusy(false); }
  }
  return (
    <div className="auth-page">
      <div className="auth-hero">
        <Link to="/login" className="back">← Login</Link>
        <BrandMark brand={brand} size={72} />
        <h1>Lupa kata laluan</h1>
        <p>Kami bantu pulihkan akses anda.</p>
      </div>
      <div className="motif-strip" />
      {res ? (
        <div className="card auth-card">
          {res.mode === "email"
            ? <p>Jika akaun wujud, pautan tetapan semula telah dihantar ke email anda. Semak juga folder spam. Pautan sah untuk masa terhad.</p>
            : <p>{res.note || "Permintaan anda telah dihantar kepada admin BKK. Mereka akan beri kata laluan sementara; sila hubungi admin jika perlu cepat."}</p>}
          <Link className="btn wide" to="/login">Kembali ke login</Link>
        </div>
      ) : (
        <form className="card auth-card" onSubmit={submit}>
          <input placeholder="No. ahli atau email" value={id} onChange={(e) => setId(e.target.value)} required />
          {err && <p className="error">{err}</p>}
          <button className="btn wide" disabled={busy}>{busy ? "Sekejap..." : "Hantar"}</button>
        </form>
      )}
    </div>
  );
}
