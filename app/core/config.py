"""Application configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _ensure_ssl_query(url: str) -> str:
    """Add sslmode=require for non-local Postgres (Render/Neon/Supabase)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "postgres"}:
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "sslmode" not in query and "ssl" not in query:
        query["sslmode"] = "require"
    return urlunparse(parsed._replace(query=urlencode(query)))


def _normalize_db_url(url: str, driver: str) -> str:
    """Convert Render/Heroku-style postgres URLs to SQLAlchemy driver URLs."""
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    for prefix in (
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
    ):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix) :]
            break
    if url.startswith("postgresql://"):
        url = f"postgresql+{driver}://" + url[len("postgresql://") :]
    return _ensure_ssl_query(url)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # App — accept APP_ENV or ENV (Render/common PaaS)
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "ENV"),
    )
    app_version: str = "0.2.0"
    api_v1_str: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    secret_key: SecretStr = Field(default="change-me-in-production")
    frontend_url: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://geotrade:geotrade_secret@localhost:5432/geotrade"
    database_sync_url: str = "postgresql+psycopg2://geotrade:geotrade_secret@localhost:5432/geotrade"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl_seconds: int = 60

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Rate limiting
    rate_limit_default: str = "100/minute"
    rate_limit_simulation: str = "10/minute"

    # Model artifacts
    model_artifacts_dir: Path = Path("./model_artifacts")

    # NLP
    nlp_model_name: str = "cross-encoder/nli-distilroberta-base"
    sentence_transformer_model: str = "all-MiniLM-L6-v2"
    spacy_model: str = "en_core_web_sm"

    # GTI
    gti_decay_lambda: float = 0.05  # per-hour decay constant
    gti_version: str = "1.0.0"

    # Pipeline
    pipeline_version: str = "1.0.0"

    # Telemetry
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "geotrade"
    enable_otel: bool = False

    # Alert webhooks
    discord_webhook_url: str = ""
    slack_webhook_url: str = ""

    # External data APIs
    finnhub_api_key: str = ""
    finnhub_api_key_2: str = ""   # second key for round-robin rotation (doubles rate limit)
    twelvedata_api_key: str = ""
    polygon_api_key: str = ""
    alphavantage_api_key: str = ""
    newsapi_key: str = ""
    fred_api_key: str = ""
    openrouter_api_key: str = ""

    # CoinGecko (free, no key required for basic usage)
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"

    # Market data mode
    market_data_live_only: bool = False  # True => disable synthetic fallback

    # Alpaca Markets broker (read from environment — never hardcode)
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"
    alpaca_paper: bool = True  # True = paper trading; set False only for live

    # OANDA v20 Practice API (paper forex trading)
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_environment: Literal["practice", "live"] = "practice"

    # CCXT secondary exchange (e.g. binance, kraken, coinbase)
    ccxt_exchange: str = "binance"  # exchange id recognised by ccxt
    ccxt_api_key: str = ""
    ccxt_secret: str = ""
    ccxt_sandbox: bool = True  # True = testnet / sandbox mode

    # Paper trading ingestion schedule (seconds between price fetches)
    paper_trading_fetch_interval: int = 30

    # Supabase (waitlist) — use service_role key for server-side inserts (bypasses RLS)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    @field_validator("model_artifacts_dir", mode="before")
    @classmethod
    def create_artifacts_dir(cls, v: str | Path) -> Path:
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_async_database_url(cls, v: Any) -> Any:
        if isinstance(v, str):
            return _normalize_db_url(v, "asyncpg")
        return v

    @field_validator("database_sync_url", mode="before")
    @classmethod
    def normalize_sync_database_url(cls, v: Any) -> Any:
        if isinstance(v, str):
            return _normalize_db_url(v, "psycopg2")
        return v

    @model_validator(mode="after")
    def derive_sync_url_if_needed(self) -> Settings:
        """If sync URL still looks like the async URL / bare postgres, normalize it."""
        sync = self.database_sync_url
        if "+asyncpg" in sync or (
            sync.startswith("postgresql://") and "+psycopg" not in sync
        ):
            object.__setattr__(
                self,
                "database_sync_url",
                _normalize_db_url(sync, "psycopg2"),
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
