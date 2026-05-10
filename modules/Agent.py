from pathlib import Path
from string import Template
from langchain_groq import ChatGroq

# путь к папке с промптами (работает из любой директории запуска)
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(filename: str, **kwargs) -> str:
    """Загружает промпт из файла и подставляет переменные ${var}."""
    text = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    # безопасная подстановка переменных через ${var}
    return Template(text).safe_substitute(kwargs)


def xml_escape(text: str) -> str:
    """Экранирует &, <, > для безопасной вставки в XML."""
    if text is None:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def wrap_untrusted_text(tag: str, text: str) -> str:
    """Оборачивает недоверенный текст в XML-тег с экранированием."""
    return f"<{tag}>\n{xml_escape(text or '')}\n</{tag}>"


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
        """Обращение к LLM"""
        trusted_query = wrap_untrusted_text("USER_MESSAGE", query)
        trusted_context = wrap_untrusted_text("UNTRUSTED_CONTEXT", context)

        prompt = load_prompt("system_base.txt").strip()

        response = self.llm.invoke(prompt)
        return response.content