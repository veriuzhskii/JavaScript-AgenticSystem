
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os
from modules import RAG

def ensure_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY ERROR: переменная окружения GROQ_API_KEY не найдена.")
    return api_key

class Agent:
    def __init__(self):
        """Инициализация агента с дефолтными параметрами"""
        load_dotenv()
        self.api_key = ensure_api_key()
        self.model = "llama-3.3-70b-versatile"  # или другая модель
        self.temperature = 0.3
        self.rag = RAG()
        self.llm = ChatGroq(
            temperature=self.temperature,
            model_name=self.model,
            groq_api_key=self.api_key,
            max_tokens=1000,
        )

    def ask_with_history(self, messages: list, query: str) -> str:
        """Обработка запроса с историей (для совместимости с app.py)"""
        # Извлекаем контекст из истории, если нужно
        # Или просто используем последний запрос
        docs = self.rag.vectorize_and_search(query, n_results=3)
        context = self.rag.format_context(docs)
        
        # Формируем промпт с учётом истории
        history_text = ""
        if messages:
            # Берем последние 5 сообщений для контекста
            recent_msgs = messages[-5:]
            history_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent_msgs])
        
        prompt = f"""Ты помощник по JavaScript. Отвечай на русском языке.

История диалога:
{history_text}

Контекст из документации:
{context}

Вопрос пользователя: {query}

Ответ:"""

        response = self.llm.invoke(prompt)
        return response.content
    
    def generate_chat_title(self, first_message: str) -> str:
        """Генерирует название чата по первому сообщению"""
        prompt = f"Создай короткое название для чата (максимум 5-6 слов) на русском языке по первому сообщению пользователя: '{first_message}'. Только название, без кавычек и пояснений."
        
        try:
            response = self.llm.invoke(prompt)
            title = response.content.strip()
            # Ограничиваем длину
            if len(title) > 80:
                title = title[:77] + "..."
            return title
        except:
            # В случае ошибки берем первые слова сообщения
            words = first_message.split()[:5]
            return " ".join(words) + "..."

    def execute(self, query: str, context: str = "") -> str:
        """Оригинальный метод execute (оставляем для обратной совместимости)"""
        docs = self.rag.vectorize_and_search(query, n_results=3)
        context = self.rag.format_context(docs)
        prompt = f"Ответь на запрос пользователя {query}, используя этот контекст {context}"
        
        response = self.llm.invoke(prompt)
        return response.content

def main():
    try:
        system = Agent()
        query = input("Введите запрос: ").strip()
        
        if not query:
            raise ValueError("Пустой запрос")
        
        result = system.ask_with_history([], query)
        print(result)
        return result
    except Exception as e:
        print(f"Ошибка в main: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()