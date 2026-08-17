from __future__ import annotations

import pytest

from app.services.market.base_provider import MarketDataPoint
from app.services.market.market_service import UnifiedMarketService


def point(symbol: str, asset_class: str, price: float = 100.0) -> MarketDataPoint:
    return MarketDataPoint(
        symbol=symbol,
        asset_class=asset_class,
        price=price,
        change=1.2,
        timestamp=1,
        source="test",
        name=symbol,
    )


@pytest.mark.asyncio
async def test_get_by_asset_class_supports_etfs_and_indices(monkeypatch) -> None:
    service = UnifiedMarketService()

    async def fake_etfs():
        return [point("SPY", "etfs")]

    async def fake_indices():
        return [point("SPX", "indices", 5000.0)]

    monkeypatch.setattr(service, "_fetch_etfs", fake_etfs)
    monkeypatch.setattr(service, "_fetch_indices", fake_indices)

    etfs = await service.get_by_asset_class("etfs")
    indices = await service.get_by_asset_class("indices")

    assert etfs["count"] == 1
    assert etfs["data"][0]["symbol"] == "SPY"
    assert etfs["data"][0]["status"] == "ok"
    assert indices["count"] == 1
    assert indices["data"][0]["symbol"] == "SPX"


@pytest.mark.asyncio
async def test_get_all_markets_includes_etfs_and_indices(monkeypatch) -> None:
    service = UnifiedMarketService()

    async def fake_stocks():
        return [point("AAPL", "stocks")]

    async def fake_crypto():
        return [point("BTC", "crypto")]

    async def fake_forex():
        return [point("EURUSD", "forex", 1.1)]

    async def fake_commodities():
        return [point("XAUUSD", "commodities", 2400.0)]

    async def fake_bonds():
        return [point("US10Y", "bonds", 4.2)]

    async def fake_etfs():
        return [point("SPY", "etfs")]

    async def fake_indices():
        return [point("SPX", "indices", 5000.0)]

    monkeypatch.setattr(service, "_fetch_stocks", fake_stocks)
    monkeypatch.setattr(service, "_fetch_crypto", fake_crypto)
    monkeypatch.setattr(service, "_fetch_forex", fake_forex)
    monkeypatch.setattr(service, "_fetch_commodities", fake_commodities)
    monkeypatch.setattr(service, "_fetch_bonds", fake_bonds)
    monkeypatch.setattr(service, "_fetch_etfs", fake_etfs)
    monkeypatch.setattr(service, "_fetch_indices", fake_indices)

    response = await service.get_all_markets()

    assert response["count"] == 7
    assert set(response["data"]) == {
        "stocks",
        "crypto",
        "forex",
        "commodities",
        "bonds",
        "etfs",
        "indices",
    }
    assert response["data"]["etfs"][0]["symbol"] == "SPY"
    assert response["data"]["indices"][0]["symbol"] == "SPX"


@pytest.mark.asyncio
async def test_backfill_fills_only_missing_symbols(monkeypatch) -> None:
    """A partial primary outage is topped up per symbol, not all-or-nothing."""
    service = UnifiedMarketService()

    primary = [
        point("AAPL", "stocks"),
        MarketDataPoint.unavailable("MSFT", "stocks", "alpaca"),
    ]
    asked: list[list[str]] = []

    async def fallback(missing):
        asked.append(missing)
        return [point("MSFT", "stocks", 400.0)]

    rows = await service._backfill(["AAPL", "MSFT"], primary, "stocks", fallback)

    assert asked == [["MSFT"]], "fallback should only be asked for the missing symbol"
    assert [r.symbol for r in rows] == ["AAPL", "MSFT"]
    assert all(r.status == "ok" for r in rows)
    assert rows[1].price == 400.0


@pytest.mark.asyncio
async def test_backfill_chains_fallbacks_in_order() -> None:
    """Each fallback only sees what the previous one could not price."""
    service = UnifiedMarketService()

    async def first(missing):
        return [point("B", "stocks")]

    async def second(missing):
        assert missing == ["C"]
        return [point("C", "stocks")]

    rows = await service._backfill(["A", "B", "C"], [point("A", "stocks")], "stocks", first, second)

    assert [r.symbol for r in rows] == ["A", "B", "C"]
    assert all(r.status == "ok" for r in rows)


@pytest.mark.asyncio
async def test_backfill_marks_unpriceable_symbols_unavailable() -> None:
    """Symbols no provider can price stay in the list, flagged as unavailable."""
    service = UnifiedMarketService()

    async def fallback(missing):
        return []

    rows = await service._backfill(["A", "B"], [point("A", "stocks")], "stocks", fallback)

    assert [r.symbol for r in rows] == ["A", "B"]
    assert rows[1].status == "unavailable"
    assert rows[1].price == 0.0


@pytest.mark.asyncio
async def test_fetch_commodities_uses_reference_fallback_when_providers_fail(monkeypatch) -> None:
    """Commodity rows should not collapse to zero when upstreams are throttled."""
    service = UnifiedMarketService()

    symbols = ["WTI", "COPPER"]

    async def primary(_symbols):
        return [
            MarketDataPoint.unavailable(symbol, "commodities", "twelvedata")
            for symbol in _symbols
        ]

    async def yahoo(_missing):
        return []

    async def etf_proxy(_missing):
        return []

    monkeypatch.setattr(service.commodities, "get_default_symbols", lambda: symbols)
    monkeypatch.setattr(service.commodities, "fetch_prices", primary)
    monkeypatch.setattr(service.yahoo, "fetch_commodities", yahoo)
    monkeypatch.setattr(service, "_derive_commodities_from_etfs", etf_proxy)

    rows = await service._fetch_commodities()

    assert [row.symbol for row in rows] == symbols
    assert all(row.status == "ok" for row in rows)
    assert all(row.price > 0 for row in rows)
    assert all(row.source == "reference" for row in rows)
    assert all(row.data_status == "reference" for row in rows)
    assert any(row.change != 0 for row in rows)


@pytest.mark.asyncio
async def test_fetch_class_reuses_recent_result(monkeypatch) -> None:
    """Repeated calls inside the TTL hit the provider once."""
    service = UnifiedMarketService()
    calls = 0

    async def fake_bonds():
        nonlocal calls
        calls += 1
        return [point("US10Y", "bonds", 4.2)]

    monkeypatch.setattr(service, "_fetch_bonds", fake_bonds)

    first = await service._fetch_class("bonds")
    second = await service._fetch_class("bonds")

    assert calls == 1
    assert first == second


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_fetch(monkeypatch) -> None:
    """Simultaneous requests for a class do not stampede the provider."""
    import asyncio

    service = UnifiedMarketService()
    calls = 0

    async def fake_stocks():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return [point("AAPL", "stocks")]

    monkeypatch.setattr(service, "_fetch_stocks", fake_stocks)

    await asyncio.gather(*(service._fetch_class("stocks") for _ in range(5)))

    assert calls == 1


@pytest.mark.asyncio
async def test_get_by_asset_class_rejects_unknown_class() -> None:
    service = UnifiedMarketService()
    result = await service.get_by_asset_class("nonsense")
    assert "error" in result
    assert "etfs" in result["valid_classes"]
