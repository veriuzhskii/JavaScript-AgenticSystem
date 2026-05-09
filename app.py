import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from model import MultiAgentSystem
from src.db import (
    Topic,
    User,
    UserRoadmapItem,
    UserTopic,
    create_db_and_tables,
    get_async_session,
    seed_topics,
)
from src.schemas import UserCreate, UserRead
from src.users import auth_backend, current_active_user, fastapi_users, get_user_manager

load_dotenv()

app = FastAPI(title="JavaScript Chat")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HISTORY_DIR = "history"
DEFAULT_CHAT_TITLE = "Новый чат"

try:
    rag = MultiAgentSystem()
except Exception as e:
    print("RAG initiation failed", e)
    rag = None


class ChatRequest(BaseModel):
    chat_id: str | None = None
    messages: List[Dict[str, str]]


class RenameChatRequest(BaseModel):
    title: str


class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str


class TopicRead(BaseModel):
    key: str
    title: str


class UserTopicsResponse(BaseModel):
    topics: List[TopicRead]
    learned_topic_keys: List[str]


class UpdateUserTopicsRequest(BaseModel):
    topic_keys: List[str] = Field(default_factory=list)


class UpdateRoadmapItemsRequest(BaseModel):
    item_slugs: List[str] = Field(default_factory=list)


@app.on_event("startup")
async def on_startup():
    await create_db_and_tables()
    await seed_topics()
    await seed_extra_topics()


async def seed_extra_topics():
    """Ensure new topic keys added to the frontend survey exist in the DB."""
    from sqlalchemy import insert
    from src.db import get_async_session

    extra = [
        {"key": "this", "title": "Ключевое слово this"},
        {"key": "modules", "title": "Модули"},
    ]

    async for session in get_async_session():
        existing = await session.execute(select(Topic.key))
        existing_keys = set(existing.scalars().all())

        for topic in extra:
            if topic["key"] not in existing_keys:
                session.add(Topic(key=topic["key"], title=topic["title"]))

        await session.commit()
        break


app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)


def ensure_history_dir(directory: str) -> None:
    os.makedirs(directory, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_chat_title(title: str) -> str:
    clean = re.sub(r"\s+", " ", (title or "")).strip()
    if not clean:
        return DEFAULT_CHAT_TITLE
    return clean[:80]


def make_user_history_dir(user_id: str, root_directory: str = HISTORY_DIR) -> str:
    directory = os.path.join(root_directory, user_id)
    ensure_history_dir(directory)
    return directory


def make_chat_filepath(chat_id: str, directory: str) -> str:
    ensure_history_dir(directory)
    return os.path.join(directory, f"{chat_id}.json")


def build_empty_chat(chat_id: str) -> Dict[str, Any]:
    now = utc_now_iso()
    return {
        "chat_id": chat_id,
        "title": DEFAULT_CHAT_TITLE,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def load_chat(chat_id: str, directory: str) -> Dict[str, Any]:
    filepath = make_chat_filepath(chat_id, directory)

    if not os.path.exists(filepath):
        return build_empty_chat(chat_id)

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "chat_id": data.get("chat_id", chat_id),
        "title": sanitize_chat_title(data.get("title", DEFAULT_CHAT_TITLE)),
        "created_at": data.get("created_at", utc_now_iso()),
        "updated_at": data.get("updated_at", utc_now_iso()),
        "messages": data.get("messages", []),
    }


def save_chat(chat_data: Dict[str, Any], directory: str) -> None:
    ensure_history_dir(directory)
    filepath = make_chat_filepath(chat_data["chat_id"], directory)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=4)


def list_chat_summaries(directory: str) -> List[Dict[str, Any]]:
    ensure_history_dir(directory)

    chats: List[Dict[str, Any]] = []

    for filename in os.listdir(directory):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(directory, filename)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            chats.append(
                {
                    "chat_id": data.get("chat_id"),
                    "title": sanitize_chat_title(data.get("title", DEFAULT_CHAT_TITLE)),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                }
            )
        except Exception as e:
            print(f"Не удалось прочитать файл {filepath}: {e}")

    chats.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return chats


