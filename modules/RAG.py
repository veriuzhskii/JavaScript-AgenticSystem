from typing import Any, Dict, List, Optional

import chromadb
import pandas as pd
import torch
import torch.nn.functional as F
from chonkie import RecursiveChunker

from torch import Tensor
from transformers import AutoModel, AutoTokenizer

def get_device() -> str:
    """Запуск на видеокарте для ускорения вычислений"""
    return "cuda" if torch.cuda.is_available() else "cpu"


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
        """Читает CSV, возвращает список dict с ключами 'id' и 'text'."""
        df = pd.read_csv(self.data_file)

        if "text" not in df.columns:
            raise ValueError("В CSV-файле отсутствует колонка 'text'")

        df = df.dropna(subset=["text"])
        texts = df["text"].astype(str).tolist()

        dataset = [{"id": i, "text": text} for i, text in enumerate(texts)]
        print(f"[RAG] len(dataset) = {len(dataset)}")
        return dataset

    def chunk_dataset(self) -> List[Dict[str, Any]]:
        """Делит датасет на чанки"""
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
        """Усредняет эмбеддинги токенов с учётом attention_mask."""
        last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
        return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

    def get_embeddings(self, chunks: List[Dict[str, Any]]) -> Tensor:
        """Создаёт нормализованные эмбеддинги для списка чанков."""
        input_texts = [f"passage: {c['text']}" for c in chunks]
        print(f"[RAG] embedding {len(input_texts)} passages, batch_size={self.embed_batch_size}")

        all_embs: List[Tensor] = []

        #градиенты не считаем для скорости
        with torch.no_grad():
            for i in range(0, len(input_texts), self.embed_batch_size):
                batch_texts = input_texts[i: i + self.embed_batch_size]

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
        """Добавляет чанки и их эмбеддинги в ChromaDB батчами."""
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
        """Векторизует запрос и возвращает n_results ближайших документов."""
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
        """Склеивает список документов через разделитель '---'."""
        if not docs:
            return ""
        return "\n\n---\n\n".join(docs)