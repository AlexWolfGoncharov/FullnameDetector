"""FastAPI application entry point"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.models.schemas import (
    CommentRequest,
    NameDetectionResponse,
    HealthResponse,
    SetupStatus
)
from app.services.pipeline import get_pipeline, NameDetectionPipeline
from app.services.request_logger import get_request_logger
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
    - Прізвище + Ім'я + По батькові
    - Прізвище + Ім'я
    - Тільки прізвище
    - Тільки ім'я
    - ПІБ не знайдено
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
        roberta_ner=health["roberta_ner"],
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
        import app.services.pipeline as pipeline_module
        pipeline_module._pipeline = None
        get_pipeline()

    return {
        "success": success,
        "status": status
    }


@app.get("/logs/stats")
async def get_log_stats():
    """Отримати статистику логування запитів"""
    request_logger = get_request_logger()
    return request_logger.get_stats()


@app.get("/logs/download")
async def download_logs():
    """Скачати CSV файл з логами запитів"""
    request_logger = get_request_logger()
    log_path = request_logger.get_log_path()

    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    return FileResponse(
        path=log_path,
        filename="requests.csv",
        media_type="text/csv"
    )


@app.delete("/logs/clear")
async def clear_logs():
    """Очистити логи запитів"""
    request_logger = get_request_logger()
    request_logger.clear()
    return {"message": "Logs cleared"}


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
