import os
import glob
import json
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from model import MultiAgentSystem

from contextlib import asynccontextmanager

from src.db import User, create_db_and_tables
from src.schemas import UserCreate, UserRead, UserUpdate
from src.users import auth_backend, current_active_user, fastapi_users, UserManager, get_user_manager

load_dotenv()

HISTORY_DIR = "history"

try:
    rag = MultiAgentSystem()
except Exception as e:
    print("RAG initiation failed", e)
    rag = None

@asynccontextmanager
async def lifespan(app: FastAPI):   
    await create_db_and_tables()   
    yield


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


def get_next_history_number(directory: str = HISTORY_DIR) -> int:
    ensure_history_dir(directory)

    pattern = os.path.join(directory, "history-*.json")
    existing_files = glob.glob(pattern)

    if not existing_files:
        return 1

    numbers = []
    for file_path in existing_files:
        filename = os.path.basename(file_path)
        try:
            num_str = filename.replace("history-", "").replace(".json", "")
            numbers.append(int(num_str))
        except ValueError:
            continue

    return max(numbers) + 1 if numbers else 1


def make_history_filepath(session_id: int, directory: str = HISTORY_DIR) -> str:
    ensure_history_dir(directory)
    return os.path.join(directory, f"history-{session_id}.json")

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


@app.post("/chat")
def chat(request: ChatRequest, user: User = Depends(current_active_user)):
    if rag is None:
        raise HTTPException(status_code=500, detail="RAG is down")

    try:
        last_user_message = None
        for msg in reversed(request.messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content")
                break

        if not last_user_message:
            raise HTTPException(status_code=400, detail="No user message")

        answer = rag.ask_with_history(request.messages, last_user_message)

        # логика сохранения истории в history/
        next_num = get_next_history_number(HISTORY_DIR)
        filepath = make_history_filepath(next_num, HISTORY_DIR)

        data_to_save = {
            "session_id": next_num,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "messages": request.messages,
            "last_user_message": last_user_message,
            "last_answer": answer,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)

        print(f"История сохранена в файл: {filepath}")
        # -------------------------------------------

        return {"answer": answer}

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