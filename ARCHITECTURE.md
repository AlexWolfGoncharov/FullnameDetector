# Ukrainian Name Detection API — Архітектура

## Опис

API для визначення ПІБ (прізвище, ім'я, по батькові) у платіжних коментарях українською мовою з перевіркою на санкційний список РНБО.

---

## Багаторівнева архітектура (Multi-Tier Pipeline)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Запит                                   │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 1: Quick Filter (< 1ms)                                   │
│  - Regex для очевидних випадків БЕЗ ПІБ                         │
│  - "зарплата", "аванс", "податки", "Слава Україні" → БЕЗ ПІБ   │
│  - Формат коментаря: "Призначення-Кастомна частина"             │
│  Очікувано: 30–40% запитів                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 2a: spaCy NER (2–5ms)                                     │
│  - uk_core_news_md                                              │
│  - Розпізнає PER (персони), патерни ПІБ                         │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 2b: RoBERTa NER (опційно, ~50–100ms)                      │
│  - EvanD/xlm-roberta-base-ukrainian-ner-ukrner                  │
│  - Вища точність для складних випадків                          │
│  - Використовується разом зі spaCy (обираємо кращий результат)  │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 3: LLM Fallback (1–3 сек)                                 │
│  - MamayLM-Gemma-3-4B-IT (Ollama або llama.cpp)                 │
│  - Лише для низької впевненості або часткових результатів       │
│  - Rate limiting, thread-safe                                   │
│  Очікувано: 3–5% запитів                                        │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Sanctions Checker                                              │
│  - Перевірка виявлених імен у sanctions_individuals.csv         │
│  - Правила: потрібне прізвище, при збігу імені — ігноруємо      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Формат коментарів

- **Стандарт-ПІБ:** `Заробітна плата-Булатов Руслан Олександрович` — обробляємо частину після тире.
- **ПІБ-призначення:** `Подопригора Андрій Петрович - зарплата` — обробляємо частину перед тире.
- Типові призначення: зарплата, зарплатна, премія, аванс, виплата, переказ, оплата.

---

## Структура проекту

```
Fullname_detector/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI застосунок
│   ├── config.py            # Pydantic Settings
│   ├── setup.py             # Автозавантаження моделей
│   ├── models/
│   │   └── schemas.py       # Pydantic моделі
│   ├── services/
│   │   ├── quick_filter.py  # Tier 1: Regex
│   │   ├── ner_engine.py    # Tier 2a: spaCy
│   │   ├── roberta_ner.py   # Tier 2b: RoBERTa NER
│   │   ├── llm_fallback.py  # Tier 3: Ollama / llama.cpp
│   │   ├── pipeline.py      # Оркестрація
│   │   ├── cache.py         # LRU кеш
│   │   ├── sanctions_checker.py  # Перевірка санкцій
│   │   └── request_logger.py     # Логування запитів
│   └── data/
│       ├── patterns.py      # Regex паттерни
│       └── sanctions_individuals.csv
├── tests/
│   ├── test_pipeline.py
│   ├── test_quick_filter.py
│   ├── test_comprehensive.py
│   ├── test_real_comments.py
│   └── test_data/
│       └── comments.json
├── scripts/
│   ├── test_via_api.py      # Тест API
│   └── llama_cpp_test.py    # Тест LLM
├── run.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Моделі

| Компонент | Модель | RAM | Латентність |
|-----------|--------|-----|-------------|
| Tier 2a | uk_core_news_md | ~200 MB | 2–5 ms |
| Tier 2b | xlm-roberta-base-ukrainian-ner-ukrner | ~500 MB | 50–100 ms |
| Tier 3 | MamayLM-Gemma-3-4B-IT Q4_K_M | ~2.5 GB | 1–3 s |

---

## LLM (Tier 3)

**Модель:** MamayLM-Gemma-3-4B-IT (INSAIT-Institute/MamayLM-Gemma-3-4B-IT-v1.0-GGUF)

**Бекенди:**
1. **llama_cpp** — локальний GGUF через llama-cpp-python.
2. **ollama** — через Ollama (рекомендовано для Apple Silicon). При запуску:
   - автоматично стартує `ollama serve`, якщо не запущений;
   - завантажує GGUF та створює модель в Ollama, якщо її ще немає.

**Env:**
- `NAME_DETECTOR_LLM_BACKEND=ollama` або `llama_cpp`
- `NAME_DETECTOR_LLM_ENABLED=false` — вимкнути LLM.

---

## Sanctions Checker

- Файл: `app/data/sanctions_individuals.csv` (TSV).
- **Правила:**
  - `NAME_ONLY` (без прізвища) → ігнорується.
  - При частковому збігу: прізвище має збігатися; якщо є ім'я і воно відрізняється — не флагуємо.

---

## API Endpoints

| Метод | Шлях | Опис |
|-------|------|------|
| POST | /detect-name | Визначити ПІБ у коментарі |
| GET | /health | Стан сервісу |
| GET | /stats | Статистика (tier1/2/3, cache) |
| GET | /setup-status | Статус моделей |
| POST | /setup | Повторне завантаження моделей |
| GET | /logs/download | Завантажити логи запитів |

---

## Запуск

```bash
# Встановлення
python -m venv venv
source venv/bin/activate  # або venv\Scripts\activate на Windows
pip install -r requirements.txt

# Автоналаштування + запуск
python run.py --port 8000

# Лише налаштування
python run.py --setup-only

# Запуск без LLM
NAME_DETECTOR_LLM_ENABLED=false python run.py
```

---

## Тестування

```bash
# Unit-тести
python -m pytest tests/ -v

# Тест API (сервер має бути запущений)
python scripts/test_via_api.py http://localhost:8000
```
