"""FastAPI application entry point"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models.schemas import (
    CommentRequest,
    NameDetectionResponse,
    HealthResponse,
    SetupStatus
)
from app.services.pipeline import get_pipeline, NameDetectionPipeline
from app.setup import SetupManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    logger.info("=" * 60)
    logger.info("Starting Ukrainian Name Detection API")
    logger.info("=" * 60)

    # Auto-setup on first run
    settings = get_settings()
    setup_manager = SetupManager()

    # Check and download models if needed
    setup_manager.setup_all()

    # Initialize pipeline
    pipeline = get_pipeline()
    status = pipeline.get_health()
    logger.info(f"Pipeline status: {status}")

    logger.info("=" * 60)
    logger.info(f"API ready at http://{settings.host}:{settings.port}")
    logger.info("Docs: http://localhost:8000/docs")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down...")


# Create FastAPI app
settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="API для визначення ПІБ у платіжних коментарях",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/detect-name", response_model=NameDetectionResponse)
async def detect_name(request: CommentRequest):
    """
    Визначити ПІБ у платіжному коментарі.

    **Приклади:**
    - "Зарплата за грудень" → has_name: false
    - "Переказ Іванову Петру Олександровичу" → has_name: true

    **Категорії:**
    - Фамилия + Имя + Отчество
    - Фамилия + Имя
    - Только фамилия
    - Имя без фамилии
    - Не содержит ФИО
    """
    try:
        pipeline = get_pipeline()
        result = await pipeline.process(request.comment)
        return result
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Перевірка стану API та компонентів"""
    pipeline = get_pipeline()
    health = pipeline.get_health()

    return HealthResponse(
        status="healthy",
        spacy_model=health["ner_engine"],
        llm_available=health["llm_fallback"] == "available",
        cache_enabled=health["cache"] == "enabled"
    )


@app.get("/stats")
async def get_stats():
    """Отримати статистику обробки запитів"""
    pipeline = get_pipeline()
    return pipeline.get_stats()


@app.get("/setup-status", response_model=SetupStatus)
async def setup_status():
    """Перевірити статус налаштування моделей"""
    setup_manager = SetupManager()
    status = setup_manager.verify_setup()
    status["ready"] = status["spacy_model"] and (status["llm_model"] or not get_settings().llm_enabled)
    return status


@app.post("/setup")
async def run_setup():
    """Запустити автоматичне налаштування (завантаження моделей)"""
    setup_manager = SetupManager()
    success = setup_manager.setup_all()
    status = setup_manager.verify_setup()

    if success:
        # Reinitialize pipeline with new models
        global _pipeline
        from app.services.pipeline import _pipeline
        _pipeline = None
        get_pipeline()

    return {
        "success": success,
        "status": status
    }


def main():
    """Run the application"""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )


if __name__ == "__main__":
    main()
