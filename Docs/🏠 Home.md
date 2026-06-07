# Solana AI Trading Agent

> Автоматический агент для торговли meme-токенами на Solana. Мониторит pump.fun, Twitter и DexScreener, анализирует с помощью AI, исполняет сделки через Jupiter.

---

## Навигация

| Раздел | Описание |
|--------|----------|
| [[Architecture]] | Общая схема системы и взаимодействие компонентов |
| [[Components/Data Sources]] | Источники данных — pump.fun, Twitter, DexScreener |
| [[Components/AI Analyzer]] | Анализ сигналов через Claude API |
| [[Components/Trade Executor]] | Исполнение сделок через Jupiter + Solana wallet |
| [[Components/Position Manager]] | Управление открытыми позициями |
| [[Strategy/Trading Strategy]] | Когда покупать, когда продавать, размер позиции |
| [[Strategy/Filters and Security]] | Защита от скамов и потери депозита |
| [[Development/Tech Stack]] | Библиотеки, инструменты, языки |
| [[Development/Roadmap]] | Этапы разработки — от MVP до продакшна |

---

## Суть проекта в одном абзаце

Агент слушает WebSocket pump.fun и видит каждый новый токен на Solане в момент запуска. Параллельно мониторит Twitter на упоминания токенов от KOL-аккаунтов. Когда токен проходит автоматические фильтры (ликвидность, холдеры, отсутствие rug-признаков), Claude анализирует контекст и выставляет оценку. При высоком скоре — покупка через Jupiter. Продажа происходит автоматически по стратегии частичных выходов при x2 / x4 / x10, со стоп-лоссом на -50%.

---

## Статус

- [x] Архитектура спроектирована
- [ ] MVP: pump.fun listener + базовые фильтры
- [ ] Интеграция Claude API
- [ ] Jupiter swap executor
- [ ] Position Manager
- [ ] Paper trading (без реальных денег)
- [ ] Боевой запуск с малым депозитом
