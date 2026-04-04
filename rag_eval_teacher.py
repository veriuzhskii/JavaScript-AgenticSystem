# rag_eval_teacher.py
import json
import os
from dotenv import load_dotenv

from ragas import evaluate, EvaluationDataset
from ragas.metrics import Faithfulness, LLMContextRecall, FactualCorrectness
from ragas.llms import LangchainLLMWrapper
from langchain_groq import ChatGroq

from agentic import RAG, Agent, ensure_api_key

# ---------------- ENV ----------------
load_dotenv()
api_key = ensure_api_key()

# ---------------- LOAD DATA ----------------
with open("teacher_dataset.json", "r", encoding="utf-8") as f:
    teacher_data = json.load(f)["teacher"]

# ---------------- INIT ----------------
rag = RAG(
    data_file="./mdn_web_javascript-7.csv",
    chunk_size=500,
    max_length=256,
    persist_directory="./chroma_data",
    embed_batch_size=64,
)

#manager = Agent(
    #"Менеджер",
        #"Определи, к какой теме JavaScript относится запрос. Верни только короткое название темы, без пояснений.",
    #api_key,
    #model="groq/compound-mini",
    #temperature=0.2,
#)

teacher = Agent(
     "учитель",
        "Проанализируй запрос ученика и объясни, почему так происходит. НЕ исправляй код. Объясняй простыми словами.",
    api_key,
    model="openai/gpt-oss-20b",
    temperature=0.4,
)

eval_llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
)
evaluator_llm = LangchainLLMWrapper(eval_llm)

# ---------------- BUILD DATASET ----------------
dataset_list = []
MAX_CONTEXT_CHARS = 2000
N = 2  # по одному вопросу с каждого уровня

for level in teacher_data:
    for q in teacher_data[level][:N]:
        question = q["question"]
        reference = q["answer"]

        # Получаем тему через менеджера (можно для RAG retrieval)
        #theme = manager.execute(question)

        # Получаем контекст из RAG
        context_docs = rag.vectorize_and_search(question, n_results=3)
        contexts = [d for d in context_docs]  # просто список текстов
        context_text = "\n".join(contexts)[:MAX_CONTEXT_CHARS]

        # Получаем ответ учителя
        teacher_output = teacher.execute(question, context=context_text)

        print("=" * 80)
        print(f"[Level: {level}]")
        print(f"Question:\n{question}\n")

        #print("Retrieved Contexts:")
        #for i, ctx in enumerate(contexts, 1):
            #print(f"\n--- Context {i} ---")
            #print(ctx[:500])  # чтобы не заспамить терминал

        print("\nTeacher Output:")
        print(teacher_output)
        print("=" * 80 + "\n")


        # Добавляем в датасет для оценки
        dataset_list.append({
            "user_input": question,
            "retrieved_contexts": contexts,
            "response": teacher_output,
            "reference": reference,
        })

# ---------------- EVAL ----------------
dataset = EvaluationDataset.from_list(dataset_list)

results = evaluate(
    dataset=dataset,
    metrics=[
        #Faithfulness(),
        LLMContextRecall(),
        #FactualCorrectness(),
    ],
    llm=evaluator_llm,
    
)

print("\nTEACHER RAG EVAL RESULT:")
print(results)