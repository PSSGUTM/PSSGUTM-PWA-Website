import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtDate } from "../api.js";

// Halaman yang dibuka apabila ahli mengimbas QR kehadiran
export default function Hadir() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [state, setState] = useState("");   // "" | ok | already
  const [err, setErr] = useState("");
  useEffect(() => { api.get(`/persatuan/hadir/${token}`).then(setInfo).catch((e) => setErr(e.message)); }, [token]);
  const mark = () => api.post(`/persatuan/hadir/${token}`).then((r) => setState(r.already ? "already" : "ok")).catch((e) => setErr(e.message));
  return (
    <div className="card" style={{ textAlign: "center" }}>
      <h2>Kehadiran</h2>
      {info && <p><b>{info.title}</b><br /><span className="muted small">{fmtDate(info.date)}</span></p>}
      {err && <p className="error">{err}</p>}
      {state === "ok" && <p><b>✅ Kehadiran anda direkodkan.</b></p>}
      {state === "already" && <p><b>Anda sudah direkodkan.</b></p>}
      {info && !state && !err && (info.open
        ? <button className="btn wide" onClick={mark}>Saya hadir</button>
        : <p className="error">Kehadiran ini sudah ditutup.</p>)}
      <p><Link to="/">Kembali</Link></p>
    </div>
  );
}
