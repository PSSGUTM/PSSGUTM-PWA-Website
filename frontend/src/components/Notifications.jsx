import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
  if (isNaN(d)) return "";
  return d.toLocaleString("ms-MY", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kuala_Lumpur" });
}

function fmtDate(d) {
  if (!d) return "";
  const x = new Date(d + "T00:00:00");
  return x.toLocaleDateString("ms-MY", { weekday: "long", day: "numeric", month: "short" });
}

const SEV = { warning: ["⚠️", "Amaran"], task: ["📌", "Tugasan"], info: ["🔔", "Maklumat"] };

export function useNotes() {
  const [notes, setNotes] = useState(null);
  const load = () => api.get("/notifications").then(setNotes).catch(() => setNotes([]));
  useEffect(() => { load(); }, []);
  return [notes, setNotes, load];
}

// Senarai notifikasi: tekan = ke tugasan berkaitan; butang × padam (kecuali amaran).
export default function Notifications({ limit, notes, setNotes, warningsOnly = false }) {
  const nav = useNavigate();
  const [err, setErr] = useState("");
  if (!notes) return null;
  const pool = warningsOnly ? notes.filter((n) => n.severity === "warning") : notes;
  const list = limit ? pool.slice(0, limit) : pool;
  if (!list.length) return limit ? null : <p className="muted">Tiada notifikasi.</p>;

  async function open(n) {
    if (!n.read && n.id) api.post(`/notifications/${n.id}/read`).catch(() => {});
    setNotes(notes.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
    if (n.link) nav(n.link);
  }
  async function remove(e, n) {
    e.stopPropagation();
    try { await api.del(`/notifications/${n.id}`); setNotes(notes.filter((x) => x.id !== n.id)); }
    catch (e2) { setErr(e2.message); }
  }
  return (
    <>
      {list.map((n) => {
        const [icon, label] = SEV[n.severity] || SEV.info;
        return (
          <div key={n.id} className={`noti ${n.severity} ${n.read ? "read" : ""}`} onClick={() => open(n)} role={n.link ? "button" : undefined}>
            <span className="noti-ico">{icon}</span>
            <div className="noti-body">
              <b>{n.title}</b>
              {n.body && <div className="small">{n.body}</div>}
              <div className="noti-date">{when(n.created_at)}</div>
              <div className="small muted">{label}{n.link ? " · tekan untuk buka" : ""}{!n.deletable ? ` · hilang bila selesai, atau boleh dipadam ${fmtDate(n.unlock_date)}` : ""}</div>
            </div>
            {n.deletable
              ? <button type="button" className="noti-x" aria-label="Padam notifikasi" onClick={(e) => remove(e, n)}>✕</button>
              : <span className="noti-lock" title={`Boleh dipadam ${fmtDate(n.unlock_date)}`}>🔒</span>}
          </div>
        );
      })}
      {err && <p className="error small">{err}</p>}
    </>
  );
}
