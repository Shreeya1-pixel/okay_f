"""Unified Market Service.

Coordinates all market data providers and returns unified responses.
This is the core service for the market data module.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Awaitable, Callable, Dict, List, Optional, Any

from app.core.logging import get_logger
from app.services.market.base_provider import MarketDataPoint
from app.services.market.alpaca_provider import get_alpaca_provider
from app.services.market.coingecko_provider import get_coingecko_provider
from app.services.market.forex_provider import get_forex_provider
from app.services.market.commodities_provider import get_commodities_provider
from app.services.market.fred_provider import get_fred_provider
from app.services.market.yahoo_provider import get_yahoo_provider
from app.services.market.finnhub_provider import get_finnhub_provider

logger = get_logger(__name__)

ASSET_CLASSES = ("stocks", "crypto", "forex", "commodities", "bonds", "etfs", "indices")

# Providers are polled at most this often; concurrent callers share one fetch so
# a browser refreshing every few seconds cannot exhaust upstream rate limits.
# Classes served by one cheap batch request refresh fastest; classes that cost a
# request per symbol refresh more slowly to stay inside free-tier quotas.
FETCH_TTL_SECONDS = 15.0
FETCH_TTL_OVERRIDES = {
    "crypto": 30.0,       # one CoinGecko request covers the whole list
    "bonds": 300.0,       # FRED publishes daily, polling faster gains nothing
    "stocks": 60.0,       # per-symbol fallback paths are quota constrained
    "forex": 60.0,
    "commodities": 60.0,
    "etfs": 60.0,
    "indices": 60.0,
}

# How long a symbol's last good price stays usable when every provider fails for
# it. Free-tier upstreams throttle intermittently; showing the most recent real
# price (tagged with a ':cached' source) beats blanking the asset out entirely.
LAST_GOOD_TTL_SECONDS = 600.0


class UnifiedMarketService:
    """Core service that coordinates all market data providers.

    Responsibilities:
    - Call all providers concurrently
    - Merge results into unified format
    - Provide filtered access by asset class
    - Handle errors gracefully
    """

    def __init__(self) -> None:
        self.alpaca = get_alpaca_provider()
        self.coingecko = get_coingecko_provider()
        self.forex = get_forex_provider()
        self.commodities = get_commodities_provider()
        self.fred = get_fred_provider()
        self.yahoo = get_yahoo_provider()
        self.finnhub = get_finnhub_provider()

        # In-memory cache for latest data
        self._cache: Dict[str, MarketDataPoint] = {}
        self._last_update: Optional[datetime] = None

        # Per-asset-class fetch cache: class -> (fetched_at, rows)
        self._class_cache: Dict[str, tuple[float, List[MarketDataPoint]]] = {}
        self._class_locks: Dict[str, asyncio.Lock] = {c: asyncio.Lock() for c in ASSET_CLASSES}

        # Last successfully priced row per symbol: symbol -> (fetched_at, point)
        self._last_good: Dict[str, tuple[float, MarketDataPoint]] = {}

    async def get_all_markets(self) -> Dict[str, Any]:
        """Fetch all market data from all providers.

        Two-phase fetch: primary classes first (stocks, crypto, forex, bonds,
        etfs) populate the cache, then dependent classes (indices, commodities)
        can derive from cached ETF data when their primary sources are down.
        """
        logger.info("Fetching all market data")

        # ETF prices are dependency data for commodity/index proxy derivation.
        # Fetch them before stock gap-filling can spend the shared Finnhub quota.
        primary = ("crypto", "forex", "bonds", "etfs")
        derived = ("indices", "commodities")

        primary_results = await asyncio.gather(
            *(self._fetch_class(ac) for ac in primary),
            return_exceptions=True,
        )

        all_data: Dict[str, List[Dict[str, Any]]] = {}
        for asset_class, result in zip(primary, primary_results):
            if isinstance(result, list):
                all_data[asset_class] = [row.to_dict() for row in result]
            else:
                logger.error(f"{asset_class} fetch error: {result}")
                all_data[asset_class] = [
                    MarketDataPoint.unavailable(
                        sym, asset_class, self._source_for(asset_class)
                    ).to_dict()
                    for sym in self._symbols_for(asset_class)
                ]

        # Populate cache so ETF proxy derivation can use it
        self._update_cache_from_data(all_data)

        # Phase 2: fetch classes that can derive from cached ETF data
        derived_results = await asyncio.gather(
            *(self._fetch_class(ac) for ac in derived),
            return_exceptions=True,
        )
        for asset_class, result in zip(derived, derived_results):
            if isinstance(result, list):
                all_data[asset_class] = [row.to_dict() for row in result]
            else:
                logger.error(f"{asset_class} fetch error: {result}")
                all_data[asset_class] = [
                    MarketDataPoint.unavailable(
                        sym, asset_class, self._source_for(asset_class)
                    ).to_dict()
                    for sym in self._symbols_for(asset_class)
                ]

        self._update_cache_from_data(all_data)

        stock_rows = await self._fetch_class("stocks")
        all_data["stocks"] = [row.to_dict() for row in stock_rows]
        self._update_cache_from_data({"stocks": all_data["stocks"]})
        self._last_update = datetime.now(UTC)

        return {
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "count": sum(len(v) for v in all_data.values()),
            "data": all_data,
            "counts": {k: len(v) for k, v in all_data.items()},
        }

    def _update_cache_from_data(self, all_data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Update the in-memory cache from fetched market data."""
        for asset_class, items in all_data.items():
            for item in items:
                if "symbol" in item and item.get("price", 0) > 0:
                    self._cache[item["symbol"]] = MarketDataPoint(
                        symbol=item["symbol"],
                        asset_class=asset_class,
                        price=item.get("price", 0),
                        change=item.get("change", 0),
                        timestamp=item.get("timestamp", 0),
                        source=item.get("source", "unknown"),
                        volume=item.get("volume", 0),
                        high_24h=item.get("high_24h", 0),
                        low_24h=item.get("low_24h", 0),
                        open_24h=item.get("open_24h", 0),
                        name=item.get("name", item["symbol"]),
                        status=item.get("status", "ok"),
                        currency=item.get("currency", "USD"),
                        market_cap=item.get("market_cap", 0),
                        data_status=item.get("data_status", "live"),
                    )

    async def get_by_asset_class(self, asset_class: str) -> Dict[str, Any]:
        """Get market data for a specific asset class.

        Args:
            asset_class: One of "stocks", "crypto", "forex", "commodities", "bonds", "etfs", "indices"

        Returns:
            Market data for the specified asset class
        """
        asset_class = asset_class.lower()

        if asset_class not in ASSET_CLASSES:
            return {
                "error": f"Unknown asset class: {asset_class}",
                "valid_classes": list(ASSET_CLASSES),
            }

        data = await self._fetch_class(asset_class)
        return {
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "count": len(data),
            "asset_class": asset_class,
            "data": [d.to_dict() for d in data],
        }

    async def _fetch_class(self, asset_class: str) -> List[MarketDataPoint]:
        """Fetch one asset class, reusing a recent result when one exists.

        Concurrent callers for the same class share a single upstream fetch.
        """
        fetchers: Dict[str, Callable[[], Awaitable[List[MarketDataPoint]]]] = {
            "stocks": self._fetch_stocks,
            "crypto": self._fetch_crypto,
            "forex": self._fetch_forex,
            "commodities": self._fetch_commodities,
            "bonds": self._fetch_bonds,
            "etfs": self._fetch_etfs,
            "indices": self._fetch_indices,
        }

        cached = self._fresh_cache(asset_class)
        if cached is not None:
            return cached

        async with self._class_locks[asset_class]:
            # Another caller may have refreshed while we waited for the lock.
            cached = self._fresh_cache(asset_class)
            if cached is not None:
                return cached

            rows = await fetchers[asset_class]()
            self._class_cache[asset_class] = (asyncio.get_running_loop().time(), rows)
            return rows

    def _fresh_cache(self, asset_class: str) -> Optional[List[MarketDataPoint]]:
        """Return cached rows for the class when still inside the TTL."""
        entry = self._class_cache.get(asset_class)
        if entry is None:
            return None
        fetched_at, rows = entry
        ttl = FETCH_TTL_OVERRIDES.get(asset_class, FETCH_TTL_SECONDS)
        if asyncio.get_running_loop().time() - fetched_at < ttl:
            return rows
        return None

    def _symbols_for(self, asset_class: str) -> List[str]:
        """Return the configured symbol universe for an asset class."""
        if asset_class == "stocks":
            return self.alpaca.get_stock_symbols()
        if asset_class == "crypto":
            return self.coingecko.get_default_symbols()
        if asset_class == "forex":
            return self.forex.get_default_symbols()
        if asset_class == "commodities":
            return self.commodities.get_default_symbols()
        if asset_class == "bonds":
            return self.fred.get_default_symbols()
        if asset_class == "etfs":
            return self.alpaca.get_etf_symbols()
        if asset_class == "indices":
            return self.yahoo.get_index_symbols()
        return []

    def _source_for(self, asset_class: str) -> str:
        """Return the primary provider name for an asset class."""
        return {
            "stocks": self.alpaca.name,
            "crypto": self.coingecko.name,
            "forex": self.forex.name,
            "commodities": self.commodities.name,
            "bonds": self.fred.name,
            "etfs": self.alpaca.name,
            "indices": self.yahoo.name,
        }.get(asset_class, "unknown")

    async def _fetch_stocks(self) -> List[MarketDataPoint]:
        """Fetch stock prices from Alpaca, backfilling gaps from Finnhub+Yahoo."""
        symbols = self.alpaca.get_stock_symbols()
        results: List[MarketDataPoint] = []
        if self.alpaca.is_configured:
            try:
                results = await self.alpaca.fetch_prices(symbols)
            except Exception as e:
                logger.warning(f"Stocks Alpaca fetch failed: {e}")

        return await self._backfill(
            symbols,
            results,
            "stocks",
            lambda missing: self.finnhub.fetch_symbols(missing, "stocks"),
            lambda missing: self.yahoo.fetch_symbols(missing, "stocks"),
        )

    async def _fetch_crypto(self) -> List[MarketDataPoint]:
        """Fetch crypto prices from CoinGecko."""
        symbols = self.coingecko.get_default_symbols()
        try:
            results = await self.coingecko.fetch_prices(symbols)
        except Exception as e:
            logger.warning(f"Crypto fetch failed: {e}")
            return [MarketDataPoint.unavailable(sym, "crypto", self.coingecko.name) for sym in symbols]

        # CoinGecko returns the live top-N by market cap, which need not match the
        # configured list, so keep every live row rather than reindexing by symbol.
        live = [r for r in results if r.price > 0 and r.status == "ok"]
        if live:
            now = self._now()
            for row in live:
                self._last_good[row.symbol] = (now, row)
            return live

        logger.warning("CoinGecko returned no live prices (likely rate limited)")
        return self._reindex(symbols, [], "crypto", self.coingecko.name)

    async def _fetch_forex(self) -> List[MarketDataPoint]:
        """Fetch forex rates, backfilling gaps from Yahoo's keyless FX feed."""
        symbols = self.forex.get_default_symbols()
        results: List[MarketDataPoint] = []
        try:
            results = await self.forex.fetch_prices(symbols)
        except Exception as e:
            logger.warning(f"Forex fetch failed: {e}")

        return await self._backfill(
            symbols,
            results,
            "forex",
            lambda missing: self.yahoo.fetch_forex(missing),
            lambda missing: self.forex.fetch_reference_rates(missing),
        )

    async def _fetch_commodities(self) -> List[MarketDataPoint]:
        """Fetch commodity prices, backfilling from Yahoo futures and ETF proxies."""
        symbols = self.commodities.get_default_symbols()
        results: List[MarketDataPoint] = []
        try:
            results = await self.commodities.fetch_prices(symbols)
        except Exception as e:
            logger.warning(f"Commodities fetch failed: {e}")

        rows = await self._backfill(
            symbols,
            results,
            "commodities",
            lambda missing: self.yahoo.fetch_commodities(missing),
            lambda missing: self._derive_commodities_from_etfs(missing),
            lambda missing: self._reference_commodity_prices(missing),
        )
        return rows

    async def _fetch_bonds(self) -> List[MarketDataPoint]:
        """Fetch bond yields from FRED."""
        symbols = self.fred.get_default_symbols()
        try:
            results = await self.fred.fetch_prices(symbols)
        except Exception as e:
            logger.warning(f"Bonds fetch failed: {e}")
            return [MarketDataPoint.unavailable(sym, "bonds", self.fred.name) for sym in symbols]

        return self._reindex(symbols, results, "bonds", self.fred.name)

    async def _fetch_etfs(self) -> List[MarketDataPoint]:
        """Fetch ETF prices from Alpaca, backfilling gaps from Yahoo+Finnhub."""
        symbols = self.alpaca.get_etf_symbols()
        results: List[MarketDataPoint] = []
        if self.alpaca.is_configured:
            try:
                results = await self.alpaca.fetch_etf_prices(symbols)
            except Exception as e:
                logger.warning(f"ETFs Alpaca fetch failed: {e}")

        return await self._backfill(
            symbols,
            results,
            "etfs",
            lambda missing: self.yahoo.fetch_symbols(missing, "etfs"),
            lambda missing: self.finnhub.fetch_symbols(missing, "etfs"),
        )

    async def _fetch_indices(self) -> List[MarketDataPoint]:
        """Fetch equity index levels, deriving from ETF proxies when Yahoo fails."""
        symbols = self.yahoo.get_index_symbols()
        try:
            results = await self.yahoo.fetch_symbols(
                symbols,
                "indices",
                self.yahoo.get_index_symbol_map(),
                self.yahoo.get_index_names(),
            )
        except Exception as e:
            logger.warning(f"Indices fetch failed: {e}")
            results = [MarketDataPoint.unavailable(sym, "indices", self.yahoo.name) for sym in symbols]

        live = {r.symbol: r for r in results if r.price > 0 and r.status == "ok"}
        missing = [s for s in symbols if s not in live]
        if missing:
            derived = await self._derive_indices_from_etfs(missing)
            for d in derived:
                if d.price > 0:
                    live[d.symbol] = d

        return self._reindex(symbols, list(live.values()), "indices", self.yahoo.name)

    # Index → ETF proxy mapping for when Yahoo is unavailable.
    _INDEX_ETF_PROXY = {
        "SPX": "SPY", "NDX": "QQQ", "DJI": "DIA", "RUT": "IWM",
    }
    # Index names for display.
    _INDEX_NAMES = {
        "SPX": "S&P 500", "NDX": "Nasdaq 100", "DJI": "Dow Jones",
        "RUT": "Russell 2000", "DAX": "DAX 40", "FTSE": "FTSE 100",
        "CAC": "CAC 40", "NKY": "Nikkei 225", "HSI": "Hang Seng",
    }
    # Commodity → ETF proxy mapping.
    _COMMODITY_ETF_PROXY = {
        "XAUUSD": "GLD", "XAGUSD": "SLV", "PLATINUM": "PPLT",
        "PALLADIUM": "PALL", "COPPER": "CPER", "WTI": "USO",
        "BRENT": "BNO", "NATGAS": "UNG", "HEATINGOIL": "UHN",
        "CORN": "CORN", "WHEAT": "WEAT", "SOYBEANS": "SOYB",
        "COFFEE": "JO", "SUGAR": "CANE", "COTTON": "BAL",
        "COCOA": "NIB", "ORANGEJUICE": "DBA", "LEANHOGS": "DBA",
        "LIVECATTLE": "DBA", "FEEDERCATTLE": "DBA", "OATS": "DBA",
        "ROUGH_RICE": "DBA", "SOYMEAL": "SOYB", "SOYOIL": "SOYB",
        "LUMBER": "WOOD",
    }
    _COMMODITY_NAMES = {
        "XAUUSD": "Gold", "XAGUSD": "Silver", "WTI": "WTI Crude Oil",
        "BRENT": "Brent Crude", "NATGAS": "Natural Gas", "COPPER": "Copper",
        "PLATINUM": "Platinum", "PALLADIUM": "Palladium",
        "HEATINGOIL": "Heating Oil", "CORN": "Corn", "WHEAT": "Wheat",
        "SOYBEANS": "Soybeans", "COFFEE": "Coffee", "SUGAR": "Sugar",
        "COTTON": "Cotton", "COCOA": "Cocoa", "ORANGEJUICE": "Orange Juice",
        "LEANHOGS": "Lean Hogs", "LIVECATTLE": "Live Cattle",
        "FEEDERCATTLE": "Feeder Cattle", "OATS": "Oats",
        "ROUGH_RICE": "Rough Rice", "SOYMEAL": "Soybean Meal",
        "SOYOIL": "Soybean Oil", "LUMBER": "Lumber",
    }
    _COMMODITY_REFERENCE_CHANGE = {
        "XAUUSD": 0.35, "XAGUSD": 0.55, "PLATINUM": 0.25,
        "PALLADIUM": -0.40, "COPPER": 0.30, "WTI": 0.75,
        "BRENT": 0.65, "NATGAS": -0.80, "HEATINGOIL": 0.45,
        "CORN": -0.20, "WHEAT": 0.40, "SOYBEANS": -0.15,
        "COFFEE": 0.70, "SUGAR": -0.30, "COTTON": 0.20,
        "COCOA": 0.85, "ORANGEJUICE": -0.25, "LEANHOGS": 0.10,
        "LIVECATTLE": 0.18, "FEEDERCATTLE": 0.12, "OATS": -0.10,
        "ROUGH_RICE": 0.08, "SOYMEAL": -0.12, "SOYOIL": 0.16,
        "LUMBER": 0.50,
    }

    async def _derive_from_etf_proxies(
        self,
        missing: List[str],
        proxy_map: dict[str, str],
        names: dict[str, str],
        asset_class: str,
    ) -> List[MarketDataPoint]:
        """Derive asset prices from their ETF proxies.

        First checks the in-memory cache (populated by prior ETF fetches),
        then falls back to a Finnhub call only for ETFs not yet cached.
        """
        proxied = [(sym, proxy_map[sym]) for sym in missing if sym in proxy_map]
        if not proxied:
            return []

        etf_by_sym: dict[str, MarketDataPoint] = {}
        uncached_etfs: list[str] = []
        for _, etf_sym in proxied:
            cached = self._cache.get(etf_sym)
            if cached and cached.price > 0:
                etf_by_sym[etf_sym] = cached
            elif etf_sym not in etf_by_sym:
                uncached_etfs.append(etf_sym)

        if uncached_etfs:
            try:
                live = await self.finnhub.fetch_symbols(list(set(uncached_etfs)), "etfs")
                for r in live:
                    if r.price > 0:
                        etf_by_sym[r.symbol] = r
            except Exception:
                pass

        results: List[MarketDataPoint] = []
        for target_sym, etf_sym in proxied:
            etf = etf_by_sym.get(etf_sym)
            if not etf:
                continue
            results.append(MarketDataPoint(
                symbol=target_sym,
                asset_class=asset_class,
                price=etf.price,
                change=etf.change,
                timestamp=etf.timestamp,
                source=f"derived:{etf.source}",
                volume=etf.volume,
                high_24h=etf.high_24h,
                low_24h=etf.low_24h,
                open_24h=etf.open_24h,
                name=names.get(target_sym, target_sym),
                data_status="delayed",
            ))
        if results:
            logger.info(f"Derived {len(results)} {asset_class} prices from ETF proxies")
        return results

    async def _derive_indices_from_etfs(
        self, missing: List[str],
    ) -> List[MarketDataPoint]:
        return await self._derive_from_etf_proxies(
            missing, self._INDEX_ETF_PROXY, self._INDEX_NAMES, "indices",
        )

    async def _derive_commodities_from_etfs(
        self, missing: List[str],
    ) -> List[MarketDataPoint]:
        return await self._derive_from_etf_proxies(
            missing, self._COMMODITY_ETF_PROXY, self._COMMODITY_NAMES, "commodities",
        )

    async def _reference_commodity_prices(
        self, missing: List[str],
    ) -> List[MarketDataPoint]:
        """Return labeled commodity reference prices when live feeds are exhausted.

        This is the final fallback after real providers and ETF proxies fail. It
        keeps the UI and signal engine out of the misleading all-zero state while
        preserving provenance through source/data_status.
        """
        from app.config.asset_universe import get_asset_universe

        universe = get_asset_universe()
        timestamp = int(datetime.now(UTC).timestamp() * 1000)
        rows: List[MarketDataPoint] = []

        for symbol in missing:
            asset = universe.get_asset(symbol)
            price = float(asset.base_price if asset and asset.base_price > 0 else 100.0)
            change = self._COMMODITY_REFERENCE_CHANGE.get(symbol, 0.0)
            previous = price / (1 + change / 100) if change != -100 else price
            day_range = max(abs(change) / 100, 0.004)
            rows.append(MarketDataPoint(
                symbol=symbol,
                asset_class="commodities",
                price=round(price, 6),
                change=round(change, 4),
                timestamp=timestamp,
                source="reference",
                volume=0.0,
                high_24h=round(price * (1 + day_range / 2), 6),
                low_24h=round(price * (1 - day_range / 2), 6),
                open_24h=round(previous, 6),
                name=self._COMMODITY_NAMES.get(symbol, asset.label if asset else symbol),
                data_status="reference",
            ))

        if rows:
            logger.warning(
                f"commodities: using reference fallback for {len(rows)} symbols"
            )
        return rows

    async def _backfill(
        self,
        symbols: List[str],
        results: List[MarketDataPoint],
        asset_class: str,
        *fallbacks: Callable[[List[str]], Awaitable[List[MarketDataPoint]]],
    ) -> List[MarketDataPoint]:
        """Fill every symbol the primary provider could not price from a fallback.

        Runs per symbol rather than all-or-nothing, so a partial provider outage
        (or an unset API key) still yields a complete asset list. Fallbacks are
        tried in order and each one only sees the symbols still missing.
        """
        live = {r.symbol: r for r in results if r.price > 0 and r.status == "ok"}

        for fallback in fallbacks:
            missing = [sym for sym in symbols if sym not in live]
            if not missing:
                break

            logger.info(
                f"{asset_class}: backfilling {len(missing)}/{len(symbols)} symbols from fallback"
            )
            try:
                for row in await fallback(missing):
                    if row.price > 0 and row.status == "ok":
                        live[row.symbol] = row
            except Exception as e:
                logger.warning(f"{asset_class} fallback failed: {e}")

        return self._reindex(symbols, list(live.values()), asset_class, self._source_for(asset_class))

    def _reindex(
        self,
        symbols: List[str],
        results: List[MarketDataPoint],
        asset_class: str,
        source: str,
    ) -> List[MarketDataPoint]:
        """Return one row per configured symbol, in configured order.

        Symbols nothing could price this cycle fall back to their most recent
        real price while it is still recent enough to be meaningful.
        """
        by_symbol = {r.symbol: r for r in results}
        now = self._now()

        rows: List[MarketDataPoint] = []
        for sym in symbols:
            row = by_symbol.get(sym)
            if row is not None and row.price > 0 and row.status == "ok":
                self._last_good[sym] = (now, row)
                rows.append(row)
                continue

            recovered = self._last_good_point(sym, asset_class, now)
            rows.append(
                recovered
                or row
                or MarketDataPoint.unavailable(sym, asset_class, source)
            )

        stale = sum(1 for r in rows if r.source.endswith(":cached"))
        unavailable = sum(1 for r in rows if r.status != "ok")
        if unavailable or stale:
            logger.warning(
                f"{asset_class}: {unavailable}/{len(rows)} unavailable, "
                f"{stale}/{len(rows)} served from last known price"
            )
        return rows

    def _last_good_point(
        self,
        symbol: str,
        asset_class: str,
        now: float,
    ) -> Optional[MarketDataPoint]:
        """Return the last real price for a symbol if it is still recent."""
        entry = self._last_good.get(symbol)
        if entry is None:
            return None

        fetched_at, point = entry
        if now - fetched_at > LAST_GOOD_TTL_SECONDS:
            del self._last_good[symbol]
            return None

        source = point.source if point.source.endswith(":cached") else f"{point.source}:cached"
        return MarketDataPoint(
            symbol=point.symbol,
            asset_class=asset_class,
            price=point.price,
            change=point.change,
            timestamp=point.timestamp,
            source=source,
            volume=point.volume,
            high_24h=point.high_24h,
            low_24h=point.low_24h,
            open_24h=point.open_24h,
            name=point.name,
            currency=point.currency,
            market_cap=point.market_cap,
            data_status="stale",
        )

    @staticmethod
    def _now() -> float:
        """Monotonic clock that also works outside a running event loop."""
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return 0.0

    def get_cached(self, symbol: str) -> Optional[MarketDataPoint]:
        """Get cached data for a symbol."""
        return self._cache.get(symbol)

    def get_all_cached(self) -> Dict[str, Any]:
        """Get all cached market data."""
        return {
            "timestamp": int(datetime.now(UTC).timestamp() * 1000) if self._last_update else 0,
            "count": len(self._cache),
            "data": {sym: dp.to_dict() for sym, dp in self._cache.items()}
        }

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "cached_symbols": len(self._cache),
            "providers": {
                "stocks": self.alpaca.name,
                "crypto": self.coingecko.name,
                "forex": self.forex.name,
                "commodities": self.commodities.name,
                "bonds": self.fred.name,
                "etfs": self.alpaca.name,
                "indices": self.yahoo.name,
                "fallback": self.yahoo.name,
            },
            "universe": {c: len(self._symbols_for(c)) for c in ASSET_CLASSES},
        }


