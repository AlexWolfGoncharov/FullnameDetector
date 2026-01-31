"""Tier 3: LLM Fallback - Ollama or llama.cpp for complex cases"""

import re
import asyncio
import logging
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.models.schemas import NameCategory, NameDetectionResponse
from app.config import get_settings

logger = logging.getLogger(__name__)


# Prompt template для Gemma 3 (формат chat template)
# Примітка: <bos> не додаємо вручну - llama-cpp-python додає його автоматично
PROMPT_TEMPLATE = """<start_of_turn>user
Проаналізуй платіжний коментар. Визнач чи ЯВНО написане ПІБ людини.

КРИТИЧНО ВАЖЛИВО:
- Відповідай ТІЛЬКИ якщо ім'я/прізвище БУКВАЛЬНО написане в тексті
- НЕ вигадуй імена яких немає в тексті
- Якщо сумніваєшся - відповідай НЕМАЄ_ПІБ

НЕ є іменами: зарплата, заробітна, премія, аванс, виплата, переказ, оплата, рахунок, поповнення, товари, послуги, плата, жовтня, січня, лютого, березня, квітня, травня, червня, липня, серпня, вересня, листопада, грудня, року, грн, UAH.

Формат відповіді:
- "ПОВНЕ_ПІБ | Прізвище Ім'я По-батькові" - всі 3 частини є в тексті
- "ПРІЗВИЩЕ_ІМЯ | Прізвище Ім'я" - 2 частини є в тексті
- "ТІЛЬКИ_ПРІЗВИЩЕ | Прізвище" - тільки прізвище в тексті
- "ТІЛЬКИ_ІМЯ | Ім'я" - тільки ім'я в тексті
- "НЕМАЄ_ПІБ" - ПІБ не знайдено

Коментар: {comment}<end_of_turn>
<start_of_turn>model
"""


