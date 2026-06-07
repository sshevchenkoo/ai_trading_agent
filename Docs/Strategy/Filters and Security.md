# Фильтры и безопасность

Первая линия защиты — дешёвые быстрые проверки без AI. Отсеивают ~85-90% токенов.

---

## Обязательные фильтры (fail = пропустить)

```python
HARD_FILTERS = {
    # Ликвидность
    "min_liquidity_sol": 50,          # менее 50 SOL → легко манипулировать
    "max_liquidity_sol": 10_000,      # слишком большой → уже поздно входить
    
    # Холдеры
    "min_holder_count": 100,          # менее 100 → слишком концентрированно
    "max_top10_holder_pct": 50,       # топ-10 держат более 50% → скам риск
    
    # Возраст
    "max_age_minutes_new_token": 60,  # для новых — не старше часа
    
    # Dev активность
    "dev_sold_pct_threshold": 5,      # dev продал > 5% supply → выходим
    
    # Объём
    "min_buy_sell_ratio": 1.5,        # покупок должно быть в 1.5х больше продаж
    "min_txns_per_hour": 20,          # минимум 20 транзакций в час
}
```

---

## Чёрный список нарративов

Перегретые темы с низким потенциалом роста:

```python
NARRATIVE_BLACKLIST = [
    # Слишком заезженные
    "elon", "musk", "trump", "biden", "pepe", "doge",
    "shib", "floki", "inu", "moon", "safe",
    
    # Клоны известных проектов
    "baby", "mini", "micro", "super", "mega",
    
    # Очевидный скам
    "100x", "1000x", "guaranteed", "presale",
]
```

---

## Признаки Honeypot / Rug Pull

```python
async def check_contract_safety(token_address: str) -> dict:
    """
    Проверяем on-chain признаки скама
    Используем: Rugcheck API или rug.check
    """
    
    DANGER_FLAGS = {
        "mint_authority_not_revoked": True,  # создатель может напечатать токены
        "freeze_authority_exists": True,      # может заморозить кошельки
        "top1_holder_over_20pct": True,       # один кошелёк > 20%
        "dev_created_rugged_tokens": True,    # история скамов у создателя
        "liquidity_not_locked": True,         # LP токены не заблокированы
    }
    
    # Rugcheck.xyz API
    resp = await httpx.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report")
    report = resp.json()
    
    return {
        "is_safe": report["score"] >= 500,
        "risk_level": report["risks"],
        "score": report["score"],
    }
```

### Rugcheck Score

| Score | Интерпретация |
|-------|---------------|
| 800-1000 | Хорошо — проходит |
| 500-800 | Средне — проверить детали |
| < 500 | Опасно — пропустить |

---

## Проверка создателя токена

```python
async def check_creator_history(creator_wallet: str) -> dict:
    """
    Смотрим историю кошелька создателя
    """
    # pump.fun API или Solana Explorer
    prev_tokens = await get_creator_tokens(creator_wallet)
    
    rugged_count = sum(1 for t in prev_tokens if t["status"] == "rugged")
    total_count = len(prev_tokens)
    rug_rate = rugged_count / total_count if total_count > 0 else 0
    
    return {
        "total_tokens_created": total_count,
        "rugged_count": rugged_count,
        "rug_rate": rug_rate,
        "pass": rug_rate < 0.3,  # rug rate менее 30% — ок
    }
```

---

## Антибот защита

Боты с обеих сторон создают фейковые сигналы:

```python
ANTIBOT_CHECKS = {
    # Фейковый объём
    "wash_trading_threshold": 0.3,    # если один адрес > 30% объёма — подозрительно
    
    # Фейковые твиты
    "min_tweet_account_age_days": 30, # аккаунт моложе месяца — бот
    "min_tweet_account_followers": 50, # менее 50 фолловеров — игнор
    "max_tweets_per_hour_account": 20, # более 20 твитов в час — бот
    
    # Сэндвич-атаки
    "use_jito_bundles": True,         # Jito MEV protection
}
```

---

## Whitelist KOL-аккаунтов Twitter

```python
# Аккаунты чьи упоминания дают +2 к score
KOL_WHITELIST = {
    # Добавить реальных крипто-инфлюенсеров со Solana-сообщества
    # Пример структуры:
    "username": {
        "weight": 2.0,
        "followers": 500_000,
        "category": "trader",
    }
}
```

---

## Итоговый фильтр-пайплайн

```
1. Базовые метрики (ликвидность, холдеры, возраст)     → fail 60% токенов
2. Нарративный blacklist                                → fail ещё 10%
3. Rugcheck score                                       → fail ещё 10%
4. Creator history                                      → fail ещё 5%
5. Antibot проверки                                     → fail ещё 5%
─────────────────────────────────────────────────────────────────────
Остаётся ~10% токенов → идут на AI Analyzer
```

---

## Ссылки

- [[Components/AI Analyzer]] — следующий уровень проверки
- [[Strategy/Trading Strategy]] — условия входа в сделку
- [[Components/Data Sources]] — откуда берём данные для фильтров
