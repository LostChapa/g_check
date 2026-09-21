import asyncio
import os
import httpx
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv()

MODEL_NAME = os.getenv("MODEL", "cotype_pro_3")
BASE_URL = os.getenv("BASE_URL", "") or None
API_KEY = os.getenv("API_KEY", os.getenv("API", ""))

MCP_SERVER_URL = "http://127.0.0.1:8000/gost/mcp"

# Явный HTTP-клиент для корректной работы с редиректами
http_client = httpx.AsyncClient(
    base_url="http://127.0.0.1:8000",
    follow_redirects=True,
    timeout=30.0
)

# Инициализация MCP Toolset (без дублирования)
mcp_toolset = MCPToolset(MCP_SERVER_URL)

# Инициализация модели (без дублирования)
model = OpenAIChatModel(
    MODEL_NAME,
    provider=OpenAIProvider(base_url=BASE_URL, api_key=API_KEY),
)

agent = Agent(
    model=model,
    system_prompt=(
        "Ты — опытный ассистент для проведения нормоконтроля технической документации по ГОСТ.\n"
        "У тебя есть доступ к MCP-серверу, который предоставляет инструменты для работы с файлами.\n\n"
        "Основные правила:\n"
        "1. Если пользователь просит проанализировать документ, сначала убедись, что файл загружен. "
        "Если файлов нет, вежливо попроси пользователя загрузить их через интерфейс.\n"
        "2. Для анализа структуры документа (.docx) используй инструмент 'parse_document_file', "
        "передавая ему точное имя файла (например, 'gost_doc.docx').\n"
        "3. ВАЖНО: Инструмент 'parse_document_file' НЕ возвращает содержимое документа напрямую — "
        "он сохраняет AST-дерево в JSON-файл в рабочей директории и возвращает строку с именем этого файла. "
        "Для чтения содержимого JSON-файла используй инструмент 'read_ast_file', передавая ему имя файла из ответа.\n"
        "4. Отвечай четко, структурировано и на русском языке.\n"
        "5. Если инструмент возвращает ошибку (например, файл не найден), сообщи об этом пользователю "
        "и предложи проверить имя файла или загрузить его заново."
    ),
    toolsets=[mcp_toolset],
)


async def interactive_chat():
    print("🤖 Интерактивный чат с агентом нормоконтроля запущен!")
    print(f"🔗 Подключение к MCP: {MCP_SERVER_URL}")
    print("-" * 60)
    message_history = None

    while True:
        try:
            user_input = input("\n👤 Вы: ").strip()
            if user_input.lower() in ['exit', 'quit', 'выход']:
                print("👋 До свидания!")
                break
            if not user_input:
                continue

            print("⏳ Агент думает (возможно, вызывает инструменты MCP)...")

            result = await agent.run(
                user_input,
                message_history=message_history
            )

            print(f"\n🤖 Агент: {result.output}")
            message_history = result.all_messages()

        except KeyboardInterrupt:
            print("\n👋 Чат принудительно завершен.")
            break
        except Exception as e:
            print(f"\n❌ Произошла ошибка: {e}")


if __name__ == '__main__':
    asyncio.run(interactive_chat())