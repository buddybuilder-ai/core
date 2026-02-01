"""BuddyBuilder AI - FastAPI Application Factory."""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    print(f"🚀 Starting {settings.APP_NAME}...")
    yield
    # Shutdown
    print(f"👋 Shutting down {settings.APP_NAME}...")


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
    # from src.api.v1.router import api_v1_router
    # app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return app


# Create the app instance
app = create_app()
