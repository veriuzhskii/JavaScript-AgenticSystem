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

        # сhroma persistent
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
        print(result)
        return result
    except Exception as e:
        print(f"Ошибка в main: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()