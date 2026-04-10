"""Project and chat message endpoints."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from src.api.v1.auth.service import get_current_user
from src.api.v1.projects.schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from src.core.database import get_db
from src.models.chat import ChatMessage
from src.models.project import Project
from src.models.user import User

router = APIRouter(prefix="/projects", tags=["Projects"])


async def _get_project_or_404(project_id: UUID, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == user.id,
            col(Project.is_active).is_(True),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    result = await db.execute(
        select(Project).where(
            Project.user_id == current_user.id,
            col(Project.is_active).is_(True),
        )
    )
    return list(result.scalars().all())


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    now = datetime.now(UTC)
    project = Project(
        user_id=current_user.id,
        name=body.name,
        room_spec=body.room_spec,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    return await _get_project_or_404(project_id, current_user, db)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    project = await _get_project_or_404(project_id, current_user, db)
    if body.name is not None:
        project.name = body.name
    if body.room_spec is not None:
        project.room_spec = body.room_spec
    if body.latest_layout is not None:
        project.latest_layout = body.latest_layout
    project.updated_at = datetime.now(UTC)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await _get_project_or_404(project_id, current_user, db)
    project.is_active = False
    project.updated_at = datetime.now(UTC)
    db.add(project)
    await db.commit()


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------


@router.get("/{project_id}/messages", response_model=list[ChatMessageResponse])
async def list_messages(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessage]:
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(col(ChatMessage.created_at))
    )
    return list(result.scalars().all())


@router.post("/{project_id}/messages", response_model=ChatMessageResponse, status_code=201)
async def create_message(
    project_id: UUID,
    body: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatMessage:
    await _get_project_or_404(project_id, current_user, db)
    msg = ChatMessage(
        project_id=project_id,
        role=body.role,
        content=body.content,
        intent=body.intent,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg
