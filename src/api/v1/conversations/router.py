"""Conversation and chat message endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from src.api.v1.auth.service import get_current_user
from src.api.v1.conversations.schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ConversationCreate,
    ConversationResponse,
)
from src.core.database import get_db
from src.models.chat import ChatMessage
from src.models.conversation import Conversation
from src.models.user import User

router = APIRouter(prefix="/conversations", tags=["Conversations"])


async def _get_conversation_or_404(
    conversation_id: UUID, user: User, db: AsyncSession
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    kind: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.user_id == current_user.id)
    if kind is not None:
        stmt = stmt.where(Conversation.kind == kind)
    stmt = stmt.order_by(col(Conversation.created_at).desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    conv = Conversation(user_id=current_user.id, title=body.title, kind="general")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    return await _get_conversation_or_404(conversation_id, current_user, db)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    conv = await _get_conversation_or_404(conversation_id, current_user, db)
    conv.title = body.title
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    conv = await _get_conversation_or_404(conversation_id, current_user, db)
    await db.delete(conv)
    await db.commit()


@router.get("/{conversation_id}/messages", response_model=list[ChatMessageResponse])
async def list_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessage]:
    await _get_conversation_or_404(conversation_id, current_user, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(col(ChatMessage.created_at))
    )
    return list(result.scalars().all())


@router.post("/{conversation_id}/messages", response_model=ChatMessageResponse, status_code=201)
async def create_message(
    conversation_id: UUID,
    body: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatMessage:
    await _get_conversation_or_404(conversation_id, current_user, db)
    msg = ChatMessage(
        conversation_id=conversation_id,
        role=body.role,
        content=body.content,
        intent=body.intent,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg
