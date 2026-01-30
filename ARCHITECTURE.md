# Ukrainian Name Detection API - Архітектура

## Вимоги
- **Навантаження:** > 100 RPS
- **Ресурси:** 16GB RAM, без GPU
- **Точність:** < 1% помилок (критична)
- **Режим:** Real-time API

## Проблема

При 100+ RPS та 16GB RAM без GPU, використання LLM для кожного запиту **неможливе**:
- Gemma 9B: ~2-5 сек/запит на CPU = max 0.5 RPS
- Gemma 2B quantized: ~0.5-1 сек/запит = max 2 RPS

**Рішення:** Багаторівнева архітектура з мінімальним використанням LLM.

---

## Архітектура: Multi-Tier Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                         Запит                                   │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 1: Швидкий фільтр (< 1ms)                                 │
│  - Regex для очевидних випадків БЕЗ ПІБ                         │
│  - "зарплата", "аванс", "податки" → НЕ МІСТИТЬ ПІБ              │
│  - Пусті/короткі коментарі                                      │
│  Очікувано: 60-70% запитів завершуються тут                     │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 2: NER модель (5-20ms)                                    │
│  - spaCy uk_core_news_trf або uk_core_news_md                   │
│  - Розпізнає PER (персони) в тексті                             │
│  - Класифікує: ПІБ, Ім'я+Прізвище, тільки Ім'я                  │
│  Очікувано: 25-35% запитів                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 3: LLM Fallback (1-3 сек) - ТІЛЬКИ для складних випадків  │
│  - Неоднозначні результати NER                                  │
│  - Низька впевненість                                           │
│  - Черга з rate limiting                                        │
│  Очікувано: 3-5% запитів                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Компоненти

### Tier 1: Quick Filter

**Характеристики:**
- Час: < 1ms
- RAM: ~1MB
- Throughput: 10,000+ RPS

**Реалізація:**
```python
# Швидкі паттерни БЕЗ ПІБ
NO_NAME_PATTERNS = [
    r'^(зарплата|зп|з/п)(\s|$)',
    r'^(аванс|премія|виплата)(\s|$)',
    r'^(поповнення|переказ коштів)$',
    r'^(податки|єсв|пдв)(\s|$)',
    r'^\d+[\s\.]*(грн|uah|₴)',
]
```

### Tier 2: NER Engine

**Модель:** `uk_core_news_trf` (трансформер) або `uk_core_news_md` (швидша)

**Характеристики uk_core_news_trf:**
- Час: 10-30ms на CPU
- RAM: ~2GB
- Throughput: 30-100 RPS (з threading)

**Характеристики uk_core_news_md:**
- Час: 2-5ms
- RAM: ~200MB
- Throughput: 200-500 RPS
- Точність: на 5-10% нижча

### Tier 3: LLM Fallback

**Модель:** `INSAIT-Institute/MamayLM` - спеціалізована українська LLM

**Про MamayLM:**
- Базується на Gemma 2 9B
- Оптимізована для української мови
- HuggingFace: `INSAIT-Institute/MamayLM-Gemma2-9B-Instruct`
- Підтримує GGUF формат для llama.cpp/Ollama

**Варіанти запуску:**
1. **Через Ollama** (рекомендовано):
   ```bash
   # Створити Modelfile для MamayLM
   ollama create mamaylm -f Modelfile
   ```

2. **Через llama-cpp-python** (для більшого контролю):
   ```python
   from llama_cpp import Llama
   llm = Llama(model_path="mamaylm-9b-q4_k_m.gguf", n_ctx=2048)
   ```

3. **Через HuggingFace Transformers** (потребує більше RAM):
   ```python
   from transformers import AutoModelForCausalLM, AutoTokenizer
   model = AutoModelForCausalLM.from_pretrained("INSAIT-Institute/MamayLM-Gemma2-9B-Instruct")
   ```

**Коли викликається:**
- NER повернув суперечливі результати
- Confidence < 0.7
- Виявлено потенційне ім'я, але не впевнений у класифікації

**Rate Limiting:**
- Max 5 concurrent LLM requests
- Timeout: 10 секунд
- Fallback до NER результату при timeout

**Характеристики MamayLM (Q4 quantized):**
- RAM: ~6GB
- Час відповіді: 2-5 сек на CPU
- Точність на українській: найвища серед open-source

---

## Структура проекту

