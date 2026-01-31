"""
Комплексні тести для перевірки роботи pipeline:
- Різні варіанти початку коментаря (Заробітна плата-, Переказ коштiв-)
- Перевірка санкційного списку (хто є / кого немає)
- Привітання та стоп-слова (Слава Україні, з Новим Роком)
- Різні формати платіжних коментарів

Запуск: pytest tests/test_comprehensive.py -v
(Перший запуск завантажує моделі - може зайняти 1-2 хв)
"""

import pytest
from app.services.pipeline import get_pipeline
from app.models.schemas import NameCategory, NameDetectionResponse


@pytest.fixture(scope="module")
def pipeline():
    """Pipeline з повною ініціалізацією"""
    p = get_pipeline()
    return p


# ========== Коментарі БЕЗ ПІБ (різні префікси) ==========
NO_NAME_COMMENTS = [
    # Заробітна плата - варіанти
    "Заробітна плата-за II половину листопада 2025 р.",
    "Заробітна плата-ДОПЛАТА за несприятливi умови працi  Грудень  2025 р",
    "Заробітна плата-за другу половину листопада місяця  2025 року.",
    "Заробітна плата-Призначення: грошове забезпечення",
    "Заробітна плата-Заробітна плата за листопад 2025р. Податки сплачені повністю 15.11.2025р.",
    "Заробітна плата-Додаткова винагорода за листопад 2025 А4267",
    "Заробітна плата-Зарплата за 1 половину листопада 2025р",
    "Заробітна плата-за 2 пол листопада 2025 року",
    "Заробітна плата-Зарплата за 2 половину листопада 2025р",
    "Заробітна плата-Переказ коштiвЗаробітна плата",
    "Заробітна плата-чрюсЄэ яырЄр",  # некоректний текст
    # Переказ коштів
    "Переказ коштiв-Матеріальна допомога грошова проф виплата не із ФОП не більш ніж 4240 грн",
    # Інші префікси
    "Премія-за досягнення результатів 4 квартал 2025",
    "Аванс-за грудень 2025 року",
]


# ========== Привітання та стоп-слова (НЕ мають розпізнаватись як ПІБ) ==========
GREETING_NO_NAME = [
    "Заробітна плата-Слава Україні",
    "Переказ-зі святим Миколаєм",
    "Премія-з Новим Роком",
    "Заробітна плата-Вітаю з Різдвом",
    "Переказ коштів-З Днем народження",
    "Заробітна плата-З 8 березня",
]


# ========== Коментарі З ПІБ ==========
WITH_NAME_COMMENTS = [
    ("Заробітна плата-Булатов Руслан Олександрович", True, "Булатов Руслан Олександрович"),
    ("Заробітна плата-Іванов Петро Олександрович", True, "Іванов Петро Олександрович"),
    ("Переказ коштів-Коваленко Марія Іванівна", True, "Коваленко Марія Іванівна"),
    ("Премія-Петренко Андрій", True, "Петренко Андрій"),
]


# ========== Санкційний список ==========
# Особи Є в санкційному списку РНБО
SANCTIONS_IN_LIST = [
    "Заробітна плата-Булатов Руслан Рустемович",      # Булатов Руслан Рустемович - active
    "Переказ-Журавльов Олексій Олександрович",       # Журавльов Олексій Олександрович - active
    "Премія-Кисельов Дмитро Костянтинович",          # Кисельов Дмитро Костянтинович - active
    "Заробітна плата-Діденко Олексій Миколайович",   # Діденко Олексій Миколайович - active
]

# Особи НЕМАЄ в санкційному списку (звичайні імена)
SANCTIONS_NOT_IN_LIST = [
    "Заробітна плата-Іванов Петро Олександрович",
    "Переказ-Коваленко Марія Василівна",
    "Премія-Мельник Олександр Олександрович",
    "Заробітна плата-Шевченко Тарас Григорович",
]


