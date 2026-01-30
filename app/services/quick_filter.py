"""Tier 1: Quick Filter - Fast regex-based filtering"""

import re
import logging
from typing import Optional, Tuple

from app.models.schemas import NameCategory, NameDetectionResponse
from app.data.patterns import matches_no_name_pattern, matches_name_indicator

logger = logging.getLogger(__name__)


class QuickFilter:
    """
    Tier 1 processor - fast regex filtering.

    Handles ~60-70% of requests by quickly identifying:
    - Comments that definitely don't contain names
    - Very short/empty comments
    - Numeric-only comments
    """

    def __init__(self):
        self.min_length = 3  # Minimum comment length to process

    def process(self, comment: str) -> Optional[NameDetectionResponse]:
        """
        Try to quickly determine if comment has no name.

        Returns:
            NameDetectionResponse if we can determine NO_NAME with high confidence
            None if the comment needs further processing
        """
        if not comment:
            return self._no_name_response()

        comment = comment.strip()

        # Too short
        if len(comment) < self.min_length:
            return self._no_name_response()

        # Only digits/punctuation
        if self._is_numeric_only(comment):
            return self._no_name_response()

        # Matches definite no-name patterns
        if matches_no_name_pattern(comment):
            logger.debug(f"Quick filter: NO_NAME pattern matched for '{comment}'")
            return self._no_name_response()

        # Has clear name indicators - pass to NER
        if matches_name_indicator(comment):
            logger.debug(f"Quick filter: name indicator found, passing to NER")
            return None

        # Uncertain - pass to next tier
        return None

    def _is_numeric_only(self, text: str) -> bool:
        """Check if text is only numbers and punctuation"""
        cleaned = re.sub(r'[\d\s\.,\-+/\\()₴$€грнuahusdeur]+', '', text.lower())
        return len(cleaned) == 0

    def _no_name_response(self) -> NameDetectionResponse:
        """Create response for no name detected"""
        return NameDetectionResponse(
            has_name=False,
            category=NameCategory.NO_NAME,
            detected_name=None,
            confidence=1.0,
            tier_used=1
        )
