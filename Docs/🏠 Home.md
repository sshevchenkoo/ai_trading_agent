# Solana AI Trading Agent

> Automated meme-token trading bot on Solana. Monitors pump.fun, Twitter, and DexScreener, analyses tokens with Claude AI, and executes trades via Jupiter.

---

## Navigation

| Section | Description |
|---------|-------------|
| [[Architecture]] | System overview and component interactions |
| [[Components/Data Sources]] | Data sources — pump.fun, Twitter, DexScreener |
| [[Components/AI Analyzer]] | Token analysis via Claude API |
| [[Components/Trade Executor]] | Trade execution via Jupiter + Solana wallet |
| [[Components/Position Manager]] | Open position management |
| [[Strategy/Trading Strategy]] | When to buy, when to sell, position sizing |
| [[Strategy/Filters and Security]] | Scam protection and capital preservation rules |
| [[Development/Tech Stack]] | Libraries, tools, languages |
| [[Development/Roadmap]] | Development phases — from MVP to production |

---

## Summary

The agent listens to the pump.fun WebSocket and sees every new Solana token the moment it launches. In parallel, it monitors Twitter for token mentions from KOL accounts. When a token passes automated filters (liquidity, holders, no rug indicators), Claude analyses the context and assigns a score. At a high score, a buy is executed via Jupiter. Selling happens automatically using a partial-exit strategy at x2 / x4 / x10, with a -50% stop-loss.

---

## Status

- [x] Architecture designed
- [x] MVP: pump.fun listener + basic filters
- [x] Claude API integration
- [x] Jupiter swap executor
- [x] Position Manager
- [x] Paper trading (no real money)
- [ ] Live launch with small deposit
