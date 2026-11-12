import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

let loading;
function loadGsi() {
  if (window.google?.accounts?.id) return Promise.resolve();
  loading ??= new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = res;
    s.onerror = () => { loading = null; rej(new Error("gsi")); };
    document.head.appendChild(s);
  });
  return loading;
}

const CID_KEY = "gsi_client_id";
const readCid = () => { try { return localStorage.getItem(CID_KEY); } catch { return null; } };
const saveCid = (v) => { try { localStorage.setItem(CID_KEY, v); } catch { /* abaikan */ } };

// Butang rasmi "Log masuk dengan Google". Client ID disimpan dalam peranti supaya butang cepat muncul walaupun
// server (Render percuma) sedang bangun. Disembunyikan jika server belum ada GOOGLE_CLIENT_ID.
export default function GoogleButton({ onCredential, text = "signin_with" }) {
  const ref = useRef(null);
  const cb = useRef(onCredential);
  cb.current = onCredential;
  const cached = readCid();
  const [phase, setPhase] = useState(cached === "" ? "off" : "loading");   // loading | ready | off

  useEffect(() => {
    let dead = false;
    const draw = async (client_id) => {
      await loadGsi();
      if (dead || !ref.current) return;
      window.google.accounts.id.initialize({ client_id, callback: (r) => cb.current(r.credential) });
      window.google.accounts.id.renderButton(ref.current, {
        theme: "outline", size: "large", shape: "pill", text, width: Math.min(320, ref.current.parentElement.clientWidth || 320), locale: "ms",
      });
      setPhase("ready");
    };
    if (cached) draw(cached).catch(() => !dead && setPhase("off"));
    api.publicGet("/auth/google/info").then(async ({ client_id }) => {
      if (dead) return;
      saveCid(client_id || "");
      if (!client_id) return setPhase("off");
      if (client_id !== cached) await draw(client_id);
    }).catch(() => { if (!dead && !cached) setPhase("off"); });
    return () => { dead = true; };
  }, []);

  if (phase === "off") return null;
  return (
    <div style={{ textAlign: "center", margin: ".4rem 0" }}>
      {phase === "loading" && <div className="gbtn-ph" role="status">⏳ Memuatkan Google…</div>}
      <div ref={ref} style={{ display: phase === "ready" ? "inline-block" : "none" }} />
      <p className="muted small" style={{ margin: ".4rem 0 0" }}>atau guna emel dan kata laluan di bawah</p>
    </div>
  );
}
