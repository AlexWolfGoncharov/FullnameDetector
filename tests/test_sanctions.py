"""Тести перевірки санкцій — false positives і правильні збіги"""

import pytest
from app.services.sanctions_checker import get_sanctions_checker
from app.models.schemas import NameCategory


@pytest.fixture(scope="module")
def sanctions():
    """Sanctions checker instance"""
    return get_sanctions_checker()


class TestSanctionsSurnameMustMatch:
    """Прізвище має збігатися — інакше false positive"""

    @pytest.mark.parametrize("name,reason", [
        ("Мельник Ігор Петрович", "прізвище Мельник ≠ Вітченко (в списку Вітченко Ігор Петрович)"),
        ("Левченко Анна Володимирівна", "прізвище Левченко ≠ Зинов'єва (в списку Зинов'єва Анна Володимирівна)"),
    ])
    def test_surname_differs_no_match(self, sanctions, name, reason):
        """Ім'я+по батькові співпадають з санкційним, але прізвище різне — НЕ флагувати"""
        if not sanctions.is_loaded:
            pytest.skip("Sanctions list not loaded")
        match = sanctions.check(name)
        assert match.found is False, f"{reason}"

    def test_surname_matches_partial_ok(self, sanctions):
        """Прізвище збігається — може бути match"""
        if not sanctions.is_loaded:
            pytest.skip("Sanctions list not loaded")
        # Булатов Руслан Рустемович — в санкціях
        match = sanctions.check("Булатов Руслан Рустемович")
        assert match.found is True


class TestSanctionsFirstNameMustMatch:
    """Якщо є ім'я — воно має збігатися з санкційним"""

    @pytest.mark.parametrize("name,reason", [
        ("Іванов Петро Олександрович", "ім'я Петро ≠ Олег (в списку Іванов Олег Олександрович)"),
        ("Іванов Петро Сергійович", "ім'я Петро ≠ Олександр (в списку Іванов Олександр Сергійович)"),
    ])
    def test_first_name_differs_no_match(self, sanctions, name, reason):
        """Прізвище+по батькові співпадають, але ім'я різне — НЕ флагувати"""
        if not sanctions.is_loaded:
            pytest.skip("Sanctions list not loaded")
        match = sanctions.check(name)
        assert match.found is False, f"{reason}"


class TestSanctionsCorrectMatches:
    """Правильні збіги — особи в санкціях"""

    @pytest.mark.parametrize("name", [
        "Булатов Руслан Рустемович",
        "Журавльов Олексій Олександрович",
    ])
    def test_person_in_sanctions_flagged(self, sanctions, name):
        """Особи з санкційного списку мають флагуватися"""
        if not sanctions.is_loaded:
            pytest.skip("Sanctions list not loaded")
        match = sanctions.check(name)
        assert match.found is True


class TestSanctionsNameOnlyIgnored:
    """NAME_ONLY (без прізвища) — ігнорується"""

    def test_name_only_no_sanctions_check(self, sanctions):
        """Тільки ім'я — не перевіряємо на санкції"""
        if not sanctions.is_loaded:
            pytest.skip("Sanctions list not loaded")
        match = sanctions.check("Олександр", category=NameCategory.NAME_ONLY)
        assert match.found is False
