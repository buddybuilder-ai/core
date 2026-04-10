"""API v1 router - aggregates all endpoint routers."""

from fastapi import APIRouter

from src.api.v1.auth.router import router as auth_router
from src.api.v1.chat.router import router as chat_router
from src.api.v1.conversations.router import router as conversations_router
from src.api.v1.layout.router import router as layout_router
from src.api.v1.projects.router import router as projects_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(layout_router)
