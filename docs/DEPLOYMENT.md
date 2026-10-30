# Deployment guide

Poketect deploys in two independent pieces. The frontend works on its own; adding the backend
unlocks Claude-powered conversation and saves trainer edits to the database.

| Piece | Where | What you get |
|---|---|---|
| Frontend (static) | GitHub Pages (already live) or Vercel | Scanner (model runs in the browser), Pokédex, trainer, map, offline chat |
| Backend (FastAPI) | Render, Railway, Fly.io, any Docker host | `/api/*`, Claude chat with tool calling, server-side identification, SQLite |

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
ephemeral: trainer edits reset when the service restarts. Attach a persistent disk and set
`DATABASE_URL=sqlite:////var/data/pokedex.db` (run `scripts/load_db.py` once) to keep them.

## 4. Everything with Docker (local or any VPS)

```powershell
Copy-Item .env.example .env   # then put your key in .env
docker compose up --build
# UI  http://localhost:8080   API docs  http://localhost:8000/docs
```

## Secrets checklist

- `.env` is in `.gitignore`; only `.env.example` (no real key) is committed.
- The Claude key lives only on the backend. The browser never sees it.
