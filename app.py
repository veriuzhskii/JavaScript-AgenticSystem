import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from model import MultiAgentSystem

from contextlib import asynccontextmanager

from src.db import User, create_db_and_tables
from src.schemas import UserCreate, UserRead, UserUpdate
from src.users import auth_backend, current_active_user, fastapi_users, UserManager, get_user_manager

load_dotenv()

HISTORY_DIR = "history"
DEFAULT_CHAT_TITLE = "Новый чат"

try:
    rag = MultiAgentSystem()
except Exception as e:
    print("RAG initiation failed", e)
    rag = None

@asynccontextmanager
async def lifespan(app: FastAPI):   
    await create_db_and_tables()   
    yield

class ChatRequest(BaseModel):
    chat_id: str | None = None
    messages: List[Dict[str, str]]


class RenameChatRequest(BaseModel):
    title: str

app = FastAPI(title="JavaScript Chat", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000"], # обязательно конкретный хост
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router( 
fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)

app.include_router( 
fastapi_users.get_register_router(UserRead, UserCreate),  
prefix="/auth",   
tags=["auth"],
)

app.include_router(   
fastapi_users.get_reset_password_router(),   
prefix="/auth",   
tags=["auth"],
)

app.include_router( 
fastapi_users.get_verify_router(UserRead), 
prefix="/auth",  
tags=["auth"],
)

app.include_router(
fastapi_users.get_users_router(UserRead, UserUpdate),
prefix="/users",  
tags=["users"],
)

def ensure_history_dir(directory: str = HISTORY_DIR) -> None:
    os.makedirs(directory, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_chat_title(title: str) -> str:
    clean = re.sub(r"\s+", " ", (title or "")).strip()
    if not clean:
        return DEFAULT_CHAT_TITLE
    return clean[:80]


def make_chat_filepath(chat_id: str, directory: str = HISTORY_DIR) -> str:
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


def load_chat(chat_id: str, directory: str = HISTORY_DIR) -> Dict[str, Any]:
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


def save_chat(chat_data: Dict[str, Any], directory: str = HISTORY_DIR) -> None:
    ensure_history_dir(directory)
    filepath = make_chat_filepath(chat_data["chat_id"], directory)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=4)


def list_chat_summaries(directory: str = HISTORY_DIR) -> List[Dict[str, Any]]:
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


def make_history_filepath(session_id: int, directory: str = HISTORY_DIR) -> str:
    ensure_history_dir(directory)
    return os.path.join(directory, f"history-{session_id}.json")

def get_first_user_message(messages: List[Dict[str, str]]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            content = str(msg.get("content", "")).strip()
            if content:
                return content
    return ""

class ChatRequest(BaseModel):
    messages: list[dict[str, str]]


@app.get("/debug-cookies")
async def debug_cookies(request: Request):
    """посмотреть все Cookie"""
    return {
        "cookies": dict(request.cookies),
        "headers": dict(request.headers)
    }

@app.get("/", response_class=HTMLResponse)

async def root(request: Request):
    """перенаправляет на страницу чата или авторизации"""
    # получаем Cookie
    token = request.cookies.get("fastapiusersauth")
    
    if token:
        try:
            with open("templates/index.html", "r", encoding="utf-8") as f:
                return f.read()
        except:
            return RedirectResponse(url="/auth-page")
    else:
        # нет токена - на страницу входа
        return RedirectResponse(url="/auth-page")
    
async def serve_frontend():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл index.html не найден")

@app.get("/auth-page", response_class=HTMLResponse)
async def serve_auth_page():
    try:
        with open("templates/auth.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл auth.html не найден")
    

    
@app.get("/authenticated-route")
async def authenticated_route(user: User = Depends(current_active_user)):
    
    return {"message": f"Hello {user.email}!"}


@app.get("/chats")
def get_chats():
    return {"chats": list_chat_summaries(HISTORY_DIR)}


@app.get("/chats/{chat_id}")
def get_chat(chat_id: str):
    filepath = make_chat_filepath(chat_id, HISTORY_DIR)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Чат не найден")

    chat = load_chat(chat_id, HISTORY_DIR)
    return chat


@app.patch("/chats/{chat_id}/title")
def rename_chat(chat_id: str, request: RenameChatRequest):
    filepath = make_chat_filepath(chat_id, HISTORY_DIR)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Чат не найден")

    chat = load_chat(chat_id, HISTORY_DIR)
    new_title = sanitize_chat_title(request.title)

    if not new_title:
        raise HTTPException(status_code=400, detail="Пустое название чата")

    chat["title"] = new_title
    chat["updated_at"] = utc_now_iso()
    save_chat(chat, HISTORY_DIR)

    return chat


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str):
    filepath = make_chat_filepath(chat_id, HISTORY_DIR)

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

        chat_id = request.chat_id.strip() if request.chat_id else ""
        is_new_chat = False

        if not chat_id:
            chat_id = str(uuid4())
            chat_data = build_empty_chat(chat_id)
            is_new_chat = True
        else:
            filepath = make_chat_filepath(chat_id, HISTORY_DIR)
            if os.path.exists(filepath):
                chat_data = load_chat(chat_id, HISTORY_DIR)
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

        save_chat(chat_data, HISTORY_DIR)

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
    

class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str

@app.post("/auth/simple-reset-password")
async def simple_reset_password(
    reset_data: ResetPasswordRequest,
    user_manager: UserManager = Depends(get_user_manager)
):
    """
    сбрасывает пароль пользователя без подтверждения по email.
    """
    try:
        result = await user_manager.simple_reset_password(
            email=reset_data.email,
            new_password=reset_data.new_password
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")