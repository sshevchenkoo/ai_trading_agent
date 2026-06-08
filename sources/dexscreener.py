from datetime import datetime, timezone

import httpx

from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("dexscreener")

BASE_URL = "https://api.dexscreener.com"
BIRDEYE_URL = "https://public-api.birdeye.so"


async def fetch_new_pairs() -> list[TokenSignal]:
    """Poll DexScreener for the latest Solana token profiles."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{BASE_URL}/token-profiles/latest/v1")
            resp.raise_for_status()
            items = resp.json()

        signals = []
        for item in items:
            if item.get("chainId") != "solana":
                continue
            address = item.get("tokenAddress")
            if not address:
                continue
            signals.append(TokenSignal(
                token_address=address,
                symbol=item.get("header", "???")[:10],
                name=item.get("description", "")[:50],
                description=item.get("description", ""),
                source="dexscreener",
            ))

        log.info("dexscreener_polled", count=len(signals))
        return signals

    except Exception as e:
        log.error("dexscreener_poll_failed", error=str(e))
        return []


async def fetch_top_gainers(limit: int = 10) -> list[TokenSignal]:
    """
    Fetch top Solana tokens by 5-minute price gain from Birdeye.
    Catches tokens that are already pumping — different from new pump.fun launches.
    Requires BIRDEYE_API_KEY.
    """
    from config import settings
    if not settings.birdeye_api_key:
        return []

    try:
        headers = {"X-API-KEY": settings.birdeye_api_key, "x-chain": "solana"}
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            resp = await client.get(
                f"{BIRDEYE_URL}/defi/v3/token/list",
                params={
                    "sort_by": "priceChange5mPercent",
                    "sort_type": "desc",
                    "min_liquidity": 1000,
                    "limit": limit,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        items = (data.get("data") or {}).get("items") or []
        signals = []
        for item in items[:limit]:
            address = item.get("address")
            if not address:
                continue
            signals.append(TokenSignal(
                token_address=address,
                symbol=(item.get("symbol") or "???")[:15],
                name=(item.get("name") or "")[:50],
                description="",
                source="dex_top_gainers",
                market_cap_usd=float(item.get("mc") or 0),
                liquidity_sol=0.0,
            ))

        log.info("top_gainers_fetched", count=len(signals))
        return signals

    except Exception as e:
        log.warning("top_gainers_failed", error=str(e))
        return []


async def enrich_signal(signal: TokenSignal) -> TokenSignal:
    """Fetch on-chain metrics for a single token and fill in the signal."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/latest/dex/tokens/{signal.token_address}"
            )
            resp.raise_for_status()
            data = resp.json()

        pairs = data.get("pairs") or []
        if not pairs:
            return signal

        pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))

        liquidity_quote = float(pair.get("liquidity", {}).get("quote", 0) or 0)
        market_cap = float(pair.get("marketCap", 0) or 0)
        txns_h1 = pair.get("txns", {}).get("h1", {})
        buys = int(txns_h1.get("buys", 0) or 0)
        sells = int(txns_h1.get("sells", 0) or 0)

        created_at_ms = pair.get("pairCreatedAt")
        age_minutes = 0
        if created_at_ms:
            created = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc)
            age_minutes = int(
                (datetime.now(tz=timezone.utc) - created).total_seconds() / 60
            )

        if pair.get("baseToken", {}).get("symbol"):
            signal.symbol = pair["baseToken"]["symbol"]
        if pair.get("baseToken", {}).get("name"):
            signal.name = pair["baseToken"]["name"]

        signal.liquidity_sol = liquidity_quote
        signal.market_cap_usd = market_cap
        signal.buy_count_1h = buys
        signal.sell_count_1h = sells
        signal.age_minutes = age_minutes

        log.debug(
            "enriched",
            symbol=signal.symbol,
            liquidity_sol=round(signal.liquidity_sol, 1),
            age_minutes=age_minutes,
        )

    except Exception as e:
        log.warning("enrich_failed", symbol=signal.symbol, error=str(e))

    return signal
