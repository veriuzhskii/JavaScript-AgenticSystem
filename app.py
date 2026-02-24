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

try:
    rag = MultiAgentSystem()
except Exception as e:
    print("Блин, что-то опять упало(((", e)
    rag = None



class ChatRequest(BaseModel):
    messages: list[dict[str, str]]

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
        raise HTTPException(status_code=500, detail="RAG caput")

    try:
        last_user_message = None
        for msg in reversed(request.messages):
            if msg["role"] == "user":
                last_user_message = msg["content"]
                break

        if not last_user_message:
            raise HTTPException(status_code=400, detail="No user message")

        answer = rag.ask_with_history(request.messages, last_user_message)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG Error: {str(e)}")