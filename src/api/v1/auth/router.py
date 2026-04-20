"""Auth endpoints: register, login, logout, me."""

from fastapi import APIRouter, Depends, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from src.api.v1.auth.service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
)
from src.core.database import get_db
from src.models.user import User

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["Auth"])

_COOKIE_NAME = "access_token"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days in seconds


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_COOKIE_MAX_AGE,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new user and return a JWT token."""
    user = await create_user(db, body.email, body.password, body.display_name)
    token = create_access_token(user.id)
    _set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and return a JWT token."""
    user = await authenticate_user(db, body.email, body.password)
    token = create_access_token(user.id)
    _set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    """Clear the auth cookie."""
    response.delete_cookie(key=_COOKIE_NAME, httponly=True, secure=True, samesite="strict")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.model_validate(current_user)
