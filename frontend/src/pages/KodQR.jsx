import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import jsQR from "jsqr";

// Ambil token kehadiran daripada pautan penuh (…/hadir/<token>) atau token sahaja
function tokenOf(text) {
  const m = String(text || "").match(/\/hadir\/([A-Za-z0-9_-]{6,})/);
  if (m) return m[1];
  return /^[A-Za-z0-9_-]{8,40}$/.test(String(text || "").trim()) ? text.trim() : null;
}

export default function KodQR() {
  const navigate = useNavigate();
  const video = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
  const [err, setErr] = useState("");
  const [code, setCode] = useState("");
  const [scanning, setScanning] = useState(false);

  // Semak sokongan getUserMedia (kamera pelayar)
  const hasCamera = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  useEffect(() => {
    if (!scanning) return undefined;
    let stop = false;
    let stream = null;

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });

        if (stop) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        if (video.current) {
          video.current.srcObject = stream;
          video.current.setAttribute("playsinline", "true");
          video.current.setAttribute("webkit-playsinline", "true");
          await video.current.play();
        }

        // Semak sama ada BarcodeDetector disokong natif (Android/Chrome)
        let nativeDetector = null;
        if (typeof window !== "undefined" && "BarcodeDetector" in window) {
          try {
            nativeDetector = new window.BarcodeDetector({ formats: ["qr_code"] });
          } catch {
            nativeDetector = null;
          }
        }

        let lastCheck = 0;
        const tick = async (now) => {
          if (stop || !video.current) return;

          // Periksa setiap 200ms untuk menjimatkan bateri & CPU peranti
          if (now - lastCheck > 200) {
            lastCheck = now;
            const vid = video.current;
            if (vid.readyState >= vid.HAVE_CURRENT_DATA && vid.videoWidth > 0 && vid.videoHeight > 0) {
              let foundRaw = null;

              // 1. Cuba BarcodeDetector natif
              if (nativeDetector) {
                try {
                  const detected = await nativeDetector.detect(vid);
                  if (detected?.length > 0 && detected[0].rawValue) {
                    foundRaw = detected[0].rawValue;
                  }
                } catch {
                  /* fallback ke jsQR */
                }
              }

              // 2. Fallback ke jsQR (100% serasi iPhone / iOS Safari)
              if (!foundRaw) {
                try {
                  let canvas = canvasRef.current;
                  if (!canvas) {
                    canvas = document.createElement("canvas");
                    canvasRef.current = canvas;
                  }
                  canvas.width = vid.videoWidth;
                  canvas.height = vid.videoHeight;
                  const ctx = canvas.getContext("2d", { willReadFrequently: true });
                  ctx.drawImage(vid, 0, 0, canvas.width, canvas.height);
                  const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                  const result = jsQR(imgData.data, imgData.width, imgData.height, {
                    inversionAttempts: "dontInvert",
                  });
                  if (result && result.data) {
                    foundRaw = result.data;
                  }
                } catch {
                  /* abaikan ralat frame */
                }
              }

              if (foundRaw) {
                const t = tokenOf(foundRaw);
                if (t) {
                  navigate(`/hadir/${t}`);
                  return;
                }
              }
            }
          }

          if (!stop) {
            requestAnimationFrame(tick);
          }
        };

        requestAnimationFrame(tick);
      } catch {
        setErr("Kamera tak dapat dibuka. Pastikan izin kamera dibenarkan di tetapan telefon, atau masukkan kod/gambar di bawah.");
        setScanning(false);
      }
    })();

    return () => {
      stop = true;
      if (stream) stream.getTracks().forEach((t) => t.stop());
    };
  }, [scanning]);

  // Imbas daripada fail gambar / tangkap gambar kamera (sangat berguna untuk iPhone)
  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setErr("");
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0);
        const imgData = ctx.getImageData(0, 0, img.width, img.height);
        const qr = jsQR(imgData.data, imgData.width, imgData.height);
        if (qr && qr.data) {
          const t = tokenOf(qr.data);
          if (t) {
            navigate(`/hadir/${t}`);
            return;
          }
        }
        setErr("Kod QR tidak dijumpai dalam gambar ini. Pastikan gambar QR jelas dan cuba lagi.");
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  };

  const submit = (e) => {
    e.preventDefault();
    const t = tokenOf(code);
    if (!t) return setErr("Kod atau pautan tak sah.");
    navigate(`/hadir/${t}`);
  };

  return (
    <div>
      <div className="card" style={{ textAlign: "center", padding: "1.2rem" }}>
        <h3 style={{ margin: "0 0 .4rem" }}>📷 Imbas Kehadiran</h3>
        <p className="small muted" style={{ margin: "0 0 1rem" }}>
          Imbas kod QR yang dipaparkan oleh pengambil kehadiran (BLG, MT atau biro).
        </p>

        {scanning && (
          <div style={{ position: "relative", marginBottom: ".8rem" }}>
            <video
              ref={video}
              playsInline
              webkit-playsinline="true"
              autoPlay
              muted
              className="fr-video"
            />
            <p className="small" style={{ color: "var(--accent)", fontWeight: 600 }}>
              Sedang mengimbas… halakan kamera ke kod QR
            </p>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
          {hasCamera && (
            <button
              type="button"
              className="btn wide"
              onClick={() => {
                setErr("");
                setScanning((s) => !s);
              }}
            >
              {scanning ? "⏹️ Hentikan Kamera" : "📷 Buka Kamera & Imbas"}
            </button>
          )}

          {/* Pilihan alternatif imbas dari tangkap gambar kamera (100% sokong iPhone) */}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            ref={fileInputRef}
            onChange={onFileChange}
            style={{ display: "none" }}
          />
          <button
            type="button"
            className="btn ghost wide"
            onClick={() => fileInputRef.current?.click()}
          >
            📸 Tangkap / Pilih Gambar QR
          </button>
        </div>

        <div style={{ background: "rgba(212, 169, 78, 0.1)", borderRadius: 10, padding: ".75rem .9rem", marginTop: "1rem", textAlign: "left", fontSize: ".82rem", lineHeight: 1.45 }}>
          <b>💡 Petua untuk pengguna iPhone:</b>
          <ul style={{ margin: ".3rem 0 0", paddingLeft: "1.1rem" }}>
            <li>Boleh guna butang <b>Buka Kamera</b> di atas (kini disokong pada Safari &amp; Chrome iOS).</li>
            <li>Atau buka <b>Kamera asal iPhone</b>, halakan ke kod QR, dan tekan pautan kuning yang muncul di skrin untuk terus hadir.</li>
          </ul>
        </div>
      </div>

      <form className="card" onSubmit={submit} style={{ padding: "1.2rem" }}>
        <label className="small" style={{ fontWeight: 600 }}>
          Atau masukkan kod / pautan kehadiran secara manual:
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Contoh: https://pssgutm-app.onrender.com/hadir/abc123xy"
            style={{ marginTop: ".4rem" }}
          />
        </label>
        <button className="btn ghost wide" type="submit" style={{ marginTop: ".6rem" }}>
          Hadir Menggunakan Kod
        </button>
      </form>

      {err && <p className="error" style={{ textAlign: "center", marginTop: ".5rem" }}>⚠️ {err}</p>}
    </div>
  );
}
