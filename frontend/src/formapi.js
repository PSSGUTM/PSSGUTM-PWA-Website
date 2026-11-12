import { auth } from "./api.js";

export const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Hantar borang multipart (fail pilihan) dengan token log masuk
export async function sendForm(method, path, form) {
  const a = auth.get();
  const res = await fetch(BASE + path, { method, headers: { Authorization: `Bearer ${a.token}` }, body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Gagal");
  return data;
}

export const imgUrl = (name) => (name ? `${BASE}/laman/img/${name}` : "");
