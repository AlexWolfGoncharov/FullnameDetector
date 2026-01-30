"""Cache service for name detection results"""

import hashlib
import logging
from typing import Optional

from cachetools import LRUCache

from app.models.schemas import NameDetectionResponse
from app.config import get_settings

logger = logging.getLogger(__name__)


class CacheService:
    """LRU Cache for name detection results"""

    def __init__(self):
        self.settings = get_settings()
        self._cache: Optional[LRUCache] = None
        self._hits = 0
        self._misses = 0

        if self.settings.cache_enabled:
            self._cache = LRUCache(maxsize=self.settings.cache_maxsize)
            logger.info(f"Cache initialized with maxsize={self.settings.cache_maxsize}")

    @property
    def is_enabled(self) -> bool:
        return self._cache is not None

    def _get_key(self, comment: str) -> str:
        """Generate cache key from comment"""
        normalized = comment.strip().lower()
        return hashlib.md5(normalized.encode()).hexdigest()

    def get(self, comment: str) -> Optional[NameDetectionResponse]:
        """Get cached result"""
        if not self.is_enabled:
            return None

        key = self._get_key(comment)
        result = self._cache.get(key)

        if result is not None:
            self._hits += 1
            logger.debug(f"Cache hit for: {comment[:30]}...")
            return result

        self._misses += 1
        return None

    def set(self, comment: str, response: NameDetectionResponse) -> None:
        """Cache result"""
        if not self.is_enabled:
            return

        key = self._get_key(comment)
        self._cache[key] = response
        logger.debug(f"Cached result for: {comment[:30]}...")

    def get_stats(self) -> dict:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        return {
            "enabled": self.is_enabled,
            "size": len(self._cache) if self._cache else 0,
            "maxsize": self.settings.cache_maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%"
        }

    def clear(self) -> None:
        """Clear cache"""
        if self._cache:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info("Cache cleared")
