# ANTIGRAVITY.md — Panduan Pembangunan AI (Google Antigravity)

Dokumen ini adalah panduan konteks kerja untuk Google Antigravity bagi projek **PSSGUTM Transport & Pengurusan Persatuan**.

> Sila rujuk fail terperinci berikut:
> - Konteks Projek & Peta Kod: [`CLAUDE.md`](CLAUDE.md)
> - Panduan Pembangunan & Arahan AI: [`docs/06-membangun-dengan-ai.md`](docs/06-membangun-dengan-ai.md)
> - Peraturan Bisnes: [`docs/02-peraturan-bisnes.md`](docs/02-peraturan-bisnes.md)
> - Log Keputusan: [`docs/07-log-keputusan.md`](docs/07-log-keputusan.md)

## Peraturan Kerja Utama
1. Satu perubahan = satu branch = `pytest` + `npm run build` lulus sebelum merge ke `main`.
2. Jangan pernah DROP data produksi. Sebarang perubahan skema pangkalan data mesti dikemas kini dalam `backend/app/models.py` DAN `migrate.py`.
3. Repo mesti KEKAL PRIVATE. Jangan commit `.env`, fail rahsia atau data peribadi ahli.
