# venv: chromenv

import os
import torch
import torch.nn.functional as F
import pandas as pd
import chromadb

from torch import Tensor
from transformers import AutoTokenizer, AutoModel
from chonkie import RecursiveChunker
from langchain_groq import ChatGroq
from dotenv import load_dotenv

# --------------------------------------------------
# DEVICE (macOS / Apple Silicon)
# --------------------------------------------------

device = "mps" if torch.backends.mps.is_available() else "cpu"
print("Using device:", device)

torch.set_grad_enabled(False)

# --------------------------------------------------
# ENV
# --------------------------------------------------

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY ERROR")

query = """Почему мой цикл for не работает, если я использую let вместо var?
or (let i = 0; i < 5; i++) {
  console.log(i);
}
console.log(i); // ReferenceError: i is not defined
"""

# --------------------------------------------------
# RAG
# --------------------------------------------------

class RAG:
    def __init__(
        self,
        data_file: str = "./mdn_web_javascript-7.csv",
        chunk_size: int = 500,
        max_length: int = 256,
        persist_directory: str = "./chroma_data",
    ):
        self.data_file = data_file
        self.chunk_size = chunk_size
        self.max_length = max_length
        self.persist_directory = persist_directory

        self.dataset = self.get_data()
        self.chunks = self.chunk_dataset()

        self.tokenizer = AutoTokenizer.from_pretrained(
            "intfloat/multilingual-e5-small"
        )

        self.embedding_model = AutoModel.from_pretrained(
            "intfloat/multilingual-e5-small"
        ).to(device)

        self.embedding_model.eval()

        self.embeddings = self.get_embeddings()

        self.vector_db = chromadb.PersistentClient(
            path=self.persist_directory
        )

        self.collection = self.vector_db.get_or_create_collection(
            name="js_collection",
            configuration={
                "hnsw": {
                    "space": "cosine",
                    "batch_size": 4,
                }
            },
        )

        if self.collection.count() == 0:
            self.add_documents_to_db()

    # --------------------------------------------------

    def get_data(self) -> list[dict]:
        df = pd.read_csv(self.data_file)
        dataset = []

        for i, text in enumerate(df["text"]):
            dataset.append({
                "id": i,
                "text": text,
            })

        print(f"len(dataset): {len(dataset)}")
        return dataset

    # --------------------------------------------------

    def chunk_dataset(self):
        chunker = RecursiveChunker(chunk_size=self.chunk_size)
        chunks = []
        chunk_id = 0

        for doc in self.dataset:
            doc_chunks = chunker(doc["text"])

            for chunk in doc_chunks:
                chunks.append({
                    "id": f"chunk_{chunk_id}",
                    "original_doc_id": doc["id"],
                    "text": chunk.text,
                    "size_tokens": chunk.token_count,
                })
                chunk_id += 1

        return chunks

    # --------------------------------------------------

    def average_pool(
        self,
        last_hidden_states: Tensor,
        attention_mask: Tensor,
    ) -> Tensor:
        masked = last_hidden_states.masked_fill(
            ~attention_mask[..., None].bool(), 0.0
        )
        return masked.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

    # --------------------------------------------------

    def get_embeddings(self):
        input_texts = [
            "passage: " + chunk["text"]
            for chunk in self.chunks
        ][:7000]

        print(f"len(input_texts): {len(input_texts)}")

        BATCH_SIZE = 8
        all_embeddings = []

        for i in range(0, len(input_texts), BATCH_SIZE):
            batch_texts = input_texts[i:i + BATCH_SIZE]

            batch = self.tokenizer(
                batch_texts,
                max_length=self.max_length,
                padding=True,
                truncation=True,
                return_tensors="pt",
            )

            batch = {k: v.to(device) for k, v in batch.items()}

            with torch.no_grad():
                outputs = self.embedding_model(**batch)

            emb = self.average_pool(
                outputs.last_hidden_state,
                batch["attention_mask"],
            )

            emb = F.normalize(emb, p=2, dim=1)
            all_embeddings.append(emb.cpu())

            del outputs
            del batch

        embeddings = torch.cat(all_embeddings, dim=0)
        return embeddings

    # --------------------------------------------------

    def add_documents_to_db(self):
        documents = [c["text"] for c in self.chunks[:7000]]
        ids = [c["id"] for c in self.chunks[:7000]]
        embeddings_np = self.embeddings.numpy()

        self.collection.add(
            documents=documents,
            embeddings=embeddings_np,
            ids=ids,
        )

        print(f"Stored embeddings: {len(embeddings_np)}")

    # --------------------------------------------------

    def vectorize_and_search(self, query: str):
        batch = self.tokenizer(
            [f"query: {query}"],
            max_length=self.max_length,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )

        batch = {k: v.to(device) for k, v in batch.items()}

        with torch.no_grad():
            outputs = self.embedding_model(**batch)

        query_emb = self.average_pool(
            outputs.last_hidden_state,
            batch["attention_mask"],
        )

        query_emb = F.normalize(query_emb, p=2, dim=1)

        results = self.collection.query(
            query_embeddings=query_emb.cpu().numpy(),
            include=["documents"],
            n_results=3,
        )

        return results["documents"]

# --------------------------------------------------
# AGENT
# --------------------------------------------------

class Agent:
    def __init__(self, name, instruction, api_key, model):
        self.name = name
        self.instruction = instruction
        self.llm = ChatGroq(
            temperature=0.7,
            model_name=model,
            groq_api_key=api_key,
            max_tokens=1000,
        )

    def execute(self, query, context=""):
        prompt = f"""
ROLE: Ты {self.name}, {self.instruction}

Требования:
1. Отвечай на русском языке
2. Будь информативным и точным
3. Используй маркдаун

Контекст:
{context}

Ответ:
"""
        response = self.llm.invoke(prompt)
        return response.content

# --------------------------------------------------
# PIPELINE
# --------------------------------------------------

rag = RAG()

manager = Agent(
    "менеджер",
    f"определи тему javascript для запроса: {query}. Верни только тему",
    api_key,
    model="groq/compound-mini",
)

theme = manager.execute(query)
print("theme:", theme)

context = rag.vectorize_and_search(theme)
print("context:", context)

teacher = Agent(
    "учитель",
    f"объясни запрос ученика: {query}",
    api_key,
    model="openai/gpt-oss-20b",
)

teacher_output = teacher.execute(query, context)
print("teacher:", teacher_output)

coder = Agent(
    "программист",
    f"исправь код из запроса: {query}. Верни только код",
    api_key,
    model="meta-llama/llama-4-scout-17b-16e-instruct",
)

code = coder.execute(query, context)
print("coder:", code)

validator = Agent(
    "редактор",
    "проверь согласованность объяснения и кода",
    api_key,
    model="llama-3.3-70b-versatile",
)

result = validator.execute(query, f"{teacher_output}\n{code}")
print("validator:", result)