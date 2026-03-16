import os
import glob
import json
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from model import MultiAgentSystem

load_dotenv()

app = FastAPI(title="JavaScript Chat")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HISTORY_DIR = "history"

try:
    rag = MultiAgentSystem()
except Exception as e:
    print("RAG initiation failed", e)
    rag = None


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]


def ensure_history_dir(directory: str = HISTORY_DIR) -> None:
    """Гарантирует, что папка истории существует."""
    os.makedirs(directory, exist_ok=True)


def get_next_history_number(directory: str = HISTORY_DIR) -> int:
    """Находит следующий доступный номер для файла истории."""
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
    """Формирует путь к файлу истории."""
    ensure_history_dir(directory)
    return os.path.join(directory, f"history-{session_id}.json")


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл index.html не найден")


@app.post("/chat")
def chat(request: ChatRequest):
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

        # --- логика сохранения истории в history/ ---
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