from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.response import failed
from app.api.v1.router import api_router
from app.container import build_container
from app.core.config import Settings
from app.core.errors import DomainError


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = build_container(active_settings)
        await app.state.container.scheduled_refresh_service.start()
        try:
            yield
        finally:
            await app.state.container.scheduled_refresh_service.stop()

    app = FastAPI(title="CyMediaFlow", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4173", "http://terminal.local:4173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=failed(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(FileNotFoundError)
    async def handle_file_not_found(request: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=failed(request, "POSTER_NOT_FOUND", str(exc)),
        )

    app.include_router(api_router)
    return app


app = create_app()
