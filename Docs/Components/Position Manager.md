# Position Manager

Tracks all open positions, monitors prices, and executes exits (sells) according to the strategy.

---

## Position structure

```python
@dataclass
class Position:
    token_address: str
    symbol: str

    # Entry data
    buy_price_usd: float
    buy_price_sol: float
    amount_tokens: int       # tokens purchased
    invested_sol: float      # SOL spent
    buy_tx_signature: str
    opened_at: datetime

    # Exit strategy
    targets: list[SellTarget] = field(default_factory=lambda: [
        SellTarget(multiplier=2.0, pct_to_sell=50),   # x2 → sell 50%
        SellTarget(multiplier=4.0, pct_to_sell=50),   # x4 → sell 50% of remainder
        SellTarget(multiplier=10.0, pct_to_sell=100), # x10 → sell all
    ])
    stop_loss_pct: float = -0.50  # -50% → sell all

    # Status
    status: str = "open"  # open | closed | partial | partial2
    realized_pnl_sol: float = 0.0
    sold_targets: list[int] = field(default_factory=list)

@dataclass
class SellTarget:
    multiplier: float    # x2, x4, x10
    pct_to_sell: int     # % of remaining balance to sell
    executed: bool = False
    execution_price: float = None
```

---

## Price monitoring

```python
class PositionManager:
    def __init__(self, executor: TradeExecutor):
        self.positions: dict[str, Position] = {}
        self.executor = executor

    async def monitor_loop(self):
        while True:
            for token_address, position in list(self.positions.items()):
                if position.status != "open":
                    continue

                current_price = await self.get_current_price(token_address)
                await self.check_triggers(position, current_price)

            await asyncio.sleep(10)  # check every 10 seconds

    async def check_triggers(self, pos: Position, current_price: float):
        multiplier = current_price / pos.buy_price_usd
        pnl_pct = (multiplier - 1.0)

        # Stop-loss
        if pnl_pct <= pos.stop_loss_pct:
            await self.execute_sell(pos, amount=pos.remaining_tokens, reason="stop_loss")
            return

        # Target levels
        for i, target in enumerate(pos.targets):
            if i in pos.sold_targets:
                continue
            if multiplier >= target.multiplier:
                amount = int(pos.remaining_tokens * target.pct_to_sell / 100)
                await self.execute_sell(pos, amount=amount, reason=f"target_x{target.multiplier}")
                pos.sold_targets.append(i)

    async def get_current_price(self, token_address: str) -> float:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            )
            data = resp.json()
            return float(data["pairs"][0]["priceUsd"])

    async def execute_sell(self, pos: Position, amount: int, reason: str):
        print(f"SELL {pos.symbol}: {amount} tokens, reason={reason}")
        tx = await self.executor.sell(pos.token_address, amount)
        if tx:
            pos.remaining_tokens -= amount
            if pos.remaining_tokens == 0:
                pos.status = "closed"
            self.log_trade(pos, amount, reason, tx)
```

---

## Exit logic — detailed

```
Example: bought for 0.2 SOL, entry price = $0.0001

x10 scenario:
├── x2 ($0.0002): sell 50%  → receive ~0.2 SOL (recovered capital)
│                            → remaining 50% tokens are "free"
├── x4 ($0.0004): sell 25%  → receive ~0.2 SOL more
└── x10 ($0.001): sell 25%  → receive ~0.5 SOL more

Total: ~0.9 SOL from 0.2 SOL invested = +350% (x4.5 average)

Why not wait for x10 all at once?
→ Most tokens never reach x10
→ Partial sells guarantee profit even if the run stalls
```

---

## Trailing Stop (optional)

After x2, a trailing stop can replace fixed levels:

```python
# After first sell at x2
# Trailing stop = 30% from peak
if pos.trailing_stop_enabled:
    pos.highest_price = max(pos.highest_price, current_price)
    trailing_stop_price = pos.highest_price * 0.70

    if current_price <= trailing_stop_price:
        await self.execute_sell(pos, pos.remaining_tokens, "trailing_stop")
```

---

## Limits and risk management

```python
RISK_LIMITS = {
    "max_open_positions": 5,        # no more than 5 simultaneous positions
    "max_position_size_sol": 0.5,   # no more than 0.5 SOL per position
    "max_daily_loss_sol": 1.0,      # halt trading after 1 SOL lost in a day
    "max_token_age_hours": 24,      # don't hold a position longer than 24 hours
}
```

---

## Links

- [[Strategy/Trading Strategy]] — exit strategy details
- [[Components/Trade Executor]] — order execution
- [[Development/Roadmap]] — when trailing stop is added
