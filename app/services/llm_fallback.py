"""Tier 3: LLM Fallback - Ollama or llama.cpp for complex cases"""

import re
import asyncio
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.models.schemas import NameCategory, NameDetectionResponse
from app.config import get_settings

logger = logging.getLogger(__name__)


# Prompt template для Gemma 3 (формат chat template)
PROMPT_TEMPLATE = """<bos><start_of_turn>user
Проаналізуй український платіжний коментар і визнач, чи містить він ПІБ (прізвище, ім'я, по батькові) людини.

ІГНОРУЙ ці слова як НЕ імена: зарплата, премія, аванс, виплата, переказ, податки, поповнення, рахунок, оплата, послуги, товари.

Відповідь ТІЛЬКИ в одному з форматів:
1. "ПОВНЕ_ПІБ | Прізвище Ім'я По-батькові" - якщо є всі три частини
2. "ПРІЗВИЩЕ_ІМЯ | Прізвище Ім'я" - якщо є прізвище та ім'я
3. "ТІЛЬКИ_ПРІЗВИЩЕ | Прізвище" - якщо є тільки прізвище
4. "ТІЛЬКИ_ІМЯ | Ім'я" - якщо є тільки ім'я
5. "НЕМАЄ_ПІБ" - якщо ПІБ відсутнє

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
                return self._parse_llm_response(output)
            else:
                logger.error(f"Ollama error: {response.status_code}")

        except httpx.TimeoutException:
            logger.warning(f"Ollama timeout for: {comment[:50]}...")
        except Exception as e:
            logger.error(f"Ollama error: {e}")

        return None

    def _process_llama_cpp_sync(self, comment: str) -> Optional[NameDetectionResponse]:
        """Process with llama.cpp"""
        if self._llm is None:
            return None

        # Форматуємо промпт для Gemma 3
        prompt = PROMPT_TEMPLATE.format(comment=comment)

        try:
            response = self._llm(
                prompt,
                max_tokens=self.settings.llm_max_tokens,
                temperature=self.settings.llm_temperature,
                stop=["\n", "Коментар:"],
                echo=False
            )

            output = response["choices"][0]["text"].strip()
            logger.debug(f"LLM output: {output}")
            return self._parse_llm_response(output)

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

    def _parse_llm_response(self, output: str) -> NameDetectionResponse:
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
            category_str = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else None

            if "ПОВНЕ_ПІБ" in category_str:
                category = NameCategory.FULL_NAME
            elif "ПРІЗВИЩЕ_ІМЯ" in category_str:
                category = NameCategory.SURNAME_NAME
            elif "ТІЛЬКИ_ПРІЗВИЩЕ" in category_str:
                category = NameCategory.SURNAME_ONLY
            elif "ТІЛЬКИ_ІМЯ" in category_str:
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
                    category = NameCategory.NAME_ONLY

        has_name = category != NameCategory.NO_NAME

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
