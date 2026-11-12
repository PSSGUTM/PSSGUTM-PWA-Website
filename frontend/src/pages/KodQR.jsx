import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

// Ambil token kehadiran daripada pautan penuh (…/hadir/<token>) atau token sahaja
function tokenOf(text) {
  const m = String(text || "").match(/\/hadir\/([A-Za-z0-9_-]{6,})/);
  if (m) return m[1];
  return /^[A-Za-z0-9_-]{8,40}$/.test(String(text || "").trim()) ? text.trim() : null;
}

export default function KodQR() {
  const navigate = useNavigate();
  const video = useRef(null);
  const [err, setErr] = useState("");
  const [code, setCode] = useState("");
  const [scanning, setScanning] = useState(false);
  const supported = typeof window !== "undefined" && "BarcodeDetector" in window && navigator.mediaDevices?.getUserMedia;

  useEffect(() => {
    if (!scanning) return undefined;
    let stop = false, stream;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        video.current.srcObject = stream;
        await video.current.play();
        const det = new window.BarcodeDetector({ formats: ["qr_code"] });
        const tick = async () => {
          if (stop) return;
          try {
            const r = await det.detect(video.current);
            const t = r[0] && tokenOf(r[0].rawValue);
            if (t) { navigate(`/hadir/${t}`); return; }
          } catch { /* cuba lagi */ }
          setTimeout(tick, 300);
        };
        tick();
      } catch { setErr("Kamera tak dapat dibuka. Benarkan akses kamera atau masukkan kod di bawah."); setScanning(false); }
    })();
    return () => { stop = true; stream?.getTracks().forEach((t) => t.stop()); };
  }, [scanning]);

  const submit = (e) => {
    e.preventDefault();
    const t = tokenOf(code);
    if (!t) return setErr("Kod atau pautan tak sah.");
    navigate(`/hadir/${t}`);
  };
  return (
    <div>
      <div className="card" style={{ textAlign: "center" }}>
        <p className="small muted">Imbas kod QR yang dipaparkan oleh pengambil kehadiran (BLG, MT atau biro).</p>
        {scanning ? <video ref={video} playsInline muted className="fr-video" /> : null}
        {supported ? (
          <button className="btn wide" onClick={() => { setErr(""); setScanning((s) => !s); }}>{scanning ? "Henti kamera" : "Buka kamera dan imbas"}</button>
        ) : <p className="small muted">Pelayar ini tak menyokong imbasan dalam app. Imbas dengan kamera telefon biasa (ia membuka pautan), atau masukkan kod di bawah.</p>}
      </div>
      <form className="card" onSubmit={submit}>
        <label className="small">Masukkan kod atau tampal pautan kehadiran
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="cth https://…/hadir/abc123…" /></label>
        <button className="btn ghost wide">Teruskan</button>
      </form>
      {err && <p className="error">{err}</p>}
    </div>
  );
}
