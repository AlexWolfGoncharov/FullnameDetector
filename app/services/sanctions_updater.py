"""Оновлення санкційного списку — при старті та щодня о 3:00"""

import csv
import logging
import re
from pathlib import Path
from typing import Optional

from app.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

OUTPUT_FILE = PROJECT_ROOT / "app" / "data" / "sanctions_individuals.csv"
OPENSANCTIONS_URL = "https://data.opensanctions.org/datasets/latest/ua_nsdc_sanctions/targets.simple.csv"
DRS_EXPORT_URL = "https://drs.nsdc.gov.ua/export/subjects"


def _parse_status(sanctions_str: str) -> str:
    if not sanctions_str:
        return "unknown"
    s = sanctions_str.lower()
    if "active" in s:
        return "active"
    if "expired" in s:
        return "expired"
    return "unknown"


def _extract_translit(aliases: str) -> str:
    if not aliases:
        return ""
    for part in aliases.split(";"):
        part = part.strip().strip('"')
        if part and re.search(r"[a-zA-Z]", part) and not re.search(r"[а-яіїєґ]", part.lower()):
            return part
    return ""


def _fetch_opensanctions() -> list:
    import urllib.request
    logger.info("Завантаження санкцій з OpenSanctions...")
    req = urllib.request.Request(OPENSANCTIONS_URL, headers={"User-Agent": "UkrainianNameDetector/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode("utf-8")
    reader = csv.DictReader(text.splitlines(), quotechar='"', skipinitialspace=True)
    rows = []
    for row in reader:
        if row.get("schema") != "Person":
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        aliases_raw = row.get("aliases") or ""
        aliases_clean = [
            a.strip().strip('"').strip()
            for a in re.split(r";(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", aliases_raw)
            if a.strip().strip('"') and a.strip().strip('"') != name
        ]
        aliases = "; ".join(aliases_clean[:5])
        status = _parse_status(row.get("sanctions") or "")
        translit = _extract_translit(aliases_raw)
        rows.append({
            "sid": row.get("id", ""),
            "name": name,
            "translit_name": translit,
            "aliases": aliases,
            "status": status,
        })
    logger.info(f"Завантажено {len(rows)} фізичних осіб")
    return rows


def _fetch_drs_direct() -> Optional[list]:
    try:
        import urllib.request
        req = urllib.request.Request(DRS_EXPORT_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; UkrainianNameDetector/1.0)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8")
        if "Just a moment" in text or "cloudflare" in text.lower():
            return None
        reader = csv.DictReader(text.splitlines(), delimiter="\t")
        rows = [
            {
                "sid": r.get("sid", ""),
                "name": (r.get("name") or "").strip(),
                "translit_name": r.get("translit_name", ""),
                "aliases": r.get("aliases", ""),
                "status": r.get("status", "active"),
            }
            for r in reader
            if (r.get("name") or "").strip()
        ]
        if rows:
            logger.info(f"Завантажено {len(rows)} записів з DRS")
            return rows
    except Exception as e:
        logger.warning(f"DRS недоступний: {e}")
    return None


def run_update() -> bool:
    """Завантажити оновлений список та зберегти. Повертає True при успіху."""
    rows = _fetch_drs_direct()
    if not rows:
        rows = _fetch_opensanctions()
    if not rows:
        logger.error("Не вдалося завантажити санкційний список")
        return False

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.rename(OUTPUT_FILE.with_suffix(".csv.backup"))

    fieldnames = ["sid", "name", "translit_name", "aliases", "status"]
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Санкції оновлено: {OUTPUT_FILE} ({len(rows)} записів)")
    return True
