# venv is chromenv
import torch.nn.functional as F
import chromadb
import pandas as pd
from torch import Tensor
import torch
from transformers import AutoTokenizer, AutoModel
#from transformers import pipeline
from chonkie import RecursiveChunker
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os
from datetime import datetime

# если хотите использовать gpu
#device = "cuda" if torch.cuda.is_available() else "cpu"

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY ERROR")

query =  """Почему мой цикл for не работает, если я использую let вместо var?  or (let i = 0; i < 5; i++) {  console.log(i);
}  console.log(i); // ReferenceError: i is not defined """

class RAG:
    def __init__(
        self,
        data_file = "./mdn_web_javascript-7.csv",
        chunk_size: int = 500,
        max_length: int = 256,
        llm_model: str = "openai/gpt-oss-20b",
        persist_directory: str = "./chroma_data"):

        self.data_file = data_file
        self.chunk_size = chunk_size
        self.max_length = max_length
        self.llm_model = llm_model
        self.dataset = self.get_data()
        self.chunks = self.chunk_dataset()

        self.tokenizer = AutoTokenizer.from_pretrained('intfloat/multilingual-e5-small')
        self.embedding_model = AutoModel.from_pretrained('intfloat/multilingual-e5-small')

        self.embeddings = self.get_embeddings()

        self.persist_directory = persist_directory

        self.vector_db = chromadb.PersistentClient(path=self.persist_directory)

        self.collection = self.vector_db.get_or_create_collection( # default is all-MiniLM-L6-v2
            name="js_collection",
            configuration={
                "hnsw": {
                    "space": "cosine",
                    "batch_size": 4
                }
            }
            )
        
        if self.collection.count() == 0:
            self.add_documents_to_db()
        
        self.llm =  ChatGroq(
            temperature=0.7,
            model_name=self.llm_model,
            groq_api_key=api_key,
            max_tokens=1000
        )


    def get_data(self) -> list[str]:
        df = pd.read_csv(self.data_file)
        texts = []
        for one in df["text"]:
            texts.append(one)

        dataset = []
        for i, text in enumerate(texts):
            doc = {
                "id": i,
                "text": text
            }
            dataset.append(doc)
        print(f"len(dataset): {len(dataset)}")
        return dataset


    def chunk_dataset(self):
        chunker = RecursiveChunker(chunk_size = self.chunk_size)
        chunks = []
        text_chunks = []

        for doc in self.dataset:
            doc_chunks = chunker(doc['text'])
        
            # Добавляем все чанки документа в общий список text_chunks
            text_chunks.extend(doc_chunks)

            for i, chunk in enumerate(doc_chunks):
                chunk_data = {
                        'id': f'chunk_{i}',
                        'original_doc_id': doc['id'],
                        'text': chunk.text,
                        'size_tokens': chunk.token_count,
                        }
                chunks.append(chunk_data)

    #   print(len(text_chunks))

        return chunks


    # усредняющий пулинг 
    def average_pool(self,
                    last_hidden_states: Tensor,
                    attention_mask: Tensor) -> Tensor:
        last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
        return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

    def get_embeddings(self):
        input_texts = []

        for chunk in self.chunks:
            input_texts.append("passage:" + chunk['text'])
        print(f"len(input_texts): {len(input_texts)}")
        input_texts = input_texts[0:7000] # если нужно уменьшить количество чанков для тестирования

        # Tokenize the input texts
        batch_dict = self.tokenizer(input_texts, max_length=self.max_length, padding=True, truncation=True, return_tensors='pt')
        # Переносим все тензоры из batch_dict на устройство
        # batch_dict = {k: v.to(device) for k, v in batch_dict.items()}
        # self.embedding_model.to(device)
        with torch.no_grad():
            outputs = self.embedding_model(**batch_dict)
        embeddings = self.average_pool(outputs.last_hidden_state, batch_dict['attention_mask'])
        del outputs
        #torch.cuda.empty_cache() 

        # normalize embeddings
        embeddings = F.normalize(embeddings, p=2, dim=1)
        scores = (embeddings[:3] @ embeddings[3:].T) * 100
        #print(f"scores: {scores.tolist()}")
        return embeddings

    def add_documents_to_db(self):
        embeddings_np = self.embeddings.detach().numpy() # хрома требует numpy array
        documents=[chunk['text'] for chunk in self.chunks]
        documents=documents[0:7000] # тоже обрезаем если надо
        self.collection.add(
            documents=documents, 
            embeddings=embeddings_np,
            ids=[str(i) for i in range(7000)] # индексы=documents, полный объем - 12896
            )
        print(f"len(nembeddings): {len(embeddings_np)}")


    def vectorize_and_search(self, query):
        '''Векторизирует запрос и ищет в бд'''
        input_texts = [f'query: {query}']
        batch_dict = self.tokenizer(input_texts, max_length=self.max_length, padding=True, truncation=True, return_tensors='pt')
        # перенос на gpu если надо
        #batch_dict = {k: v.to(device) for k, v in batch_dict.items()}
        outputs = self.embedding_model(**batch_dict)
        query_embeddings = self.average_pool(outputs.last_hidden_state, batch_dict['attention_mask'])
        query_embeddings = F.normalize(query_embeddings, p=2, dim=1)
        results = self.collection.query(
            query_embeddings=query_embeddings.detach().cpu().numpy(),
            include=["documents", "metadatas", "embeddings"],
            n_results=3,
        )
        context = results['documents']
        return context


class Agent:
  def __init__(self, name, instruction, api_key, model):
    self.name = name
    self.instruction = instruction
    self.llm =  ChatGroq(
            temperature=0.7,
            model_name=model,
            groq_api_key=api_key,
            max_tokens=1000
        )
    self.model = model
    
  def execute(self, query, context=""):
    prompt = f"""
ROLE: Ты {self.name}, {self.instruction}

Требования:
1. Отвечай на русском языке
2. Будь информативным и точным
3. Используй маркдаун для форматирования

Ответ:
"""
    response = self.llm.invoke(prompt)
    return response.content


# инициализируем раг
rag = RAG()
manager = Agent("менеджер", f"""определи к какой теме в области javascript относится этот запрос {query}. Не пиши ничего кроме выделенной темы""",
                api_key, model='groq/compound-mini')
# менеджер дает тему и все
theme = manager.execute(query)
print(f"theme: {theme}")
# раг по теме вытягивает контекст
context = rag.vectorize_and_search(theme)
print(f"filanl context: {context}")
teacher = Agent("учитель", f"""Проанализируй запрос ученика {query} и ответь на вопрос, объясни так, чтобы ученик понял, НЕ исправляй код.
                Для ответа сверяйся с эталоном {context}""",
                api_key, model='openai/gpt-oss-20b')
teacher_output = teacher.execute(query)
print(f"teacher: {teacher_output}")
coder = Agent("программист", f"""Найди код в {query} и минимально исправь его так, чтобы он работал как надо.
              Для ответа сверяйся с эталоном {context}.
              Верни только исправленный код, без слов.""",
              api_key, model='meta-llama/llama-4-scout-17b-16e-instruct')
code = coder.execute(query)
print(f"coder: {code}")

answers = {
    "explanation": {teacher_output},
    "code": {code}
            }

validator = Agent("редактор", f"""Проверь, нет ли фактических ошибок и соотносится ли объяснение {teacher_output} с кодом {code}.
                  Если нет, отредактируй полученный текст и код и верни ТОЛЬКО их в той же форме, что получил""",
                  api_key, model='llama-3.3-70b-versatile')
result = validator.execute(query)
print(f"validator: {result}")