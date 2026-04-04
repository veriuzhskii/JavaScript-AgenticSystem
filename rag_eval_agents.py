# rag_eval_two_questions_safe.py
import os
import json
from dotenv import load_dotenv
from ragas import evaluate, EvaluationDataset
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import LLMContextRecall, Faithfulness, FactualCorrectness
from langchain_groq import ChatGroq
from agents import rag, manager, teacher, coder

# ---------------- ENV ----------------
load_dotenv()
if not os.getenv("GROQ_API_KEY"):
    raise ValueError("Установи переменную окружения GROQ_API_KEY")

# ---------------- Загрузка вопросов ----------------
with open("questions.json", "r", encoding="utf-8") as f:
    questions_data = json.load(f)

dataset_list = []

# Ограничение контекста для LLM
max_context_chars = 2000

# ---------------- Берём первые два вопроса ----------------
N = 5 
dataset_list = []
max_context_chars = 2000

# Проходим по уровням для teacher
for level in questions_data["teacher"]:
    # Берём первые N вопросов уровня
    for q in questions_data["teacher"][level][:N]:
        question_text = q["question"]
        reference_answer = q["answer"]

        # Получаем тему через менеджера
        theme = manager.execute(question_text)

        # Вытаскиваем контекст
        context_list_nested = rag.vectorize_and_search(theme)
        context_list = [item for sublist in context_list_nested for item in sublist]

        # Ограничиваем контекст
        context_text = "\n".join(context_list)
        if len(context_text) > max_context_chars:
            context_text = context_text[:max_context_chars] + "\n...[truncated]"

        # Получаем ответы только от teacher
        teacher_output = teacher.execute(question_text, context=context_text)

        dataset_list.append({
            "user_input": question_text,
            "retrieved_contexts": context_list,
            "response": teacher_output,
            "reference": reference_answer,
        })

# Проходим по уровню для coder
for level in questions_data["coder"]:
    # Берём первые N вопросов уровня
    for q in questions_data["coder"][level][:N]:
        question_text = q["question"]
        reference_answer = q["answer"]

        theme = manager.execute(question_text)

        context_list_nested = rag.vectorize_and_search(theme)
        context_list = [item for sublist in context_list_nested for item in sublist]

        context_text = "\n".join(context_list)
        if len(context_text) > max_context_chars:
            context_text = context_text[:max_context_chars] + "\n...[truncated]"

        coder_output = coder.execute(question_text, context=context_text)

        dataset_list.append({
            "user_input": question_text,
            "retrieved_contexts": context_list,
            "response": coder_output,
            "reference": reference_answer,
        })


# ---------------- Инициализация LLM для Ragas Eval ----------------
eval_llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.3,
    max_tokens=2000
)
evaluator_llm = LangchainLLMWrapper(eval_llm)

# ---------------- Создаём EvaluationDataset ----------------
evaluation_dataset = EvaluationDataset.from_list(dataset_list)

# ---------------- Запускаем оценку ----------------
results = evaluate(
    dataset=evaluation_dataset,
    metrics=[LLMContextRecall(), Faithfulness(), FactualCorrectness()],
    llm=evaluator_llm,
)

# ---------------- Выводим результат ----------------
print("RAG Eval Result (первые 2 вопроса):")

# Для новых версий Ragas
if hasattr(results, "to_dict"):
    metrics_dict = results.to_dict()
    for metric_name, metric_value in metrics_dict.items():
        print(f"{metric_name}: {metric_value}")
else:
    # fallback: просто печатаем весь объект
    print(results)
