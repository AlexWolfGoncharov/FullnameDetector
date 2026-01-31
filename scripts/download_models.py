#!/usr/bin/env python3
"""
Скачування всіх моделей для Ukrainian Name Detection API.

Запуск: HF_TOKEN=hf_xxx python scripts/download_models.py
Або створіть .env з HF_TOKEN=...
"""

import os
import shutil
import sys
from pathlib import Path

# Додаємо корінь проекту в path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def get_hf_token():
    """Отримати HF token з env або .env"""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token and (PROJECT_ROOT / ".env").exists():
        with open(PROJECT_ROOT / ".env") as f:
            for line in f:
                if line.strip().startswith("HF_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"\'')
                    break
    return token or None


def download_llm_gguf():
    """MamayLM GGUF (~2.5GB) — в models/ для llama.cpp"""
    from huggingface_hub import hf_hub_download

    filename = "MamayLM-Gemma-3-4B-IT-v1.0.Q4_K_M.gguf"
    dest = MODELS_DIR / filename
    if dest.exists() and dest.stat().st_size > 1_000_000_000:
        print(f"[OK] LLM вже є: {dest}")
        return True

    print("Завантаження MamayLM GGUF (~2.5GB)...")
    token = get_hf_token()

    def _do_download(tok):
        return hf_hub_download(
            repo_id="INSAIT-Institute/MamayLM-Gemma-3-4B-IT-v1.0-GGUF",
            filename=filename,
            token=tok,
        )

    try:
        path = _do_download(token)
    except Exception as e:
        if "401" in str(e) or "expired" in str(e).lower() or "Unauthorized" in str(e):
            print("  Токен прострочений — завантаження без токена")
            path = _do_download(None)
        else:
            raise

    src = Path(path)
    if src.exists():
        shutil.copy2(src, dest)
        print(f"Скопійовано в {dest}")
    else:
        raise FileNotFoundError(f"Завантаження не вдалось: {path}")
    print(f"[OK] LLM: {dest}")
    return True


def download_roberta_ner():
    """RoBERTa NER — в HF cache для transformers"""
    cache_dir = MODELS_DIR / "hf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache_dir)

    from transformers import AutoTokenizer, AutoModelForTokenClassification

    model_name = "EvanD/xlm-roberta-base-ukrainian-ner-ukrner"
    token = get_hf_token()

    def _load(tok):
        AutoTokenizer.from_pretrained(model_name, token=tok)
        AutoModelForTokenClassification.from_pretrained(model_name, token=tok)

    print(f"Завантаження RoBERTa NER: {model_name}...")
    try:
        _load(token)
    except Exception as e:
        if "401" in str(e) or "expired" in str(e).lower() or "Unauthorized" in str(e):
            print("  Токен прострочений — завантаження без токена (модель публічна)")
            _load(None)
        else:
            raise
    print("[OK] RoBERTa NER")
    return True


def download_spacy():
    """spaCy uk_core_news_md — в Docker вже є, локально через pip"""
    if os.path.exists("/.dockerenv"):
        print("[OK] spaCy — встановлено в Dockerfile")
        return True
    try:
        import spacy
        spacy.load("uk_core_news_md")
        print("[OK] spaCy uk_core_news_md вже є")
        return True
    except OSError:
        pass
    print("Встановлення spaCy uk_core_news_md...")
    import subprocess
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "spacy>=3.8,<3.9"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "-m", "spacy", "download", "uk_core_news_md"],
        check=True,
        capture_output=True,
    )
    print("[OK] spaCy uk_core_news_md")
    return True


def main():
    print("=" * 50)
    print("Завантаження моделей для Ukrainian Name Detection API")
    print("=" * 50)
    token = get_hf_token()
    if token:
        print("HF_TOKEN знайдено")
    else:
        print("HF_TOKEN не задано — публічні моделі завантажаться без нього")

    download_spacy()
    download_roberta_ner()
    download_llm_gguf()

    print("=" * 50)
    print("Готово. Моделі в:", MODELS_DIR)
    print("=" * 50)


if __name__ == "__main__":
    main()
