"""Main pipeline orchestrating all tiers"""

import re
import time
import logging
import asyncio
from typing import Optional

from app.models.schemas import NameDetectionResponse, NameCategory, SanctionsCheckResult
from app.services.quick_filter import QuickFilter
from app.services.ner_engine import NEREngine
from app.services.roberta_ner import get_roberta_ner
from app.services.llm_fallback import LLMFallback
from app.services.cache import CacheService
from app.services.request_logger import get_request_logger
from app.services.sanctions_checker import get_sanctions_checker
from app.config import get_settings

logger = logging.getLogger(__name__)


class NameDetectionPipeline:
    """
    Multi-tier pipeline for name detection.

    Flow:
    1. Cache check
    2. Tier 1: Quick Filter (regex)
    3. Tier 2a: spaCy NER (uk_core_news_md)
    4. Tier 2b: RoBERTa NER (xlm-roberta-base-ukrainian-ner)
    5. Tier 3: LLM Fallback (MamayLM) - for verification and complex cases
    """

    def __init__(self):
        self.settings = get_settings()
        self.cache = CacheService()
        self.quick_filter = QuickFilter()
        self.ner_engine = NEREngine()
        self.roberta_ner = get_roberta_ner()
        self.llm_fallback = LLMFallback()
        self.request_logger = get_request_logger()
        self.sanctions_checker = get_sanctions_checker()

        self._stats = {
            "total_requests": 0,
            "tier1_handled": 0,
            "tier2_handled": 0,
            "tier2b_handled": 0,  # RoBERTa NER
            "tier3_handled": 0,
            "cache_hits": 0
        }

    def initialize(self) -> dict:
        """Initialize all components and return status"""
        llm_loaded = False
        if self.settings.llm_enabled:
            llm_loaded = self.llm_fallback.load()
            if llm_loaded:
                logger.info("LLM fallback loaded and available")
            else:
                logger.warning("LLM fallback enabled but failed to load")
        else:
            logger.info("LLM fallback is disabled in settings")
        
        # Load RoBERTa NER (optional - may fail if transformers not installed)
        roberta_loaded = False
        try:
            roberta_loaded = self.roberta_ner.load()
            if roberta_loaded:
                logger.info("RoBERTa NER loaded and available")
        except Exception as e:
            logger.warning(f"RoBERTa NER failed to load: {e}")

        status = {
            "cache": self.cache.is_enabled,
            "quick_filter": True,
            "ner_engine": self.ner_engine.load(),
            "roberta_ner": roberta_loaded,
            "llm_fallback": llm_loaded
        }

        logger.info(f"Pipeline initialized: {status}")
        logger.info(f"LLM available: {self.llm_fallback.is_available}")
        logger.info(f"RoBERTa NER available: {self.roberta_ner.is_loaded}")
        logger.info(f"Sanctions checker: {self.sanctions_checker.get_stats()}")
        return status

    GREETING_PHRASES = frozenset({
        'слава україні', 'зі святим миколаєм', 'з новим роком',
        'вітаю з різдвом', 'з днем народження', 'з 8 березня',
    })

    def _is_greeting_not_name(self, text: str) -> bool:
        """Чи є текст привітанням, а не ПІБ"""
        if not text:
            return False
        t = text.strip().lower()
        return t in self.GREETING_PHRASES or t.startswith(('слава ', 'зі святим ', 'з новим '))

    def _extract_full_name_from_text(self, text: str) -> Optional[str]:
        """Витягти повне ПІБ (3 слова) з тексту, якщо є чіткий патерн"""
        if not text or len(text.split()) < 3:
            return None
        # Прізвище Ім'я По-батькові (третє слово — відмінкове закінчення)
        pat = r'([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+(?:ович|івна|овна|евич|ївна|евна|ич|івич))'
        m = re.search(pat, text.strip())
        return m.group(0) if m else None

    def _with_meta(
        self,
        result: NameDetectionResponse,
        tier_detail: str,
        t0: float
    ) -> NameDetectionResponse:
        """Додати tier_detail та processing_time_ms до відповіді"""
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return result.model_copy(
            update={"tier_detail": tier_detail, "processing_time_ms": round(elapsed_ms, 2)}
        )

    def _check_sanctions(self, result: NameDetectionResponse) -> NameDetectionResponse:
        """Перевірка імені на санкційний список"""
        if not result.has_name or not result.detected_name:
            return result

        if not self.sanctions_checker.is_loaded:
            return result

        match = self.sanctions_checker.check(result.detected_name, result.category)

        result.sanctions_check = SanctionsCheckResult(
            checked=True,
            found=match.found,
            match_type=match.match_type if match.found else None,
            matched_name=match.matched_name,
            status=match.status,
            confidence=match.confidence
        )

        if match.found:
            logger.warning(
                f"Sanctions match: '{result.detected_name}' -> '{match.matched_name}' "
                f"({match.match_type}, {match.status})"
            )

        return result

    def process_sync(self, comment: str) -> NameDetectionResponse:
        """Synchronous processing"""
        t0 = time.perf_counter()
        self._stats["total_requests"] += 1

        # Извлекаем часть после первого тире (кастомный комментарий с ПІБ)
        # Формат: "Стандартное назначение-Кастомный комментарий с ПІБ"
        # Або: "ПІБ-Призначення" (ім'я перед тире)
        original_comment = comment
        processed_comment = comment
        STANDARD_WORDS = {'зарплата', 'заробітна', 'премія', 'аванс', 'виплата', 'переказ', 'оплата'}

        if "-" in comment:
            parts = comment.split("-", 1)
            part_before = parts[0].strip() if parts[0] else ""
            part_after = parts[1].strip() if len(parts) > 1 else ""

            # Якщо після тире - стандартне призначення (одне слово), беремо частину перед тире
            if part_after and part_after.lower() in STANDARD_WORDS and len(part_before.split()) >= 2:
                processed_comment = part_before  # "ПІБ - зарплата"
            else:
                processed_comment = part_after or part_before
            logger.debug(f"Extracted: '{processed_comment}' from '{original_comment}'")

        # Если после тире ничего нет или только пробелы, возвращаем "нет ПІБ"
        if not processed_comment or not processed_comment.strip():
            result = NameDetectionResponse(
                has_name=False,
                category=NameCategory.NO_NAME,
                detected_name=None,
                confidence=1.0,
                tier_used=1
            )
            self.cache.set(original_comment, result)
            r = self._with_meta(result, "1", t0)
            self.request_logger.log(original_comment, processed_comment, r)
            return r

        # Check cache (используем оригинальный комментарий для кеша)
        cached = self.cache.get(original_comment)
        if cached:
            self._stats["cache_hits"] += 1
            return self._with_meta(cached, "cache", t0)

        # Tier 1: Quick Filter
        result = self.quick_filter.process(processed_comment)
        if result is not None:
            self._stats["tier1_handled"] += 1
            result = self._check_sanctions(result)
            self.cache.set(original_comment, result)
            r = self._with_meta(result, "1", t0)
            self.request_logger.log(original_comment, processed_comment, r)
            return r

        # Tier 2a: spaCy NER Engine
        spacy_result, spacy_confidence = self.ner_engine.process(processed_comment)

        # Tier 2b: RoBERTa NER (if available)
        roberta_result = None
        roberta_confidence = 0.0
        if self.roberta_ner.is_loaded:
            try:
                roberta_result, roberta_confidence = self.roberta_ner.process(processed_comment)
            except Exception as e:
                logger.warning(f"RoBERTa NER failed: {e}")

        # Вибираємо найкращий результат з NER моделей
        result = None
        confidence = 0.0

        tier_detail = "2a"  # default NER
        if roberta_result and spacy_result:
            # Пріоритет: повне ПІБ (FULL_NAME) над частковим, потім за confidence
            spacy_full = spacy_result.category == NameCategory.FULL_NAME
            roberta_full = roberta_result.category == NameCategory.FULL_NAME
            if spacy_full and not roberta_full:
                result = spacy_result
                confidence = spacy_confidence
                tier_detail = "2a"
                logger.debug("Using spaCy: FULL_NAME (RoBERTa partial)")
            elif roberta_full and not spacy_full:
                result = roberta_result
                confidence = roberta_confidence
                tier_detail = "2b"
                logger.debug("Using RoBERTa: FULL_NAME")
            elif roberta_confidence > spacy_confidence:
                result = roberta_result
                confidence = roberta_confidence
                tier_detail = "2b"
            else:
                result = spacy_result
                confidence = spacy_confidence
                tier_detail = "2a"
        elif roberta_result:
            result = roberta_result
            confidence = roberta_confidence
            tier_detail = "2b"
        elif spacy_result:
            result = spacy_result
            confidence = spacy_confidence
            tier_detail = "2a"

        if result is not None:
            # Верифікуємо через LLM якщо доступний і впевненість низька
            if self.llm_fallback.is_available and confidence < self.settings.llm_verification_threshold:
                try:
                    llm_result = self.llm_fallback.process_sync(processed_comment)
                    if llm_result is not None:
                        # Використовуємо LLM якщо він знайшов повніше ім'я
                        use_llm = (
                            (llm_result.has_name and not result.has_name) or
                            (llm_result.category == NameCategory.FULL_NAME and
                             result.category != NameCategory.FULL_NAME) or
                            (llm_result.confidence > confidence + 0.1)
                        )
                        if use_llm:
                            logger.debug(f"LLM verified: {llm_result.category}")
                            self._stats["tier3_handled"] += 1
                            llm_result = self._check_sanctions(llm_result)
                            self.cache.set(original_comment, llm_result)
                            r = self._with_meta(llm_result, "3", t0)
                            self.request_logger.log(original_comment, processed_comment, r)
                            return r
                except Exception as e:
                    logger.warning(f"LLM verification failed: {e}")

            # Використовуємо результат NER - але відкидаємо привітання
            if result.has_name and result.detected_name and self._is_greeting_not_name(result.detected_name):
                result = NameDetectionResponse(
                    has_name=False, category=NameCategory.NO_NAME,
                    detected_name=None, confidence=1.0, tier_used=2
                )
            # Якщо NER повернув часткове ім'я, але текст містить повне ПІБ (3 слова) — коригуємо
            elif result.has_name and result.category != NameCategory.FULL_NAME:
                full_match = self._extract_full_name_from_text(processed_comment)
                if full_match:
                    result = result.model_copy(
                        update={
                            "has_name": True,
                            "category": NameCategory.FULL_NAME,
                            "detected_name": full_match,
                            "confidence": max(result.confidence, 0.9),
                        }
                    )
                    logger.debug(f"Upgraded to FULL_NAME: {full_match}")
            self._stats["tier2_handled"] += 1
            if tier_detail == "2b":
                self._stats["tier2b_handled"] += 1
            result = self._check_sanctions(result)
            self.cache.set(original_comment, result)
            r = self._with_meta(result, tier_detail, t0)
            self.request_logger.log(original_comment, processed_comment, r)
            return r

        # NER не дав результат - пробуємо LLM
        if self.llm_fallback.is_available:
            llm_result = self.llm_fallback.process_sync(processed_comment)
            if llm_result is not None:
                self._stats["tier3_handled"] += 1
                llm_result = self._check_sanctions(llm_result)
                self.cache.set(original_comment, llm_result)
                r = self._with_meta(llm_result, "3", t0)
                self.request_logger.log(original_comment, processed_comment, r)
                return r

        # Should not reach here, but return default
        default_result = NameDetectionResponse(
            has_name=False,
            category=NameCategory.NO_NAME,
            detected_name=None,
            confidence=0.5,
            tier_used=2
        )
        self.cache.set(original_comment, default_result)
        r = self._with_meta(default_result, "2a", t0)
        self.request_logger.log(original_comment, processed_comment, r)
        return r

    async def process(self, comment: str) -> NameDetectionResponse:
        """Async processing - uses thread pool for CPU-bound operations"""
        # For now, delegate to sync version in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.process_sync, comment)

    def get_stats(self) -> dict:
        """Get pipeline statistics"""
        total = self._stats["total_requests"]
        if total == 0:
            percentages = {"tier1": 0, "tier2": 0, "tier2b": 0, "tier3": 0, "cache": 0}
        else:
            percentages = {
                "tier1": self._stats["tier1_handled"] / total * 100,
                "tier2": self._stats["tier2_handled"] / total * 100,
                "tier2b": self._stats["tier2b_handled"] / total * 100,
                "tier3": self._stats["tier3_handled"] / total * 100,
                "cache": self._stats["cache_hits"] / total * 100
            }

        return {
            "total_requests": total,
            "tier1_handled": self._stats["tier1_handled"],
            "tier2_handled": self._stats["tier2_handled"],
            "tier2b_handled": self._stats["tier2b_handled"],
            "tier3_handled": self._stats["tier3_handled"],
            "cache_hits": self._stats["cache_hits"],
            "percentages": {k: f"{v:.1f}%" for k, v in percentages.items()},
            "cache_stats": self.cache.get_stats()
        }

    def get_health(self) -> dict:
        """Get health status of all components"""
        return {
            "ner_engine": "loaded" if self.ner_engine.is_loaded else "not_loaded",
            "roberta_ner": "loaded" if self.roberta_ner.is_loaded else "not_loaded",
            "llm_fallback": "available" if self.llm_fallback.is_available else "unavailable",
            "cache": "enabled" if self.cache.is_enabled else "disabled"
        }


# Global pipeline instance
_pipeline: Optional[NameDetectionPipeline] = None


def get_pipeline() -> NameDetectionPipeline:
    """Get or create global pipeline instance"""
    global _pipeline
    if _pipeline is None:
        _pipeline = NameDetectionPipeline()
        _pipeline.initialize()
    return _pipeline
