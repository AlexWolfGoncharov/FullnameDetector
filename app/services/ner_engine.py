"""Tier 2: NER Engine - spaCy-based named entity recognition"""

import re
import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass

from app.models.schemas import NameCategory, NameDetectionResponse
from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class NameParts:
    """Extracted name parts"""
    surname: Optional[str] = None
    first_name: Optional[str] = None
    patronymic: Optional[str] = None
    raw_text: str = ""
    confidence: float = 0.0


class NEREngine:
    """
    Tier 2 processor - spaCy NER for name extraction.

    Uses Ukrainian NER model to:
    - Extract person entities (PER)
    - Classify name parts (surname, first name, patronymic)
    """

    def __init__(self):
        self.settings = get_settings()
        self._nlp = None
        self._loaded = False

    def load(self) -> bool:
        """Load spaCy model"""
        if self._loaded:
            return True

        try:
            import spacy
            logger.info(f"Loading spaCy model: {self.settings.spacy_model}")
            self._nlp = spacy.load(self.settings.spacy_model)
            self._loaded = True
            logger.info("spaCy model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load spaCy model: {e}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def process(self, comment: str) -> Tuple[Optional[NameDetectionResponse], float]:
        """
        Process comment with NER.

        Returns:
            Tuple of (response, confidence)
            If confidence < threshold, LLM fallback should be used
        """
        if not self._loaded:
            if not self.load():
                return None, 0.0

        comment = comment.strip()
        doc = self._nlp(comment)

        # Extract person entities
        persons = [ent for ent in doc.ents if ent.label_ == "PER"]

        # Сначала пробуем паттерн-матчинг для полных имен (3 слова)
        # Это важно, так как NER может не распознать редкие фамилии
        name_parts = self._extract_name_by_pattern(comment)
        if name_parts and name_parts.confidence > 0.7:
            return self._create_response(name_parts), name_parts.confidence

        if not persons:
            # Try pattern-based extraction as fallback
            if name_parts and name_parts.confidence > 0.5:
                return self._create_response(name_parts), name_parts.confidence

            return NameDetectionResponse(
                has_name=False,
                category=NameCategory.NO_NAME,
                detected_name=None,
                confidence=0.8,  # Less confident than Tier 1
                tier_used=2
            ), 0.8

        # Get the most relevant person entity
        best_person = max(persons, key=lambda e: len(e.text))
        name_parts_ner = self._parse_name_parts(best_person.text)

        # Если NER нашел только 2 слова, но паттерн нашел 3 - используем паттерн
        if name_parts and name_parts.surname and name_parts.first_name and name_parts.patronymic:
            if not (name_parts_ner.surname and name_parts_ner.first_name and name_parts_ner.patronymic):
                # Паттерн нашел полное имя, а NER только частичное - используем паттерн
                return self._create_response(name_parts), name_parts.confidence

        if name_parts_ner.confidence < self.settings.ner_confidence_threshold:
            # Low confidence - signal for LLM fallback
            return self._create_response(name_parts_ner), name_parts_ner.confidence

        return self._create_response(name_parts_ner), name_parts_ner.confidence

    def _parse_name_parts(self, text: str) -> NameParts:
        """Parse extracted name into parts"""
        text = text.strip()
        parts = text.split()

        result = NameParts(raw_text=text)

        if len(parts) == 0:
            return result

        # Patronymic patterns (Ukrainian/Russian)
        patronymic_patterns = [
            r'.*ович$', r'.*івна$', r'.*овна$', r'.*евич$',
            r'.*ївна$', r'.*евна$', r'.*ич$', r'.*івич$'
        ]

        def is_patronymic(word: str) -> bool:
            for pattern in patronymic_patterns:
                if re.match(pattern, word, re.IGNORECASE):
                    return True
            return False

        if len(parts) == 3:
            # Full name: Surname FirstName Patronymic
            result.surname = parts[0]
            result.first_name = parts[1]
            result.patronymic = parts[2]
            result.confidence = 0.95 if is_patronymic(parts[2]) else 0.7

        elif len(parts) == 2:
            # Two parts: could be Surname+FirstName or FirstName+Patronymic
            if is_patronymic(parts[1]):
                result.first_name = parts[0]
                result.patronymic = parts[1]
                result.confidence = 0.85
            else:
                result.surname = parts[0]
                result.first_name = parts[1]
                result.confidence = 0.8

        elif len(parts) == 1:
            # Single word - likely surname or first name
            if self._looks_like_surname(parts[0]):
                result.surname = parts[0]
                result.confidence = 0.6
            else:
                result.first_name = parts[0]
                result.confidence = 0.5

        return result

    def _looks_like_surname(self, word: str) -> bool:
        """Heuristic to check if word looks like a surname"""
        # Common Ukrainian surname endings
        surname_endings = [
            'ко', 'енко', 'ук', 'юк', 'чук', 'ський', 'цький',
            'ов', 'ев', 'єв', 'ін', 'їн', 'ак', 'як', 'ик'
        ]
        word_lower = word.lower()
        for ending in surname_endings:
            if word_lower.endswith(ending):
                return True
        return False

    def _extract_name_by_pattern(self, text: str) -> Optional[NameParts]:
        """Try to extract name using regex patterns when NER fails"""

        # Full name pattern: Прізвище Ім'я По-батькові
        # Более гибкий паттерн - третье слово должно заканчиваться на отчество
        full_name_pattern = r'([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+(?:ович|івна|овна|евич|ївна|евна|ич|івич))'
        match = re.search(full_name_pattern, text)
        if match:
            # Проверяем, что первое слово может быть фамилией
            surname = match.group(1)
            if self._looks_like_surname(surname) or len(surname) > 3:
                return NameParts(
                    surname=match.group(1),
                    first_name=match.group(2),
                    patronymic=match.group(3),
                    raw_text=match.group(0),
                    confidence=0.9
                )
            # Если первое слово не похоже на фамилию, но есть отчество - все равно считаем полным именем
            return NameParts(
                surname=match.group(1),
                first_name=match.group(2),
                patronymic=match.group(3),
                raw_text=match.group(0),
                confidence=0.85
            )

        # Более простой паттерн для 3 слов без строгой проверки отчества
        # На случай, если отчество не распознается паттерном
        three_words_pattern = r'^([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)$'
        match = re.match(three_words_pattern, text.strip())
        if match:
            # Если третье слово похоже на отчество - это полное имя
            third_word = match.group(3)
            patronymic_patterns = [
                r'.*ович$', r'.*івна$', r'.*овна$', r'.*евич$',
                r'.*ївна$', r'.*евна$', r'.*ич$', r'.*івич$'
            ]
            is_patronymic = any(re.match(p, third_word, re.IGNORECASE) for p in patronymic_patterns)
            
            if is_patronymic:
                return NameParts(
                    surname=match.group(1),
                    first_name=match.group(2),
                    patronymic=match.group(3),
                    raw_text=match.group(0),
                    confidence=0.9
                )

        # Two name pattern
        two_name_pattern = r'([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)'
        match = re.search(two_name_pattern, text)
        if match:
            return NameParts(
                surname=match.group(1),
                first_name=match.group(2),
                raw_text=match.group(0),
                confidence=0.6
            )

        return None

    def _create_response(self, name_parts: NameParts) -> NameDetectionResponse:
        """Create response from parsed name parts"""

        if name_parts.surname and name_parts.first_name and name_parts.patronymic:
            category = NameCategory.FULL_NAME
            detected = f"{name_parts.surname} {name_parts.first_name} {name_parts.patronymic}"
        elif name_parts.surname and name_parts.first_name:
            category = NameCategory.SURNAME_NAME
            detected = f"{name_parts.surname} {name_parts.first_name}"
        elif name_parts.first_name and name_parts.patronymic:
            category = NameCategory.SURNAME_NAME  # Name + patronymic
            detected = f"{name_parts.first_name} {name_parts.patronymic}"
        elif name_parts.surname:
            category = NameCategory.SURNAME_ONLY
            detected = name_parts.surname
        elif name_parts.first_name:
            category = NameCategory.NAME_ONLY
            detected = name_parts.first_name
        else:
            category = NameCategory.NO_NAME
            detected = None

        return NameDetectionResponse(
            has_name=category != NameCategory.NO_NAME,
            category=category,
            detected_name=detected,
            confidence=name_parts.confidence,
            tier_used=2
        )
