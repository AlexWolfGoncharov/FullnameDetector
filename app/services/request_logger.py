"""Request logger - saves all requests and responses to CSV for analysis"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import threading

from app.models.schemas import NameDetectionResponse
from app.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Шлях до файлу логів
LOGS_DIR = PROJECT_ROOT / "logs"
REQUEST_LOG_FILE = LOGS_DIR / "requests.csv"


class RequestLogger:
    """Logs all API requests and responses to CSV file"""

    _instance: Optional["RequestLogger"] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._file_lock = threading.Lock()

        # Створюємо директорію логів
        LOGS_DIR.mkdir(exist_ok=True)

        # Ініціалізуємо CSV файл з заголовками
        NEW_HEADER = [
            "timestamp", "original_comment", "processed_comment", "has_name",
            "category", "detected_name", "confidence", "tier_used",
            "tier_detail", "processing_time_ms", "sanctions_checked",
            "sanctions_found", "sanctions_matched_name", "sanctions_status",
        ]
        if REQUEST_LOG_FILE.exists():
            with open(REQUEST_LOG_FILE, "r", encoding="utf-8") as f:
                first = f.readline().strip().split(",")
            if "tier_detail" not in first:
                # Старий формат — бэкап і новий файл
                backup = REQUEST_LOG_FILE.with_suffix(".backup.csv")
                import shutil
                shutil.copy(REQUEST_LOG_FILE, backup)
                logger.info(f"Backed up old logs to {backup}")
                self._write_header()
        else:
            self._write_header()

        logger.info(f"Request logger initialized: {REQUEST_LOG_FILE}")

    def _write_header(self):
        """Write CSV header"""
        with open(REQUEST_LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "original_comment",
                "processed_comment",
                "has_name",
                "category",
                "detected_name",
                "confidence",
                "tier_used",
                "tier_detail",
                "processing_time_ms",
                "sanctions_checked",
                "sanctions_found",
                "sanctions_matched_name",
                "sanctions_status",
            ])

    def log(
        self,
        original_comment: str,
        processed_comment: str,
        response: NameDetectionResponse
    ):
        """Log request and response to CSV"""
        sc = response.sanctions_check
        with self._file_lock:
            try:
                with open(REQUEST_LOG_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(),
                        original_comment,
                        processed_comment,
                        response.has_name,
                        response.category.value,
                        response.detected_name or "",
                        response.confidence,
                        response.tier_used,
                        response.tier_detail or "",
                        response.processing_time_ms or "",
                        sc.checked if sc else False,
                        sc.found if sc else False,
                        (sc.matched_name or "") if sc else "",
                        (sc.status or "") if sc else "",
                    ])
            except Exception as e:
                logger.error(f"Failed to log request: {e}")

    def get_log_path(self) -> Path:
        """Get path to log file"""
        return REQUEST_LOG_FILE

    def get_stats(self) -> dict:
        """Get logging statistics"""
        if not REQUEST_LOG_FILE.exists():
            return {"total_logged": 0, "file": str(REQUEST_LOG_FILE)}

        # Рахуємо рядки (мінус заголовок)
        with open(REQUEST_LOG_FILE, "r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f) - 1

        return {
            "total_logged": max(0, line_count),
            "file": str(REQUEST_LOG_FILE),
            "size_kb": REQUEST_LOG_FILE.stat().st_size / 1024
        }

    def clear(self):
        """Clear log file"""
        with self._file_lock:
            self._write_header()
            logger.info("Request log cleared")


# Global instance
def get_request_logger() -> RequestLogger:
    """Get singleton request logger instance"""
    return RequestLogger()
