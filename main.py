import json
import os
import re

from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

from modules import RAG, Agent
from pathlib import Path
from string import Template

# путь к папке с промптами (работает из любой директории запуска)
PROMPTS_DIR = Path(__file__).parent / "prompts"

# -----------------------------
# Utils
# -----------------------------
CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")

JAVASCRIPT_TOPICS = [
    "variables",
    "data types",
    "operators",
    "conditionals",
    "loops",
    "functions",
    "arrays",
    "objects",
    "string",
    "number",
    "boolean",
    "null",
    "undefined",
    "scope",
    "hoisting",
    "closure",
    "this",
    "prototype",
    "class",
    "inheritance",
    "modules",
    "async",
    "promise",
    "fetch",
    "event loop",
    "dom",
    "events",
    "json",
    "error handling",
    "try catch",
    "es6",
    "destructuring",
    "spread",
    "rest",
    "map",
    "filter",
    "reduce",
    "set",
    "map object",
    "weakmap",
    "weakset",
    "regexp",
    "typescript",
    "ооп",
    "переменные",
    "типы данных",
    "операторы",
    "условия",
    "циклы",
    "функции",
    "массивы",
    "объекты",
    "замыкания",
    "область видимости",
    "прототипы",
    "классы",
    "модули",
    "асинхронность",
    "промисы",
    "event loop",
    "dom",
    "события",
    "обработка ошибок",
]

# подозрительные паттерны prompt injection / jailbreak
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous\s+instructions",
    r"forget\s+(all\s+)?previous\s+instructions",
    r"забудь\s+все\s+предыдущие\s+инструкции",
    r"игнорируй\s+все\s+предыдущие\s+инструкции",
    r"проигнорируй\s+все\s+предыдущие\s+инструкции",
    r"system\s+prompt",
    r"developer\s+message",
    r"hidden\s+instructions",
    r"reveal\s+.*instructions",
    r"show\s+.*prompt",
    r"print\s+.*prompt",
    r"act\s+as\s+",
    r"you\s+are\s+now\s+",
    r"pretend\s+to\s+be",
    r"roleplay\s+as",
    r"jailbreak",
    r"bypass\s+safety",
    r"override\s+instructions",
    r"do\s+not\s+follow\s+the\s+above",
    r"answer\s+as\s+the\s+system",
    r"simulate\s+developer",
    r"выведи\s+системный\s+промпт",
    r"покажи\s+системный\s+промпт",
    r"раскрой\s+скрытые\s+инструкции",
    r"ответь\s+как\s+system",
    r"ответь\s+как\s+разработчик",
]


def ensure_api_key() -> str:
    '''Получает апи-ключ из переменных среды'''
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY ERROR: переменная окружения GROQ_API_KEY не найдена.")
    return api_key


