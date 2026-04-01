import json
import os
import re

from typing import Any, Dict, List, Optional

import chromadb
import pandas as pd
import torch
import torch.nn.functional as F
from chonkie import RecursiveChunker
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from torch import Tensor
from transformers import AutoModel, AutoTokenizer


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


def safe_json_loads(raw_text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    text = raw_text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except Exception:
        return fallback


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
        collection_name: str = "js_collection",
        embed_model_name: str = "intfloat/multilingual-e5-small",
        embed_batch_size: int = 64,
        max_chunks_to_index: Optional[int] = 12896,
    ):
        self.data_file = data_file
        self.chunk_size = chunk_size
        self.max_length = max_length
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embed_model_name = embed_model_name
        self.embed_batch_size = embed_batch_size
        self.max_chunks_to_index = max_chunks_to_index

        self.device = get_device()
        print(f"[RAG] device = {self.device}")

        self.dataset = self.get_data()
        self.chunks = self.chunk_dataset()

        if self.max_chunks_to_index is not None:
            self.chunks = self.chunks[: self.max_chunks_to_index]

        self.tokenizer = AutoTokenizer.from_pretrained(self.embed_model_name)
        self.embedding_model = AutoModel.from_pretrained(self.embed_model_name).to(self.device)
        self.embedding_model.eval()

        self.vector_db = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.vector_db.get_or_create_collection(
            name=self.collection_name,
            configuration={
                "hnsw": {
                    "space": "cosine",
                    "batch_size": 4,
                }
            },
        )

        collection_count = self.collection.count()
        current_chunks_count = len(self.chunks)

        if collection_count == 0:
            print("[RAG] Chroma collection is empty -> building embeddings and indexing...")
            embeddings = self.get_embeddings(self.chunks)
            self.add_documents_to_db(self.chunks, embeddings)
        else:
            print(
                f"[RAG] Chroma collection already has {collection_count} docs "
                f"(current chunks: {current_chunks_count}) -> skip indexing."
            )

    def get_data(self) -> List[Dict[str, Any]]:
        df = pd.read_csv(self.data_file)

        if "text" not in df.columns:
            raise ValueError("В CSV-файле отсутствует колонка 'text'")

        df = df.dropna(subset=["text"])
        texts = df["text"].astype(str).tolist()

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

    @staticmethod
    def average_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
        return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

    def get_embeddings(self, chunks: List[Dict[str, Any]]) -> Tensor:
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

                all_embs.append(emb.detach().cpu())

        embeddings = torch.cat(all_embs, dim=0)
        print(f"[RAG] embeddings shape = {tuple(embeddings.shape)} (stored on CPU)")
        return embeddings

    def add_documents_to_db(self, chunks: List[Dict[str, Any]], embeddings: Tensor) -> None:
        embeddings_np = embeddings.numpy()
        documents = [c["text"] for c in chunks]
        metadatas = [{"original_doc_id": c["original_doc_id"], "chunk_id": c["id"]} for c in chunks]

        max_batch = 5000
        total = len(documents)

        for start in range(0, total, max_batch):
            end = min(start + max_batch, total)

            batch_docs = documents[start:end]
            batch_embs = embeddings_np[start:end]
            batch_metas = metadatas[start:end]
            batch_ids = [str(i) for i in range(start, end)]

            self.collection.add(
                documents=batch_docs,
                embeddings=batch_embs,
                ids=batch_ids,
                metadatas=batch_metas,
            )

            print(f"[RAG] Indexed {end}/{total} docs into Chroma (batch {start}-{end})")

        print(f"[RAG] Indexed total {total} docs into Chroma")

    def vectorize_and_search(self, query: str, n_results: int = 3) -> List[str]:
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
            include=["documents", "distances"],
            n_results=n_results,
        )

        docs = results.get("documents", [])
        if not docs or not docs[0]:
            return []

        return docs[0]

    @staticmethod
    def format_context(docs: List[str]) -> str:
        if not docs:
            return ""
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
РОЛЬ: {self.name}

