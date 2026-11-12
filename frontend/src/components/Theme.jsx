import { useState } from "react";
import { api, auth } from "../api.js";

const KEY = "pssgutm_theme";

export function getTheme() {
  try { return localStorage.getItem(KEY) || "auto"; } catch { return "auto"; }
}

// auto = ikut tetapan telefon; light/dark = pilihan manual
export function applyTheme(t) {
  const r = document.documentElement;
  if (t === "light" || t === "dark") r.setAttribute("data-theme", t); else r.removeAttribute("data-theme");
}

export function setTheme(t) {
  try { if (t === "auto") localStorage.removeItem(KEY); else localStorage.setItem(KEY, t); } catch { /* abaikan */ }
  applyTheme(t);
}

// Pilihan disimpan pada AKAUN (ikut ke peranti lain); salinan setempat hanya supaya paparan betul sebelum log masuk.
export function syncTheme(t) {
  if (t !== "light" && t !== "dark" && t !== "auto") return;
  setTheme(t);
}

export function ThemeSwitch() {
  const [t, setT] = useState(auth.get()?.user?.theme || getTheme());
  const pick = (v) => {
    setTheme(v); setT(v);
    const s = auth.get();
    if (s) auth.set({ ...s, user: { ...s.user, theme: v } });
    api.put("/profile/theme", { theme: v }).catch(() => {});
  };
  return (
    <div>
      <div className="seg" role="group" aria-label="Paparan">
        {[["auto", "Ikut telefon"], ["light", "☀️ Cerah"], ["dark", "🌙 Gelap"]].map(([k, l]) => (
          <button type="button" key={k} className={t === k ? "on" : ""} onClick={() => pick(k)}>{l}</button>
        ))}
      </div>
    </div>
  );
}
