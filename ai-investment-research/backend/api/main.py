"""FastAPI 入口。階段 A 只提供 /health；其餘端點在後續階段加入。"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import __version__
from backend.config import Settings, get_settings
from backend.logging_config import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="AI Investment Research API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.exception("unhandled error request_id=%s path=%s", request_id, request.url.path)
        return JSONResponse(
            status_code=500, content={"error": "internal_error", "request_id": request_id}
        )

    @app.get("/health")
    def health() -> dict:
        # 只回報「是否已設定」，絕不回傳任何密鑰內容。
        return {
            "status": "ok",
            "version": __version__,
            "app_env": settings.app_env,
            "llm_provider": settings.llm_provider,
            "database_configured": settings.database_url is not None,
            "llm_key_configured": settings.llm_api_key is not None,
        }

    return app


app = create_app()
