const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const KEY = "pssgutm_auth";

export const auth = {
  get() {
    try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
  },
  set(data) { localStorage.setItem(KEY, JSON.stringify(data)); },
  clear() { localStorage.removeItem(KEY); },
};

async function request(path, { method = "GET", body, form } = {}) {
  const a = auth.get();
  const headers = {};
  if (a?.token) headers.Authorization = `Bearer ${a.token}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(BASE + path, {
    method, headers, body: form ?? (body ? JSON.stringify(body) : undefined),
  });
  if (res.status === 401 && a) {
    auth.clear();
    window.location.href = "/login";
    throw new Error("Sila login semula");
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) {
    const d = data?.detail;
    const msg = Array.isArray(d) ? d.map((x) => x.msg).join(", ") : d;
    throw new Error(msg || `Ralat ${res.status}`);
  }
  return data;
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: "POST", body }),
  put: (p, body) => request(p, { method: "PUT", body }),
  del: (p) => request(p, { method: "DELETE" }),
  upload: (p, file, fields = {}) => {
    const form = new FormData();
    Object.entries(fields).forEach(([k, v]) => form.append(k, v));
    form.append("file", file);
    return request(p, { method: "POST", form });
  },
  // Ambil fail bertoken sebagai blob URL (QR bayaran)
  async blobUrl(path) {
    const a = auth.get();
    const res = await fetch(BASE + path, { headers: { Authorization: `Bearer ${a.token}` } });
    if (!res.ok) throw new Error("Gagal memuatkan fail");
    return URL.createObjectURL(await res.blob());
  },
  publicGet: async (p) => {
    const res = await fetch(BASE + p);
    if (!res.ok) throw new Error(`Ralat ${res.status}`);
    return res.json();
  },
  // Buka resit (perlukan token, jadi ambil sebagai blob)
  async openReceipt(id) {
    const a = auth.get();
    const res = await fetch(`${BASE}/admin/payments/${id}/receipt`, {
      headers: { Authorization: `Bearer ${a.token}` },
    });
    if (!res.ok) throw new Error("Resit tak dapat dibuka");
    window.open(URL.createObjectURL(await res.blob()), "_blank");
  },
};

const HARI = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu"];
const BULAN = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogo", "Sep", "Okt", "Nov", "Dis"];
export function fmtDate(iso) {
  const d = new Date(iso + "T00:00:00");
  const p = (n) => String(n).padStart(2, "0");
  return `${HARI[d.getDay()]} ${p(d.getDate())}/${p(d.getMonth() + 1)}`;   // contoh: Sabtu 14/10
}
export function fmtTime(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
}
