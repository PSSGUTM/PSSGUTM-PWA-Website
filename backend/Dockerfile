FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
COPY requirements-postgres.txt .
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt
COPY app ./app
COPY start.sh .
RUN chmod +x /srv/start.sh && mkdir -p /srv/uploads
# Seed dijalankan dahulu (selamat diulang), kemudian server dimulakan
CMD ["/srv/start.sh"]
