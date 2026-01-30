"""Configuration settings for the API"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"


class Settings(BaseSettings):
    """Application settings"""

    # API
    app_name: str = "Ukrainian Name Detection API"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # NER Engine (Tier 2)
    spacy_model: str = "uk_core_news_md"
    ner_confidence_threshold: float = 0.7

    # LLM Fallback (Tier 3) - llama.cpp з MamayLM (легкий для слабых машин)
    llm_enabled: bool = True
    llm_backend: str = "llama_cpp"  # "ollama" or "llama_cpp"

    # MamayLM-Gemma-3-4B-IT - українська модель в GGUF форматі (легка версія)
    # Використовуємо Q4_K_M квантізацію для балансу між якістю та розміром
    llm_model_name: str = "mamaylm-gemma-3-4b-it-v1.0-Q4_K_M.gguf"
    llm_model_repo: str = "INSAIT-Institute/MamayLM-Gemma-3-4B-IT-v1.0-GGUF"
    llm_model_file: str = "mamaylm-gemma-3-4b-it-v1.0-Q4_K_M.gguf"
    llm_model_size_mb: int = 2500  # ~2.5GB (набагато легше ніж 9B)

    # Ollama settings (if using ollama backend)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    # HuggingFace token для закритих моделей
    hf_token: str = "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"

    # LLM параметри (оптимізовані для слабких машин)
    llm_context_length: int = 2048
    llm_threads: int = 2  # Менше потоків для слабких машин
    llm_max_tokens: int = 150
    llm_temperature: float = 0.1
    llm_timeout: int = 30  # Менший таймаут для швидшої відповіді
    llm_max_concurrent: int = 2  # Менше одночасних запитів

    # Cache
    cache_enabled: bool = True
    cache_maxsize: int = 10000

    @property
    def llm_model_path(self) -> Path:
        return MODELS_DIR / self.llm_model_name

    class Config:
        env_file = ".env"
        env_prefix = "NAME_DETECTOR_"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
