# Trade Executor

Receives a signal from [[Components/AI Analyzer]] and executes a swap via Jupiter Aggregator — the best DEX aggregator on Solana.

---

## Why Jupiter

- Best prices through aggregated liquidity from Raydium, Orca, Whirlpool, and others
- Supports all pump.fun tokens
- Simple REST API
- Automatically selects the optimal route

---

## Buy flow

```
AI Score ≥ threshold
       │
       ▼
1. Get quote (GET /quote)
       │
       ▼
2. Check slippage / price impact
       │
       ├── price_impact > 15% → CANCEL (insufficient liquidity)
       │
       ▼
3. Get transaction (POST /swap)
       │
       ▼
4. Sign with wallet keypair
       │
       ▼
5. Send to Solana (sendRawTransaction)
       │
       ▼
6. Wait for confirmation (confirmTransaction)
       │
       ▼
7. Record position in Position Manager
```

---

## Code

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

        async with httpx.AsyncClient() as client:
            quote_resp = await client.get(f"{JUPITER_API}/quote", params={
                "inputMint": SOL_MINT,
                "outputMint": token_address,
                "amount": amount_lamports,
                "slippageBps": 1000,  # 10% — needed for meme tokens
            })
            quote = quote_resp.json()

        price_impact = float(quote.get("priceImpactPct", 0))
        if price_impact > 0.15:
            print(f"Price impact too high: {price_impact:.1%}, skipping")
            return None

        async with httpx.AsyncClient() as client:
            swap_resp = await client.post(f"{JUPITER_API}/swap", json={
                "quoteResponse": quote,
                "userPublicKey": str(self.wallet.pubkey()),
                "wrapAndUnwrapSol": True,
                "prioritizationFeeLamports": 100_000,
            })
            swap_data = swap_resp.json()

        tx_bytes = base64.b64decode(swap_data["swapTransaction"])
        tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = self.wallet.sign_transaction(tx)

        from solana.rpc.async_api import AsyncClient
        async with AsyncClient(self.rpc_url) as rpc:
            result = await rpc.send_raw_transaction(bytes(signed_tx))
            tx_signature = result.value
            await rpc.confirm_transaction(tx_signature)

        return str(tx_signature)

    async def sell(self, token_address: str, amount_tokens: int) -> str | None:
        # Same as buy, but inputMint = token_address, outputMint = SOL_MINT
        ...
```

---

## Slippage settings by scenario

| Scenario | Slippage |
|----------|----------|
| New pump.fun token | 10–15% |
| Token with liquidity > 500 SOL | 3–5% |
| Selling during pump (fast) | 15–20% |
| Stop-loss (any price) | 25–50% |

---

## Priority Fee (transaction speed)

On Solana, transactions with a higher priority fee are processed faster — critical during fast price moves:

```python
# Normal mode
prioritization_fee = 100_000   # 0.0001 SOL

# High competition (active pump, everyone buying)
prioritization_fee = 1_000_000  # 0.001 SOL

# Maximum (urgent stop-loss sell)
prioritization_fee = 5_000_000  # 0.005 SOL
```

---

## Wallet and security

```python
# NEVER store the private key in code or in a committed .env
# Load from a secured file or environment variable

import os
from solders.keypair import Keypair
import base58

# Option 1: from env variable (base58-encoded private key)
private_key_b58 = os.environ["WALLET_PRIVATE_KEY"]
keypair = Keypair.from_bytes(base58.b58decode(private_key_b58))

# Option 2: from file (never commit this file!)
with open("wallet.json") as f:
    secret = json.load(f)
keypair = Keypair.from_bytes(bytes(secret))
```

**Wallet security rules:**
- Use a dedicated wallet for the bot (not your main wallet)
- Keep only the working deposit on the bot wallet
- Store main funds in cold storage
- `.gitignore` must include `wallet.json` and `.env`

---

## RPC Node

Public RPC is slow — a paid node is needed for reliability:

| Provider | Cost | Quality |
|----------|------|---------|
| Helius | $49–499/mo | excellent |
| QuickNode | $49+/mo | excellent |
| Triton | $99+/mo | excellent |
| mainnet.helius-rpc.com (free) | free | rate-limited |

---

## Links

- [[Components/Position Manager]] — what happens after a buy
- [[Strategy/Trading Strategy]] — buy/sell decision logic
- [[Development/Tech Stack]] — dependencies and libraries
