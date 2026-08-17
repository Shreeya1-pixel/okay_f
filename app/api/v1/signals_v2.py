"""Enhanced Signals V2 — trader-focused intelligence endpoint.

Returns the full expanded asset universe with:
  - BUY/SELL/HOLD action
  - Confidence + uncertainty
  - Bullish / bearish strength
  - Volatility label
  - Trade setup (entry, stop, target, R:R)
  - Signal reliability metrics (accuracy, Sharpe, win rate, max drawdown)
  - Event → market reaction timeline
  - Structured reasoning chain (Event → Impact → Mechanism → Movement)
  - Asset universe metadata (category, geo_sensitivity, description)
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import _make_cache_key, cache_get, cache_set
from app.core.database import get_db
from app.core.logging import get_logger
from app.config.asset_universe import AssetUniverse, get_asset_universe, AssetDefinition
from app.repositories.event_repo import EventRepository
from app.services.market import get_all_markets
from app.services.trade_setup import compute_trade_setup

router = APIRouter(prefix="/signals/v2", tags=["signals-v2"])
logger = get_logger(__name__)

# ── Per-event asset sensitivity rules ────────────────────────────────────────
_EVENT_ASSET_RULES: dict[str, dict[str, tuple[str, float]]] = {
    "military_escalation": {
        # ── Commodities ──────────────────────────────────────────────────────
        "XAUUSD": ("BUY",  0.88), "XAGUSD": ("BUY",  0.72),
        "WTI":    ("BUY",  0.80), "NATGAS": ("BUY",  0.65),
        "BTC":    ("HOLD", 0.55), "BRENT":  ("BUY",  0.82),
        # ── Defense stocks ───────────────────────────────────────────────────
        "LMT":    ("BUY",  0.85), "RTX":    ("BUY",  0.84),
        "NOC":    ("BUY",  0.80), "GD":     ("BUY",  0.78),
        "BA":     ("BUY",  0.70), "ITA":    ("BUY",  0.83),
        # ── ETF proxies ──────────────────────────────────────────────────────
        "GLD":    ("BUY",  0.86), "SLV":    ("BUY",  0.70),
        "USO":    ("BUY",  0.78), "UNG":    ("BUY",  0.62),
        # ── Other ────────────────────────────────────────────────────────────
        "TLT":    ("BUY",  0.72),
        "SPX":    ("SELL", 0.68), "NDX":    ("SELL", 0.65), "DAX":    ("SELL", 0.70),
        "USDJPY": ("SELL", 0.65), "USDCHF": ("SELL", 0.62),
    },
    "energy_supply_disruption": {
        "WTI":    ("BUY",  0.92), "BRENT":  ("BUY",  0.90), "NATGAS": ("BUY",  0.88),
        "XAUUSD": ("BUY",  0.68), "XAGUSD": ("BUY",  0.58),
        "LMT":    ("BUY",  0.60), "RTX":    ("BUY",  0.58),
        "XOM":    ("BUY",  0.82), "CVX":    ("BUY",  0.80),
        "XLE":    ("BUY",  0.85),
        "DAX":    ("SELL", 0.72), "EURUSD": ("SELL", 0.68),
        "USO":    ("BUY",  0.90), "UNG":    ("BUY",  0.86),
    },
    "trade_restrictions": {
        "COPPER":   ("SELL", 0.80), "SOYBEANS": ("SELL", 0.78), "NDX":  ("SELL", 0.72),
        "HSI":      ("SELL", 0.85), "USDCNH":   ("BUY",  0.75),
        "XAUUSD":   ("BUY",  0.65), "XAGUSD":   ("SELL", 0.58),
        "WTI":      ("SELL", 0.55), "NATGAS":   ("BUY",  0.62),
        "BTC":      ("SELL", 0.60), "ETH":      ("SELL", 0.58),
        "BA":       ("SELL", 0.65),
    },
    "sanctions": {
        "XAUUSD": ("BUY",  0.82), "XAGUSD": ("BUY",  0.70),
        "WTI":    ("BUY",  0.70), "BTC":    ("BUY",  0.65),
        "LMT":    ("BUY",  0.72), "RTX":    ("BUY",  0.70),
        "NOC":    ("BUY",  0.68), "GD":     ("BUY",  0.65),
        "EURUSD": ("SELL", 0.68), "DAX":    ("SELL", 0.72),
    },
    "political_instability": {
        "XAUUSD": ("BUY",  0.75), "XAGUSD": ("BUY",  0.62),
        "TLT":    ("BUY",  0.70),
        "BTC":    ("HOLD", 0.52),
        "LMT":    ("BUY",  0.60), "RTX":    ("BUY",  0.58),
        "SPX":    ("SELL", 0.65), "EURUSD": ("SELL", 0.60),
    },
    "nuclear_threat": {
        "XAUUSD": ("BUY",  0.92), "XAGUSD": ("BUY",  0.80),
        "TLT":    ("BUY",  0.85),
        "LMT":    ("BUY",  0.88), "RTX":    ("BUY",  0.85),
        "NOC":    ("BUY",  0.88), "GD":     ("BUY",  0.80),
        "ITA":    ("BUY",  0.86), "BTC":    ("HOLD", 0.50),
        "USDJPY": ("SELL", 0.80), "SPX":    ("SELL", 0.78), "NDX":    ("SELL", 0.75),
    },
    "territorial_dispute": {
        "XAUUSD": ("BUY",  0.78), "XAGUSD": ("BUY",  0.65),
        "NKY":    ("SELL", 0.72), "USDJPY": ("SELL", 0.68),
        "LMT":    ("BUY",  0.75), "RTX":    ("BUY",  0.73),
        "NOC":    ("BUY",  0.70), "GD":     ("BUY",  0.68),
        "ITA":    ("BUY",  0.72), "BTC":    ("HOLD", 0.48),
    },
    "economic_policy_change": {
        "XAUUSD": ("BUY",  0.70), "XAGUSD": ("BUY",  0.60),
        "BTC":    ("BUY",  0.62), "TLT":    ("BUY",  0.65),
        "SPX":    ("SELL", 0.55),
        "NATGAS": ("HOLD", 0.50), "WTI":    ("HOLD", 0.48),
    },
    "cyber_attack": {
        "XAUUSD": ("BUY",  0.72), "TLT":    ("BUY",  0.68),
        "NOC":    ("BUY",  0.80), "LMT":    ("BUY",  0.75),
        "RTX":    ("BUY",  0.72), "ITA":    ("BUY",  0.78),
        "NDX":    ("SELL", 0.65), "SPX":    ("SELL", 0.60),
        "BTC":    ("SELL", 0.58),
    },
}

# ── Explainable analysis helpers ──────────────────────────────────────────────
def _build_reasoning_chain(
    asset: AssetDefinition,
    action: str,
    event: dict | None,
    confidence: float,
    market: dict,
) -> list[dict]:
    quote_ts = _iso_timestamp(market.get("timestamp"))
    change = float(market.get("change") or 0.0)
    source = str(market.get("source") or "unknown")
    status = str(market.get("data_status") or "unavailable")
    event_evidence = (
        f"{event['title']} · severity {float(event['severity']):.0%}"
        if event else "No qualifying real event was found in the last 48 hours"
    )
    return [
        {
            "step": 1, "label": "Market Quote",
            "description": f"{asset.label} quote received from {source}",
            "evidence": f"As of {quote_ts} · status {status}",
            "phase": "market_data", "confidence_contribution": 0.40,
        },
        {
            "step": 2, "label": "Movement Analysis",
            "description": f"Observed session movement is {change:+.2f}%",
            "evidence": "Direction is calculated from the provider's current and previous-session values",
            "phase": "movement", "confidence_contribution": 0.35,
        },
        {
            "step": 3, "label": "Event Context",
            "description": event["category"].replace("_", " ") if event else "No event overlay applied",
            "evidence": event_evidence,
            "phase": "event", "confidence_contribution": 0.15 if event else 0.0,
        },
        {
            "step": 4, "label": "Decision",
            "description": f"{action} with {confidence:.0%} confidence",
            "evidence": "Signal requires a priced quote and combines observed movement with any verified event sensitivity",
            "phase": "signal", "confidence_contribution": 0.10,
        },
    ]

# ── Event → market reaction timeline ─────────────────────────────────────────
def _build_event_timeline(
    event: dict | None,
    asset: AssetDefinition,
    action: str,
    market: dict,
    confidence: float,
) -> list[dict]:
    timeline = [
        {
            "ts": _iso_timestamp(market.get("timestamp")),
            "label": "Market Quote Updated",
            "detail": f"{asset.label} {float(market.get('change') or 0.0):+.2f}% · {market.get('source', 'unknown')}",
            "phase": "market_data",
        },
    ]
    if event:
        timeline.append({
            "ts": event["ts"], "label": "Event Classified",
            "detail": f"{event['title']} · severity {float(event['severity']):.0%}",
            "phase": "event",
        })
    timeline.append({
        "ts": datetime.now(UTC).isoformat(),
        "label": f"{action} Analysis Generated",
        "detail": f"{asset.label} · confidence {confidence:.0%}",
        "phase": "signal",
    })
    return sorted(timeline, key=lambda row: row["ts"])


@router.get("/all")
async def get_all_signals(
    category: str | None = Query(default=None, description="Filter by asset category"),
    action: str | None   = Query(default=None, description="Filter: BUY | SELL | HOLD"),
    limit: int           = Query(default=300, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return enriched trading signals for the full asset universe.

    Each signal includes:
    - Trade setup (entry/stop/target/R:R)
    - Bullish/bearish strength
    - Volatility label
    - Signal reliability metrics
    - Event → market reaction timeline
    - 4-step causal reasoning chain
    """
    cache_key = _make_cache_key("signals_v2_real_v3", category or "all", action or "all", limit)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    universe = get_asset_universe()
    try:
        live_events = await _load_live_events(db, limit=200)
    except Exception as exc:
        logger.warning("signals_v2_event_query_failed", error=str(exc))
        live_events = []

    try:
        market_response = await get_all_markets()
    except Exception as exc:
        logger.error("signals_v2_market_fetch_failed", error=str(exc))
        market_response = {"data": {}}

    market_rows = [
        row
        for rows in market_response.get("data", {}).values()
        if isinstance(rows, list)
        for row in rows
        if isinstance(row, dict) and row.get("symbol")
    ]
    market_by_symbol = {str(row["symbol"]).upper(): row for row in market_rows}
    assets = [_asset_for_market_row(row, universe) for row in market_rows]

    # Filter by category if requested
    if category:
        requested = category.lower()
        assets = [
            asset for asset in assets
            if asset.category.lower() == requested
            or asset.asset_class.lower() == requested
            or _market_class_for_category(asset.category) == requested
        ]

    signals: list[dict] = []

    for asset in assets:
        market = market_by_symbol[asset.symbol.upper()]
        current_price = float(market.get("price") or 0.0)
        change = float(market.get("change") or 0.0)
        # Compute implied deviation when the source reports no change data
        if change == 0.0 and current_price > 0 and asset.base_price > 0:
            change = round(((current_price - asset.base_price) / asset.base_price) * 100, 4)
        priced = current_price > 0 and market.get("status") != "unavailable"
        triggering_event = _pick_event_for_asset(asset, live_events)
        act, confidence, directional_bias = _analyze_action(
            asset, market, triggering_event
        )
        uncertainty = 1.0 - confidence
        realized_vol = _observed_volatility(market)

        if priced:
            setup = compute_trade_setup(
                action=act,
                price=current_price,
                realized_vol=realized_vol,
                directional_bias=directional_bias,
                confidence=confidence,
                win_rate=0.5,
            )
            trade_setup = {
                "current_price": round(current_price, 6),
                "entry_price": setup.entry_price,
                "stop_loss": setup.stop_loss,
                "target_price": setup.target_price,
                "risk_reward": setup.risk_reward_ratio,
                "atr_pct": setup.atr_estimate_pct,
                "max_position_pct": setup.max_position_pct,
            }
            volatility_label = setup.volatility_label
            bullish_strength = setup.bullish_strength
            bearish_strength = setup.bearish_strength
        else:
            trade_setup = {
                "current_price": 0.0, "entry_price": 0.0, "stop_loss": 0.0,
                "target_price": 0.0, "risk_reward": 0.0, "atr_pct": 0.0,
                "max_position_pct": 0.0,
            }
            volatility_label = "UNAVAILABLE"
            bullish_strength = 0.0
            bearish_strength = 0.0

        chain = _build_reasoning_chain(asset, act, triggering_event, confidence, market)
        timeline = _build_event_timeline(triggering_event, asset, act, market, confidence)
        event_title = triggering_event["title"] if triggering_event else "No verified event linked"
        summary = (
            f"{act} {asset.label}: observed movement {change:+.2f}% from "
            f"{market.get('source', 'unknown')} ({market.get('data_status', 'unavailable')}). "
            f"{event_title}."
        )

        sig = {
            # ── Identity ──────────────────────────────────────────────
            "symbol":         asset.symbol,
            "label":          asset.label,
            "asset_class":    asset.category,
            "category":       asset.category,
            "sector":         asset.sector,
            "region":         asset.region,
            "description":    asset.description,
            "geo_sensitivity": asset.geo_sensitivity,
            # ── Signal ────────────────────────────────────────────────
            "action":          act,
            "confidence_pct":  round(confidence * 100, 1),
            "uncertainty_pct": round(uncertainty * 100, 1),
            "time_horizon":    "current session",
            # ── Strength meters ───────────────────────────────────────
            "bullish_strength":  bullish_strength,
            "bearish_strength":  bearish_strength,
            "volatility_label":  volatility_label,
            "vol_spike_prob":    0.0,
            # ── Trade setup ───────────────────────────────────────────
            "trade_setup": trade_setup,
            # ── Reliability ───────────────────────────────────────────
            "reliability": {
                "historical_accuracy": 0.0,
                "win_rate":            0.0,
                "sharpe_ratio":        0.0,
                "max_drawdown":        0.0,
                "basis":               "No validated backtest is configured",
            },
            # ── Trigger ───────────────────────────────────────────────
            "triggering_event": {
                "id":       triggering_event["id"] if triggering_event else "none",
                "title":    event_title,
                "category": triggering_event["category"] if triggering_event else "none",
                "severity": triggering_event["severity"] if triggering_event else 0.0,
                "ts":       triggering_event["ts"] if triggering_event else _iso_timestamp(market.get("timestamp")),
            },
            # ── Reasoning ─────────────────────────────────────────────
            "reasoning_summary":  summary,
            "reasoning_chain":    chain,
            # ── Event timeline ────────────────────────────────────────
            "event_timeline":     timeline,
            # ── Related ───────────────────────────────────────────────
            "related_assets":    _find_related(asset, universe),
            # ── Metadata ──────────────────────────────────────────────
            "generated_at": datetime.now(UTC).isoformat(),
            "price": current_price if priced else None,
            "live_change_pct": change if priced else None,
            "quote_timestamp": _iso_timestamp(market.get("timestamp")),
            "data_status": market.get("data_status", "unavailable"),
            "data_source": market.get("source", "unknown"),
            "analysis_basis": "observed_market_movement_and_verified_events",
            "actionable": (
                priced
                and act in ("BUY", "SELL")
                and market.get("data_status") not in ("reference", "estimated")
            ),
        }
        signals.append(sig)

    # Filter by action if requested
    if action:
        signals = [s for s in signals if s["action"].upper() == action.upper()]

    # Priced assets first, then strongest evidence, while preserving all rows.
    signals.sort(key=lambda s: (s["price"] is not None, s["confidence_pct"]), reverse=True)
    signals = signals[:limit]

    result = {
        "signals":     signals,
        "total":       len(signals),
        "asset_count": len(market_rows),
        "priced_count": sum(1 for signal in signals if signal["price"] is not None),
        "events_used": len(live_events),
        "events_source": "database" if live_events else "none",
        "market_counts": market_response.get("counts", {}),
        "data_as_of":  datetime.now(UTC).isoformat(),
        "not_financial_advice": True,
    }

    await cache_set(cache_key, result, ttl=45)
    return result