```
fullname_detector/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── config.py            # Налаштування
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py       # Pydantic моделі
│   ├── services/
│   │   ├── __init__.py
│   │   ├── quick_filter.py  # Tier 1: Regex фільтр
│   │   ├── ner_engine.py    # Tier 2: spaCy NER
│   │   ├── llm_fallback.py  # Tier 3: Ollama
│   │   ├── pipeline.py      # Orchestration
│   │   └── cache.py         # LRU/Redis cache
│   └── data/
│       ├── patterns.py      # Regex паттерни
│       └── name_lists.py    # Списки імен/прізвищ
├── tests/
│   ├── test_quick_filter.py
│   ├── test_ner_engine.py
│   ├── test_pipeline.py
│   └── test_data/
│       └── comments.json    # Тестові дані
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## Залежності

```txt
# requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
gunicorn==21.2.0
pydantic==2.5.3
spacy==3.7.2
aiohttp==3.9.1
python-multipart==0.0.6
cachetools==5.3.2
httpx==0.26.0
pytest==7.4.4
pytest-asyncio==0.23.3

# Для MamayLM (вибрати один варіант)
# Варіант 1: llama-cpp-python (рекомендовано для CPU)
llama-cpp-python==0.2.56

# Варіант 2: HuggingFace (потребує більше RAM)
# transformers==4.37.0
# accelerate==0.26.0
# torch==2.1.2
```

---

## Налаштування MamayLM

### Варіант 1: Через Ollama (найпростіше)

```bash
# 1. Завантажити GGUF модель
wget https://huggingface.co/INSAIT-Institute/MamayLM-Gemma2-9B-Instruct-GGUF/resolve/main/mamaylm-gemma2-9b-instruct-q4_k_m.gguf

# 2. Створити Modelfile
cat > Modelfile << 'EOF'
FROM ./mamaylm-gemma2-9b-instruct-q4_k_m.gguf

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_ctx 2048

SYSTEM """Ти - асистент для аналізу українських платіжних коментарів. Твоє завдання - визначати чи містить коментар ПІБ (прізвище, ім'я, по батькові)."""
EOF

# 3. Створити модель в Ollama
ollama create mamaylm -f Modelfile

# 4. Перевірити
ollama run mamaylm "Визнач ПІБ: Переказ Іванову Петру"
```

### Варіант 2: Через llama-cpp-python (більше контролю)

```python
from llama_cpp import Llama

llm = Llama(
    model_path="mamaylm-gemma2-9b-instruct-q4_k_m.gguf",
    n_ctx=2048,
    n_threads=4,
    verbose=False
)

response = llm(
    "Визнач ПІБ у коментарі: Переказ Іванову Петру",
    max_tokens=100,
    temperature=0.1
)
```

### Варіант 3: Через HuggingFace (потребує 16GB+ RAM)

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model_name = "INSAIT-Institute/MamayLM-Gemma2-9B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto"
)
```

---

## Оптимізації

### 1. Caching
```python
from cachetools import LRUCache

cache = LRUCache(maxsize=10000)
# Очікувана cache hit rate: 20-40%
```

### 2. Async Processing
```python
@app.post("/detect-name")
async def detect_name_endpoint(request: Request):
    return await asyncio.to_thread(process_comment, request.comment)
```

### 3. Worker Pool
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
# 4 workers × 25 RPS = 100+ RPS
```

---

## API Endpoints

### POST /detect-name

**Request:**
```json
{
  "comment": "Переказ Іванову Петру Олександровичу"
}
```

**Response:**
```json
{
  "has_name": true,
  "category": "Фамилия + Имя + Отчество",
  "detected_name": "Іванов Петро Олександрович",
  "confidence": 0.95,
  "tier_used": 2
}
```

### GET /health

**Response:**
```json
{
  "status": "healthy",
  "ner_model": "loaded",
  "llm_available": true
}
```

---

## Очікувані результати

| Метрика | Значення |
|---------|----------|
| Throughput | 100-150 RPS |
| P50 Latency | 5ms |
| P95 Latency | 50ms |
| P99 Latency | 200ms |
| RAM Usage | 3-4GB |
| Error Rate | < 1% |

---

## Запуск

### Development
```bash
# Встановлення залежностей
pip install -r requirements.txt
python -m spacy download uk_core_news_trf

# Запуск MamayLM через Ollama
ollama serve

# Завантажити GGUF модель MamayLM та створити Modelfile
# Див. секцію "Налаштування MamayLM"

# Запуск API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production
```bash
# Docker
docker-compose up -d

# Або напряму
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```

---

## Тестування

```bash
# Unit тести
pytest tests/ -v

# Тест API
curl -X POST http://localhost:8000/detect-name \
  -H "Content-Type: application/json" \
  -d '{"comment": "Переказ Іванову Петру Олександровичу"}'
```

---

## План імплементації

- [ ] Етап 1: Базова структура проекту
- [ ] Етап 2: Tier 1 - Quick Filter (regex)
- [ ] Етап 3: Tier 2 - NER Engine (spaCy)
- [ ] Етап 4: Tier 3 - LLM Fallback (MamayLM)
- [ ] Етап 5: Pipeline та caching
- [ ] Етап 6: Тести та Docker
