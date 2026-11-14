# --- 1. Compilar la interfaz (solo en la fase de construcción) ---
FROM node:22-alpine AS interfaz
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Imagen final: Python + archivos estáticos ---
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COMPELECTRIX_DATA=/data \
    COMPELECTRIX_FRONTEND=/app/frontend
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 1000 -m compelectrix && mkdir /data && chown compelectrix /data
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY --from=interfaz /src/dist ./frontend
USER compelectrix
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/salud')" || exit 1
# Un solo proceso: suficiente para uso personal y lo más ligero para la Raspberry
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
