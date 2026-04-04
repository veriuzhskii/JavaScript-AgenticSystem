# evaluate_ragas_multiple_agents.py

from langchain_groq import ChatGroq

import os
import json
from typing import List, Dict

from dotenv import load_dotenv
from datasets import Dataset

from ragas import evaluate
from ragas.metrics.collections.context_precision import ContextPrecision
from ragas.metrics.collections.context_recall import ContextRecall
from ragas.metrics.collections.faithfulness import Faithfulness
from ragas.metrics.collections.answer_relevancy import AnswerRelevancy
from ragas.llms import llm_factory


# импорт твоих классов
from agents import RAG, Agent


# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY not found")

ragas_llm = llm_factory("gpt-4o-mini")


# --------------------------------------------------
# INIT RAG + AGENTS
# --------------------------------------------------
rag = RAG()

manager = Agent(
    name="менеджер",
    instruction=(
        "Определи, к какой теме в области JavaScript относится запрос. "
        "Верни только название темы, без пояснений."
    ),
    api_key=api_key,
    model="groq/compound-mini",
)

teacher = Agent(
    name="учитель",
    instruction=(
        "Проанализируй запрос ученика и ответь на вопрос, "
        "объясни так, чтобы ученик понял. "
        "Используй предоставленный контекст."
    ),
    api_key=api_key,
    model="openai/gpt-oss-20b",
)


# --------------------------------------------------
# LOAD QUESTIONS
# --------------------------------------------------
def load_questions(path: str, role: str, level: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data[role][level]


# --------------------------------------------------
# SINGLE SAMPLE PIPELINE
# --------------------------------------------------
def run_single_sample(sample: Dict) -> Dict:
    question = sample["question"]

    # 1. тема
    theme = manager.execute(question)

    # 2. контекст
    contexts = rag.vectorize_and_search(theme)[0]  # list[str]

    # 3. ответ
    answer = teacher.execute(question, context=contexts)

    return {
        "question": question,
        "answer": answer,
        "contexts": contexts,
    }


# --------------------------------------------------
# EVALUATE JSON WITH RAGAS
# --------------------------------------------------
def evaluate_json(
    json_path: str,
    role: str = "teacher",
    level: str = "beginner",
    limit: int | None = None,
):
    samples = load_questions(json_path, role, level)
    if limit:
        samples = samples[:limit]

    questions = []
    answers = []
    contexts = []

    for i, sample in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] processing...")

        result = run_single_sample(sample)

        questions.append(result["question"])
        answers.append(result["answer"])
        contexts.append(result["contexts"])

    dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
        }
    )

    metrics = evaluate(
        dataset,
        metrics=[
            ContextPrecision(llm=ragas_llm),
            ContextRecall(llm=ragas_llm),
            Faithfulness(llm=ragas_llm),
            AnswerRelevancy(llm=ragas_llm),
    ],
)

    return metrics


# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    results = evaluate_json(
        json_path="./questions.json",
        role="teacher",
        level="beginner",
        limit=1,  # сначала небольшая выборка
    )

    print("\nRAGAS RESULTS:")
    print(results)