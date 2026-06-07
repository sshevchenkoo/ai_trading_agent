from datetime import datetime, timezone

import httpx

from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("dexscreener")

BASE_URL = "https://api.dexscreener.com"


async def enrich_signal(signal: TokenSignal) -> TokenSignal:
    """Fetch on-chain metrics from DexScreener and fill in the signal."""
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

        # Pick the pair with highest liquidity
        pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))

        liquidity_quote = pair.get("liquidity", {}).get("quote", 0) or 0
        liquidity_usd = pair.get("liquidity", {}).get("usd", 0) or 0
        price_usd = float(pair.get("priceUsd", 0) or 0)
        market_cap = float(pair.get("marketCap", 0) or 0)

        txns_h1 = pair.get("txns", {}).get("h1", {})
        buys = int(txns_h1.get("buys", 0) or 0)
        sells = int(txns_h1.get("sells", 0) or 0)

        created_at_ms = pair.get("pairCreatedAt")
        age_minutes = 0
        if created_at_ms:
            created = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc)
            age_minutes = int((datetime.now(tz=timezone.utc) - created).total_seconds() / 60)

        signal.liquidity_sol = float(liquidity_quote)
        signal.market_cap_usd = market_cap or liquidity_usd
        signal.buy_count_1h = buys
        signal.sell_count_1h = sells
        signal.age_minutes = age_minutes

        log.debug(
            "dexscreener_enriched",
            symbol=signal.symbol,
            liquidity_sol=signal.liquidity_sol,
            age_minutes=age_minutes,
            buys=buys,
            sells=sells,
        )
    except Exception as e:
        log.warning("dexscreener_fetch_failed", symbol=signal.symbol, error=str(e))

    return signal
