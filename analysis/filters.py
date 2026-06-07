from dataclasses import dataclass
from config import settings
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("filters")

NARRATIVE_BLACKLIST = {
    "elon", "musk", "trump", "biden", "pepe", "doge",
    "shib", "floki", "inu", "moon", "safe",
    "baby", "mini", "micro", "super", "mega",
    "100x", "1000x", "guaranteed", "presale",
}


@dataclass
class FilterResult:
    passed: bool
    score: float
    reason: str = ""


def apply_filters(signal: TokenSignal) -> FilterResult:
    name_lower = (signal.name + " " + signal.symbol).lower()

    # Liquidity
    if signal.liquidity_sol < settings.min_liquidity_sol:
        return FilterResult(False, 0, f"liquidity_too_low={signal.liquidity_sol:.1f}SOL")
    if signal.liquidity_sol > 10_000:
        return FilterResult(False, 0, f"liquidity_too_high={signal.liquidity_sol:.0f}SOL")

    # Narrative blacklist (only check if name is known)
    if signal.name and signal.symbol:
        for word in NARRATIVE_BLACKLIST:
            if word in name_lower:
                return FilterResult(False, 0, f"blacklist_narrative={word}")

    # Dev sold
    if signal.dev_wallet_sold:
        return FilterResult(False, 0, "dev_wallet_sold")

    # Age (only for new tokens)
    if signal.source == "pumpfun" and signal.age_minutes > 60:
        return FilterResult(False, 0, f"token_too_old={signal.age_minutes}min")

    # Buy/sell ratio (only if we have data)
    if signal.buy_count_1h > 0 or signal.sell_count_1h > 0:
        if signal.sell_count_1h > 0 and signal.buy_sell_ratio < 1.5:
            return FilterResult(False, 0, f"low_buy_sell_ratio={signal.buy_sell_ratio:.2f}")
        if signal.buy_count_1h + signal.sell_count_1h < 20 and signal.age_minutes > 10:
            return FilterResult(False, 0, "low_txn_volume")

    # Score calculation
    score = 5.0

    # Liquidity bonus
    if signal.liquidity_sol >= 200:
        score += 1.0
    elif signal.liquidity_sol >= 100:
        score += 0.5

    # Buy pressure
    if signal.buy_sell_ratio >= 3:
        score += 1.0
    elif signal.buy_sell_ratio >= 2:
        score += 0.5

    # Social signals
    if signal.kol_mentions:
        score += 1.5
    if signal.twitter_mentions_1h >= 10:
        score += 0.5

    log.info(
        "filter_pass",
        symbol=signal.symbol,
        rule_score=round(score, 2),
        liquidity_sol=signal.liquidity_sol,
        ratio=round(signal.buy_sell_ratio, 2),
    )

    return FilterResult(True, round(score, 2))
