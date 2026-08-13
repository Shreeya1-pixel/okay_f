# Deploy GeoTrade on Railway (frontend + backend)

This monorepo needs **two services** (Railpack auto-detect fails at repo root).

Repo: your GitHub fork (e.g. `Shreeya1-pixel/okay_f`).

---

## 1. Create project + databases

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub** → `okay_f`
2. Delete/ignore the failed auto service if Railpack already failed once.
3. **+ New** → **Database** → **PostgreSQL**
4. **+ New** → **Database** → **Redis**

---

## 2. Backend API service

**+ New** → **GitHub Repo** → same `okay_f` (or rename the failed service).

### Settings
| Setting | Value |
|---------|--------|
| Config-as-code path | `/railway.toml` |
| (or) Builder | Dockerfile |
| Dockerfile path | `infra/docker/Dockerfile` |
| Custom start command | `./scripts/start_api.sh` |
| Health check path | `/health` |

### Variables (API)
Link Postgres + Redis from the Variable UI (“Add variable reference”), then add:

```
APP_ENV=production
ENV=production
WEB_CONCURRENCY=1
DATABASE_URL=${{Postgres.DATABASE_URL}}
DATABASE_SYNC_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
TWELVEDATA_API_KEY=...
FINNHUB_API_KEY=...
FRED_API_KEY=...
ALPHAVANTAGE_API_KEY=...
NEWSAPI_KEY=...
FRONTEND_URL=https://<your-frontend-domain>.up.railway.app
```

Generate a public domain: Service → **Settings** → **Networking** → **Generate domain**.

> First API Docker build pulls Torch/ML deps and can take **15–30+ minutes** and a lot of disk/RAM. Upgrade the service if the build OOMs.

---

## 3. Frontend service

**+ New** → **GitHub Repo** → same `okay_f` again.

### Settings
| Setting | Value |
|---------|--------|
| Config-as-code path | `/frontend/railway.toml` |
| Dockerfile path | `infra/docker/Dockerfile.frontend` |

### Variables (Frontend — needed at **build** time)
```
VITE_API_URL=https://<your-api-domain>.up.railway.app/api/v1
```

Generate a public domain for the frontend, then put that URL into the API’s `FRONTEND_URL` and redeploy the API.

---

## 4. (Optional) Celery worker

Same Dockerfile as API, start command `./scripts/start_worker.sh`, same DB/Redis/API key env vars. Without a worker, scheduled ingestion won’t run; many read APIs still work.

---

## Local check

```bash
cp .env.example .env
make up && make migrate
cd frontend && pnpm install && pnpm dev
```

- API: http://localhost:8000/docs  
- UI: http://localhost:5173
