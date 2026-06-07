# Trade Executor — Исполнение сделок

Получает сигнал от [[Компоненты/AI Analyzer]] и исполняет своп через Jupiter Aggregator — лучший DEX aggregator на Solане.

---

## Почему Jupiter

- Лучшие цены за счёт агрегации ликвидности с Raydium, Orca, Whirlpool и других DEX
- Поддерживает все pump.fun токены
- Простой REST API
- Автоматически выбирает лучший маршрут

---

## Флоу покупки

```
AI Score ≥ threshold
       │
       ▼
1. Получить котировку (GET /quote)
       │
       ▼
2. Проверить slippage / price impact
       │
       ├── price_impact > 15% → ОТМЕНА (мало ликвидности)
       │
       ▼
3. Получить транзакцию (POST /swap)
       │
       ▼
4. Подписать ключом кошелька
       │
       ▼
5. Отправить на Solana (sendRawTransaction)
       │
       ▼
6. Ждать подтверждения (confirmTransaction)
       │
       ▼
7. Записать позицию в Position Manager
```

---

## Код

```python
import httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
import base64

JUPITER_API = "https://quote-api.jup.ag/v6"
SOL_MINT = "So11111111111111111111111111111111111111112"

class TradeExecutor:
    def __init__(self, wallet: Keypair, rpc_url: str):
        self.wallet = wallet
        self.rpc_url = rpc_url
    
    async def buy(self, token_address: str, amount_sol: float) -> str | None:
        amount_lamports = int(amount_sol * 1_000_000_000)
        
        # 1. Котировка
        async with httpx.AsyncClient() as client:
            quote_resp = await client.get(f"{JUPITER_API}/quote", params={
                "inputMint": SOL_MINT,
                "outputMint": token_address,
                "amount": amount_lamports,
                "slippageBps": 1000,  # 10% — нужно для meme токенов
            })
            quote = quote_resp.json()
        
        # 2. Проверка price impact
        price_impact = float(quote.get("priceImpactPct", 0))
        if price_impact > 0.15:
            print(f"Price impact too high: {price_impact:.1%}, skipping")
            return None
        
        # 3. Транзакция
        async with httpx.AsyncClient() as client:
            swap_resp = await client.post(f"{JUPITER_API}/swap", json={
                "quoteResponse": quote,
                "userPublicKey": str(self.wallet.pubkey()),
                "wrapAndUnwrapSol": True,
                "prioritizationFeeLamports": 100_000,  # 0.0001 SOL priority fee
            })
            swap_data = swap_resp.json()
        
        # 4. Подпись и отправка
        tx_bytes = base64.b64decode(swap_data["swapTransaction"])
        tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = self.wallet.sign_transaction(tx)
        
        # 5. Отправка
        from solana.rpc.async_api import AsyncClient
        async with AsyncClient(self.rpc_url) as rpc:
            result = await rpc.send_raw_transaction(bytes(signed_tx))
            tx_signature = result.value
            
            # Ждём подтверждения
            await rpc.confirm_transaction(tx_signature)
        
        return str(tx_signature)
    
    async def sell(self, token_address: str, amount_tokens: int) -> str | None:
        # Аналогично buy, но inputMint = token_address, outputMint = SOL_MINT
        ...
```

---

## Настройки slippage для разных ситуаций

| Ситуация | Slippage |
|----------|----------|
| Новый pump.fun токен | 10-15% |
| Токен с ликвидностью > 500 SOL | 3-5% |
| Продажа при памп (быстро) | 15-20% |
| Стоп-лосс (любая цена) | 25-50% |

---

## Priority Fee (ускорение транзакции)

На Solане транзакции с higher priority fee обрабатываются быстрее — критично при быстрых движениях цены:

```python
# Нормальный режим
prioritization_fee = 100_000  # 0.0001 SOL

# Высокий конкурс (памп идёт, все хотят купить)
prioritization_fee = 1_000_000  # 0.001 SOL

# Максимальный (срочная продажа на стоп-лосс)
prioritization_fee = 5_000_000  # 0.005 SOL
```

---

## Кошелёк и безопасность

```python
# НИКОГДА не хранить приватный ключ в коде или .env в git
# Загружать из защищённого файла или переменной окружения

import os
from solders.keypair import Keypair
import base58

# Вариант 1: из env переменной (base58 encoded private key)
private_key_b58 = os.environ["WALLET_PRIVATE_KEY"]
keypair = Keypair.from_bytes(base58.b58decode(private_key_b58))

# Вариант 2: из файла (никогда не коммитить!)
with open("wallet.json") as f:
    secret = json.load(f)
keypair = Keypair.from_bytes(bytes(secret))
```

**Правила безопасности кошелька:**
- Отдельный кошелёк только для бота (не основной)
- Держать на боте минимум SOL (только рабочий депозит)
- Основные средства — на холодном кошельке
- `.gitignore` должен включать `wallet.json` и `.env`

---

## RPC Node

Публичный RPC медленный — нужен платный для надёжности:

| Провайдер | Стоимость | Качество |
|-----------|-----------|----------|
| Helius | $49-499/мес | отлично |
| QuickNode | $49+/мес | отлично |
| Triton | $99+/мес | отлично |
| mainnet.helius-rpc.com (бесплатный) | бесплатно | ограничения |

---

## Ссылки

- [[Components/Position Manager]] — что происходит после покупки
- [[Strategy/Trading Strategy]] — логика решений о покупке/продаже
- [[Development/Tech Stack]] — зависимости и библиотеки
