# Deploy GeoTrade (all on Render)

Frontend + API + workers + Postgres + Redis on **[Render](https://render.com)**.

| Service | Name | Role | Create via |
|---------|------|------|------------|
| Web | `geotrade-web` | Vite frontend (nginx) | **Web Service** (Docker) |
| Web | `geotrade-api` | FastAPI | **Web Service** (Docker) |
| Worker | `geotrade-worker` | Celery jobs | **Background Worker** |
| Worker | `geotrade-beat` | Celery scheduler | **Background Worker** |
| Redis | `geotrade-redis` | Cache + queue | **Key Value** |
| Postgres | `geotrade-db` | Database | **Postgres** |

You can use **Blueprint** (`render.yaml`) *or* create each service manually (same result; Blueprint is not required).

---

## Manual deploy (recommended if skipping Blueprint)

1. **Postgres** → name `geotrade-db`
2. **Key Value** → name `geotrade-redis`
3. **Web Service** `geotrade-api`
   - Repo: your GitHub fork
   - Runtime: Docker · Dockerfile: `infra/docker/Dockerfile`
   - Docker command: `./scripts/start_api.sh`
   - Health check: `/health`
   - Env: wire `DATABASE_URL` / `DATABASE_SYNC_URL` from Postgres, Redis URLs from Key Value, set `APP_ENV=production`, paste market API keys
4. **Background Worker** `geotrade-worker` — same Dockerfile, command `./scripts/start_worker.sh`, same env/keys
5. **Background Worker** `geotrade-beat` — command `./scripts/start_beat.sh`, DB + Redis env
6. **Web Service** `geotrade-web`
   - Dockerfile: `infra/docker/Dockerfile.frontend`
   - Env: `VITE_API_URL=https://<your-api-host>/api/v1`
7. Set API `FRONTEND_URL=https://<your-web-host>`

### Required secret env vars (API + worker)

`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TWELVEDATA_API_KEY`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `ALPHAVANTAGE_API_KEY`, `NEWSAPI_KEY`

---

## Blueprint path (optional)

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → select the repo → Apply.
3. Fill `sync: false` secrets when prompted.

### If Render adds a random URL suffix

1. Copy the real API URL.
2. On `geotrade-web` set env `VITE_API_URL=https://<real-api-host>/api/v1` → clear cache & redeploy.
3. On `geotrade-api` set `FRONTEND_URL=https://<real-web-host>`.

CORS already allows `*.onrender.com`.

---

## RAM note

Torch + NLP are heavy. If `geotrade-api` OOMs on **starter**, upgrade API (and worker) to **standard**.

---

## Local check

```bash
cp .env.example .env   # fill keys — never commit .env
make up
make migrate
# API: http://localhost:8000/docs

cd frontend && pnpm install && pnpm dev
# UI: http://localhost:5173
```
