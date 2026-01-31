"""RoBERTa-based NER for Ukrainian - higher quality name extraction"""

import logging
import re
import threading
from typing import Optional, List, Tuple

from app.models.schemas import NameCategory, NameDetectionResponse
from app.config import get_settings

logger = logging.getLogger(__name__)

# Модель для українського NER
MODEL_NAME = "EvanD/xlm-roberta-base-ukrainian-ner-ukrner"


class RobertaNER:
    """
    XLM-RoBERTa based NER for Ukrainian language.

    Використовує модель EvanD/xlm-roberta-base-ukrainian-ner-ukrner
    для точнішого розпізнавання імен.

    Підтримує теги:
    - PER (Person) - імена людей
    - LOC (Location) - географічні назви
    - ORG (Organization) - організації
    """

    def __init__(self):
        self.settings = get_settings()
        self._pipeline = None
        self._loaded = False
        self._lock = threading.Lock()  # PyTorch/MPS не завжди thread-safe

    def load(self) -> bool:
        """Load RoBERTa NER model"""
        if self._loaded:
            return True

        try:
            from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

            logger.info(f"Loading RoBERTa NER model: {MODEL_NAME}")

            tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
            model = AutoModelForTokenClassification.from_pretrained(MODEL_NAME)

            self._pipeline = pipeline(
                "ner",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple"
            )

            self._loaded = True
            logger.info("RoBERTa NER model loaded successfully")
            return True

        except ImportError as e:
            logger.warning(f"transformers not installed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load RoBERTa NER model: {e}")
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def extract_persons(self, text: str) -> List[dict]:
        """
        Extract person entities from text.

        Returns list of dicts with:
        - word: extracted text
        - score: confidence score
        - start: start position
        - end: end position
        """
        if not self._loaded or not self._pipeline:
            return []

        try:
            with self._lock:
                results = self._pipeline(text)

                # Фільтруємо тільки PER (Person) entities
                def is_per(r):
                    label = r.get("entity_group") or r.get("entity", "")
                    return label == "PER" or (isinstance(label, str) and "PER" in label.upper())

                persons = [
                    {"word": r["word"], "score": r["score"], "start": r["start"], "end": r["end"]}
                    for r in results
                    if is_per(r)
                ]

                # Якщо нічого не знайдено - спробуємо додати контекст
                if not persons:
                    context_prefixes = [
                        "Переказ для ",
                        "Платіж для ",
                        "Це ",
                    ]
                    for prefix in context_prefixes:
                        augmented = prefix + text
                        results = self._pipeline(augmented)
                        for r in results:
                            if (r.get("entity_group") or r.get("entity", "")) == "PER":
                                prefix_len = len(prefix)
                                if r["start"] >= prefix_len:
                                    persons.append({
                                        "word": r["word"],
                                        "score": r["score"],
                                        "start": r["start"] - prefix_len,
                                        "end": r["end"] - prefix_len
                                    })
                        if persons:
                            break

            return persons

        except Exception as e:
            logger.error(f"RoBERTa NER error: {e}")
            return []

    def process(self, text: str) -> Tuple[Optional[NameDetectionResponse], float]:
        """
        Process text and extract name.

        Returns:
            Tuple of (NameDetectionResponse, confidence)
        """
        if not self._loaded:
            return None, 0.0

        persons = self.extract_persons(text)

        if not persons:
            return None, 0.0

        # Беремо найбільш впевнений результат
        # Якщо є кілька PER entities поряд - об'єднуємо їх
        merged_name = self._merge_adjacent_entities(persons, text)

        if not merged_name:
            return None, 0.0

        name = merged_name["word"]
        confidence = merged_name["score"]

        # Визначаємо категорію за кількістю слів
        words = name.split()

        if len(words) >= 3:
            category = NameCategory.FULL_NAME
        elif len(words) == 2:
            category = NameCategory.SURNAME_NAME
        else:
            # Одне слово - визначаємо прізвище це чи ім'я
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

        return NameDetectionResponse(
            has_name=True,
            category=category,
            detected_name=name,
            confidence=confidence,
            tier_used=2  # RoBERTa це частина Tier 2
        ), confidence

    def _merge_adjacent_entities(self, entities: List[dict], original_text: str) -> Optional[dict]:
        """
        Merge adjacent PER entities into one name.

        Example: "Іванов" + "Петро" + "Сергійович" -> "Іванов Петро Сергійович"
        """
        if not entities:
            return None

        if len(entities) == 1:
            return entities[0]

        # Сортуємо за позицією
        sorted_entities = sorted(entities, key=lambda x: x["start"])

        # Об'єднуємо сусідні entities (з відстанню <= 2 символи)
        merged = []
        current_group = [sorted_entities[0]]

        for i in range(1, len(sorted_entities)):
            prev = sorted_entities[i - 1]
            curr = sorted_entities[i]

            # Якщо відстань між entities <= 2 символи - об'єднуємо
            gap = curr["start"] - prev["end"]
            if gap <= 2:
                current_group.append(curr)
            else:
                merged.append(current_group)
                current_group = [curr]

        merged.append(current_group)

        # Знаходимо найбільшу групу з найвищим середнім score
        best_group = max(merged, key=lambda g: (len(g), sum(e["score"] for e in g) / len(g)))

        if len(best_group) == 1:
            return best_group[0]

        # Витягуємо текст з оригіналу
        start = best_group[0]["start"]
        end = best_group[-1]["end"]
        combined_text = original_text[start:end].strip()

        # Очищаємо від зайвих символів
        combined_text = re.sub(r'\s+', ' ', combined_text)

        avg_score = sum(e["score"] for e in best_group) / len(best_group)

        return {
            "word": combined_text,
            "score": avg_score,
            "start": start,
            "end": end
        }


# Singleton instance
_roberta_ner: Optional[RobertaNER] = None


def get_roberta_ner() -> RobertaNER:
    """Get singleton RoBERTa NER instance"""
    global _roberta_ner
    if _roberta_ner is None:
        _roberta_ner = RobertaNER()
    return _roberta_ner
