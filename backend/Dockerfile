# API image. Build from the repo root:  docker build -f backend/Dockerfile -t pokedex-api .
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY scripts/load_db.py scripts/
COPY data/processed/ data/processed/
COPY models/pokemon_cnn.onnx models/labels.json models/

# Build the SQLite database inside the image from the committed processed JSON.
RUN python scripts/load_db.py

WORKDIR /app/backend
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