@router.get("/universe")
async def get_asset_universe_endpoint() -> dict:
    """Return the full asset universe grouped by category."""
    universe = get_asset_universe()
    return {
        "grouped":    universe.grouped(),
        "total":      len(universe),
        "symbols":    universe.symbols(),
        "data_as_of": datetime.now(UTC).isoformat(),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pick_event_for_asset(asset: AssetDefinition, events: list[dict]) -> dict | None:
    """Return the most relevant event for an asset based on geo_sensitivity."""
    for evt in events:
        if evt["category"] in asset.geo_sensitivity:
            return evt
    return None


def _asset_for_market_row(row: dict, universe: "AssetUniverse") -> AssetDefinition:
    """Resolve metadata for a real market row without inventing a price."""
    symbol = str(row["symbol"]).upper()
    configured = universe.get_asset(symbol)
    if configured:
        return configured

    market_class = str(row.get("asset_class") or "other").lower()
    category = {
        "stocks": "stock", "crypto": "crypto", "forex": "forex",
        "commodities": "commodity", "bonds": "bond", "etfs": "etf",
        "indices": "equity_index",
    }.get(market_class, market_class)
    name = str(row.get("name") or symbol)
    return AssetDefinition(
        symbol=symbol,
        name=name,
        asset_class=market_class,
        region="global",
        sector=market_class,
        label=name,
        description=f"{name} - {market_class}",
        category=category,
        geo_sensitivity=["political_instability", "economic_policy_change"],
    )


def _market_class_for_category(category: str) -> str:
    return {
        "stock": "stocks", "crypto": "crypto", "forex": "forex",
        "commodity": "commodities", "bond": "bonds", "etf": "etfs",
        "equity_index": "indices",
    }.get(category, category)


def _analyze_action(
    asset: AssetDefinition,
    market: dict,
    event: dict | None,
) -> tuple[str, float, float]:
    """Create an explainable direction score from real movement and real events."""
    price = float(market.get("price") or 0.0)
    if price <= 0 or market.get("status") == "unavailable":
        return "HOLD", 0.0, 0.0

    change = float(market.get("change") or 0.0)

    # When the provider returns no change data (e.g. daily reference rates),
    # compute implied deviation from the asset's base_price so that the AI
    # analysis still produces meaningful bullish/bearish signals.
    if change == 0.0 and asset.base_price > 0 and price > 0:
        change = ((price - asset.base_price) / asset.base_price) * 100

    threshold = {
        "stock": 0.50, "crypto": 1.00, "forex": 0.15,
        "commodity": 0.60, "bond": 0.35, "etf": 0.45,
        "equity_index": 0.40,
    }.get(asset.category, 0.50)
    movement_score = max(-1.0, min(1.0, change / threshold))
    score = movement_score

    if event:
        rule = _EVENT_ASSET_RULES.get(event["category"], {}).get(asset.symbol)
        if rule:
            event_action, event_confidence = rule
            event_direction = 1.0 if event_action == "BUY" else -1.0 if event_action == "SELL" else 0.0
            event_score = event_direction * event_confidence * float(event["severity"])
            score = movement_score * 0.70 + event_score * 0.30

    action = "BUY" if score >= 0.35 else "SELL" if score <= -0.35 else "HOLD"
    freshness = {
        "live": 1.0, "delayed": 0.85, "stale": 0.55,
        "reference": 0.35, "estimated": 0.35, "unavailable": 0.0,
    }.get(str(market.get("data_status") or "unavailable"), 0.7)
    confidence = min(0.95, (0.45 + abs(score) * 0.45) * freshness)
    if action == "HOLD":
        confidence = min(confidence, 0.55 * freshness)
    return action, confidence, score


def _observed_volatility(market: dict) -> float:
    """Estimate annualized volatility only from the current observed quote range."""
    price = float(market.get("price") or 0.0)
    high = float(market.get("high_24h") or 0.0)
    low = float(market.get("low_24h") or 0.0)
    change = abs(float(market.get("change") or 0.0)) / 100
    range_return = (high - low) / price if price > 0 and high >= low > 0 else 0.0
    daily_observation = max(range_return, change)
    return max(0.01, min(2.0, daily_observation * math.sqrt(252)))


def _iso_timestamp(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    if isinstance(value, str) and value:
        return value
    return datetime.now(UTC).isoformat()


def _map_classification_to_category(classification: str | None, title: str) -> str:
    raw = (classification or "").strip().lower()
    if raw in _EVENT_ASSET_RULES:
        return raw
    simple_map = {
        "escalation": "military_escalation",
        "tension": "political_instability",
        "normal": "economic_policy_change",
    }
    if raw in simple_map:
        return simple_map[raw]
    return _infer_category_from_title(title)


def _infer_category_from_title(title: str) -> str:
    lower = title.lower()
    keyword_map = [
        ("energy_supply_disruption", ("oil", "gas", "lng", "pipeline", "opec", "refinery", "supply")),
        ("trade_restrictions", ("tariff", "sanction", "export control", "trade", "restriction", "embargo")),
        ("cyber_attack", ("cyber", "ransomware", "ddos", "malware")),
        ("nuclear_threat", ("nuclear", "ballistic", "warhead")),
        ("military_escalation", ("missile", "airstrike", "invasion", "military", "drone", "navy", "army")),
        ("territorial_dispute", ("border", "territorial", "south china sea", "strait")),
        ("diplomatic_breakdown", ("diplomatic", "talks collapsed", "expelled ambassador")),
        ("political_instability", ("protest", "coup", "election crisis", "unrest", "cabinet collapse")),
        ("economic_policy_change", ("central bank", "rate hike", "rate cut", "fiscal", "policy")),
    ]
    for category, keywords in keyword_map:
        if any(kw in lower for kw in keywords):
            return category
    return "political_instability"


async def _load_live_events(db: AsyncSession, limit: int = 200) -> list[dict]:
    """Load recent classified events and map to signal-event payload shape."""
    repo = EventRepository(db)
    now = datetime.now(UTC)
    start = now - timedelta(hours=48)
    rows = await repo.get_timeline(start=start, end=now, limit=limit)

    mapped: list[dict] = []
    for event in rows:
        if event.severity_score is None:
            continue
        category = _map_classification_to_category(event.classification, event.title)
        mapped.append(
            {
                "id": str(event.id),
                "title": event.title,
                "category": category,
                "region": event.region or "global",
                "severity": float(event.severity_score),
                "ts": event.occurred_at.isoformat(),
            }
        )

    mapped.sort(
        key=lambda evt: (
            float(evt.get("severity", 0.0)),
            evt.get("ts", ""),
        ),
        reverse=True,
    )
    return mapped


def _find_related(asset: AssetDefinition, universe: "AssetUniverse") -> list[str]:
    """Return symbols of assets in the same sector or class."""
    related = [
        a.symbol for a in universe.all()
        if a.symbol != asset.symbol and (a.sector == asset.sector or a.region == asset.region)
    ]
    return related[:4]
