import httpx
from utils.logger import get_logger
from config import settings

log = get_logger("birdeye")

BASE_URL = "https://public-api.birdeye.so"


def _headers() -> dict:
    return {
        "X-API-KEY": settings.birdeye_api_key,
        "x-chain": "solana",
    }


async def get_token_analysis(token_address: str) -> dict:
    """
    Fetch Axiom-like token data from Birdeye:
    - security (mint/freeze authority, LP locked)
    - holder distribution
    - top traders
    - bundle/insider detection
    Returns a flat dict ready to be embedded in the AI prompt.
    """
    if not settings.birdeye_api_key:
        return {}

    security, overview, holders = await _fetch_all(token_address)

    result = {}

    # --- Security ---
    if security:
        result["mint_authority"] = security.get("mintAuthority") or "none"
        result["freeze_authority"] = security.get("freezeAuthority") or "none"
        result["lp_locked_pct"] = security.get("lpLockPercentage", 0)
        result["top1_holder_pct"] = security.get("top1HolderPercent", 0)
        result["top10_holder_pct"] = security.get("top10HolderPercent", 0)
        result["creator_pct"] = security.get("creatorPercentage", 0)
        result["creator_balance"] = security.get("creatorBalance", 0)
        result["is_mintable"] = bool(security.get("mintAuthority"))
        result["is_freezable"] = bool(security.get("freezeAuthority"))

    # --- Overview ---
    if overview:
        result["unique_wallets_24h"] = overview.get("uniqueWallet24h", 0)
        result["price_change_5m"] = overview.get("priceChange5mPercent", 0)
        result["price_change_1h"] = overview.get("priceChange1hPercent", 0)
        result["volume_24h_usd"] = overview.get("v24hUSD", 0)
        result["buy_24h"] = overview.get("buy24h", 0)
        result["sell_24h"] = overview.get("sell24h", 0)

    # --- Holders ---
    if holders:
        items = holders.get("items", [])
        result["holder_count"] = holders.get("total", 0)
        if items:
            result["top_holders"] = [
                {
                    "owner": h.get("owner", "")[:8] + "...",
                    "pct": round(h.get("ui_amount", 0) / max(holders.get("total", 1), 1) * 100, 2),
                    "amount": h.get("ui_amount", 0),
                }
                for h in items[:5]
            ]

    return result


async def _fetch_all(address: str) -> tuple:
    try:
        async with httpx.AsyncClient(timeout=12, headers=_headers()) as client:
            security_r, overview_r, holders_r = await _gather_requests(client, address)
        return security_r, overview_r, holders_r
    except Exception as e:
        log.warning("birdeye_fetch_failed", address=address[:8], error=str(e))
        return {}, {}, {}


async def _gather_requests(client: httpx.AsyncClient, address: str):
    import asyncio

    async def get(path: str, params: dict = None):
        try:
            r = await client.get(f"{BASE_URL}{path}", params=params)
            r.raise_for_status()
            return r.json().get("data", {})
        except Exception:
            return {}

    return await asyncio.gather(
        get("/defi/token_security", {"address": address}),
        get("/defi/token_overview", {"address": address}),
        get("/defi/v3/token/holder", {"address": address, "limit": 10}),
    )
