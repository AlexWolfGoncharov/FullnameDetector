#!/usr/bin/env python3
"""
Ручне оновлення санкційного списку (при старті API оновлення виконується автоматично).

Запуск: python scripts/fetch_sanctions.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.sanctions_updater import run_update


def main():
    if run_update():
        print("Готово. Перезапустіть API для завантаження нового списку.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
