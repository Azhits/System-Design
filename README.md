# System Design: Автоматизация обработки тикетов поддержки

Доказательство концепции (PoC) и системный дизайн для автоматической системы сортировки и подготовки ответов на тикеты поддержки. Система классифицирует входящие тикеты, определяет риск наличия персональных данных (ПДн), ищет релевантные ответы в базе знаний и принимает решение — автоматически закрыть тикет, предложить черновик оператору или эскалировать на полную ручную проверку — с поддержкой плавной деградации при высокой нагрузке или недоступности LLM.

## Ценность для бизнеса

При 200 000 тикетов в день и стоимости ручной обработки 150 ₽/тикет дневные операционные расходы составляют около 30 млн ₽. Около 40% потока — типовые повторяющиеся обращения, пригодные для автоматизации. Целевой показатель системы — автоматическое безопасное закрытие 30–40% таких тикетов (≈ 25 000–32 000 тикетов/день), что даёт **экономию 3,75–4,8 млн ₽ в день** при сохранении SLA первого ответа (15 мин) и без ухудшения CSAT (текущий 4,2/5). Для рискованных категорий (billing, complaint, abuse, high-PII) автозакрытие не применяется — только prepare-and-suggest, чтобы не ухудшать reopen rate (текущий 9%). Полный продуктовый расчёт — в [docs/product.md](docs/product.md).

## Быстрый старт

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn poc.app:app --reload
```

Откройте браузер: **http://127.0.0.1:8000** — интерактивный UI с 4 кнопками быстрых сценариев.

Или через curl:
```bash
# Happy path
curl -X POST http://127.0.0.1:8000/tickets \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id": "T100", "text": "Не могу войти в личный кабинет, забыл пароль"}'

# Risky path (PII + payment)
curl -X POST "http://127.0.0.1:8000/tickets?queue_size=0&llm_available=true" \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id": "T101", "text": "Иванов Алексей Петрович, тел +7 916 123-45-67, с карты 4276 1234 5678 9010 списали 3500 руб без моего ведома"}'

# High load (degradation L2)
curl -X POST "http://127.0.0.1:8000/tickets?queue_size=300" \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id": "T102", "text": "Как изменить тариф подписки?"}'

# LLM unavailable (retrieval fallback)
curl -X POST "http://127.0.0.1:8000/tickets?llm_available=false" \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id": "T103", "text": "Приложение вылетает при открытии раздела оплаты"}'

# Прогнать все mock-тикеты
curl http://127.0.0.1:8000/tickets/mock

