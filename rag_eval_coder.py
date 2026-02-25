# rag_eval_coder.py
import json
from dotenv import load_dotenv

from ragas import evaluate, EvaluationDataset
from ragas.metrics import FactualCorrectness
from ragas.llms import LangchainLLMWrapper
from langchain_groq import ChatGroq

from agentic import RAG, Agent, ensure_api_key

# ---------------- ENV ----------------
load_dotenv()
api_key = ensure_api_key()

# ---------------- LOAD DATA ----------------
with open("coder_dataset.json", "r", encoding="utf-8") as f:
    coder_data = json.load(f)["coder"]

# ---------------- INIT ----------------
rag = RAG(
    data_file="./mdn_web_javascript-7.csv",
    chunk_size=500,
    max_length=256,
    persist_directory="./chroma_data",
    embed_batch_size=64,
)

coder = Agent(
    "Программист",
    "Найди код в запросе и минимально исправь его так, чтобы он работал без ошибки. "
    "Верни ТОЛЬКО исправленный код, без пояснений.",
    api_key,
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    temperature=0.2,
)

eval_llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
)
evaluator_llm = LangchainLLMWrapper(eval_llm)

# ---------------- BUILD DATASET ----------------
dataset_list = []
MAX_CONTEXT_CHARS = 2000
N = 10  # сколько примеров брать с каждого уровня

for level in coder_data:
    for q in coder_data[level][:N]:
        question = q["question"]
        reference_code = q["answer"]

        # --- RAG retrieval ---
        context_docs = rag.vectorize_and_search(question, n_results=3)
        contexts = [d for d in context_docs]
        context_text = "\n".join(contexts)[:MAX_CONTEXT_CHARS]

        # --- Coder answer ---
        coder_output = coder.execute(question, context=context_text)

        print("=" * 80)
        print(f"[Level: {level}]")
        print("Question:\n", question)
        print("\nCoder Output:\n", coder_output)
        print("\nReference:\n", reference_code)
        print("=" * 80 + "\n")

        dataset_list.append({
            "user_input": question,
            "retrieved_contexts": contexts,
            "response": coder_output,
            "reference": reference_code,
        })

# ---------------- EVAL ----------------
dataset = EvaluationDataset.from_list(dataset_list)

results = evaluate(
    dataset=dataset,
    metrics=[
        FactualCorrectness(mode="f1"),
    ],
    llm=evaluator_llm,
)

print("\nCODER RAG EVAL RESULT:")
print(results)