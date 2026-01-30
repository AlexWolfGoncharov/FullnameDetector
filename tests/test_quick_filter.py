"""Tests for Tier 1: Quick Filter"""

import pytest
from app.services.quick_filter import QuickFilter
from app.models.schemas import NameCategory


@pytest.fixture
def quick_filter():
    return QuickFilter()


class TestQuickFilterNoName:
    """Test cases where no name should be detected"""

    @pytest.mark.parametrize("comment", [
        "Зарплата за грудень",
        "Заробітна плата за 2 ч 11.2025 р.",
        "зп за листопад",
        "з/п",
        "Аванс",
        "Премія за квартал",
        "Виплата",
    ])
    def test_salary_patterns(self, quick_filter, comment):
        result = quick_filter.process(comment)
        assert result is not None
        assert result.has_name is False
        assert result.category == NameCategory.NO_NAME
        assert result.tier_used == 1

    @pytest.mark.parametrize("comment", [
        "Податки",
        "ЄСВ за 11.2025",
        "ПДВ",
        "НДФЛ",
        "Військовий збір",
    ])
    def test_tax_patterns(self, quick_filter, comment):
        result = quick_filter.process(comment)
        assert result is not None
        assert result.has_name is False

    @pytest.mark.parametrize("comment", [
        "Поповнення",
        "Переказ коштів",
        "Комунальні послуги",
        "Оплата послуг",
    ])
    def test_transfer_patterns(self, quick_filter, comment):
        result = quick_filter.process(comment)
        assert result is not None
        assert result.has_name is False

    @pytest.mark.parametrize("comment", [
        "1000 грн",
        "500.50",
        "1234567890",
        "100 UAH",
        "50$",
    ])
    def test_numeric_only(self, quick_filter, comment):
        result = quick_filter.process(comment)
        assert result is not None
        assert result.has_name is False

    @pytest.mark.parametrize("comment", [
        "",
        "   ",
        "ab",
        "12",
    ])
    def test_short_or_empty(self, quick_filter, comment):
        result = quick_filter.process(comment)
        assert result is not None
        assert result.has_name is False


class TestQuickFilterPassThrough:
    """Test cases that should be passed to NER"""

    @pytest.mark.parametrize("comment", [
        "Переказ Іванову Петру",
        "Для Шевченко Тараса",
        "Від Коваленко",
        "На карту Бондаренко Андрію Петровичу",
    ])
    def test_name_indicators(self, quick_filter, comment):
        result = quick_filter.process(comment)
        # Should return None to pass to NER
        assert result is None

    @pytest.mark.parametrize("comment", [
        "Якийсь текст без паттернів",
        "Невідомий формат коментаря",
    ])
    def test_unknown_patterns(self, quick_filter, comment):
        result = quick_filter.process(comment)
        # Should return None for uncertain cases
        assert result is None
