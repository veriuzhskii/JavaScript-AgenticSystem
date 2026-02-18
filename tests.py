import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import torch
import torch.nn.functional as F
from torch import Tensor
import pandas as pd
import chromadb
from transformers import AutoTokenizer, AutoModel
from chonkie import RecursiveChunker
from langchain_groq import ChatGroq
from deepeval.test_case import LLMTestCase
from deepeval.models import DeepEvalBaseLLM
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    AnswerRelevancyMetric,
    FaithfulnessMetric
)
from dotenv import load_dotenv
import sys
import json

# -----------------------------
# Utils
# -----------------------------


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def ensure_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY ERROR: переменная окружения GROQ_API_KEY не найдена.")
    return api_key

# -----------------------------
# RAG
# -----------------------------
class RAG:
    def __init__(
        self,
        data_file: str = "./mdn_web_javascript-7.csv",
        chunk_size: int = 500,
        max_length: int = 256,
        persist_directory: str = "./chroma_data",
        embed_model_name: str = "intfloat/multilingual-e5-small",
        # batching
        embed_batch_size: int = 64,
        # сколько документов реально индексировать (чтобы быстро тестировать)
        max_chunks_to_index: Optional[int] = 12896,
    ):
        self.data_file = data_file
        self.chunk_size = chunk_size
        self.max_length = max_length
        self.persist_directory = persist_directory
        self.embed_model_name = embed_model_name
        self.embed_batch_size = embed_batch_size
        self.max_chunks_to_index = max_chunks_to_index

        self.device = get_device()
        print(f"[RAG] device = {self.device}")

        self.dataset = self.get_data()
        self.chunks = self.chunk_dataset()

        # ограничим количество чанков для индекса (если задано)
        if self.max_chunks_to_index is not None:
            self.chunks = self.chunks[: self.max_chunks_to_index]

        self.tokenizer = AutoTokenizer.from_pretrained(self.embed_model_name)
        self.embedding_model = AutoModel.from_pretrained(self.embed_model_name).to(self.device)
        self.embedding_model.eval()

        # Chroma persistent
        self.vector_db = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.vector_db.get_or_create_collection(
            name="js_collection",
            configuration={
                "hnsw": {
                    "space": "cosine",
                    "batch_size": 4
                }
            },
        )

        # Если коллекция пустая — считаем эмбеддинги и добавляем
        if self.collection.count() == 0:
            print("[RAG] Chroma collection is empty -> building embeddings and indexing...")
            self.embeddings = self.get_embeddings(self.chunks)
            self.add_documents_to_db(self.chunks, self.embeddings)
        else:
            print(f"[RAG] Chroma collection already has {self.collection.count()} docs -> skip indexing.")

    def get_data(self) -> List[Dict[str, Any]]:
        df = pd.read_csv(self.data_file)
        texts = df["text"].tolist()

        dataset = [{"id": i, "text": text} for i, text in enumerate(texts)]
        print(f"[RAG] len(dataset) = {len(dataset)}")
        return dataset

    def chunk_dataset(self) -> List[Dict[str, Any]]:
        chunker = RecursiveChunker(chunk_size=self.chunk_size)
        chunks: List[Dict[str, Any]] = []

        global_chunk_id = 0
        for doc in self.dataset:
            doc_chunks = chunker(doc["text"])
            for chunk in doc_chunks:
                chunks.append(
                    {
                        "id": f"chunk_{global_chunk_id}",
                        "original_doc_id": doc["id"],
                        "text": chunk.text,
                        "size_tokens": chunk.token_count,
                    }
                )
                global_chunk_id += 1

        print(f"[RAG] len(chunks) = {len(chunks)}")
        return chunks

    # усредняющий пулинг
    @staticmethod
    def average_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
        return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

    def get_embeddings(self, chunks: List[Dict[str, Any]]) -> Tensor:
        # E5: "passage:" для документов
        input_texts = [f"passage: {c['text']}" for c in chunks]
        print(f"[RAG] embedding {len(input_texts)} passages, batch_size={self.embed_batch_size}")

        all_embs: List[Tensor] = []

        with torch.no_grad():
            for i in range(0, len(input_texts), self.embed_batch_size):
                batch_texts = input_texts[i : i + self.embed_batch_size]

                batch_dict = self.tokenizer(
                    batch_texts,
                    max_length=self.max_length,
                    padding=True,
                    truncation=True,
                    return_tensors="pt",
                )
                batch_dict = {k: v.to(self.device) for k, v in batch_dict.items()}

                outputs = self.embedding_model(**batch_dict)
                emb = self.average_pool(outputs.last_hidden_state, batch_dict["attention_mask"])
                emb = F.normalize(emb, p=2, dim=1)

                # складываем на CPU, чтобы не забивать VRAM
                all_embs.append(emb.detach().cpu())

        embeddings = torch.cat(all_embs, dim=0)
        print(f"[RAG] embeddings shape = {tuple(embeddings.shape)} (stored on CPU)")
        return embeddings

    def add_documents_to_db(self, chunks: List[Dict[str, Any]], embeddings: Tensor) -> None:
        embeddings_np = embeddings.numpy()  # Chroma требует numpy
        documents = [c["text"] for c in chunks]
        ids = [str(i) for i in range(len(documents))]  # простые ids 0..N-1

        # (опционально) можно добавить метаданные
        metadatas = [{"original_doc_id": c["original_doc_id"], "chunk_id": c["id"]} for c in chunks]

        self.collection.add(
            documents=documents,
            embeddings=embeddings_np,
            ids=ids,
            metadatas=metadatas,
        )
        print(f"[RAG] Indexed {len(documents)} docs into Chroma")

    def vectorize_and_search(self, query: str, n_results: int = 3) -> List[str]:
        # E5: "query:" для запросов
        input_texts = [f"query: {query}"]

        batch_dict = self.tokenizer(
            input_texts,
            max_length=self.max_length,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        batch_dict = {k: v.to(self.device) for k, v in batch_dict.items()}

        with torch.no_grad():
            outputs = self.embedding_model(**batch_dict)
            q_emb = self.average_pool(outputs.last_hidden_state, batch_dict["attention_mask"])
            q_emb = F.normalize(q_emb, p=2, dim=1)

        results = self.collection.query(
            query_embeddings=q_emb.detach().cpu().numpy(),
            include=["documents", "metadatas"],
            n_results=n_results,
        )

        # results["documents"] имеет форму [[doc1, doc2, doc3]] для одного запроса
        docs = results["documents"][0]
        return docs

    @staticmethod
    def format_context(docs: List[str]) -> str:
        # делаем читаемый “эталон”
        return "\n\n---\n\n".join(docs)

# -----------------------------
# Agent
# -----------------------------
class Agent:
    def __init__(self, name: str, instruction: str, api_key: str, model: str, temperature: float = 0.7):
        self.name = name
        self.instruction = instruction
        self.model = model
        self.llm = ChatGroq(
            temperature=temperature,
            model_name=model,
            groq_api_key=api_key,
            max_tokens=1000,
        )

    def execute(self, query: str, context: str = "") -> str:
        prompt = f"""
ROLE: Ты {self.name}.
ИНСТРУКЦИЯ: {self.instruction}

ЗАПРОС УЧЕНИКА:
{query}

КОНТЕКСТ (эталон/подсказки из базы):
{context}

Требования:
1) Отвечай на русском языке
2) Будь информативным и точным
3) Используй Markdown для форматирования
4) Если контекст не подходит к вопросу — скажи об этом и ответь по общим знаниям JavaScript.

Ответ:
""".strip()

        response = self.llm.invoke(prompt)
        return response.content
    


# -----------------------------
# Main
# -----------------------------
def main():
# -----------------------------
# Testing with Deepeval
# -----------------------------
    def deepeval_testing(test_file):
        """Пары вопрос-ответ берутся из файла"""
        with open (test_file, "r", encoding="utf-8") as c:
            cases = json.load(c)
        qa_pairs = []

        for level, questions_list in cases.items():
                print(f"Processing level: {level}")
                for question_dict in questions_list:
                    question = question_dict.get("question", "No question provided")
                    answer = question_dict.get("answer", "No answer provided")
                    qa_pairs.append((question, answer))
        return qa_pairs
    
    qa_pairs = deepeval_testing("short_test_cases.txt")
    print(len(qa_pairs))
    print(qa_pairs[2])

    api_key = ensure_api_key()

    # Инициализируем RAG (эмбеддинги пойдут на GPU, если есть CUDA)
    rag = RAG(
        data_file="./mdn_web_javascript-7.csv",
        chunk_size=500,
        max_length=256,
        persist_directory="./chroma_data",
        embed_model_name="intfloat/multilingual-e5-small",
        embed_batch_size=64,
        max_chunks_to_index=12896,
    )
    for query, expected_output in qa_pairs:
        query=query

        # Агент-менеджер определяет тему (можно, но не обязательно)
        manager = Agent(
            "Менеджер",
            "Определи, к какой теме JavaScript относится запрос. Верни только короткое название темы, без пояснений.",
            api_key,
            model="groq/compound-mini",
            temperature=0.2,
        )
        theme = manager.execute(query)
        print(f"\n[theme] {theme}\n")

        # Достаём контекст
        docs = rag.vectorize_and_search(theme, n_results=3)
        context_text = rag.format_context(docs)
        #print(f"docs: {docs}")

        # print("[final context docs]")
        # for i, d in enumerate(docs, 1):
        #     print(f"\n--- DOC {i} ---\n{d[:800]}{'...' if len(d) > 800 else ''}")

        # Учитель: объяснение
        teacher = Agent(
            "учитель",
            "Проанализируй запрос ученика и объясни, почему так происходит. НЕ исправляй код. Объясняй простыми словами.",
            api_key,
            model="openai/gpt-oss-20b",
            temperature=0.4,
        )
        teacher_output = teacher.execute(query, context_text)
        print(f"\n[teacher]\n{teacher_output}\n")
        test_case = LLMTestCase(
                input=query,
                actual_output=teacher_output,
                expected_output= expected_output,
                retrieval_context=docs
            )

        # Программист: минимально исправить (по сути тут “исправление” — убрать обращение к i вне блока или поменять на var)
        coder = Agent(
            "Программист",
            "Найди код в запросе и минимально исправь его так, чтобы он работал без ошибки. Верни ТОЛЬКО исправленный код, без текста.",
            api_key,
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.2,
        )
        code = coder.execute(query, context_text)
        #print(f"\n[coder]\n{code}\n")

        # Редактор: проверка согласованности
        validator = Agent(
            "Редактор",
            "Проверь, нет ли фактических ошибок и соотносится ли объяснение с кодом. "
            "Если нет — отредактируй объяснение и код. Верни в формате:\n"
            "EXPLANATION:\n...\n\nCODE:\n```javascript\n...\n```",
            api_key,
            model="llama-3.3-70b-versatile",
            temperature=0.2,
        )
        result = validator.execute(
            query,
            context=f"EXPLANATION DRAFT:\n{teacher_output}\n\nCODE DRAFT:\n{code}\n\nREFERENCE CONTEXT:\n{context_text}",
        )
        #print(f"\n[validator]\n{result}\n")

#         answers = {
#             "explanation": teacher_output,
#             "code": code,
#             "validated": result,
#         }
#         print("[answers dict ready]")

#  ---------------------------------
#  EVALUATION
# ---------------------------------
        class Evalmodel(DeepEvalBaseLLM):
            '''Create Custom Evaluation LLM'''
            def __init__(self):
                self.model = ChatGroq(
                temperature=0.2,
                model_name='groq/compound-mini',
                groq_api_key=api_key,
                max_tokens=1000,
            )
                
            def load_model(self):
                return self.model

            def generate(self, prompt: str) -> str:
                model = self.load_model()
                evaluation = model.invoke(prompt)
                return evaluation.content 
            
            async def a_generate(self, prompt: str) -> str:
                return self.generate(prompt)
            

            def get_model_name(self):
                return self.model.model_name
            
        custom_llm = Evalmodel()
        # retrieval metrics 
        contextual_precision = ContextualPrecisionMetric(model=custom_llm, async_mode=False )
        contextual_recall = ContextualRecallMetric(model=custom_llm, async_mode=False )
        contextual_relevancy = ContextualRelevancyMetric(model=custom_llm, async_mode=False )
        # generation metrics
        answer_relevancy = AnswerRelevancyMetric(model=custom_llm, async_mode=False )
        faithfulness = FaithfulnessMetric(model=custom_llm, async_mode=False )


        # logging
        with open("deepeval.log", "a", encoding='utf-8') as f:
            sys.stdout = f
            contextual_precision.measure(test_case)
            print("Contextual Precision Score: ", contextual_precision.score)
            print("Contextual Precision Reason: ", contextual_precision.reason)
            contextual_recall.measure(test_case)
            print("Contextual Recall Score: ", contextual_recall.score)
            print("Contextual Recall Reason: ", contextual_recall.reason)
            contextual_relevancy.measure(test_case)
            print("Contextual Relevancy Score: ", contextual_relevancy.score)
            print("Contextual Relevancy Reason: ", contextual_relevancy.reason)
            answer_relevancy.measure(test_case)
            print("Answer Relevancy Score: ", answer_relevancy.score)
            print("Answer Relevancy Reason: ", answer_relevancy.reason)
            faithfulness.measure(test_case)
            print("Faithfullness Score: ", faithfulness.score)
            print("Faithfullness Reason: ", faithfulness.reason)
            # возвращаем stdout обратно
        sys.stdout = sys.__stdout__

if __name__ == "__main__":
    main()