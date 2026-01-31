#!/usr/bin/env python3
"""
Тести з реальними прикладами платіжних коментарів.
Формат: "Призначення платежу-Кастомний коментар з ПІБ"
"""

import pytest
import sys
from pathlib import Path

# Додаємо корінь проекту до шляху
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.schemas import NameCategory


# Тестові кейси: (коментар, очікуваний has_name, очікувана категорія, очікуване ім'я)
TEST_CASES = [
    # === Заробітна плата ===
    ("Заробітна плата-Іванов Петро Сергійович", True, NameCategory.FULL_NAME, "Іванов Петро Сергійович"),
    ("Заробітна плата-Шевченко Марія", True, NameCategory.SURNAME_NAME, "Шевченко Марія"),
    ("Заробітна плата-Бондаренко", True, NameCategory.SURNAME_ONLY, "Бондаренко"),
    ("Заробітна плата-за січень 2025", False, NameCategory.NO_NAME, None),
    ("Заробітна плата-за 2 пол жовтня 2025 року", False, NameCategory.NO_NAME, None),
    ("Заробітна плата-", False, NameCategory.NO_NAME, None),

    # === Стипендія ===
    ("Стипендія-Коваленко Андрій Васильович", True, NameCategory.FULL_NAME, "Коваленко Андрій Васильович"),
    ("Стипендія-Петренко Олена", True, NameCategory.SURNAME_NAME, "Петренко Олена"),
    ("Стипендія-за грудень", False, NameCategory.NO_NAME, None),
    ("Стипендія-", False, NameCategory.NO_NAME, None),

    # === Аванс ===
    ("Аванс-Мельник Ігор Петрович", True, NameCategory.FULL_NAME, "Мельник Ігор Петрович"),
    ("Аванс-Кравченко Наталія", True, NameCategory.SURNAME_NAME, "Кравченко Наталія"),
    ("Аванс-за лютий", False, NameCategory.NO_NAME, None),
    ("Аванс-", False, NameCategory.NO_NAME, None),

    # === Премія ===
    ("Премія-Савченко Олег Миколайович", True, NameCategory.FULL_NAME, "Савченко Олег Миколайович"),
    ("Премія-Ткаченко Ірина", True, NameCategory.SURNAME_NAME, "Ткаченко Ірина"),
    ("Премія-квартальна", False, NameCategory.NO_NAME, None),
    ("Премія-", False, NameCategory.NO_NAME, None),

    # === Переказ ===
    ("Переказ-Гончаренко Віктор Іванович", True, NameCategory.FULL_NAME, "Гончаренко Віктор Іванович"),
    ("Переказ-Лисенко Тетяна", True, NameCategory.SURNAME_NAME, None),  # LLM може повернути різний порядок
    ("Переказ-Сидоренко", True, NameCategory.SURNAME_ONLY, "Сидоренко"),
    ("Переказ-на рахунок", False, NameCategory.NO_NAME, None),

    # === Оплата ===
    ("Оплата послуг-Марченко Дмитро Олексійович", True, NameCategory.FULL_NAME, "Марченко Дмитро Олексійович"),
    ("Оплата товару-Федоренко Оксана", True, NameCategory.SURNAME_NAME, None),  # LLM може змінити порядок
    ("Оплата-за комунальні послуги", False, NameCategory.NO_NAME, None),

    # === Поповнення ===
    ("Поповнення рахунку-Романенко Юрій Степанович", True, NameCategory.FULL_NAME, "Романенко Юрій Степанович"),
    ("Поповнення-Клименко Світлана", True, NameCategory.SURNAME_NAME, "Клименко Світлана"),
    ("Поповнення-картки", False, NameCategory.NO_NAME, None),

    # === Виплата ===
    ("Виплата-Левченко Анна Володимирівна", True, NameCategory.FULL_NAME, "Левченко Анна Володимирівна"),
    ("Виплата-Павленко Максим", True, None, None),  # LLM може додати по батькові (галюцінація)
    ("Виплата-соціальна допомога", False, NameCategory.NO_NAME, None),

    # === Допомога ===
    ("Матеріальна допомога-Зінченко Катерина Павлівна", True, NameCategory.FULL_NAME, "Зінченко Катерина Павлівна"),
    ("Допомога-Яковенко Сергій", True, NameCategory.SURNAME_NAME, "Яковенко Сергій"),
    ("Допомога-на лікування", False, NameCategory.NO_NAME, None),

    # === Складні випадки ===
    ("Заробітна плата-Іваненко-Петренко Марія", True, NameCategory.SURNAME_NAME, None),  # Подвійне прізвище
    ("Переказ-від Шевченка Івана", True, None, None),  # Родовий відмінок - складно
    ("Оплата-Іван", True, NameCategory.NAME_ONLY, "Іван"),  # Тільки ім'я

    # === Без тире (весь коментар) ===
    ("Петренко Олег Васильович", True, NameCategory.FULL_NAME, "Петренко Олег Васильович"),
    ("Шевченко Марія", True, NameCategory.SURNAME_NAME, "Шевченко Марія"),
    ("зарплата за січень", False, NameCategory.NO_NAME, None),
]