class TestNoNameComments:
    """Коментарі без ПІБ - різні варіанти початку"""

    @pytest.mark.parametrize("comment", NO_NAME_COMMENTS)
    def test_no_name_detected(self, pipeline, comment):
        """Не має знаходити ПІБ у платіжних коментарях"""
        result = pipeline.process_sync(comment)
        assert result.has_name is False, f"Очікувалось has_name=False для: {comment[:50]}..."
        assert result.category == NameCategory.NO_NAME


class TestGreetingsNoName:
    """Привітання не мають розпізнаватись як ПІБ"""

    @pytest.mark.parametrize("comment", GREETING_NO_NAME)
    def test_greetings_not_names(self, pipeline, comment):
        """Слава Україні, з Новим Роком тощо - не ПІБ"""
        result = pipeline.process_sync(comment)
        assert result.has_name is False, f"Привітання не має бути ПІБ: {comment}"


class TestWithNameComments:
    """Коментарі з ПІБ"""

    @pytest.mark.parametrize("comment,expected_has_name,expected_name", WITH_NAME_COMMENTS)
    def test_name_detected(self, pipeline, comment, expected_has_name, expected_name):
        """Має знаходити ПІБ"""
        result = pipeline.process_sync(comment)
        assert result.has_name == expected_has_name, f"Для: {comment}"
        if expected_has_name and expected_name:
            assert result.detected_name is not None
            # Перевіряємо що знайдене ім'я містить очікуване (може бути повніше)
            assert expected_name in (result.detected_name or ""), \
                f"Очікувалось '{expected_name}' в '{result.detected_name}'"


class TestSanctionsCheck:
    """Перевірка санкційного списку"""

    @pytest.mark.parametrize("comment", SANCTIONS_IN_LIST)
    def test_sanctions_match_found(self, pipeline, comment):
        """Особи Є в санкційному списку - має бути sanctions_check.found=True"""
        result = pipeline.process_sync(comment)
        assert result.has_name is True, f"Має знайти ім'я: {comment}"
        assert result.sanctions_check is not None, "Має виконуватись перевірка санкцій"
        assert result.sanctions_check.checked is True
        assert result.sanctions_check.found is True, \
            f"Очікувалось знаходження в санкціях для: {comment} -> {result.detected_name}"

    @pytest.mark.parametrize("comment", SANCTIONS_NOT_IN_LIST)
    def test_sanctions_match_not_found(self, pipeline, comment):
        """Особи НЕМАЄ в санкційному списку - sanctions_check.found=False"""
        result = pipeline.process_sync(comment)
        assert result.has_name is True, f"Має знайти ім'я: {comment}"
        if result.sanctions_check:
            assert result.sanctions_check.found is False, \
                f"Не має бути в санкціях: {result.detected_name}"


class TestCommentFormat:
    """Формат коментаря: префікс-кастомна частина"""

    def test_extract_after_dash(self, pipeline):
        """Частина після тире має оброблятись окремо"""
        # "Заробітна плата-Булатов Руслан" - ПІБ після тире
        result = pipeline.process_sync("Заробітна плата-Булатов Руслан Олександрович")
        assert result.has_name is True
        assert "Булатов" in (result.detected_name or "")

    def test_empty_after_dash(self, pipeline):
        """Якщо після тире порожньо - НЕМАЄ ПІБ"""
        result = pipeline.process_sync("Заробітна плата-")
        assert result.has_name is False

    def test_no_dash_full_comment(self, pipeline):
        """Без тире - обробляється весь коментар"""
        result = pipeline.process_sync("Переказ Іванову Петру Олександровичу")
        assert result.has_name is True


class TestResponseStructure:
    """Структура відповіді"""

    def test_sanctions_check_structure(self, pipeline):
        """Відповідь з іменем має містити sanctions_check"""
        result = pipeline.process_sync("Заробітна плата-Іванов Петро Олександрович")
        assert result.has_name is True
        assert hasattr(result, "sanctions_check")
        # sanctions_check може бути None якщо checker не завантажений
        if result.sanctions_check:
            assert hasattr(result.sanctions_check, "checked")
            assert hasattr(result.sanctions_check, "found")
            assert hasattr(result.sanctions_check, "match_type")
