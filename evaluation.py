import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Проверка
if not os.getenv("GROQ_API_KEY"):
    raise ValueError("Установи переменную окружения GROQ_API_KEY")


from ragas import evaluate, EvaluationDataset
from ragas.llms import LangchainLLMWrapper

# Импорт правильного LLM для Groq
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage


groq_llm = ChatGroq(
    model="llama-3.1-8b-instant",  # или другую доступную модель
    temperature=0.3,
)

# 2️⃣ Оборачиваем LLM для Ragas
evaluator_llm = LangchainLLMWrapper(groq_llm)

# 3️⃣ Собираем пример RAG-датасета
dataset_list = [
    {
        "user_input": "Что такое Ragas?",
        "retrieved_contexts": ["Ragas — это фреймворк для оценки RAG-систем."],
        "response": "Ragas — фреймворк для оценки RAG-систем.",
        "reference": "Ragas — это фреймворк для оценки RAG-систем.",
    },
]

evaluation_dataset = EvaluationDataset.from_list(dataset_list)

# 4️⃣ Оцениваем с помощью метрик Ragas
from ragas.metrics import LLMContextRecall, Faithfulness, FactualCorrectness

results = evaluate(
    dataset=evaluation_dataset,
    metrics=[LLMContextRecall(), Faithfulness(), FactualCorrectness()],
    llm=evaluator_llm,
)

print("RAG Eval Result:", results)
