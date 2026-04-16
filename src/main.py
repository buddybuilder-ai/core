"""BuddyBuilder AI - FastAPI Application Factory."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config.settings import get_settings

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

# Set specific loggers
logging.getLogger("src.modules.layout").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup — preload embedding model so first request isn't slow
    print(f"Starting {settings.APP_NAME}...")
    try:
        from src.modules.layout.infrastructure.vectorstore_service import get_cached_vectorstore

        get_cached_vectorstore(settings.CHROMA_DB_PATH, settings.EMBEDDING_MODEL_LOCAL)
        print("Vectorstore + embedding model loaded")
    except Exception as exc:
        print(f"Vectorstore preload skipped: {exc}")
    yield
    # Shutdown
    print(f"Shutting down {settings.APP_NAME}...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="AI-powered backend for interior design",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Rate limiter state (used by @limiter.limit decorators in routers)
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoints
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        """Basic health check."""
        return {"status": "healthy"}

    @app.get("/health/ready", tags=["Health"])
    async def readiness_check() -> dict[str, str]:
        """Readiness check for Kubernetes."""
        # TODO: Add database and service checks
        return {"status": "ready"}

    # Include API routers
    from src.api.v1.router import api_v1_router

    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return app


# Create the app instance
app = create_app()
