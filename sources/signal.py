from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TokenSignal:
    token_address: str
    symbol: str
    name: str
    description: str
    source: str  # pumpfun | dexscreener | twitter
    triggered_at: datetime = field(default_factory=datetime.utcnow)

    # Token metrics
    liquidity_sol: float = 0.0
    market_cap_usd: float = 0.0
    holder_count: int = 0
    top10_holder_pct: float = 0.0
    dev_wallet_sold: bool = False
    age_minutes: int = 0
    buy_count_1h: int = 0
    sell_count_1h: int = 0
    creator: str = ""

    # Social signals
    twitter_mentions_1h: int = 0
    kol_mentions: list = field(default_factory=list)
    tweet_texts: list = field(default_factory=list)

    # Scores (filled later)
    rule_score: float = 0.0
    ai_score: float = 0.0
    final_score: float = 0.0

    @property
    def buy_sell_ratio(self) -> float:
        if self.sell_count_1h == 0:
            return float(self.buy_count_1h)
        return self.buy_count_1h / self.sell_count_1h
