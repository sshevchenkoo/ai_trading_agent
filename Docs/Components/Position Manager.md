# Position Manager — Управление позициями

Следит за всеми открытыми позициями, мониторит цены и исполняет выходы (продажи) по стратегии.

---

## Структура позиции

```python
@dataclass
class Position:
    token_address: str
    symbol: str
    
    # Данные входа
    buy_price_usd: float
    buy_price_sol: float
    amount_tokens: int       # сколько токенов куплено
    invested_sol: float      # сколько SOL потрачено
    buy_tx_signature: str
    opened_at: datetime
    
    # Стратегия выхода
    targets: list[SellTarget] = field(default_factory=lambda: [
        SellTarget(multiplier=2.0, pct_to_sell=50),   # x2 → продать 50%
        SellTarget(multiplier=4.0, pct_to_sell=50),   # x4 → продать ещё 50% от остатка
        SellTarget(multiplier=10.0, pct_to_sell=100), # x10 → продать всё
    ])
    stop_loss_pct: float = -0.50  # -50% → продать всё
    
    # Статус
    status: str = "open"  # open | closed | partial
    realized_pnl_sol: float = 0.0
    sold_targets: list[int] = field(default_factory=list)

@dataclass  
class SellTarget:
    multiplier: float   # x2, x4, x10
    pct_to_sell: int    # % от оставшегося количества
    executed: bool = False
    execution_price: float = None
```

---

## Мониторинг цен

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
            
            await asyncio.sleep(10)  # проверяем каждые 10 секунд
    
    async def check_triggers(self, pos: Position, current_price: float):
        multiplier = current_price / pos.buy_price_usd
        pnl_pct = (multiplier - 1.0)
        
        # Стоп-лосс
        if pnl_pct <= pos.stop_loss_pct:
            await self.execute_sell(pos, amount=pos.remaining_tokens, reason="stop_loss")
            return
        
        # Целевые уровни
        for i, target in enumerate(pos.targets):
            if i in pos.sold_targets:
                continue
            if multiplier >= target.multiplier:
                amount = int(pos.remaining_tokens * target.pct_to_sell / 100)
                await self.execute_sell(pos, amount=amount, reason=f"target_x{target.multiplier}")
                pos.sold_targets.append(i)
    
    async def get_current_price(self, token_address: str) -> float:
        # DexScreener или Birdeye API
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

## Логика выходов — детально

```
Пример: купили на 0.2 SOL, цена входа = $0.0001

Сценарий x10:
├── x2 ($0.0002): продаём 50% → получаем ~0.2 SOL (вернули вложенное)
│                              → остаток 50% токенов — это бесплатные
├── x4 ($0.0004): продаём 25% (50% от остатка) → получаем ещё ~0.2 SOL
└── x10 ($0.001): продаём 25% (всё остальное) → получаем ещё ~0.5 SOL

Итого: ~0.9 SOL из 0.2 SOL вложенных = +350% (x4.5 в среднем)

Почему не ждать x10 целиком?
→ большинство токенов не доходят до x10
→ частичные продажи гарантируют прибыль даже если рост остановится
```

---

## Trailing Stop (опционально)

После x2 можно включить trailing stop вместо фиксированных уровней:

```python
# После первой продажи на x2
# Trailing stop = 30% от максимума
if pos.trailing_stop_enabled:
    pos.highest_price = max(pos.highest_price, current_price)
    trailing_stop_price = pos.highest_price * 0.70
    
    if current_price <= trailing_stop_price:
        await self.execute_sell(pos, pos.remaining_tokens, "trailing_stop")
```

---

## Лимиты и риск-менеджмент

```python
RISK_LIMITS = {
    "max_open_positions": 5,          # не более 5 позиций одновременно
    "max_position_size_sol": 0.5,     # не более 0.5 SOL на одну позицию
    "max_daily_loss_sol": 1.0,        # стоп торговли если потеряли 1 SOL за день
    "max_token_age_hours": 24,        # не держать позицию дольше суток
}
```

---

## Ссылки

- [[Strategy/Trading Strategy]] — детали стратегии выходов
- [[Components/Trade Executor]] — исполнение ордеров
- [[Development/Roadmap]] — когда внедряем trailing stop