class LLMFallback:
    """
    Tier 3 processor - LLM for complex cases.

    Supports two backends:
    - Ollama (recommended, easier setup)
    - llama.cpp (lightweight, works on weak machines, uses GGUF format)
    
    Uses MamayLM-Gemma-3-4B-IT model in GGUF format for optimal performance
    on resource-constrained systems.
    """

    def __init__(self):
        self.settings = get_settings()
        self._llm = None  # For llama.cpp
        self._loaded = False
        self._executor = ThreadPoolExecutor(max_workers=self.settings.llm_max_concurrent)
        self._semaphore = asyncio.Semaphore(self.settings.llm_max_concurrent)
        # llama.cpp не thread-safe — серіалізуємо виклики
        self._llm_lock = threading.Lock()

    def load(self) -> bool:
        """Initialize LLM backend"""
        if self._loaded:
            return True

        if not self.settings.llm_enabled:
            logger.info("LLM fallback is disabled")
            return False

        if self.settings.llm_backend == "ollama":
            return self._init_ollama()
        else:
            return self._init_llama_cpp()

    def _init_ollama(self) -> bool:
        """Initialize Ollama backend"""
        try:
            response = httpx.get(
                f"{self.settings.ollama_base_url}/api/tags",
                timeout=5.0
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                logger.info(f"Ollama connected. Available models: {model_names}")

                if not any(self.settings.ollama_model in name for name in model_names):
                    logger.warning(
                        f"Model '{self.settings.ollama_model}' not found. "
                        f"Run: ollama pull {self.settings.ollama_model}"
                    )

                self._loaded = True
                return True
        except httpx.ConnectError:
            logger.warning(
                "Ollama not running. Start with: ollama serve\n"
                f"Then pull model: ollama pull {self.settings.ollama_model}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")

        return False

    def _init_llama_cpp(self) -> bool:
        """Initialize llama.cpp backend"""
        model_path = self.settings.llm_model_path

        if not model_path.exists():
            logger.warning(f"LLM model not found: {model_path}")
            logger.warning("Run setup to download: python -m app.setup")
            return False

        try:
            from llama_cpp import Llama

            logger.info(f"Loading LLM model: {model_path}")
            self._llm = Llama(
                model_path=str(model_path),
                n_ctx=self.settings.llm_context_length,
                n_threads=self.settings.llm_threads,
                verbose=False
            )
            self._loaded = True
            logger.info("LLM model loaded successfully")
            return True

        except ImportError:
            logger.error("llama-cpp-python not installed")
        except Exception as e:
            logger.error(f"Failed to load LLM model: {e}")

        return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def is_available(self) -> bool:
        return self._loaded

    def process_sync(self, comment: str) -> Optional[NameDetectionResponse]:
        """Synchronous processing"""
        if not self.is_available:
            return None

        if self.settings.llm_backend == "ollama":
            return self._process_ollama_sync(comment)
        else:
            return self._process_llama_cpp_sync(comment)

    def _process_ollama_sync(self, comment: str) -> Optional[NameDetectionResponse]:
        """Process with Ollama"""
        prompt = PROMPT_TEMPLATE.format(comment=comment)

        try:
            response = httpx.post(
                f"{self.settings.ollama_base_url}/api/generate",
                json={
                    "model": self.settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.settings.llm_temperature,
                        "num_predict": self.settings.llm_max_tokens,
                    }
                },
                timeout=self.settings.llm_timeout
            )

            if response.status_code == 200:
                result = response.json()
                output = result.get("response", "").strip()
                logger.debug(f"Ollama output: {output}")
                return self._parse_llm_response(output, comment)
            else:
                logger.error(f"Ollama error: {response.status_code}")

        except httpx.TimeoutException:
            logger.warning(f"Ollama timeout for: {comment[:50]}...")
        except Exception as e:
            logger.error(f"Ollama error: {e}")

        return None

    def _process_llama_cpp_sync(self, comment: str) -> Optional[NameDetectionResponse]:
        """Process with llama.cpp (thread-safe: llama.cpp не підтримує паралельні виклики)"""
        if self._llm is None:
            return None

        prompt = PROMPT_TEMPLATE.format(comment=comment)

        try:
            with self._llm_lock:
                response = self._llm(
                    prompt,
                    max_tokens=self.settings.llm_max_tokens,
                    temperature=self.settings.llm_temperature,
                    stop=["\n", "Коментар:"],
                    echo=False
                )

            output = response["choices"][0]["text"].strip()
            logger.debug(f"LLM output: {output}")
            return self._parse_llm_response(output, comment)

        except Exception as e:
            logger.error(f"LLM inference error: {e}")

        return None

    async def process(self, comment: str) -> Optional[NameDetectionResponse]:
        """Async processing with rate limiting"""
        if not self.is_available:
            return None

        async with self._semaphore:
            try:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, self.process_sync, comment),
                    timeout=self.settings.llm_timeout
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(f"LLM timeout for comment: {comment[:50]}...")
                return None
            except Exception as e:
                logger.error(f"LLM async error: {e}")
                return None

    def _parse_llm_response(self, output: str, original_comment: str = "") -> NameDetectionResponse:
        """Parse LLM response into structured response"""
        output = output.strip()

        if "НЕМАЄ_ПІБ" in output or "немає" in output.lower():
            return NameDetectionResponse(
                has_name=False,
                category=NameCategory.NO_NAME,
                detected_name=None,
                confidence=0.9,
                tier_used=3
            )

        name = None
        category = NameCategory.NO_NAME

        if "|" in output:
            parts = output.split("|", 1)
            category_str = parts[0].strip().upper()
            name = parts[1].strip() if len(parts) > 1 else None

            if "ПОВНЕ_ПІБ" in category_str or "ПОВНЕ" in category_str:
                category = NameCategory.FULL_NAME
            elif "ПРІЗВИЩЕ_ІМЯ" in category_str or ("ПРІЗВИЩЕ" in category_str and "ІМЯ" in category_str):
                category = NameCategory.SURNAME_NAME
            elif "ТІЛЬКИ_ПРІЗВИЩЕ" in category_str:
                category = NameCategory.SURNAME_ONLY
            elif "ТІЛЬКИ_ІМЯ" in category_str:
                category = NameCategory.NAME_ONLY
            elif name:
                # Категорія не розпізнана, але є ім'я - визначаємо за кількістю слів
                words = name.split()
                if len(words) >= 3:
                    category = NameCategory.FULL_NAME
                elif len(words) == 2:
                    category = NameCategory.SURNAME_NAME
                else:
                    word = words[0].lower()
                    surname_endings = (
                        'енко', 'ченко', 'ук', 'чук', 'юк', 'ак', 'як',
                        'ський', 'цький', 'зький', 'ний', 'ий', 'ов', 'ев', 'єв',
                        'ін', 'їн', 'ко', 'ло', 'но', 'шин', 'ишин'
                    )
                    if word.endswith(surname_endings):
                        category = NameCategory.SURNAME_ONLY
                    else:
                        category = NameCategory.NAME_ONLY
        else:
            name_match = re.search(
                r'([А-ЯІЇЄҐ][а-яіїєґ\']+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ\']+)*)',
                output
            )
            if name_match:
                name = name_match.group(1)
                words = name.split()
                if len(words) >= 3:
                    category = NameCategory.FULL_NAME
                elif len(words) == 2:
                    category = NameCategory.SURNAME_NAME
                else:
                    # Одне слово - визначаємо прізвище це чи ім'я за закінченням
                    word = words[0].lower()
                    # Типові закінчення українських прізвищ
                    surname_endings = (
                        'енко', 'ченко', 'ук', 'чук', 'юк', 'ак', 'як',
                        'ський', 'цький', 'зький', 'ний', 'ий', 'ов', 'ев', 'єв',
                        'ін', 'їн', 'ко', 'ло', 'но', 'шин', 'ишин'
                    )
                    if word.endswith(surname_endings):
                        category = NameCategory.SURNAME_ONLY
                    else:
                        category = NameCategory.NAME_ONLY

        has_name = category != NameCategory.NO_NAME

        # Стоп-слова які часто помилково розпізнаються як імена
        STOP_WORDS = {
            'заробітна', 'зарплата', 'премія', 'аванс', 'виплата', 'переказ',
            'оплата', 'рахунок', 'поповнення', 'товари', 'послуги', 'плата',
            'прізвище', 'ім\'я', 'імя', 'батькові',
            'картки', 'карток', 'картка', 'рахунки', 'рахунків',
            'допомога', 'допомоги', 'соціальна', 'матеріальна',
            'квартальна', 'річна', 'місячна'
        }

        # Перевірка на стоп-слова
        if has_name and name:
            name_lower = name.lower()
            for stop_word in STOP_WORDS:
                if stop_word in name_lower:
                    logger.warning(f"Stop word detected in name: '{name}'")
                    return NameDetectionResponse(
                        has_name=False,
                        category=NameCategory.NO_NAME,
                        detected_name=None,
                        confidence=0.7,
                        tier_used=3
                    )

        # Валідація: перевіряємо що знайдене ім'я дійсно є в оригінальному тексті
        if has_name and name and original_comment:
            # Перевіряємо кожну частину імені
            name_parts = name.split()
            found_parts = [part for part in name_parts if part.lower() in original_comment.lower()]

            # Якщо жодна частина не знайдена - це повна галюцінація
            if len(found_parts) == 0:
                logger.warning(f"LLM hallucination detected: '{name}' not found in '{original_comment}'")
                return NameDetectionResponse(
                    has_name=False,
                    category=NameCategory.NO_NAME,
                    detected_name=None,
                    confidence=0.7,
                    tier_used=3
                )

            # Якщо знайдено тільки частину - використовуємо тільки знайдені частини
            if len(found_parts) < len(name_parts):
                logger.info(f"Partial match: using '{' '.join(found_parts)}' instead of '{name}'")
                name = ' '.join(found_parts)
                # Перевизначаємо категорію
                if len(found_parts) >= 3:
                    category = NameCategory.FULL_NAME
                elif len(found_parts) == 2:
                    category = NameCategory.SURNAME_NAME
                else:
                    word = found_parts[0].lower()
                    surname_endings = (
                        'енко', 'ченко', 'ук', 'чук', 'юк', 'ак', 'як',
                        'ський', 'цький', 'зький', 'ний', 'ий', 'ов', 'ев', 'єв',
                        'ін', 'їн', 'ко', 'ло', 'но', 'шин', 'ишин'
                    )
                    if word.endswith(surname_endings):
                        category = NameCategory.SURNAME_ONLY
                    else:
                        category = NameCategory.NAME_ONLY

        return NameDetectionResponse(
            has_name=has_name,
            category=category,
            detected_name=name if has_name else None,
            confidence=0.85,
            tier_used=3
        )

    def __del__(self):
        """Cleanup"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
