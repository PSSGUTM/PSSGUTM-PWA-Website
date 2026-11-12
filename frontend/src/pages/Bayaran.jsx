import { useEffect, useRef, useState } from "react";
import { api, fmtDate } from "../api.js";
import { useToast } from "../components/Toast.jsx";

const PAY = {
  unpaid: ["Belum bayar", "warn"], pending: ["Menunggu pengesahan", "warn"], paid: ["Dah bayar ✅", "ok"],
  rejected: ["Resit ditolak", "bad"], void: ["Tiada bayaran", "muted"],
};

function PayInfo({ info }) {
  const [qr, setQr] = useState(null);
  useEffect(() => { if (info?.has_qr) api.blobUrl("/payment-info/qr").then(setQr).catch(() => {}); }, [info?.has_qr]);
  if (!info) return null;
  if (info.locked) return (
    <section className="card">
      <h3>🏦 Bayar kepada persatuan</h3>
      <p className="small">Maklumat akaun dan QR dipaparkan <b>selepas BKK sahkan senarai kenderaan</b> pada hari latihan (atau disahkan automatik sebelum latihan). Jangan bayar sebelum itu; anda akan dimaklumkan bila bayaran dibuka dan berapa jumlahnya.</p>
    </section>
  );
  const any = info.pay_bank || info.pay_account_no || info.has_qr;
  return (
    <section className="card">
      <h3>🏦 Bayar kepada persatuan</h3>
      {!any && <p className="small muted">Maklumat akaun persatuan belum ditetapkan. Hubungi bendahari.</p>}
      {(info.pay_bank || info.pay_account_no) && (
        <p className="small">{info.pay_bank} · <b>{info.pay_account_no}</b><br />{info.pay_account_name}</p>
      )}
      {info.pay_notes && <p className="small muted">{info.pay_notes}</p>}
      {qr && <div className="imgframe"><img className="qrimg" src={qr} alt="QR persatuan" /></div>}
      <p className="small muted">Bayar sebelum {" "}<b>{"12 tengah hari hari selepas latihan"}</b>; lewat menjadi tunggakan. Bayar ke akaun persatuan sahaja (bukan kepada prebet). Tiada tunai, tiada pemulangan wang.</p>
    </section>
  );
}

export default function Bayaran() {
  const toast = useToast();
  const [sum, setSum] = useState(null);
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(0);
  const fileRef = useRef();
  const target = useRef(null);

  const load = () => Promise.all([api.get("/payments/summary"), api.get("/payments/me")])
    .then(([s, r]) => { setSum(s); setRows(r); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const pick = (p) => { target.current = p; fileRef.current.click(); };
  async function onFile(e) {
    const f = e.target.files[0]; e.target.value = "";
    if (!f || !target.current) return;
    setBusy(target.current.id);
    try { await api.upload(`/payments/${target.current.id}/receipt`, f); toast("Resit dimuat naik ✅"); await load(); }
    catch (e2) { toast(e2.message, "bad"); } finally { setBusy(0); }
  }

  return (
    <>
      <h2>Bayaran</h2>
      {err && <p className="error">{err}</p>}
      {!sum && !err && <><div className="skel" /><div className="skel" /></>}
      {sum && (
        <div className={`hero-card ${sum.total > 0 ? "" : "clear"}`}>
          <p className="eyebrow">Tunggakan anda</p>
          <div className="big">RM <span>{sum.total.toFixed(2)}</span></div>
          <div className="sub">{sum.total > 0
            ? `${sum.count} bayaran belum dibayar${sum.oldest ? ` · tertua ${fmtDate(sum.oldest)}` : ""}`
            : "Tiada tunggakan. Terima kasih!"}</div>
        </div>
      )}
      {sum?.blocked && <p className="error">Bayaran tertua melebihi 6 bulan. Tempahan baru disekat sehingga anda jelaskan.</p>}
      {sum && sum.total > 0 && !sum.blocked && <p className="small muted">Anda masih boleh menempah, tetapi sila jelaskan segera. Tempahan baru disekat jika bayaran tertua melebihi 6 bulan.</p>}
      {sum && <PayInfo info={sum.info} />}
      <input ref={fileRef} type="file" accept="image/*,application/pdf" hidden onChange={onFile} />
      <h3 style={{ marginTop: 16 }}>Senarai bayaran</h3>
      {rows && rows.length === 0 && <p className="muted small">Belum ada bayaran.</p>}
      {(rows || []).filter((p) => p.status !== "void").map((p) => (
        <div className="card" key={p.id}>
          <div className="row"><b>{fmtDate(p.training_date)}</b><span>RM{p.due.toFixed(2)}</span></div>
          <div className="row">
            <span className={`badge ${PAY[p.status][1]}`}>{PAY[p.status][0]}</span>
            {p.can_pay && <button className="btn" disabled={busy === p.id} onClick={() => pick(p)}>📤 Upload resit</button>}
          </div>
          {p.can_pay && <p className={`small ${p.overdue ? "error" : "muted"}`}>{p.overdue ? "Lewat: tunggakan. " : ""}Bayar sebelum {new Date(p.deadline).toLocaleString("ms-MY", { weekday: "long", day: "numeric", month: "numeric", hour: "numeric", minute: "2-digit" })}</p>}
          {p.status === "unpaid" && !p.can_pay && <p className="small muted">Dibuka selepas senarai disahkan.</p>}
        </div>
      ))}
    </>
  );
}
