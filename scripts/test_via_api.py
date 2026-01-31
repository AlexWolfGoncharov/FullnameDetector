#!/usr/bin/env python3
"""
Швидка перевірка через API (сервер має бути запущений).
Використання: python scripts/test_via_api.py [URL]
"""

import sys
import json
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"


def test_comment(comment: str, expect_has_name: bool) -> bool:
    """Відправити коментар і перевірити результат."""
    try:
        data = json.dumps({"comment": comment}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/detect-name",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
    except Exception as e:
        print(f"✗ Помилка: {e}")
        return False

    has_name = result.get("has_name", False)
    detected = result.get("detected_name") or "-"
    sanctions = result.get("sanctions_check", {})
    sanctions_found = sanctions.get("found", False) if sanctions else False

    ok = has_name == expect_has_name
    status = "✓" if ok else f"✗ очікувалось has_name={expect_has_name}"
    sanc_str = "САНКЦІЇ!" if sanctions_found else "ok"
    preview = (comment[:47] + "...") if len(comment) > 50 else comment
    print(f"  {status} | {detected} | {sanc_str} | {preview}")
    return ok


def main():
    print(f"=== Тестування API на {BASE_URL} ===\n")

    passed = 0
    total = 0

    print("--- Коментарі БЕЗ ПІБ ---")
    for comment in [
        "Заробітна плата-за II половину листопада 2025 р.",
        "Заробітна плата-Зарплата за 1 половину листопада 2025р",
        "Переказ коштiв-Матеріальна допомога грошова проф виплата",
        "Заробітна плата-Слава Україні",
        "Премія-з Новим Роком",
    ]:
        total += 1
        if test_comment(comment, False):
            passed += 1

    print("\n--- Коментарі З ПІБ ---")
    for comment in [
        "Заробітна плата-Булатов Руслан Олександрович",
        "Заробітна плата-Іванов Петро Олександрович",
    ]:
        total += 1
        if test_comment(comment, True):
            passed += 1

    print("\n--- Санкції: в списку (Булатов Руслан Рустемович, Журавльов) ---")
    for comment in [
        "Заробітна плата-Булатов Руслан Рустемович",
        "Переказ-Журавльов Олексій Олександрович",
    ]:
        total += 1
        if test_comment(comment, True):
            passed += 1

    print("\n--- Санкції: НЕ в списку ---")
    for comment in [
        "Заробітна плата-Іванов Петро Олександрович",
        "Премія-Мельник Олександр Олександрович",
    ]:
        total += 1
        if test_comment(comment, True):
            passed += 1

    print(f"\n=== Результат: {passed}/{total} тестів пройдено ===")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
