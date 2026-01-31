#!/usr/bin/env python3
"""
Витягти унікальні коментарі з logs/requests.csv і прогнати їх через API.

Використання:
    # Сервер має бути запущений
    python scripts/run_unique_from_logs.py [URL]
    python scripts/run_unique_from_logs.py http://localhost:8001
"""

import csv
import json
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
REQUESTS_CSV = LOGS_DIR / "requests.csv"
REQUESTS_BACKUP = LOGS_DIR / "requests.backup.csv"


def get_log_path() -> Path:
    """Обрати файл логів (основний або backup)"""
    if REQUESTS_CSV.exists():
        with open(REQUESTS_CSV, "r", encoding="utf-8") as f:
            header = f.readline().strip().split(",")
            row_count = sum(1 for _ in f)
        if "original_comment" in header and row_count > 0:
            return REQUESTS_CSV
    if REQUESTS_BACKUP.exists():
        return REQUESTS_BACKUP
    return REQUESTS_CSV  # fallback


def extract_unique_comments(log_path: Path) -> list[str]:
    """Витягти унікальні original_comment з CSV"""
    comments = set()
    with open(log_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c = row.get("original_comment", "").strip()
            if c:
                comments.add(c)
    return sorted(comments)


def call_api(comment: str, base_url: str) -> dict:
    """POST до /detect-name"""
    data = json.dumps({"comment": comment}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/detect-name",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"

    log_path = get_log_path()
    if not log_path.exists():
        print(f"Файл логів не знайдено: {log_path}")
        sys.exit(1)

    comments = extract_unique_comments(log_path)
    print(f"Знайдено {len(comments)} унікальних коментарів з {log_path}\n")

    print(f"Проганяємо через API {base_url}...\n")
    print("-" * 100)

    results = []
    for i, comment in enumerate(comments, 1):
        try:
            r = call_api(comment, base_url)
            tier = r.get("tier_detail") or r.get("tier_used", "?")
            ms = r.get("processing_time_ms", "")
            has_name = r.get("has_name", False)
            detected = r.get("detected_name") or "-"
            sanc = r.get("sanctions_check", {})
            sanc_found = sanc.get("found", False)

            line = f"{i:3}. [{tier:4}] {ms:>6}ms | has_name={has_name} | {detected[:40]:40} | sanc={sanc_found} | {comment[:45]}"
            print(line)
            results.append({"comment": comment, "response": r})
        except Exception as e:
            print(f"{i:3}. ERROR: {comment[:50]}... -> {e}")
            results.append({"comment": comment, "error": str(e)})

    print("-" * 100)
    print(f"\nОброблено: {len(results)}")

    # Зберегти результати в JSON для аналізу
    out_path = LOGS_DIR / "unique_run_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Результати збережено: {out_path}")


if __name__ == "__main__":
    main()
