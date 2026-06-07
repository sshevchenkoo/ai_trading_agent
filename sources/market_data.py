import httpx
from sources.signal import MarketContext
from utils.logger import get_logger

log = get_logger("market_data")

COINGECKO_URL = "https://api.coingecko.com/api/v3"

# Module-level cache — refresh once per poll cycle, not per token
_cached: MarketContext | None = None


async def get_market_context() -> MarketContext:
    global _cached
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{COINGECKO_URL}/simple/price",
                params={
                    "ids": "solana,bitcoin",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        sol_price = data["solana"]["usd"]
        sol_change = data["solana"]["usd_24h_change"]
        btc_change = data["bitcoin"]["usd_24h_change"]

        if sol_change > 3:
            trend = "bullish"
        elif sol_change < -3:
            trend = "bearish"
        else:
            trend = "neutral"

        ctx = MarketContext(
            sol_price_usd=sol_price,
            sol_change_24h_pct=round(sol_change, 2),
            btc_change_24h_pct=round(btc_change, 2),
            market_trend=trend,
        )
        _cached = ctx
        log.info(
            "market_context",
            sol=sol_price,
            sol_24h=sol_change,
            trend=trend,
        )
        return ctx

    except Exception as e:
        log.warning("market_data_failed", error=str(e))
        return _cached or MarketContext()