def safe_json_loads(raw_text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    '''Приводит JSON к правильному виду'''
    text = raw_text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except Exception:
        return fallback


def contains_cyrillic(text: str) -> bool:
    '''Проверяет содержится ли кириллица в коде: True|False'''
    return bool(CYRILLIC_PATTERN.search(text or ""))


def code_has_cyrillic_identifiers(code: str) -> bool:
    '''Убедиться, что кириллицу ищем только в коде'''
    if not code:
        return False
    return contains_cyrillic(code)

def build_title_fallback(message: str, max_words: int = 6, max_len: int = 60) -> str:
    '''Дефолтное название нового чата'''
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


def detect_prompt_injection(text: str) -> Tuple[bool, str]:
    '''Отсеивает длинные запросы и запросы с подозрительными маркерами'''
    normalized = (text or "").strip().lower()

    if not normalized:
        return False, ""

    if len(normalized) > 12000:
        return True, "слишком длинный запрос с потенциальным риском prompt injection"

    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return True, f"обнаружен подозрительный паттерн: {pattern}"

    suspicious_markers = [
        "```system",
        "```developer",
        "<system>",
        "</system>",
        "<developer>",
        "</developer>",
        "BEGIN_SYSTEM_PROMPT",
        "END_SYSTEM_PROMPT",
    ]
    for marker in suspicious_markers:
        if marker.lower() in normalized:
            return True, f"обнаружен подозрительный маркер: {marker}"

    return False, ""


def sanitize_model_text(text: str) -> str:
    '''Анализирует ответ модели и
    предотвращает утечку системных инструкций'''
    cleaned = (text or "").strip()

    forbidden_patterns = [
        r"(?i)system\s+prompt",
        r"(?i)developer\s+message",
        r"(?i)hidden\s+instructions",
        r"(?i)internal\s+instructions",
        r"(?i)внутренн\w+\s+инструкц\w+",
        r"(?i)системн\w+\s+промпт",
    ]

    for pattern in forbidden_patterns:
        if re.search(pattern, cleaned):
            return (
                "Я не могу раскрывать внутренние инструкции системы. "
                "Но я могу помочь с вопросами по JavaScript: объяснить теорию, "
                "разобрать ошибку или посмотреть код."
            )

    return cleaned

def load_prompt(filename: str, **kwargs) -> str:
    '''Загрузка промптов'''
    text = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    # безопасная подстановка переменных через ${var}
    return Template(text).safe_substitute(kwargs)

# -----------------------------
# MultiAgent
# -----------------------------
class MultiAgentSystem:
    '''Основная логика мультиагентной системы'''
    def __init__(self, api_key: Optional[str] = None, config_path: str = "agent_config.json"):
        self.api_key = api_key or ensure_api_key()

        config_file = Path(__file__).parent / config_path
        with open(config_file, "r", encoding="utf-8") as f:
            self.default_config = json.load(f)

        self.rag = RAG()
        self.agents: Dict[str, Agent] = {}

    def _get_instruction(self, agent_name: str) -> str:
        '''Получает промпты для каждого агента'''
        instructions = {
            "manager": (
                load_prompt("manager.txt")
            ),
            "teacher": (
                load_prompt("teacher.txt")
            ),
            "coder": (
                load_prompt("coder.txt")
            ),
            "validator": (
                load_prompt("validator.txt")
            ),
            "title_generator": (
                load_prompt("title_generator.txt")
            ),
        }
        return instructions.get(agent_name, "")

    def _get_agent(self, name: str) -> Agent:
        ''' Инициализация агента: имя, инструкция, апи-ключ, модель, температура'''
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
        ''' Приводит историю к виду: role, content'''
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
        '''Приведение ответа менеджера к правильному JSON'''
        # дефолтный ответ
        fallback = {
            "route": "manager",
            "need_retrieval": False,
            "reason": "fallback route",
            "direct_response": (
                "Я помогаю с изучением JavaScript: могу объяснять теорию, разбирать ошибки и помогать с исправлением кода. Задай вопрос по теме или пришли свой код."
            ),
        }

        data = safe_json_loads(raw_output, fallback)

        route = str(data.get("route", "manager")).strip()
        if route not in {"manager", "teacher_coder", "unsupported"}:
            route = "manager"

        return {
            "route": route,
            "need_retrieval": bool(data.get("need_retrieval", False)),
            "reason": str(data.get("reason", "")).strip(),
            "direct_response": sanitize_model_text(str(data.get("direct_response", "")).strip()),
        }


    def _should_use_rag(self, route: Dict[str, Any]) -> bool:
        '''Возвращает True/False на need_retrieval'''
        return route["route"] in {"teacher_coder"} and route["need_retrieval"]

    def generate_chat_title(self, first_user_message: str) -> str:
        '''Генерирует названия чатов'''
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

    def _blocked_response(self, reason: str) -> Dict[str, Any]:
        '''Заглушка на случай jailbreak'''
        return {
            "route": {
                "route": "unsupported",
                "need_retrieval": False,
                "reason": reason,
                "direct_response": (
                    "Я не могу выполнять запросы, которые пытаются изменить мои правила или раскрыть внутренние инструкции. Но я могу помочь с вопросами по JavaScript."
                ),
            },
            "explanation": (
                "Я не могу выполнять запросы, которые пытаются изменить мои правила или раскрыть внутренние инструкции. Но я могу помочь с вопросами по JavaScript."
            ),
            "code": "",
            "context": "",
            "manager_raw": "",
            "teacher_raw": "",
            "coder_raw": "",
            "validator_raw": "",
        }

    def process_query(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        '''Блок инъекций, выбор маршрута, вызов агентов'''
        # внешняя защита до LLM
        is_injection, injection_reason = detect_prompt_injection(query)
        if is_injection:
            return self._blocked_response(injection_reason)

        history_text = self._format_history(history)

        # при желании можно проверять и недавнюю историю
        history_injection, history_reason = detect_prompt_injection(history_text)
        if history_injection:
            return self._blocked_response(f"подозрительная история сообщений: {history_reason}")

        manager_context = (
            f"HISTORY:\n{history_text}\n\n"
            "Система специализируется на помощи в изучении JavaScript: теория, объяснения, разбор ошибок, исправление кода."
        )
        # инициализация менеджера
        manager = self._get_agent("manager")
        manager_output = manager.execute(query, manager_context)
        route = self._parse_manager_output(manager_output)
        
        # если маршрут "unsupported"
        if route["route"] in {"manager", "unsupported"}:
            direct_response = route["direct_response"].strip()

            #заглушки на случай, когда прямой ответ не сгенерирован
            if not direct_response:
                if route["route"] == "manager":
                    direct_response = (
                        "Я помогаю с изучением JavaScript: объясняю теорию, разбираю ошибки и помогаю исправлять код. Можешь задать вопрос по теме или прислать фрагмент кода."
                    )
                else:
                    direct_response = (
                        "Я специализируюсь на вопросах по JavaScript и помощи в обучении. Попробуй задать вопрос по JavaScript или пришли код, который нужно разобрать."
                    )

            # проверка ответа менеджера
            direct_response = sanitize_model_text(direct_response)

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
        # здесь будут retrieved docs
        context_text = ""

        # менеджер решает необходим ли retrieval по базе
        if self._should_use_rag(route):
            docs = self.rag.vectorize_and_search(query, n_results=3)
            context_text = self.rag.format_context(docs)

        coder_output = ""
        teacher_output = ""

        # сохраняем retrieved context и историю сообщений в worker_context
        worker_context_parts = []
        if history_text:
            worker_context_parts.append(f"HISTORY:\n{history_text}")
        if context_text:
            worker_context_parts.append(f"REFERENCE:\n{context_text}")

        worker_context = "\n\n".join(worker_context_parts).strip()

        # если выбран маршрут teacher_coder
        if route["route"] in {"teacher_coder"}:
            coder = self._get_agent("coder")
            #кодер получает JSON от менеджера
            coder_output = coder.execute(manager_output)
            teacher = self._get_agent("teacher")
            # учитель получает JSON от кодера, историю сообщений и retrieved context
            teacher_output = sanitize_model_text(teacher.execute(coder_output, worker_context))
           
        # кодер перегенерирует ответ в случае если
        if coder_output != "NO_CODE_FOUND" and code_has_cyrillic_identifiers(coder_output):
            retry_context = (
                f"{worker_context}\n\n"
                "Твой предыдущий ответ нарушил правило: в коде обнаружена кириллица. Сгенерируй код заново. Все идентификаторы должны быть только на английском языке."
            ).strip()
            coder = self._get_agent("coder")
            coder_output = coder.execute(manager_output, retry_context)

        # валидатор получает три части: запрос пользователя, текст от учителя и JSON от кодера
        validator_input_parts = [
            f"USER QUERY:\n{query}",
            f"TEACHER OUTPUT:\n{teacher_output or ''}",
            f"CODER OUTPUT:\n{coder_output if coder_output != 'NO_CODE_FOUND' else ''}",
        ]

        # если есть извлеченный из базы контекст (retrieved context), валидатор получает референс
        if context_text:
            validator_input_parts.append(f"REFERENCE:\n{context_text}")

        # соединяем эти 4 части в один контекст
        validator_context = "\n\n".join(validator_input_parts).strip()

        validator = self._get_agent("validator")
        # валидатор собирает финальный ответ
        validator_output = validator.execute("Собери финальный ответ пользователю.", validator_context)
        # чистим ответ
        final_text = sanitize_model_text(validator_output)
        #если валидатор не сгенерировал, отдаем ответ учителя напрямую
        if not final_text and teacher_output:
            final_text = teacher_output.strip()

        return {
            "route": route,
            "explanation": final_text,
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
        '''Принимает: результат process_query(last_user_message, messages) в виде 'explanation', 'code'
        Возвращает: соединяет строку из explanation и code'''

        result = self.process_query(last_user_message, messages)
        return result["explanation"].strip()
       

def main():
    try:
        # заупск системы
        system = MultiAgentSystem()
        # принимаем запрос пользователя
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