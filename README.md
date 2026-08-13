# GeoTrade Backend

AI-powered geopolitical market stress intelligence service.

## Tech Stack
- **Python 3.11**
- **FastAPI** + **Pydantic v2**
- **PostgreSQL** + **TimescaleDB**
- **Redis** + **Celery**
- **SQLAlchemy 2.0**
- **NLP**: Transformers (DistilRoBERTa), VADER, HDBSCAN
- **ML**: LightGBM (Surrogate fallback to scikit-learn)

## Architecture
1. **Ingest**: Periodic collection of news (RSS/API).
2. **Intelligence**: 
   - **NLP Pipeline**: Zero-shot classification, sentiment, severity, clustering.
   - **GTI Engine**: Computes Geopolitical Tension Index with exponential decay.
   - **Market Impact**: Predicts asset volatility spikes and directional bias.
3. **Simulators**:
   - **Scenario**: Euler-Maruyama SDE for GTI path projection.
   - **Portfolio**: Monte Carlo evaluation of drawdown risk and PnL distributions.
4. **API**: Low-latency endpoints with structured audit headers and Redis caching.

## Paper / test trades (investor demo)

Hypothetical **$100,000** paper portfolios and outcome logs live under **[`trading/`](trading/README.md)**:

- **`trading/PAPER_TRADES.md`** — Round 1 trades from the frozen snapshot  
- **`trading/PAPER_TRADES_ROUND2.md`** — Round 2 trades (post–ML deployment)  
- **`trading/OUTCOME_LOG.md`** — P&L / outcome table and meeting checklist  
- **`trading/SNAPSHOT_2026-03-16.md`** — Frozen prices baseline  

*Not financial advice — demonstration only.*

## Deploy (production)

**Railway** (recommended here): two Docker services — API + frontend — plus Postgres & Redis.  
Also works on **Render**. Full steps: **[DEPLOY.md](DEPLOY.md)**.

## Quick Start (Docker)
1. Ensure Docker & Docker Compose are installed.
2. Run infrastructure:
   ```bash
   make up
   ```
3. Run migrations and seed data:
   ```bash
   make migrate
   make seed
   ```
4. API is available at `http://localhost:8000/docs`.

## Development & Testing
### Local Setup
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running Tests
Total 69 tests (Unit, Integration, Contract, Load):
```bash
make test
```

## API Endpoints
- `GET /health`: System & infrastructure health.
- `GET /gti/current`: Real-time Geopolitical Tension Index.
- `GET /signals/assets`: Market stress signals per asset.
- `POST /simulate/scenario`: Project impact of custom shocks.
- `POST /portfolio/evaluate`: Stress test holding weights.
- `POST /alerts/subscribe`: Set up Discord/Slack webhook alerts.

---
**Disclaimer**: This system provides intelligence based on AI models. ⚠️ **Not financial advice.**
