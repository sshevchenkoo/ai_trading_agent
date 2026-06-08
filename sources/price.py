import httpx
from utils.logger import get_logger

log = get_logger("price")


async def get_token_price_usd(token_address: str) -> float | None:
    """Fetch current token price via DexScreener (free, no API key)."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            )
            resp.raise_for_status()
            data = resp.json()

        pairs = data.get("pairs") or []
        if not pairs:
            return None

        pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        price = pair.get("priceUsd")
        return float(price) if price else None

    except Exception as e:
        log.warning("price_fetch_failed", token=token_address[:8], error=str(e))
        return None
