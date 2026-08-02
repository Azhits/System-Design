# Мониторинг и наблюдаемость

## Обзор

Документ описывает подход к мониторингу системы автоматической обработки тикетов поддержки на этапе PoC и в production-среде. Основная задача мониторинга — не просто следить за техническими метриками, но убедиться, что система решает исходную бизнес-задачу: снижает нагрузку на операторов без ухудшения CSAT и роста reopen rate.

## Бизнес-метрики (product KPI)

| Метрика | Описание | Целевое значение | Триггер стопа |
|---------|----------|------------------|--------------|
| `auto_close_rate` | Доля тикетов, закрытых автоматически | 30–40% от типовых | < 10% (система не работает) |
| `suggest_acceptance_rate` | Доля черновиков, принятых оператором | ≥ 60% | < 30% (черновики бесполезны) |
| `reopen_rate_auto` | Reopen rate для авто-закрытых тикетов | ≤ 9% (не хуже baseline) | > 12% устойчиво 3 дня |
| `csat_auto` | CSAT по авто-закрытым тикетам | ≥ 4,2/5 | < 4,0 устойчиво |
| `p95_first_response_ms` | 95-й перцентиль времени первого ответа (типовые) | < 2 мин | > 15 мин (SLA breach) |
| `llm_cost_per_ticket` | Стоимость LLM-инференса на тикет | < 2 ₽ | > 5 ₽ (ROI теряется) |

## Технические метрики

| Метрика | Описание |
|---------|----------|
| `pipeline_latency_p50/p95/p99` | Latency синхронного пути (цель: p95 < 500 мс) |
| `classifier_confidence_mean` | Средняя уверенность классификатора за скользящее окно |
| `retrieval_top1_score_mean` | Средний similarity score первого результата |
| `llm_fallback_count` | Количество переключений на retrieval-fallback |
| `degradation_level_current` | Текущий уровень деградации (L0–L4) |
| `pipeline_error_count` | Ошибки в пайплайне (любого типа) |
| `pii_high_rate` | Доля тикетов с high_pii (аномалия > 30%) |

## Журнал аудита (PoC)

Каждый обработанный тикет записывается в JSONL-лог (`logs/decisions.jsonl`) с полными полями:

```json
{
  "ticket_id": "T-001",
  "timestamp": "2026-08-01T10:30:00Z",
  "topic": "billing",
  "confidence": 0.87,
  "pii_risk": "high_pii",
  "pii_signals": {"name": true, "phone": true, "card_number": true},
  "action": "escalate",
  "requires_human": true,
  "degradation_level": "L0",
  "degradation_note": "normal",
  "decision_trace": [
    "topic=billing, confidence=0.871",
    "high_pii_detected: name + phone + card_number",
    "high_pii -> LLM_skipped, retrieval_only_draft, action=escalate",
    "retrieval: kb_id=KB004, similarity=0.612",
    "action=escalate -> requires_human=true"
  ],
  "latency_ms": 47.3,
  "model_version": "poc-tfidf-tree-v1"
}
```

## Алерты

### Критические (немедленная реакция)

- `degradation_level` достиг L4 — все тикеты уходят операторам без черновика
- `pipeline_error_count` > 5 за 5 минут
- `pipeline_latency_p95` > 2 000 мс (синхронный путь деградирует)
- `reopen_rate_auto` > 12% устойчиво 3 дня подряд

### Предупредительные

- `classifier_confidence_mean` < 0.50 за 50 последних тикетов — возможный дрейф данных
- `pii_high_rate` > 30% — аномальный поток или утечка данных
- `escalation_rate` > 70% — система не справляется, операторы перегружены
- `llm_fallback_count` растёт > 3× за 15 минут — проблемы с LLM-провайдером
- `suggest_acceptance_rate` < 40% за последние 500 тикетов — деградация качества черновиков

## Как отличить деградацию модели от изменения входящего потока

- **Деградация модели**: `classifier_confidence_mean` падает, но распределение тем входящих тикетов стабильно. Метрика: сравнить topic distribution за последние 7 дней с baseline.
- **Изменение потока**: резкий рост доли нетипичных тем (например, новый тип обращений после продуктового обновления). Метрика: topic entropy растёт, но confidence стабилен.
- **Обе проблемы одновременно**: `reopen_rate_auto` растёт — это сигнал для ручного аудита выборки из 50–100 тикетов.

Рекомендуемый инструмент в production: Evidently AI для мониторинга дрейфа признаков, Prometheus + Grafana для технических метрик.

## Мониторинг стоимости LLM

- Фиксировать `input_tokens` + `output_tokens` на каждый LLM-вызов в audit log.
- Агрегировать стоимость по часам; алерт при превышении ≥ 2× от дневной нормы за первые 4 часа.
- При L1 (batching) отслеживать эффективность батчинга: batch_size, cost per ticket в batched vs single режиме.
- Лимит бюджета на LLM в production: hard cap с автоматическим переключением в retrieval-only при исчерпании.

## PoC vs Production

| Аспект | PoC | Production |
|--------|-----|------------|
| Логи | JSONL-файл (`logs/decisions.jsonl`) | PostgreSQL / S3 + Loki |
| Метрики | — | Prometheus + Grafana |
| Алерты | — | PagerDuty / Telegram |
| Трейсинг | — | OpenTelemetry + Jaeger |
| Дрейф ML | — | Evidently AI |
| LLM cost | — | Token-level billing + budget cap |
