"""Regex patterns for quick filtering of payment comments"""

import re
from typing import List, Pattern

# Patterns that indicate NO NAME is present (case-insensitive)
NO_NAME_PATTERNS_RAW: List[str] = [
    # Salary and payments
    r'^(зарплата|зп|з/п|заробітна плата)(\s|$|\.)',
    r'^(аванс|премія|премия|виплата|выплата)(\s|$|\.)',
    r'^(відпускні|отпускные|лікарняні|больничные)(\s|$|\.)',
    r'^(компенсація|компенсация|допомога|помощь)(\s|$|\.)',

    # Taxes and fees
    r'^(податки|податок|налоги|налог)(\s|$|\.)',
    r'^(єсв|ндфл|пдв|ндс|єдиний внесок)(\s|$|\.)',
    r'^(військовий збір|военный сбор)(\s|$|\.)',

    # Transfers without names
    r'^(поповнення|пополнение)(\s|$|\.)',
    r'^(переказ коштів|перевод средств)$',
    r'^(переказ|перевод)$',
    r'^(оплата послуг|оплата услуг)(\s|$|\.)',
    r'^(комунальні|коммунальные)(\s|$|\.)',

    # Numbers only
    r'^\d+[\s\.]*(грн|uah|₴|usd|\$|eur|€)?$',
    r'^[\d\s\.,]+$',

    # Common non-name phrases
    r'^(рахунок|счет|invoice|інвойс)(\s|#|№|\d)',
    r'^(замовлення|заказ|order)(\s|#|№|\d)',
    r'^(договір|договор|contract)(\s|#|№|\d)',
    r'^(акт|рахунок-фактура)(\s|#|№|\d)',

    # Service payments
    r'^(за (послуги|товари|роботи|services))(\s|$|\.)',
    r'^(оренда|аренда|rent)(\s|$|\.)',
    r'^(кредит|позика|займ|loan)(\s|$|\.)',
    r'^(повернення|возврат|refund)(\s|$|\.)',

    # Utilities
    r'^(електроенергія|электроэнергия|gas|газ|вода|water)(\s|$|\.)',
    r'^(інтернет|internet|телефон|phone)(\s|$|\.)',

    # Business terms
    r'^(прибуток|прибыль|дохід|доход)(\s|$|\.)',
    r'^(витрати|расходы|costs)(\s|$|\.)',
    r'^(бюджет|budget)(\s|$|\.)',

    # Period markers (without names)
    r'^за\s+(січень|лютий|березень|квітень|травень|червень)',
    r'^за\s+(липень|серпень|вересень|жовтень|листопад|грудень)',
    r'^за\s+(январь|февраль|март|апрель|май|июнь)',
    r'^за\s+(июль|август|сентябрь|октябрь|ноябрь|декабрь)',
    r'^за\s+\d+\s*(місяць|месяц|квартал|рік|год)',
    r'^за\s+\d{1,2}[\./]\d{2,4}',

    # Привітання та гасла (не ПІБ)
    r'^слава україні$',
    r'^зі святим миколаєм$',
    r'^з новим роком$',
    r'^вітаю з різдвом$',
    r'^з днем народження$',
    r'^з 8 березня$',
]

# Patterns that indicate a name IS LIKELY present
NAME_INDICATOR_PATTERNS_RAW: List[str] = [
    # Transfer to person
    r'(переказ|перевод|на карту|на картку)\s+[А-ЯІЇЄҐА-яіїєґ]+',
    r'(від|от|from)\s+[А-ЯІЇЄҐ][а-яіїєґ]+',
    r'(для|кому|to)\s+[А-ЯІЇЄҐ][а-яіїєґ]+',

    # Name patterns (Cyrillic)
    r'[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+ович',
    r'[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+івна',
    r'[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+овна',
    r'[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ]\.\s*[А-ЯІЇЄҐ]\.',  # Іванов І.І.
]


def compile_patterns(patterns: List[str]) -> List[Pattern]:
    """Compile regex patterns with case-insensitive flag"""
    return [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]


# Compiled patterns for fast matching
NO_NAME_PATTERNS: List[Pattern] = compile_patterns(NO_NAME_PATTERNS_RAW)
NAME_INDICATOR_PATTERNS: List[Pattern] = compile_patterns(NAME_INDICATOR_PATTERNS_RAW)


def matches_no_name_pattern(text: str) -> bool:
    """Check if text matches any NO_NAME pattern"""
    text = text.strip()
    for pattern in NO_NAME_PATTERNS:
        if pattern.search(text):
            return True
    return False


def matches_name_indicator(text: str) -> bool:
    """Check if text likely contains a name"""
    text = text.strip()
    for pattern in NAME_INDICATOR_PATTERNS:
        if pattern.search(text):
            return True
    return False
