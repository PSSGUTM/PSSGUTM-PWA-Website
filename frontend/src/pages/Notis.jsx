import Notifications, { useNotes } from "../components/Notifications.jsx";

export default function Notis() {
  const [notes, setNotes] = useNotes();
  return (
    <>
      <h2>Notifikasi</h2>
      <p className="muted small">Tekan notifikasi untuk terus ke kerja berkaitan. Maklumat dan tugasan boleh dipadam (✕). Amaran 🔒 hilang sendiri bila selesai.</p>
      {!notes && <div className="skel" />}
      <Notifications notes={notes} setNotes={setNotes} />
    </>
  );
}
