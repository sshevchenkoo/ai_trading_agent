import base64
import httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

from config import settings
from utils.logger import get_logger

log = get_logger("jupiter")

SOL_MINT = "So11111111111111111111111111111111111111112"
QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
SWAP_URL = "https://quote-api.jup.ag/v6/swap"

SLIPPAGE_BPS = 500       # 5% slippage — meme tokens need this
PRIORITY_FEE = 100_000   # 0.0001 SOL priority fee for faster confirmation


async def get_quote(
    input_mint: str,
    output_mint: str,
    amount: int,  # lamports for SOL, raw units for token
) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(QUOTE_URL, params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": SLIPPAGE_BPS,
            })
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        log.warning("jupiter_quote_failed", error=str(e))
        return None


async def execute_swap(quote: dict, keypair: Keypair) -> str | None:
    """Get swap transaction from Jupiter, sign it, send to Solana RPC."""
    try:
        # Step 1: get serialized transaction from Jupiter
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(SWAP_URL, json={
                "quoteResponse": quote,
                "userPublicKey": str(keypair.pubkey()),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": PRIORITY_FEE,
            })
            resp.raise_for_status()
            swap_tx_b64 = resp.json()["swapTransaction"]

        # Step 2: deserialize → sign → serialize
        raw_tx = base64.b64decode(swap_tx_b64)
        tx = VersionedTransaction.from_bytes(raw_tx)
        signed_tx = VersionedTransaction(tx.message, [keypair])

        # Step 3: send to RPC
        rpc = AsyncClient(settings.solana_rpc_url)
        try:
            result = await rpc.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed"),
            )
            sig = str(result.value)
            log.info("swap_sent", signature=sig[:12] + "...")
            return sig
        finally:
            await rpc.close()

    except Exception as e:
        log.error("jupiter_swap_failed", error=str(e))
        return None