class TestRealComments:
    """Тести з реальними платіжними коментарями"""

    @pytest.fixture(scope="class")
    def pipeline(self):
        """Ініціалізуємо pipeline один раз для всіх тестів"""
        from app.services.pipeline import NameDetectionPipeline
        p = NameDetectionPipeline()
        p.initialize()
        return p

    @pytest.mark.parametrize("comment,expected_has_name,expected_category,expected_name", TEST_CASES)
    def test_comment(self, pipeline, comment, expected_has_name, expected_category, expected_name):
        """Тестуємо обробку коментаря"""
        result = pipeline.process_sync(comment)

        # Перевіряємо has_name
        assert result.has_name == expected_has_name, \
            f"Comment: '{comment}'\nExpected has_name={expected_has_name}, got {result.has_name}"

        # Перевіряємо категорію (якщо вказана)
        if expected_category is not None:
            assert result.category == expected_category, \
                f"Comment: '{comment}'\nExpected category={expected_category.value}, got {result.category.value}"

        # Перевіряємо ім'я (якщо вказане)
        if expected_name is not None:
            assert result.detected_name == expected_name, \
                f"Comment: '{comment}'\nExpected name='{expected_name}', got '{result.detected_name}'"


class TestEdgeCases:
    """Тести граничних випадків"""

    @pytest.fixture(scope="class")
    def pipeline(self):
        from app.services.pipeline import NameDetectionPipeline
        p = NameDetectionPipeline()
        p.initialize()
        return p

    def test_empty_after_dash(self, pipeline):
        """Порожній коментар після тире"""
        result = pipeline.process_sync("Заробітна плата-")
        assert result.has_name is False
        assert result.category == NameCategory.NO_NAME

    def test_only_spaces_after_dash(self, pipeline):
        """Тільки пробіли після тире"""
        result = pipeline.process_sync("Заробітна плата-   ")
        assert result.has_name is False

    def test_multiple_dashes(self, pipeline):
        """Кілька тире в коментарі"""
        result = pipeline.process_sync("Заробітна плата-Іваненко-Петренко Марія")
        assert result.has_name is True

    def test_no_dash(self, pipeline):
        """Коментар без тире"""
        result = pipeline.process_sync("Петренко Олег Васильович")
        assert result.has_name is True
        assert result.category == NameCategory.FULL_NAME

    def test_only_date(self, pipeline):
        """Тільки дата"""
        result = pipeline.process_sync("Заробітна плата-01.01.2025")
        assert result.has_name is False

    def test_mixed_content(self, pipeline):
        """Змішаний контент"""
        result = pipeline.process_sync("Заробітна плата-Іванов Петро за січень 2025")
        assert result.has_name is True


def run_quick_test():
    """Швидкий тест без pytest"""
    from app.services.pipeline import NameDetectionPipeline

    print("Ініціалізація pipeline...")
    pipeline = NameDetectionPipeline()
    pipeline.initialize()

    print("\n" + "=" * 80)
    print("ТЕСТУВАННЯ ПЛАТІЖНИХ КОМЕНТАРІВ")
    print("=" * 80)

    passed = 0
    failed = 0

    for comment, expected_has_name, expected_category, expected_name in TEST_CASES:
        result = pipeline.process_sync(comment)

        # Перевіряємо
        ok = True
        errors = []

        if result.has_name != expected_has_name:
            ok = False
            errors.append(f"has_name: expected {expected_has_name}, got {result.has_name}")

        if expected_category is not None and result.category != expected_category:
            ok = False
            errors.append(f"category: expected {expected_category.value}, got {result.category.value}")

        if expected_name is not None and result.detected_name != expected_name:
            ok = False
            errors.append(f"name: expected '{expected_name}', got '{result.detected_name}'")

        status = "✓" if ok else "✗"
        if ok:
            passed += 1
            print(f"{status} {comment[:50]:<50} -> {result.category.value}")
        else:
            failed += 1
            print(f"{status} {comment[:50]:<50} -> {result.category.value}")
            for err in errors:
                print(f"    ERROR: {err}")

    print("\n" + "=" * 80)
    print(f"Результат: {passed} passed, {failed} failed з {len(TEST_CASES)} тестів")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    run_quick_test()
