import httpx
from utils.logger import get_logger

log = get_logger("rugcheck")

RUGCHECK_API = "https://api.rugcheck.xyz/v1"
MIN_SAFE_SCORE = 500


async def check_token(token_address: str) -> dict:
    """
    Returns dict with:
      - is_safe: bool
      - score: int (higher = safer)
      - risks: list of risk strings
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{RUGCHECK_API}/tokens/{token_address}/report/summary")
            resp.raise_for_status()
            data = resp.json()

        score = data.get("score", 0)
        risks = [r.get("name", "") for r in data.get("risks", [])]
        is_safe = score >= MIN_SAFE_SCORE

        log.debug(
            "rugcheck_result",
            token=token_address[:8] + "...",
            score=score,
            is_safe=is_safe,
            risks=risks[:3],
        )

        return {"is_safe": is_safe, "score": score, "risks": risks}

    except Exception as e:
        log.warning("rugcheck_failed", token=token_address[:8] + "...", error=str(e))
        # On failure, don't block — let it through with a warning
        return {"is_safe": True, "score": -1, "risks": ["rugcheck_unavailable"]}