# Журнал аудита
curl http://127.0.0.1:8000/decisions
```

## Демонстрируемые сценарии

| Сценарий | Тикет | Ожидаемый результат |
|----------|-------|---------------------|
| **Happy path** | «Не могу войти, забыл пароль» | `account_access` → `auto_close`, LLM-черновик |
| **Risky path: PII + payment** | ФИО + телефон + номер карты | `high_pii` → `escalate`, LLM не вызывается |
| **Risky topic** | Жалоба / возврат средств | `billing/complaint` → `escalate`, черновик для оператора |
| **High load (L2)** | `queue_size=300` | Деградация L2, retrieval-шаблон без LLM |
| **LLM unavailable (L3)** | `llm_available=false` | Принудительная деградация L3, retrieval fallback |
| **Critical load (L4)** | `queue_size=10000` | Только маршрутизация оператору, без черновика |

## Что реальная реализация, а что архитектурный дизайн

**Реальная реализация (работает в PoC):**
- Классификация темы через TF-IDF + Decision Tree
- PII-детекция по regex-паттернам с оценкой уровня риска
- Retrieval по базе знаний (TF-IDF cosine similarity)
- Логика принятия решений (auto_close / suggest / escalate)
- Уровни деградации L0–L4 по queue_size и llm_available
- Mock-LLM с симуляцией задержек и сбоев
- Audit-лог всех решений в `logs/decisions.jsonl`
- Веб-UI с демо-сценариями, цветными бейджами, PII preview, decision trace

**Архитектурный дизайн (описан в docs/, не реализован в PoC):**
- Sentence embeddings + векторная БД вместо TF-IDF
- Реальный LLM-провайдер за circuit breaker
- NER-модель вместо regex для PII
- Очередь задач оператора (Celery/Redis) с SLA
- Централизованный audit storage (PostgreSQL/S3)
- Prometheus + Grafana мониторинг

## Допущения и ограничения

- LLM-клиент — mock-заглушка. В production заменяется реальным провайдером.
- База знаний содержит ~15 записей для демо; production требует тысячи записей.
- Классификатор обучен на ~30 синтетических примерах; точность достаточна для демо, не для production.
- PII-детекция regex-based; возможны ложные срабатывания и пропуски.
- Лог пишется в файл локально; в production — централизованное хранилище.

## Структура репозитория

```
System-Design/
├── README.md              # Этот файл
├── AI_USAGE.md            # Как использовался ИИ при разработке
├── SELF_REVIEW.md         # Самооценка: ограничения, риски, production-требования
├── requirements.txt       # Python-зависимости
├── docs/
│   ├── product.md         # Продуктовый расчёт: ROI, метрики, сценарии запуска
│   ├── architecture.md    # Архитектура, компоненты, поток данных, деградация
│   ├── ml.md              # ML/NLP подход, обоснование порогов
│   ├── monitoring.md      # Метрики, алерты, мониторинг дрейфа
│   └── risks-and-ops.md   # Риски highload, privacy, safety, runbook
└── poc/
    ├── pii.py             # Детектор ПДн и оценка уровня риска
    ├── classifier.py      # Классификация темы + оценка уверенности
    ├── retrieval.py       # TF-IDF поиск по базе знаний
    ├── llm_client.py      # Mock LLM клиент (симуляция деградации)
    ├── degradation.py     # Логика уровней деградации L0–L4
    ├── pipeline.py        # Оркестрация: classify → PII → retrieval → decision → log
    ├── app.py             # FastAPI приложение + демо-интерфейс
    ├── run_demo.py        # Скрипт запуска
    ├── data/
    │   ├── mock_tickets.json    # Тестовые тикеты (все ключевые сценарии)
    │   └── knowledge_base.json  # База знаний для retrieval
    ├── logs/
    │   └── .gitkeep             # Audit-лог записывается в decisions.jsonl
    └── static/
        └── index.html     # Веб-интерфейс с быстрыми сценариями
```

## Документация

| Файл | Содержание |
|------|------------|
| [docs/product.md](docs/product.md) | Бизнес-расчёт, ROI, метрики успеха, go/no-go |
| [docs/architecture.md](docs/architecture.md) | Архитектура, компоненты, поток данных, деградация |
| [docs/ml.md](docs/ml.md) | ML/NLP подход, обоснование порогов, валидация |
| [docs/monitoring.md](docs/monitoring.md) | Метрики, алерты, мониторинг дрейфа |
| [docs/risks-and-ops.md](docs/risks-and-ops.md) | Риски, PII/compliance, operational runbook |
| [AI_USAGE.md](AI_USAGE.md) | Использование ИИ при разработке |
| [SELF_REVIEW.md](SELF_REVIEW.md) | Самооценка: ограничения и что осталось для production |

## Технологический стек

| Компонент | PoC | Production (целевой) |
|-----------|-----|---------------------|
| API-сервер | FastAPI + Uvicorn | FastAPI + Gunicorn + K8s |
| Классификация | TF-IDF + Decision Tree | Fine-tuned transformer / LLM-classifier |
| Retrieval | TF-IDF cosine similarity | Sentence embeddings + pgvector/FAISS |
| PII detection | Regex-паттерны | Regex + NER-модель |
| LLM | Mock-заглушка | OpenAI / внутренний шлюз за circuit breaker |
| Логирование | JSONL-файл (`logs/decisions.jsonl`) | PostgreSQL / S3 + audit index |