СИСТЕМНАЯ ИНСТРУКЦИЯ:
{self.instruction}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{query}

КОНТЕКСТ:
{context}

ТРЕБОВАНИЯ К ОТВЕТУ:
- Точно следуй инструкции.
- Не раскрывай внутренние роли, маршрутизацию, черновики, этапы валидации и служебные поля.
- Если инструкция требует JSON, верни только корректный JSON.

ОТВЕТ:
        """.strip()

        response = self.llm.invoke(prompt)
        return response.content


# -----------------------------
# MultiAgent
# -----------------------------
class MultiAgentSystem:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or ensure_api_key()

        self.default_config = {
            "manager": {"model": "llama-3.1-8b-instant", "temperature": 0.0},
            "teacher": {"model": "llama-3.1-8b-instant", "temperature": 0.3},
            "coder": {"model": "llama-3.1-8b-instant", "temperature": 0.1},
            "validator": {"model": "llama-3.1-8b-instant", "temperature": 0.1},
        }

        self.rag = RAG()
        self.agents: Dict[str, Agent] = {}

    def _get_instruction(self, agent_name: str) -> str:
        instructions = {
            "manager": (
                "Ты менеджер-роутер системы помощи по JavaScript.\n"
                "Твоя задача — определить тип запроса и выбрать маршрут обработки.\n"
                "Если вопрос общий, разговорный, приветственный, относится к возможностям системы, "
                "не касается обучения JavaScript или не требует работы teacher/coder, "
                "ты должен сам подготовить короткий финальный ответ пользователю.\n"
                "Если вопрос относится к обучению JavaScript, выбери подходящий маршрут.\n\n"
                "Верни только JSON строго по схеме:\n"
                "{\n"
                '  "route": "manager" | "teacher" | "coder" | "teacher_coder" | "unsupported",\n'
                '  "need_retrieval": true | false,\n'
                '  "reason": "краткая причина выбора маршрута",\n'
                '  "direct_response": "готовый ответ пользователю или пустая строка"\n'
                "}\n\n"
                "Правила маршрутизации:\n"
                "1) manager — общие вопросы о системе: кто ты, что ты умеешь, как работаешь, помощь по интерфейсу.\n"
                "2) teacher — теоретический вопрос по JavaScript без запроса на исправление кода.\n"
                "3) coder — запрос только на исправление/дописывание/рефакторинг кода без необходимости объяснения.\n"
                "4) teacher_coder — если нужно и объяснение, и исправление кода.\n"
                "5) unsupported — если вопрос не относится к JavaScript-обучению и не является вопросом о возможностях системы.\n"
                "6) Для manager и unsupported обязательно заполни direct_response.\n"
                "7) Для teacher/coder/teacher_coder direct_response должен быть пустой строкой.\n"
                "8) need_retrieval=true только если ответ выиграет от опоры на документацию JavaScript.\n"
                "9) Никогда не пиши служебные поля, пояснения вне JSON или markdown.\n\n"
                "Тон direct_response:\n"
                "- дружелюбный;\n"
                "- краткий;\n"
                "- без упоминания менеджера, валидатора, роутинга, контекста, черновиков, JSON;\n"
                "- без программных артефактов."
            ),
            "teacher": (
                "Ты преподаватель JavaScript.\n"
                "Дай понятное, естественное и полезное объяснение на русском языке.\n"
                "Если пользователь прислал код, можешь кратко объяснить, в чем проблема, но не исправляй код целиком.\n"
                "Не упоминай внутренние роли системы.\n"
                "Не пиши служебные заголовки вроде EXPLANATION, CONTEXT, ROUTE.\n"
                "Не вставляй [EMPTY], NO_CODE_FOUND и подобные маркеры.\n"
                "Если приводишь короткие примеры кода, используй только английские имена переменных, функций и параметров.\n"
                "Никогда не используй кириллицу в идентификаторах JavaScript, даже если запрос пользователя содержит русские названия переменных.\n"
                "Если контекст документации есть, опирайся на него. Если нет, отвечай по общим знаниям JavaScript."
            ),
            "coder": (
                "Ты ассистент по коду JavaScript.\n"
                "Если в запросе есть код, исправь его минимально необходимым образом.\n"
                "Если кода нет, верни только строку NO_CODE_FOUND.\n"
                "Верни только чистый код без пояснений, без markdown, без тройных кавычек, без заголовков.\n"
                "Все идентификаторы в коде должны быть только на английском языке: имена переменных, функций, параметров, классов и свойств, которые ты создаешь или переименовываешь.\n"
                "Никогда не используй кириллицу в идентификаторах JavaScript.\n"
                "Если во входном коде есть переменные, функции или параметры с русскими именами, обязательно переименуй их в естественные английские аналоги и сохрани логику кода.\n"
                "Используй понятные общепринятые английские названия, например: name, userName, totalPrice, isActive, items, result, count.\n"
                "Строковые значения, комментарии и пользовательский текст могут оставаться на русском, но идентификаторы — только на английском."
            ),
            "validator": (
                "Ты финальный редактор ответа.\n"
                "Твоя задача — проверить и аккуратно собрать финальный пользовательский ответ на основе explanation и code.\n"
                "Нельзя упоминать внутренние роли, валидацию, роутинг, контекст, черновики, служебные поля, JSON, [EMPTY], NO_CODE_FOUND.\n"
                "Нельзя представляться.\n"
                "Если explanation пустой, не выдумывай длинное объяснение.\n"
                "Если code пустой, не добавляй блок с кодом.\n"
                "Если есть и explanation, и code, explanation должен быть кратким, а код — отдельным полем.\n"
                "Проверь, что в final_code нет кириллицы в идентификаторах JavaScript. Если кириллица есть, исправь идентификаторы на естественные английские аналоги.\n"
                "Никогда не возвращай код с русскими именами переменных, функций, параметров или классов.\n"
                "Верни только JSON строго по схеме:\n"
                "{\n"
                '  "final_text": "готовый текст для пользователя",\n'
                '  "final_code": "чистый код без markdown или пустая строка"\n'
                "}"
            ),
        }
        return instructions.get(agent_name, "")

    def _get_agent(self, name: str) -> Agent:
        if name not in self.agents:
            if name not in self.default_config:
                raise ValueError(f"Неизвестная конфигурация агента: {name}")

            self.agents[name] = Agent(
                name=name,
                instruction=self._get_instruction(name),
                api_key=self.api_key,
                model=self.default_config[name]["model"],
                temperature=self.default_config[name]["temperature"],
            )
        return self.agents[name]

    def _format_history(self, history: Optional[List[Dict[str, str]]], max_messages: int = 6) -> str:
        if not history:
            return ""

        relevant = history[-max_messages:]
        lines = []

        for msg in relevant:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _parse_manager_output(self, raw_output: str) -> Dict[str, Any]:
        fallback = {
            "route": "manager",
            "need_retrieval": False,
            "reason": "fallback route",
            "direct_response": (
                "Я помогаю с изучением JavaScript: могу объяснять теорию, разбирать ошибки "
                "и помогать с исправлением кода. Задай вопрос по теме или пришли свой код."
            ),
        }

        data = safe_json_loads(raw_output, fallback)

        route = str(data.get("route", "manager")).strip()
        if route not in {"manager", "teacher", "coder", "teacher_coder", "unsupported"}:
            route = "manager"

        return {
            "route": route,
            "need_retrieval": bool(data.get("need_retrieval", False)),
            "reason": str(data.get("reason", "")).strip(),
            "direct_response": str(data.get("direct_response", "")).strip(),
        }

    def _parse_validator_output(self, raw_output: str) -> Dict[str, str]:
        fallback = {
            "final_text": "",
            "final_code": "",
        }

        data = safe_json_loads(raw_output, fallback)

        final_text = str(data.get("final_text", "")).strip()
        final_code = str(data.get("final_code", "")).strip()

        if final_code == "NO_CODE_FOUND":
            final_code = ""

        return {
            "final_text": final_text,
            "final_code": final_code,
        }

    def _should_use_rag(self, route: Dict[str, Any]) -> bool:
        return route["route"] in {"teacher", "coder", "teacher_coder"} and route["need_retrieval"]

    def process_query(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        history_text = self._format_history(history)

        manager_context = (
            f"HISTORY:\n{history_text}\n\n"
            "Система специализируется на помощи в изучении JavaScript: теория, объяснения, "
            "разбор ошибок, исправление кода."
        )

        manager = self._get_agent("manager")
        manager_output = manager.execute(query, manager_context)
        route = self._parse_manager_output(manager_output)

        if route["route"] in {"manager", "unsupported"}:
            direct_response = route["direct_response"].strip()

            if not direct_response:
                if route["route"] == "manager":
                    direct_response = (
                        "Я помогаю с изучением JavaScript: объясняю теорию, разбираю ошибки "
                        "и помогаю исправлять код. Можешь задать вопрос по теме или прислать фрагмент кода."
                    )
                else:
                    direct_response = (
                        "Я специализируюсь на вопросах по JavaScript и помощи в обучении. "
                        "Попробуй задать вопрос по JavaScript или пришли код, который нужно разобрать."
                    )

            return {
                "route": route,
                "explanation": direct_response,
                "code": "",
                "context": "",
                "manager_raw": manager_output,
                "teacher_raw": "",
                "coder_raw": "",
                "validator_raw": "",
            }

        docs: List[str] = []
        context_text = ""

        if self._should_use_rag(route):
            docs = self.rag.vectorize_and_search(query, n_results=3)
            context_text = self.rag.format_context(docs)

        teacher_output = ""
        coder_output = ""

        worker_context_parts = []
        if history_text:
            worker_context_parts.append(f"HISTORY:\n{history_text}")
        if context_text:
            worker_context_parts.append(f"REFERENCE:\n{context_text}")

        worker_context = "\n\n".join(worker_context_parts).strip()

        if route["route"] in {"teacher", "teacher_coder"}:
            teacher = self._get_agent("teacher")
            teacher_output = teacher.execute(query, worker_context)

        if route["route"] in {"coder", "teacher_coder"}:
            coder = self._get_agent("coder")
            coder_output = coder.execute(query, worker_context)

        validator_input_parts = [
            f"USER QUERY:\n{query}",
            f"TEACHER OUTPUT:\n{teacher_output or ''}",
            f"CODER OUTPUT:\n{coder_output if coder_output != 'NO_CODE_FOUND' else ''}",
        ]

        if context_text:
            validator_input_parts.append(f"REFERENCE:\n{context_text}")

        validator_context = "\n\n".join(validator_input_parts).strip()

        validator = self._get_agent("validator")
        validator_output = validator.execute(query, validator_context)
        validated = self._parse_validator_output(validator_output)

        final_text = validated["final_text"].strip()
        final_code = validated["final_code"].strip()

        if not final_text and teacher_output:
            final_text = teacher_output.strip()

        if not final_code and coder_output and coder_output != "NO_CODE_FOUND":
            final_code = coder_output.strip()

        return {
            "route": route,
            "explanation": final_text,
            "code": final_code,
            "context": context_text,
            "manager_raw": manager_output,
            "teacher_raw": teacher_output,
            "coder_raw": coder_output,
            "validator_raw": validator_output,
        }

    def ask_with_history(
        self,
        messages: Optional[List[Dict[str, str]]],
        last_user_message: str,
    ) -> str:
        result = self.process_query(last_user_message, messages)

        response_parts: List[str] = []

        explanation = result["explanation"].strip()
        code = result["code"].strip()

        if explanation:
            response_parts.append(explanation)

        if code:
            response_parts.append(f"```javascript\n{code}\n```")

        if not response_parts:
            return "Не удалось сформировать ответ."

        return "\n\n".join(response_parts)


def main():
    try:
        system = MultiAgentSystem()
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