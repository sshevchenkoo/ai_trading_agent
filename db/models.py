from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Token(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    address: str = Field(index=True, unique=True)
    symbol: str
    name: str
    description: str = ""
    creator: str = ""
    source: str  # pumpfun | dexscreener | twitter
    seen_at: datetime = Field(default_factory=datetime.utcnow)

    # Metrics at time of discovery
    liquidity_sol: float = 0.0
    market_cap_usd: float = 0.0
    holder_count: int = 0
    top10_holder_pct: float = 0.0
    dev_wallet_sold: bool = False
    age_minutes: int = 0
    buy_count_1h: int = 0
    sell_count_1h: int = 0

    # Scores
    rule_score: Optional[float] = None
    ai_score: Optional[float] = None
    final_score: Optional[float] = None
    passed_filters: bool = False


class Signal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token_address: str = Field(index=True)
    source: str
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    raw_data: str = ""  # JSON string


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token_address: str = Field(index=True)
    symbol: str
    side: str  # buy | sell
    amount_sol: float
    price_usd: float
    tx_signature: str = ""
    reason: str = ""
    paper: bool = True
    executed_at: datetime = Field(default_factory=datetime.utcnow)


class Position(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token_address: str = Field(index=True, unique=True)
    symbol: str
    buy_price_usd: float
    invested_sol: float
    amount_tokens: float
    buy_tx_signature: str = ""
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "open"  # open | closed | partial
    realized_pnl_sol: float = 0.0
    highest_price_usd: float = 0.0
    paper: bool = True
