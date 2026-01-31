"""Configuration settings for the API"""

import os
from pathlib import Path
from pydantic import field_validator
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
    llm_verification_threshold: float = 0.85  # Использовать LLM для проверки если confidence < этого значения

    # LLM Fallback (Tier 3) - llama.cpp з MamayLM (легкий для слабых машин)
    # Для Apple Silicon рекомендуется использовать Ollama
    llm_enabled: bool = True
    llm_backend: str = "llama_cpp"  # "ollama" or "llama_cpp"

    # MamayLM-Gemma-3-4B-IT - українська модель в GGUF форматі (легка версія)
    # Використовуємо Q4_K_M квантізацію для балансу між якістю та розміром
    llm_model_name: str = "MamayLM-Gemma-3-4B-IT-v1.0.Q4_K_M.gguf"
    llm_model_repo: str = "INSAIT-Institute/MamayLM-Gemma-3-4B-IT-v1.0-GGUF"
    llm_model_file: str = "MamayLM-Gemma-3-4B-IT-v1.0.Q4_K_M.gguf"
    llm_model_size_mb: int = 2500  # ~2.5GB

    # Ollama settings (if using ollama backend)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mamaylm:latest"  # Используйте модель MamayLM через Ollama

    # HuggingFace token (з .env: NAME_DETECTOR_HF_TOKEN або HF_TOKEN) — не комітити в репо!
    hf_token: str = ""

    @field_validator("hf_token", mode="before")
    @classmethod
    def _hf_token_from_env(cls, v: str) -> str:
        return v or os.getenv("HF_TOKEN", "") or os.getenv("NAME_DETECTOR_HF_TOKEN", "")

    # LLM параметри (оптимізовані для слабких машин)
    llm_context_length: int = 2048
    llm_threads: int = 1  # 1 = стабільніше на Apple Silicon (llama.cpp)
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
