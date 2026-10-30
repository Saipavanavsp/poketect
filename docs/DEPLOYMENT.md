# Deployment guide

Poketect deploys in two independent pieces. The frontend works on its own; adding the backend
unlocks Claude-powered conversation and saves trainer edits to the database.

| Piece | Where | What you get |
|---|---|---|
| Frontend (static) | GitHub Pages (already live) or Vercel | Scanner (model runs in the browser), Pokédex, trainer, map, offline chat (a local intent router, not an LLM) |
| Backend (FastAPI) | Render, Railway, Fly.io, any Docker host | `/api/*`, Claude chat with tool calling, server-side identification, SQLite or PostgreSQL |

## 1. Frontend on GitHub Pages (current live site)

`.github/workflows/pages.yml` builds `frontend/` with `BASE_PATH=/poketect/` and publishes it on
every push to `main`. One-time setup: **Settings > Pages > Source: GitHub Actions**.

To point the live site at a deployed backend, add a repository variable:
**Settings > Secrets and variables > Actions > Variables > New variable**
`VITE_API_URL = https://your-api.onrender.com`, then re-run the workflow.

## 2. Frontend on Vercel (alternative)

1. vercel.com > Add New Project > import this repo.
2. Root directory: `frontend`. Framework preset: Vite (also set in `frontend/vercel.json`).
3. Environment variable (optional): `VITE_API_URL=https://your-api.onrender.com`.
4. Deploy. Add the Vercel URL to the backend's `CORS_ORIGINS`.

## 3. Backend on Render

1. render.com > New > **Blueprint** > select this repo. `render.yaml` defines a Docker web service.
2. In the service's Environment tab set `ANTHROPIC_API_KEY` (never commit it).
3. Update `CORS_ORIGINS` to your frontend URL(s), comma-separated.
4. Health check: `https://<service>.onrender.com/api/health`. API docs: `/docs`.

The image builds the SQLite database from `data/processed/*.json` at build time and serves the ONNX
model, so it needs no PyTorch and fits the free tier's 512 MB. On the free tier the filesystem is
ephemeral: trainer edits reset when the service restarts. To keep them, either attach a persistent
disk and set `DATABASE_URL=sqlite:////var/data/pokedex.db`, or use PostgreSQL (below). In both cases
run `python scripts/load_db.py` once against the new database (Render: service > Shell).

### PostgreSQL (recommended for production)

SQLite is the default because it needs no setup and suits one trainer with occasional edits. For a
persistent, multi-process deployment, point the API at PostgreSQL. The driver (`psycopg`) is already
in `requirements.txt` and SQLAlchemy needs no code changes:

```
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/poketect
```

On Render: New > PostgreSQL, copy its *Internal Database URL*, change the `postgresql://` prefix to
`postgresql+psycopg://`, set it as `DATABASE_URL` on the API service, then run `load_db.py` once.

### Security settings

| Variable | Default | What it does |
|---|---|---|
| `ADMIN_TOKEN` | empty (edits open) | When set, `PUT /api/trainer*` needs `Authorization: Bearer <token>`. Reads stay public. The Render blueprint generates one; find it in the Environment tab. The web app asks for it once on the first edit and keeps it in that browser. |
| `RATE_LIMIT_CHAT` | 10 | Chat requests per minute per IP. Each one spends Claude API credit. `0` turns it off. |
| `RATE_LIMIT_IDENTIFY` | 30 | Identification requests per minute per IP. |
| `MAX_UPLOAD_BYTES` | 8388608 | Upload size cap (8 MB), enforced while reading. |
| `MAX_IMAGE_PIXELS` | 40000000 | Rejects bigger images from the file header, before decoding (decompression-bomb guard). |

Uploads must be PNG, JPEG, WebP, GIF or BMP, detected from the file's bytes rather than its MIME
type. Images are decoded in memory for identification and never written to disk. Rate limits are kept
in memory per API process, and the container runs uvicorn with `--proxy-headers` so the limit applies
to each visitor's IP rather than to Render's proxy.

## 4. Everything with Docker (local or any VPS)

```powershell
Copy-Item .env.example .env   # then put your key in .env
docker compose up --build
# UI  http://localhost:8080   API docs  http://localhost:8000/docs
```

## Secrets checklist

- `.env` is in `.gitignore`; only `.env.example` (no real key) is committed.
- The Claude key lives only on the backend. The browser never sees it.
- Set `ADMIN_TOKEN` on any publicly reachable backend so only you can edit the trainer.
