#!/bin/sh
# Jalankan seed (buat data asas + akaun admin) sebelum server start.
# Seed selamat diulang — tak duplicate data, skip kalau dah ada.
echo "==> Menjalankan seed..."
python -m app.seed
echo "==> Seed selesai. Memulakan server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
