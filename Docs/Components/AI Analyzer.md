# AI Analyzer — Анализ сигналов через Claude

Вызывается после того как токен прошёл [[Strategy/Filters and Security|Rule Filters]]. Стоит денег ($0.01-0.05 за вызов), поэтому только для перспективных кандидатов.

---

## Что анализирует Claude

1. **Качество твитов** — реальный интерес или боты с накрутками?
2. **Нарратив** — есть ли у токена понятная история/мем?
3. **Timing** — на каком этапе хайп (начало/пик/конец)?
4. **Red flags** — признаки скама в описании, имени, истории создателя
5. **Потенциал** — схожесть с прошлыми успешными токенами

---

## Промпт

```python
SYSTEM_PROMPT = """
You are a Solana meme token analyst. Your job is to evaluate tokens for short-term 
trading potential (2x-10x within hours/days). Be concise and data-driven.

Return ONLY valid JSON. No markdown, no extra text.
"""

def build_analysis_prompt(signal: TokenSignal) -> str:
    return f"""
Analyze this Solana token for short-term trading potential:

TOKEN INFO:
- Symbol: ${signal.symbol}
- Name: {signal.name}  
- Description: {signal.description}
- Age: {signal.age_minutes} minutes
- Market Cap: ${signal.market_cap_usd:,.0f}
- Liquidity: {signal.liquidity_sol:.1f} SOL
- Holders: {signal.holder_count}
- Top 10 holders: {signal.top10_holder_pct:.1f}% of supply
- Dev wallet sold: {signal.dev_wallet_sold}
- Buy/Sell ratio (1h): {signal.buys_1h}/{signal.sells_1h}

SOCIAL SIGNALS:
- Twitter mentions (1h): {signal.twitter_mentions_1h}
- KOL mentions: {', '.join(signal.kol_mentions) if signal.kol_mentions else 'none'}
- Top tweets:
{chr(10).join(f'  [{t.likes}L {t.retweets}RT] {t.text[:200]}' for t in signal.tweet_texts[:5])}

Respond with JSON:
{{
  "score": <1-10, where 7+ = buy>,
  "confidence": <"low"|"medium"|"high">,
  "reasoning": "<2-3 sentences why>",
  "risk_level": <"low"|"medium"|"high"|"extreme">,
  "suggested_position_sol": <0.05-0.5>,
  "red_flags": ["<flag1>", "<flag2>"],
  "narrative_strength": <1-10>,
  "estimated_timeframe": "<short: hours|medium: 1-3 days|long: week+>"
}}
"""
```

---

## Логика вызова

```python
import anthropic

async def analyze_token(signal: TokenSignal) -> AIAnalysis:
    client = anthropic.Anthropic()
    
    response = client.messages.create(
        model="claude-opus-4-8",   # лучшая модель для анализа
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": build_analysis_prompt(signal)
        }]
    )
    
    result = json.loads(response.content[0].text)
    
    # Финальный скор = комбинация rule score + ai score
    final_score = (signal.rule_score * 0.4) + (result["score"] * 0.6)
    
    return AIAnalysis(
        score=result["score"],
        final_score=final_score,
        confidence=result["confidence"],
        reasoning=result["reasoning"],
        risk_level=result["risk_level"],
        suggested_position_sol=result["suggested_position_sol"],
        red_flags=result["red_flags"],
    )
```

---

## Пороговые значения

| final_score | Действие |
|-------------|----------|
| < 6.0 | Пропустить |
| 6.0 - 7.0 | Маленькая позиция (0.05 SOL) |
| 7.0 - 8.5 | Стандартная позиция (0.1-0.2 SOL) |
| 8.5+ | Увеличенная позиция (0.3-0.5 SOL) |

---

## Стоимость вызовов

- Claude Opus 4: ~$15 / 1M input tokens, ~$75 / 1M output tokens
- Один вызов ≈ ~800 input + 200 output tokens ≈ **$0.027**
- 100 анализов в день = ~$2.70/день
- Фильтры должны отсеивать 90%+ токенов до AI — это снижает расходы

---

## Ссылки

- [[Components/Data Sources]] — откуда берутся данные для анализа
- [[Components/Trade Executor]] — что происходит после высокого скора
- [[Strategy/Filters and Security]] — фильтры перед AI вызовом
