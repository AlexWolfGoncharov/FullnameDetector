"""Main pipeline orchestrating all tiers"""

import logging
import asyncio
from typing import Optional

from app.models.schemas import NameDetectionResponse, NameCategory
from app.services.quick_filter import QuickFilter
from app.services.ner_engine import NEREngine
from app.services.llm_fallback import LLMFallback
from app.services.cache import CacheService
from app.config import get_settings

logger = logging.getLogger(__name__)


class NameDetectionPipeline:
    """
    Multi-tier pipeline for name detection.

    Flow:
    1. Cache check
    2. Tier 1: Quick Filter (regex)
    3. Tier 2: NER Engine (spaCy)
    4. Tier 3: LLM Fallback (MamayLM) - only for low confidence
    """

    def __init__(self):
        self.settings = get_settings()
        self.cache = CacheService()
        self.quick_filter = QuickFilter()
        self.ner_engine = NEREngine()
        self.llm_fallback = LLMFallback()

        self._stats = {
            "total_requests": 0,
            "tier1_handled": 0,
            "tier2_handled": 0,
            "tier3_handled": 0,
            "cache_hits": 0
        }

    def initialize(self) -> dict:
        """Initialize all components and return status"""
        status = {
            "cache": self.cache.is_enabled,
            "quick_filter": True,
            "ner_engine": self.ner_engine.load(),
            "llm_fallback": self.llm_fallback.load() if self.settings.llm_enabled else False
        }

        logger.info(f"Pipeline initialized: {status}")
        return status

    def process_sync(self, comment: str) -> NameDetectionResponse:
        """Synchronous processing"""
        self._stats["total_requests"] += 1

        # Извлекаем часть после первого тире (кастомный комментарий с ПІБ)
        # Формат: "Стандартное назначение-Кастомный комментарий с ПІБ"
        original_comment = comment
        if "-" in comment:
            parts = comment.split("-", 1)  # Разделяем только по первому тире
            comment = parts[1].strip() if len(parts) > 1 else comment
            logger.debug(f"Extracted custom part: '{comment}' from '{original_comment}'")
        
        # Если после тире ничего нет или только пробелы, возвращаем "нет ПІБ"
        if not comment or not comment.strip():
            result = NameDetectionResponse(
                has_name=False,
                category=NameCategory.NO_NAME,
                detected_name=None,
                confidence=1.0,
                tier_used=1
            )
            self.cache.set(original_comment, result)
            return result

        # Check cache (используем оригинальный комментарий для кеша)
        cached = self.cache.get(original_comment)
        if cached:
            self._stats["cache_hits"] += 1
            return cached

        # Tier 1: Quick Filter
        result = self.quick_filter.process(comment)
        if result is not None:
            self._stats["tier1_handled"] += 1
            self.cache.set(original_comment, result)
            return result

        # Tier 2: NER Engine
        result, confidence = self.ner_engine.process(comment)
        if result is not None:
            if confidence >= self.settings.ner_confidence_threshold:
                self._stats["tier2_handled"] += 1
                self.cache.set(original_comment, result)
                return result

            # Low confidence - try LLM if available
            if self.llm_fallback.is_available:
                llm_result = self.llm_fallback.process_sync(comment)
                if llm_result is not None:
                    self._stats["tier3_handled"] += 1
                    self.cache.set(original_comment, llm_result)
                    return llm_result

            # Fallback to NER result
            self._stats["tier2_handled"] += 1
            self.cache.set(original_comment, result)
            return result

        # Should not reach here, but return default
        default_result = NameDetectionResponse(
            has_name=False,
            category=NameCategory.NO_NAME,
            detected_name=None,
            confidence=0.5,
            tier_used=2
        )
        self.cache.set(original_comment, default_result)
        return default_result

    async def process(self, comment: str) -> NameDetectionResponse:
        """Async processing - uses thread pool for CPU-bound operations"""
        # For now, delegate to sync version in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.process_sync, comment)

    def get_stats(self) -> dict:
        """Get pipeline statistics"""
        total = self._stats["total_requests"]
        if total == 0:
            percentages = {"tier1": 0, "tier2": 0, "tier3": 0, "cache": 0}
        else:
            percentages = {
                "tier1": self._stats["tier1_handled"] / total * 100,
                "tier2": self._stats["tier2_handled"] / total * 100,
                "tier3": self._stats["tier3_handled"] / total * 100,
                "cache": self._stats["cache_hits"] / total * 100
            }

        return {
            "total_requests": total,
            "tier1_handled": self._stats["tier1_handled"],
            "tier2_handled": self._stats["tier2_handled"],
            "tier3_handled": self._stats["tier3_handled"],
            "cache_hits": self._stats["cache_hits"],
            "percentages": {k: f"{v:.1f}%" for k, v in percentages.items()},
            "cache_stats": self.cache.get_stats()
        }

    def get_health(self) -> dict:
        """Get health status of all components"""
        return {
            "ner_engine": "loaded" if self.ner_engine.is_loaded else "not_loaded",
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
