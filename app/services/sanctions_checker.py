"""Sanctions checker service - перевірка імен у санкційному списку РНБО"""

import csv
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

from app.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Шлях до файлу санкцій
SANCTIONS_FILE = PROJECT_ROOT / "app" / "data" / "sanctions_individuals.csv"


@dataclass
class SanctionMatch:
    """Результат перевірки санкцій"""
    found: bool
    match_type: str  # "exact", "partial", "none"
    matched_name: Optional[str] = None
    sid: Optional[str] = None  # ID у реєстрі
    status: Optional[str] = None  # active/expired
    confidence: float = 0.0


class SanctionsChecker:
    """
    Перевіряє імена на співпадіння зі санкційним списком РНБО України.

    Підтримує:
    - Точне співпадіння
    - Часткове співпадіння (прізвище або ім'я)
    - Нечутливий до регістру пошук
    """

    _instance: Optional["SanctionsChecker"] = None

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._names: Dict[str, Dict] = {}  # normalized_name -> record
        self._name_parts: Dict[str, List[Dict]] = {}  # word -> list of records
        self._loaded = False

        self._load_sanctions()

    def _normalize(self, text: str) -> str:
        """Нормалізація тексту для порівняння"""
        if not text:
            return ""
        # Lowercase, видалення зайвих пробілів
        text = text.lower().strip()
        # Видалення апострофів і дефісів
        text = re.sub(r"['\-]", "", text)
        # Нормалізація пробілів
        text = re.sub(r"\s+", " ", text)
        return text

    def _load_sanctions(self):
        """Завантаження санкційного списку"""
        if not SANCTIONS_FILE.exists():
            logger.warning(f"Sanctions file not found: {SANCTIONS_FILE}")
            return

        try:
            with open(SANCTIONS_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")

                for row in reader:
                    name = row.get("name", "").strip()
                    if not name:
                        continue

                    record = {
                        "sid": row.get("sid", ""),
                        "name": name,
                        "translit_name": row.get("translit_name", ""),
                        "aliases": row.get("aliases", ""),
                        "status": row.get("status", ""),
                    }

                    # Зберігаємо повне нормалізоване ім'я
                    normalized = self._normalize(name)
                    self._names[normalized] = record

                    # Зберігаємо кожне слово окремо для часткового пошуку
                    for word in normalized.split():
                        if len(word) >= 3:  # Ігноруємо короткі слова
                            if word not in self._name_parts:
                                self._name_parts[word] = []
                            self._name_parts[word].append(record)

                    # Також додаємо аліаси
                    aliases = row.get("aliases", "")
                    if aliases:
                        for alias in aliases.split(";"):
                            alias = alias.strip()
                            if alias:
                                alias_normalized = self._normalize(alias)
                                if alias_normalized and alias_normalized not in self._names:
                                    self._names[alias_normalized] = record

            self._loaded = True
            logger.info(f"Loaded {len(self._names)} sanctioned names, {len(self._name_parts)} name parts")

        except Exception as e:
            logger.error(f"Failed to load sanctions file: {e}")

    def reload(self) -> bool:
        """Перезавантажити список з файлу (після оновлення CSV)"""
        self._names.clear()
        self._name_parts.clear()
        self._loaded = False
        self._load_sanctions()
        return self._loaded

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def check(self, name: str, category: Optional["NameCategory"] = None) -> SanctionMatch:
        """
        Перевірити ім'я на співпадіння зі санкційним списком.

        Правила:
        - Якщо тільки ім'я/по-батькові без прізвища (NAME_ONLY) — ігноруємо, found=False
        - Якщо є прізвище і ім'я відрізняється від санкційного — пропускаємо (found=False)
        - Потрібно хоча б прізвище для збігу

        Args:
            name: Ім'я для перевірки (Прізвище Ім'я По-батькові)
            category: Категорія виявленого імені (NAME_ONLY = без прізвища, пропускаємо)

        Returns:
            SanctionMatch з результатом перевірки
        """
        if not self._loaded or not name:
            return SanctionMatch(found=False, match_type="none")

        # NAME_ONLY — тільки ім'я або по-батькові, без прізвища. Ігноруємо.
        if category is not None:
            cat_str = str(category) if hasattr(category, "value") else str(category)
            if "NAME_ONLY" in cat_str or (hasattr(category, "name") and category.name == "NAME_ONLY"):
                return SanctionMatch(found=False, match_type="none")

        normalized = self._normalize(name)

        # 1. Точне співпадіння
        if normalized in self._names:
            record = self._names[normalized]
            return SanctionMatch(
                found=True,
                match_type="exact",
                matched_name=record["name"],
                sid=record["sid"],
                status=record["status"],
                confidence=1.0
            )

        # 2. Перевірка частин імені
        name_words = normalized.split()
        if not name_words:
            return SanctionMatch(found=False, match_type="none")

        # Шукаємо співпадіння по словах
        matches = {}  # sid -> (record, matched_words_count)

        for word in name_words:
            if len(word) < 3:
                continue

            if word in self._name_parts:
                for record in self._name_parts[word]:
                    sid = record["sid"]
                    if sid not in matches:
                        matches[sid] = (record, 0)
                    record, count = matches[sid]
                    matches[sid] = (record, count + 1)

        if not matches:
            return SanctionMatch(found=False, match_type="none")

        # Знаходимо найкраще співпадіння
        best_match = None
        best_count = 0

        for sid, (record, count) in matches.items():
            # Враховуємо кількість співпадінь відносно кількості слів у шуканому імені
            if count > best_count:
                best_count = count
                best_match = record

        if best_match and best_count >= 1:
            sanc_words = self._normalize(best_match["name"]).split()
            # Потрібно хоча б прізвище: перше слово має збігатися
            if not sanc_words or name_words[0] != sanc_words[0]:
                return SanctionMatch(found=False, match_type="none")

            # Якщо є ім'я (друге слово) і воно відрізняється — пропускаємо
            if len(name_words) >= 2 and len(sanc_words) >= 2:
                if name_words[1] != sanc_words[1]:
                    return SanctionMatch(found=False, match_type="none")

            confidence = best_count / max(len(sanc_words), len(name_words))
            if best_count >= 2 or best_count == len(name_words):
                return SanctionMatch(
                    found=True,
                    match_type="partial",
                    matched_name=best_match["name"],
                    sid=best_match["sid"],
                    status=best_match["status"],
                    confidence=min(confidence, 0.9)
                )

        return SanctionMatch(found=False, match_type="none")

    def get_stats(self) -> dict:
        """Статистика санкційного списку"""
        return {
            "loaded": self._loaded,
            "total_names": len(self._names),
            "unique_parts": len(self._name_parts),
            "file": str(SANCTIONS_FILE)
        }


# Global instance
def get_sanctions_checker() -> SanctionsChecker:
    """Get singleton sanctions checker instance"""
    return SanctionsChecker()
