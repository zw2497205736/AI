import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import get_current_user
from database import SessionLocal, get_db
from models.conversation import Conversation, Message
from schemas.chat import ConversationUpdatePayload
from services.chat_agent_service import run_chat_agent
from services.llm_service import get_chat_client, get_embedding_client
from services.memory_service import ShortTermMemory, delete_memory, extract_and_save_memories, list_memories, search_long_term_memories
from services.session_store import delete_short_memory, load_short_memory, save_short_memory


router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


async def ensure_conversation(session_id: str, user_id: str, db: AsyncSession):
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conversation = result.scalar_one_or_none()
    if conversation is None:
        db.add(Conversation(session_id=session_id, user_id=user_id, title="新对话"))
        await db.commit()


async def get_conversation(session_id: str, db: AsyncSession) -> Optional[Conversation]:
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    return result.scalar_one_or_none()


async def hydrate_short_memory(session_id: str, db: AsyncSession) -> ShortTermMemory:
    result = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc(), Message.id.asc()))
    messages = result.scalars().all()
    memory = ShortTermMemory()
    for message in messages:
        memory.add(message.role, message.content)
    return memory


def generate_conversation_title(query: str) -> str:
    compact = " ".join(query.strip().split())
    return compact[:24] if compact else "新对话"


def build_source_preview_items(chunks: list[dict], limit: int = 3) -> list[dict]:
    previews: list[dict] = []
    for item in chunks[:limit]:
        content = str(item.get("content") or "").strip()
        preview = " ".join(content.split())
        if len(preview) > 180:
            preview = preview[:180].rstrip() + "..."
        previews.append(
            {
                "filename": str(item.get("filename") or "未命名文档"),
                "source_type": str(item.get("source_type") or "unknown"),
                "score": item.get("score"),
                "preview": preview,
            }
        )
    return previews


async def save_message(session_id: str, role: str, content: str, db: AsyncSession):
    db.add(Message(session_id=session_id, role=role, content=content))
    await db.commit()


async def save_memories_in_background(user_id: str, query: str, full_response: str):
    embedding_client = get_embedding_client()
    async with SessionLocal() as session:
        await extract_and_save_memories(user_id, query, full_response, embedding_client, session)


@router.get("/stream")
async def chat_stream(
    query: str = Query(...),
    session_id: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    user_id = current_user.username

    if not session_id:
        session_id = str(uuid.uuid4())
    short_memory = await load_short_memory(session_id)
    if short_memory is None:
        short_memory = await hydrate_short_memory(session_id, db)
        await save_short_memory(session_id, short_memory)
    chat_client = get_chat_client()
    embedding_client = get_embedding_client()

    async def generate():
        await ensure_conversation(session_id, user_id, db)
        conversation = await get_conversation(session_id, db)
        if conversation and conversation.title == "新对话":
            conversation.title = generate_conversation_title(query)
            await db.commit()
        await short_memory.maybe_compress(chat_client)
        await save_short_memory(session_id, short_memory)
        agent_result = await run_chat_agent(
            query=query,
            user_id=user_id,
            short_memory=short_memory,
            chat_client=chat_client,
            embedding_client=embedding_client,
            db=db,
        )
        source_previews = build_source_preview_items(agent_result["sources"])
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"
        logger.info(
            "Chat agent payload: session_id=%s mode=%s retrieval_hit=%s sources=%s",
            session_id,
            agent_result["mode"],
            bool(agent_result["retrieval_hit"]),
            source_previews,
        )
        yield f"data: {json.dumps({'sources': source_previews, 'retrieval_hit': bool(agent_result['retrieval_hit'])})}\n\n"
        full_response = str(agent_result["response"] or "")
        yield f"data: {json.dumps({'content': full_response})}\n\n"

        short_memory.add("user", query)
        short_memory.add("assistant", full_response)
        await save_short_memory(session_id, short_memory)
        await save_message(session_id, "user", query, db)
        await save_message(session_id, "assistant", full_response, db)
        yield "data: [DONE]\n\n"
        asyncio.create_task(save_memories_in_background(user_id, query, full_response))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    await delete_short_memory(session_id)
    return {"message": "Session cleared"}


@router.get("/conversations")
async def get_conversations(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    user_id = current_user.username
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.created_at.desc(), Conversation.id.desc())
    )
    conversations = result.scalars().all()
    return [
        {
            "session_id": item.session_id,
            "title": item.title or "新对话",
            "created_at": str(item.created_at),
        }
        for item in conversations
    ]


@router.get("/conversations/{session_id}/messages")
async def get_conversation_messages(session_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    conversation = await get_conversation(session_id, db)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != current_user.username:
        raise HTTPException(status_code=403, detail="Forbidden")
    result = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc(), Message.id.asc()))
    messages = result.scalars().all()
    return {
        "session_id": session_id,
        "title": conversation.title or "新对话",
        "messages": [
            {
                "id": str(message.id),
                "role": message.role,
                "content": message.content,
                "timestamp": int(message.created_at.timestamp() * 1000) if message.created_at else 0,
            }
            for message in messages
        ],
    }


@router.patch("/conversations/{session_id}")
async def update_conversation(
    session_id: str, payload: ConversationUpdatePayload, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)
):
    conversation = await get_conversation(session_id, db)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != current_user.username:
        raise HTTPException(status_code=403, detail="Forbidden")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    conversation.title = title[:50]
    await db.commit()
    return {"message": "Updated", "title": conversation.title}


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    conversation = await get_conversation(session_id, db)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != current_user.username:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(Conversation).where(Conversation.session_id == session_id))
    await db.commit()
    await delete_short_memory(session_id)
    return {"message": "Deleted"}


@router.get("/memories")
async def get_user_memories(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    user_id = current_user.username
    memories = await list_memories(user_id, db)
    return [{"id": item.id, "key": item.key, "value": item.value, "created_at": str(item.created_at)} for item in memories]


@router.delete("/memories/{memory_id}")
async def remove_memory(memory_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    deleted = await delete_memory(memory_id, current_user.username, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Deleted"}