# Singleton factory
_market_service: Optional[UnifiedMarketService] = None


def get_unified_market_service() -> UnifiedMarketService:
    """Get Unified Market Service singleton."""
    global _market_service
    if _market_service is None:
        _market_service = UnifiedMarketService()
    return _market_service


# Convenience functions for API endpoints
async def get_all_markets() -> Dict[str, Any]:
    """Fetch all market data."""
    service = get_unified_market_service()
    return await service.get_all_markets()


async def get_by_asset_class(asset_class: str) -> Dict[str, Any]:
    """Get market data by asset class."""
    service = get_unified_market_service()
    return await service.get_by_asset_class(asset_class)


async def get_stocks() -> Dict[str, Any]:
    """Get stock market data."""
    return await get_by_asset_class("stocks")


async def get_crypto() -> Dict[str, Any]:
    """Get crypto market data."""
    return await get_by_asset_class("crypto")


async def get_forex() -> Dict[str, Any]:
    """Get forex market data."""
    return await get_by_asset_class("forex")


async def get_commodities() -> Dict[str, Any]:
    """Get commodities market data."""
    return await get_by_asset_class("commodities")


async def get_bonds() -> Dict[str, Any]:
    """Get bond market data."""
    return await get_by_asset_class("bonds")


async def get_etfs() -> Dict[str, Any]:
    """Get ETF market data."""
    return await get_by_asset_class("etfs")


async def get_indices() -> Dict[str, Any]:
    """Get equity index market data."""
    return await get_by_asset_class("indices")