def get_first_user_message(messages: List[Dict[str, str]]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            content = str(msg.get("content", "")).strip()
            if content:
                return content
    return ""


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл index.html не найден")


@app.get("/users/me", response_model=UserRead)
async def get_me(user: User = Depends(current_active_user)):
    return user


@app.post("/auth/simple-reset-password")
async def simple_reset_password(
    request: ResetPasswordRequest,
    user_manager=Depends(get_user_manager),
):
    return await user_manager.simple_reset_password(
        email=request.email,
        new_password=request.new_password,
    )


@app.get("/topics", response_model=UserTopicsResponse)
async def get_topics(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    topics_result = await session.execute(select(Topic).order_by(Topic.title))
    topics = topics_result.scalars().all()

    learned_result = await session.execute(
        select(UserTopic.topic_key).where(UserTopic.user_id == user.id)
    )
    learned_topic_keys = list(learned_result.scalars().all())

    return UserTopicsResponse(
        topics=[TopicRead(key=topic.key, title=topic.title) for topic in topics],
        learned_topic_keys=learned_topic_keys,
    )


@app.put("/topics/me", response_model=UserTopicsResponse)
async def update_my_topics(
    request: UpdateUserTopicsRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    requested_keys = list(dict.fromkeys(request.topic_keys))

    existing_topics_result = await session.execute(select(Topic.key))
    existing_topic_keys = set(existing_topics_result.scalars().all())

    # Silently filter out unknown keys so new frontend topics don't break
    # until the DB seed is updated
    requested_keys = [key for key in requested_keys if key in existing_topic_keys]

    await session.execute(delete(UserTopic).where(UserTopic.user_id == user.id))

    for topic_key in requested_keys:
        session.add(UserTopic(user_id=user.id, topic_key=topic_key))

    await session.commit()

    topics_result = await session.execute(select(Topic).order_by(Topic.title))
    topics = topics_result.scalars().all()

    return UserTopicsResponse(
        topics=[TopicRead(key=topic.key, title=topic.title) for topic in topics],
        learned_topic_keys=requested_keys,
    )


@app.get("/roadmap/items")
async def get_roadmap_items(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(UserRoadmapItem.item_slug).where(UserRoadmapItem.user_id == user.id)
    )
    return {"item_slugs": list(result.scalars().all())}


@app.put("/roadmap/items")
async def update_roadmap_items(
    request: UpdateRoadmapItemsRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    slugs = list(dict.fromkeys(s.strip() for s in request.item_slugs if s.strip()))

    await session.execute(
        delete(UserRoadmapItem).where(UserRoadmapItem.user_id == user.id)
    )

    for slug in slugs:
        session.add(UserRoadmapItem(user_id=user.id, item_slug=slug))

    await session.commit()
    return {"item_slugs": slugs}


@app.get("/chats")
def get_chats(user: User = Depends(current_active_user)):
    user_history_dir = make_user_history_dir(str(user.id))
    return {"chats": list_chat_summaries(user_history_dir)}


@app.get("/chats/{chat_id}")
def get_chat(chat_id: str, user: User = Depends(current_active_user)):
    user_history_dir = make_user_history_dir(str(user.id))
    filepath = make_chat_filepath(chat_id, user_history_dir)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Чат не найден")

    chat = load_chat(chat_id, user_history_dir)
    return chat


@app.patch("/chats/{chat_id}/title")
def rename_chat(
    chat_id: str,
    request: RenameChatRequest,
    user: User = Depends(current_active_user),
):
    user_history_dir = make_user_history_dir(str(user.id))
    filepath = make_chat_filepath(chat_id, user_history_dir)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Чат не найден")

    chat = load_chat(chat_id, user_history_dir)
    new_title = sanitize_chat_title(request.title)

    if not new_title:
        raise HTTPException(status_code=400, detail="Пустое название чата")

    chat["title"] = new_title
    chat["updated_at"] = utc_now_iso()
    save_chat(chat, user_history_dir)

    return chat


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, user: User = Depends(current_active_user)):
    user_history_dir = make_user_history_dir(str(user.id))
    filepath = make_chat_filepath(chat_id, user_history_dir)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Чат не найден")

    os.remove(filepath)
    return {"ok": True, "chat_id": chat_id}


@app.post("/chat")
def chat(request: ChatRequest, user: User = Depends(current_active_user)):
    if rag is None:
        raise HTTPException(status_code=500, detail="RAG is down")

    try:
        last_user_message = None
        for msg in reversed(request.messages):
            if msg.get("role") == "user":
                last_user_message = str(msg.get("content", "")).strip()
                if last_user_message:
                    break

        if not last_user_message:
            raise HTTPException(status_code=400, detail="No user message")

        answer = rag.ask_with_history(request.messages, last_user_message)

        user_history_dir = make_user_history_dir(str(user.id))

        chat_id = request.chat_id.strip() if request.chat_id else ""
        is_new_chat = False

        if not chat_id:
            chat_id = str(uuid4())
            chat_data = build_empty_chat(chat_id)
            is_new_chat = True
        else:
            filepath = make_chat_filepath(chat_id, user_history_dir)
            if os.path.exists(filepath):
                chat_data = load_chat(chat_id, user_history_dir)
            else:
                chat_data = build_empty_chat(chat_id)
                is_new_chat = True

        final_messages = list(request.messages)
        final_messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        if chat_data["title"] == DEFAULT_CHAT_TITLE:
            first_user_message = get_first_user_message(final_messages)
            if first_user_message:
                generated_title = rag.generate_chat_title(first_user_message)
                chat_data["title"] = sanitize_chat_title(generated_title)

        now = utc_now_iso()
        chat_data["messages"] = final_messages
        chat_data["updated_at"] = now

        if not chat_data.get("created_at"):
            chat_data["created_at"] = now

        save_chat(chat_data, user_history_dir)

        return {
            "chat_id": chat_data["chat_id"],
            "answer": answer,
            "title": chat_data["title"],
            "created_at": chat_data["created_at"],
            "updated_at": chat_data["updated_at"],
            "messages": chat_data["messages"],
            "is_new_chat": is_new_chat,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG Error: {str(e)}")