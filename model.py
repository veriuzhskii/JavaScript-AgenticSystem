<<<<<<< HEAD
import os

from typing import Any, Dict, List, Optional

from chonkie import RecursiveChunker
import chromadb
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import pandas as pd
import torch
from torch import Tensor
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
=======
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

>>>>>>> 45c438a4eb640a159f22615895478e85747de630

# -----------------------------
# Utils
# -----------------------------
<<<<<<< HEAD
=======
CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
>>>>>>> 45c438a4eb640a159f22615895478e85747de630


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def ensure_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY ERROR: переменная окружения GROQ_API_KEY не найдена.")
    return api_key

<<<<<<< HEAD
=======

def safe_json_loads(raw_text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    text = raw_text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except Exception:
        return fallback


def contains_cyrillic(text: str) -> bool:
    return bool(CYRILLIC_PATTERN.search(text or ""))


def code_has_cyrillic_identifiers(code: str) -> bool:
    if not code:
        return False
    return contains_cyrillic(code)


def build_title_fallback(message: str, max_words: int = 6, max_len: int = 60) -> str:
    text = re.sub(r"```.*?```", " ", message or "", flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[{}[\];=<>`]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "Новый чат"

    words = text.split()
    short = " ".join(words[:max_words]).strip()

    if len(short) > max_len:
        short = short[:max_len].rsplit(" ", 1)[0].strip()

    if not short:
        return "Новый чат"

    return short[:1].upper() + short[1:]


>>>>>>> 45c438a4eb640a159f22615895478e85747de630
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
<<<<<<< HEAD
        embed_model_name: str = "intfloat/multilingual-e5-small",
        # batching
        embed_batch_size: int = 64,
        # сколько документов реально индексировать (чтобы быстро тестировать)
=======
        collection_name: str = "js_collection",
        embed_model_name: str = "intfloat/multilingual-e5-small",
        embed_batch_size: int = 64,
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
        max_chunks_to_index: Optional[int] = 12896,
    ):
        self.data_file = data_file
        self.chunk_size = chunk_size
        self.max_length = max_length
        self.persist_directory = persist_directory
<<<<<<< HEAD
=======
        self.collection_name = collection_name
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
        self.embed_model_name = embed_model_name
        self.embed_batch_size = embed_batch_size
        self.max_chunks_to_index = max_chunks_to_index

        self.device = get_device()
        print(f"[RAG] device = {self.device}")

        self.dataset = self.get_data()
        self.chunks = self.chunk_dataset()

<<<<<<< HEAD
        # ограничим количество чанков для индекса (если задано)
=======
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
        if self.max_chunks_to_index is not None:
            self.chunks = self.chunks[: self.max_chunks_to_index]

        self.tokenizer = AutoTokenizer.from_pretrained(self.embed_model_name)
        self.embedding_model = AutoModel.from_pretrained(self.embed_model_name).to(self.device)
        self.embedding_model.eval()

<<<<<<< HEAD
        # сhroma persistent
        self.vector_db = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.vector_db.get_or_create_collection(
            name="js_collection",
            configuration={
                "hnsw": {
                    "space": "cosine",
                    "batch_size": 4
=======
        self.vector_db = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.vector_db.get_or_create_collection(
            name=self.collection_name,
            configuration={
                "hnsw": {
                    "space": "cosine",
                    "batch_size": 4,
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
                }
            },
        )

<<<<<<< HEAD
        # если коллекция пустая — считаем эмбеддинги и добавляем
        if self.collection.count() == 0:
            print("[RAG] Chroma collection is empty -> building embeddings and indexing...")
            self.embeddings = self.get_embeddings(self.chunks)
            self.add_documents_to_db(self.chunks, self.embeddings)
        else:
            print(f"[RAG] Chroma collection already has {self.collection.count()} docs -> skip indexing.")

    def get_data(self) -> List[Dict[str, Any]]:
        df = pd.read_csv(self.data_file)
        texts = df["text"].tolist()
=======
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
>>>>>>> 45c438a4eb640a159f22615895478e85747de630

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

<<<<<<< HEAD
    # усредняющий пулинг
=======
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
    @staticmethod
    def average_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
        return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

    def get_embeddings(self, chunks: List[Dict[str, Any]]) -> Tensor:
<<<<<<< HEAD
        # E5: "passage:" для документов
=======
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
        input_texts = [f"passage: {c['text']}" for c in chunks]
        print(f"[RAG] embedding {len(input_texts)} passages, batch_size={self.embed_batch_size}")

        all_embs: List[Tensor] = []

        with torch.no_grad():
            for i in range(0, len(input_texts), self.embed_batch_size):
<<<<<<< HEAD
                batch_texts = input_texts[i : i + self.embed_batch_size]
=======
                batch_texts = input_texts[i: i + self.embed_batch_size]
>>>>>>> 45c438a4eb640a159f22615895478e85747de630

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

<<<<<<< HEAD
                # складываем на CPU, чтобы не забивать VRAM
=======
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
                all_embs.append(emb.detach().cpu())

        embeddings = torch.cat(all_embs, dim=0)
        print(f"[RAG] embeddings shape = {tuple(embeddings.shape)} (stored on CPU)")
        return embeddings

    def add_documents_to_db(self, chunks: List[Dict[str, Any]], embeddings: Tensor) -> None:
<<<<<<< HEAD
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
=======
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
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
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
<<<<<<< HEAD
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

=======
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


>>>>>>> 45c438a4eb640a159f22615895478e85747de630
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
<<<<<<< HEAD
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
=======
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
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
        """.strip()

        response = self.llm.invoke(prompt)
        return response.content
<<<<<<< HEAD
# -----------------------------
# MultiAgent
# -----------------------------
class MultiAgentSystem():
    def __init__(self, api_key=None):
        """
        Инициализация системы с возможностью настройки моделей
        
        Args:
            api_key: ключ для API (если не указан, будет загружен из .env)
        """
        self.api_key = api_key or ensure_api_key()
        
        # конфигурация по умолчанию
        self.default_config = {
            "teacher": {"model": "llama-3.1-8b-instant", "temperature": 0.4},
            "coder": {"model": "meta-llama/llama-4-scout-17b-16e-instruct", "temperature": 0.2},
            "validator": {"model": "meta-llama/llama-4-maverick-17b-128e-instruct", "temperature": 0.2}
        }
         # Инициализируем RAG
        self.rag = RAG()
        
        # Агенты будут инициализированы по требованию
        self.agents = {}

    def _get_instruction(self, agent_name):
            """Возвращает инструкцию для агента по его имени"""
            instructions = {
                "teacher": "Проанализируй запрос ученика и объясни, почему так происходит. НЕ исправляй код. Объясняй простыми словами.",
                "coder": "Найди код в запросе и минимально исправь его так, чтобы он работал без ошибки. Верни ТОЛЬКО исправленный код, без текста.",
                "validator": "Проверь, нет ли фактических ошибок и соотносится ли объяснение с кодом. Если нет — отредактируй объяснение и код. Верни в формате:\nEXPLANATION:\n...\n\nCODE:\n```javascript\n...\n```"
            }
            return instructions.get(agent_name, "")
    
    def _get_agent(self, name):
        """Ленивая инициализация агентов"""
        instruction = self._get_instruction(name)
        self.agents[name] = Agent(
                name=name,
                instruction=instruction,
                api_key=self.api_key,
                model=self.default_config[f'{name}']["model"],
                temperature= self.default_config[f'{name}']["temperature"]
            )
        return self.agents[name]
    
    
    
    def process_query(self, query, history=None):
        """
        Основной метод для обработки запроса
        
        Args:
            query: Текстовый запрос пользователя
            history: История диалога (опционально)
        
        Returns:
            Словарь с результатами обработки
        """
        
        # 1. поиск релевантного контекста
        docs = self.rag.vectorize_and_search(query, n_results=3)
        context_text = self.rag.format_context(docs)
        
        # 2. учитель объясняет
        teacher = self._get_agent("teacher")
        teacher_output = teacher.execute(query, context_text)
        
        # 3. программист исправляет код
        coder = self._get_agent("coder")
        code = coder.execute(query, context_text)
        
        # 4. валидатор проверяет согласованность
        validator = self._get_agent("validator")
        result = validator.execute(
            query,
            context=f"EXPLANATION DRAFT:\n{teacher_output}\n\nCODE DRAFT:\n{code}\n\nREFERENCE CONTEXT:\n{context_text}",
        )
        # парсим результат валидатора
        explanation = ""
        code_result = ""
        
        if "EXPLANATION:" in result and "CODE:" in result:
            parts = result.split("CODE:")
            explanation = parts[0].replace("EXPLANATION:", "").strip()
            code_result = parts[1].strip()
        else:
            # если валидатор вернул неструктурированный ответ, используем его целиком как объяснение
            explanation = result
            code_result = code  # используем код от программиста
        
        return {
            "explanation": explanation,
            "code": code_result,
            "context": context_text
        }
    def ask_with_history(self, messages, last_user_message):
        """
        Метод для генерации сообщений. Задействован в app.py
        
        Args:
            messages: История сообщений в формате [{"role": "...", "content": "..."}, ...]
            last_user_message: Последнее сообщение пользователя
        
        Returns:
            Строка с ответом системы
        """
        # messages в качестве history
        result = self.process_query(last_user_message, messages)
        
        response = f"## Объяснение\n{result['explanation']}"
        if result['code']:
            response += f"\n\n## Исправленный код\n```javascript\n{result['code']}\n```"
        
        return response
    
def main():
    try:
        system = MultiAgentSystem()
        query = "В чём разница между изменяемыми (mutable) и неизменяемыми (immutable) значениями? Приведи примеры."
        result = system.ask_with_history(None, query)
=======


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
            "title_generator": {"model": "llama-3.1-8b-instant", "temperature": 0.2},
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
            "title_generator": (
                "Ты создаешь короткие названия чатов.\n"
                "На основе первого осмысленного сообщения пользователя придумай краткий заголовок чата.\n"
                "Заголовок должен кратко описывать тему чата.\n"
                "Правила:\n"
                "- верни только название без кавычек, без пояснений и без markdown;\n"
                "- от 2 до 6 слов;\n"
                "- естественная краткая формулировка;\n"
                "- можно на русском или английском, в зависимости от запроса пользователя;\n"
                "- не используй точку в конце;\n"
                "- не пиши 'Новый чат';\n"
                "- начинай название с заглавной буквы;\n"
                "- если запрос про код, кратко отрази задачу.\n"
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

    def generate_chat_title(self, first_user_message: str) -> str:
        cleaned_input = re.sub(r"\s+", " ", (first_user_message or "")).strip()
        if not cleaned_input:
            return "Новый чат"

        title_agent = self._get_agent("title_generator")
        raw_title = title_agent.execute(cleaned_input, "")
        title = raw_title.strip()

        title = re.sub(r"^```.*?\n?", "", title, flags=re.DOTALL)
        title = re.sub(r"```$", "", title).strip()
        title = title.replace('"', "").replace("'", "").strip()
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(r"[.!?]+$", "", title).strip()

        if not title or title.lower() == "новый чат":
            return build_title_fallback(cleaned_input)

        words = title.split()
        if len(words) > 6:
            title = " ".join(words[:6])

        if len(title) > 60:
            title = title[:60].rsplit(" ", 1)[0].strip()

        if not title:
            return build_title_fallback(cleaned_input)

        return title[:1].upper() + title[1:]

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

        if coder_output != "NO_CODE_FOUND" and code_has_cyrillic_identifiers(coder_output):
            retry_context = (
                f"{worker_context}\n\n"
                "Твой предыдущий ответ нарушил правило: в коде обнаружена кириллица. "
                "Сгенерируй код заново. Все идентификаторы должны быть только на английском языке."
            ).strip()
            coder = self._get_agent("coder")
            coder_output = coder.execute(query, retry_context)

        validator_input_parts = [
            f"USER QUERY:\n{query}",
            f"TEACHER OUTPUT:\n{teacher_output or ''}",
            f"CODER OUTPUT:\n{coder_output if coder_output != 'NO_CODE_FOUND' else ''}",
        ]

        if context_text:
            validator_input_parts.append(f"REFERENCE:\n{context_text}")

        validator_context = "\n\n".join(validator_input_parts).strip()

        validator = self._get_agent("validator")
        validator_output = validator.execute("Собери финальный ответ пользователю.", validator_context)
        validated = self._parse_validator_output(validator_output)

        final_text = validated["final_text"].strip()
        final_code = validated["final_code"].strip()

        if not final_text and teacher_output:
            final_text = teacher_output.strip()

        if not final_code and coder_output and coder_output != "NO_CODE_FOUND":
            final_code = coder_output.strip()

        if final_code and code_has_cyrillic_identifiers(final_code):
            final_code = ""

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
>>>>>>> 45c438a4eb640a159f22615895478e85747de630
        print(result)
        return result
    except Exception as e:
        print(f"Ошибка в main: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

<<<<<<< HEAD
=======

>>>>>>> 45c438a4eb640a159f22615895478e85747de630
if __name__ == "__main__":
    main()