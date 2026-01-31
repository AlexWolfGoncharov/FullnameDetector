# Ukrainian Name Detection API

API для визначення ПІБ (прізвище, ім'я, по батькові) у платіжних коментарях українською мовою з перевіркою на санкційний список РНБО.

## Можливості

- **Детекція ПІБ** — розпізнавання імен у коментарях до платежів
- **Формат коментарів** — підтримка `Заробітна плата-Булатов Руслан Олександрович` та `ПІБ - зарплата`
- **Санкції** — перевірка виявлених імен у санкційному списку РНБО
- **Багаторівнева обробка** — Quick Filter → spaCy NER → RoBERTa NER → LLM fallback
- **Кешування** — LRU-кеш для прискорення повторних запитів

## Швидкий старт

```bash
# Клонування
git clone <repo-url>
cd Fullname_detector

# Віртуальне середовище
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

# Встановлення залежностей
pip install -r requirements.txt

# Завантаження моделей (spaCy, RoBERTa, MamayLM ~3GB) — один раз
HF_TOKEN=hf_xxx python scripts/download_models.py

# Запуск
python run.py --port 8000
```

> **Примітка:** Моделі не в репозиторії (GitHub ліміт 100MB, MamayLM ~2.5GB). Скрипт `download_models.py` завантажує їх з HuggingFace. Без `HF_TOKEN` публічні моделі теж завантажаться.
>
> **Безпека:** HF токен тільки в `.env` (не комітити). Перед push встановіть hook: `./scripts/install-git-hooks.sh`

API буде доступне на `http://localhost:8000`. Документація: `http://localhost:8000/docs`.

## Приклад використання

```bash
curl -X POST "http://localhost:8000/detect-name" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Заробітна плата-Булатов Руслан Олександрович"}'
```

```json
{
  "has_name": true,
  "category": "Прізвище + Ім'я + По батькові",
  "detected_name": "Булатов Руслан Олександрович",
  "confidence": 0.95,
  "tier_used": 2,
  "sanctions_check": {
    "checked": true,
    "found": false
  }
}
```

## Конфігурація

Створіть `.env` з `.env.example`:

```bash
cp .env.example .env
```

Основні змінні:

| Змінна | Опис | За замовчуванням |
|--------|------|------------------|
| `NAME_DETECTOR_PORT` | Порт API | 8000 |
| `NAME_DETECTOR_LLM_ENABLED` | Увімкнути LLM | true |
| `NAME_DETECTOR_LLM_BACKEND` | `llama_cpp` або `ollama` | llama_cpp |
| `NAME_DETECTOR_SPACY_MODEL` | spaCy модель | uk_core_news_md |

Для Apple Silicon рекомендовано Ollama — при `NAME_DETECTOR_LLM_BACKEND=ollama` застосунок:
- автоматично запустить Ollama, якщо він не працює;
- завантажить GGUF і створить модель в Ollama, якщо її ще немає.

У `.env`: `NAME_DETECTOR_LLM_BACKEND=ollama`

## Архітектура

1. **Tier 1** — Quick Filter (regex) для очевидних випадків без ПІБ
2. **Tier 2a** — spaCy NER (uk_core_news_md)
3. **Tier 2b** — RoBERTa NER (xlm-roberta-base-ukrainian-ner-ukrner), опційно
4. **Tier 3** — LLM fallback (MamayLM-Gemma-3-4B-IT) для складних випадків
5. **Sanctions** — перевірка імен у санкційному списку

Детальніше: [ARCHITECTURE.md](ARCHITECTURE.md)

## Оновлення санкційного списку

При старті API:
1. **Разово** — завантажує оновлений список з OpenSanctions
2. **Щодня о 3:00** (Europe/Kyiv) — автоматичне оновлення

Ручний запуск:
```bash
python scripts/fetch_sanctions.py
```

Джерело: [drs.nsdc.gov.ua](https://drs.nsdc.gov.ua/export/subjects) → [OpenSanctions ua_nsdc_sanctions](https://www.opensanctions.org/datasets/ua_nsdc_sanctions/)

## Тестування

```bash
# Unit-тести
python -m pytest tests/ -v

# Тест API (потрібен запущений сервер)
python scripts/test_via_api.py http://localhost:8000
```

## Docker

Docker-образ **включає всі моделі** (spaCy, RoBERTa NER, MamayLM ~3GB) — окреме завантаження не потрібне.

```bash
# Збірка і запуск (перша збірка ~15–20 хв — завантаження моделей)
docker compose up -d

# Якщо модель закрита на HuggingFace:
HF_TOKEN=hf_xxx docker compose build
```

Порт: 8000. Документація: http://localhost:8000/docs

## Структура проекту

```
├── app/           # Код застосунку
│   ├── main.py    # FastAPI
│   ├── config.py
│   ├── services/  # Pipeline, NER, LLM, sanctions
│   └── data/      # Паттерни, санкційний список
├── tests/
├── scripts/
├── run.py
└── requirements.txt
```

## Ліцензія

[Вказати ліцензію]
