from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.access_middleware import access_middleware
from app.api.response import failed
from app.api.v1.router import api_router
from app.container import build_container
from app.core.config import Settings
from app.core.diagnostics import DiagnosticHandler, active_log_store, request_failure
from app.core.errors import DomainError
from app.infrastructure.persistence.error_logs import ErrorLogStore


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.error_logs = ErrorLogStore(active_settings.data_dir / "logs")
        token = active_log_store.set(app.state.error_logs)
        handler = DiagnosticHandler(app.state.error_logs)
        logger = logging.getLogger("app")
        logger.addHandler(handler)
        try:
            app.state.container = build_container(active_settings)
            await app.state.container.scheduled_refresh_service.start()
            await app.state.container.automation_service.start()
            try:
                yield
            finally:
                await app.state.container.automation_service.stop()
                await app.state.container.scheduled_refresh_service.stop()
        except Exception:
            logger.exception("Application lifecycle failed")
            raise
        finally:
            logger.removeHandler(handler)
            handler.close()
            active_log_store.reset(token)

    app = FastAPI(title="CyMediaFlow", version="0.1.0", lifespan=lifespan)
    app.state.settings_update_lock = asyncio.Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4173", "http://terminal.local:4173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        # Generate locally: caller-controlled headers must not enter diagnostic storage.
        request.state.request_id = f"req_{uuid4().hex}"
        token = active_log_store.set(request.app.state.error_logs)
        try:
            try:
                response = await access_middleware(request, call_next)
            except Exception as exc:
                request.state.failure = exc
                response = JSONResponse(
                    status_code=500,
                    content=failed(
                        request, "INTERNAL_ERROR", "服务内部异常，请凭请求编号查看异常日志"
                    ),
                )
            request_failure(request, response.status_code, getattr(request.state, "failure", None))
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        finally:
            active_log_store.reset(token)

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        request.state.failure = exc
        return JSONResponse(
            status_code=exc.status_code,
            content=failed(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(FileNotFoundError)
    async def handle_file_not_found(request: Request, exc: FileNotFoundError) -> JSONResponse:
        request.state.failure = exc
        return JSONResponse(
            status_code=404,
            content=failed(request, "POSTER_NOT_FOUND", str(exc)),
        )

    app.include_router(api_router)
    return app


app = create_app()
