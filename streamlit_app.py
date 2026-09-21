import json
from typing import Any, Dict, List
import requests
import streamlit as st

from agent import agent

SERVER_URL = "http://127.0.0.1:8000"
ALLOWED_TYPES = ["docx", "xlsx", "xls", "pdf"]


# --- HTTP Клиент ---
def _get(path: str) -> Any:
    response = requests.get(f"{SERVER_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def _delete(path: str) -> Any:
    response = requests.delete(f"{SERVER_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def _post_multipart(path: str, file_name: str, file_bytes: bytes) -> Any:
    files = {"file": (file_name, file_bytes, "application/octet-stream")}
    response = requests.post(f"{SERVER_URL}{path}", files=files, timeout=60)
    response.raise_for_status()
    return response.json()


def _post_json(path: str, payload: Dict[str, Any]) -> Any:
    response = requests.post(f"{SERVER_URL}{path}", json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


# --- API Функции ---
def get_health() -> Dict[str, Any]:
    return _get("/api/health")


def list_files() -> List[Dict[str, Any]]:
    response = _get("/api/files")
    return response.get("files", [])


def upload_file(file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    return _post_multipart("/api/upload", file_name, file_bytes)


def delete_file(filename: str) -> Dict[str, Any]:
    return _delete(f"/api/files/{filename}")


def download_file_content(filename: str) -> bytes:
    """Скачать содержимое файла с сервера."""
    response = requests.get(f"{SERVER_URL}/api/download/{filename}", timeout=30)
    response.raise_for_status()
    return response.content


def call_mcp_parse_tool(file_name: str) -> Dict[str, Any]:
    """Прямой вызов MCP-инструмента парсинга через JSON-RPC."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "parse_document_file",
            "arguments": {"file_path": file_name}
        }
    }
    return _post_json("/gost/mcp", payload)


# --- Управление состоянием ---
def init_state() -> None:
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "message_history" not in st.session_state:
        st.session_state["message_history"] = None
    if "files" not in st.session_state:
        st.session_state["files"] = []
    if "error" not in st.session_state:
        st.session_state["error"] = None
    if "last_parsed_ast_data" not in st.session_state:
        st.session_state["last_parsed_ast_data"] = None


def refresh_file_list() -> None:
    try:
        st.session_state["files"] = list_files()
        st.session_state["error"] = None
    except requests.exceptions.RequestException as exc:
        st.session_state["error"] = f"Не удалось связаться с сервером: {exc}"


# --- Компоненты UI ---
def render_file_manager() -> None:
    st.sidebar.header("📁 Менеджер документов")

    uploaded_file = st.sidebar.file_uploader(
        "Загрузить новый документ",
        type=ALLOWED_TYPES,
        help="Поддерживаются форматы: DOCX, XLSX, PDF"
    )

    if uploaded_file is not None:
        with st.spinner("Загрузка файла на сервер..."):
            try:
                result = upload_file(uploaded_file.name, uploaded_file.getvalue())
                st.sidebar.success(f"✅ Загружен: {result.get('name')}")
                refresh_file_list()
            except requests.exceptions.RequestException as exc:
                st.sidebar.error(f"❌ Ошибка загрузки: {exc}")

    st.sidebar.markdown("---")

    if st.session_state.get("error"):
        st.sidebar.error(st.session_state["error"])

    files = st.session_state.get("files", [])
    if not files:
        st.sidebar.info("В рабочей папке нет файлов.")
        return

    st.sidebar.markdown("**Доступные файлы:**")
    for item in files:
        name = item["name"]
        size_kb = item.get("size", 0) / 1024
        with st.sidebar.container(border=True):
            st.markdown(f"**📄 {name}**")
            st.caption(f"Размер: {size_kb:.1f} КБ")
            col1, col2 = st.columns([2, 1])
            with col1:
                st.download_button(
                    label="⬇️ Скачать",
                    data=download_file_content(name),
                    file_name=name,
                    mime="application/octet-stream",
                    use_container_width=True
                )
            with col2:
                if st.button("🗑️", key=f"del_{name}", use_container_width=True):
                    try:
                        delete_file(name)
                        st.sidebar.success(f"Удалён: {name}")
                        refresh_file_list()
                        st.rerun()
                    except requests.exceptions.RequestException as exc:
                        st.sidebar.error(f"Ошибка: {exc}")


# def render_mcp_tester() -> None:
#     """Секция для прямой проверки работы MCP-парсера без участия ИИ-агента."""
#     st.markdown("### 🛠️ Тест MCP-парсера (Нормоконтроль)")
#     st.caption("Прямой вызов инструмента `parse_document_file` для проверки AST-дерева.")

#     files = st.session_state.get("files", [])
#     docx_files = [f["name"] for f in files if f["name"].lower().endswith(".docx")]

#     if not docx_files:
#         st.warning("Загрузите файл .docx, чтобы протестировать парсер.")
#         return

#     selected_file = st.selectbox("Выберите документ для парсинга:", docx_files)

#     if st.button("🚀 Распарсить документ через MCP", type="primary"):
#         with st.spinner("Анализ структуры документа (это может занять время для больших файлов)..."):
#             try:
#                 result = call_mcp_parse_tool(selected_file)

#                 # Извлекаем текст ответа из MCP-ответа
#                 # Стандартная структура: {"result": {"content": [{"type": "text", "text": "..."}]}}
#                 mcp_response_text = ""
#                 if isinstance(result, dict):
#                     content = result.get("result", {}).get("content", [])
#                     if content and isinstance(content, list) and len(content) > 0:
#                         mcp_response_text = content[0].get("text", "")
#                     else:
#                         mcp_response_text = str(result)
#                 else:
#                     mcp_response_text = str(result)

#                 # Пытаемся извлечь имя JSON-файла из ответа
#                 # Ожидается формат: "Документ успешно распарсен. AST сохранен в файл: {filename}"
#                 json_filename = None
#                 if "AST сохранен в файл: " in mcp_response_text:
#                     json_filename = mcp_response_text.split("AST сохранен в файл: ", 1)[1].strip()

#                 if json_filename:
#                     # Читаем JSON-файл через REST API
#                     try:
#                         json_content = download_file_content(json_filename)
#                         ast_data = json.loads(json_content)
#                         st.session_state["last_parsed_ast_data"] = ast_data
#                         st.success(f"✅ Документ успешно распарсен! AST сохранен в `{json_filename}`")
#                     except Exception as e:
#                         st.warning(f"⚠️ Документ распарсен, но не удалось прочитать JSON: {e}")
#                         st.session_state["last_parsed_ast_data"] = None
#                 else:
#                     st.warning("⚠️ Не удалось определить имя JSON-файла из ответа MCP.")
#                     st.session_state["last_parsed_ast_data"] = None

#             except requests.exceptions.RequestException as exc:
#                 st.error(f"❌ Ошибка вызова MCP: {exc}")
#                 st.session_state["last_parsed_ast_data"] = None

#     # Отображение результата
#     ast_data = st.session_state.get("last_parsed_ast_data")
#     if ast_data:
#         with st.expander("📦 Показать результат (AST JSON)", expanded=False):
#             st.json(ast_data)


def render_chat() -> None:
    st.markdown("### 🤖 Чат с ИИ-агентом нормоконтроля")

    health_status = "🔴 Сервер недоступен"
    try:
        health = get_health()
        health_status = f"🟢 Сервер доступен (Workspace: `{health.get('workspace')}`)"
    except Exception:
        pass

    st.info(health_status)

    with st.form("message_form", clear_on_submit=True):
        user_message = st.text_area(
            "Ваш запрос к агенту",
            height=100,
            placeholder="Например: 'Проверь структуру загруженного документа на соответствие ГОСТ Р 2.105-2019'"
        )
        submitted = st.form_submit_button("Отправить агенту", type="primary")

    if submitted and user_message:
        with st.spinner("Агент анализирует документ и формирует ответ..."):
            try:
                result = agent.run_sync(
                    user_message,
                    message_history=st.session_state.get("message_history")
                )
                assistant_response = result.output

                st.session_state["message_history"] = result.all_messages()
                st.session_state["chat_history"].append({"role": "user", "content": user_message})
                st.session_state["chat_history"].append({"role": "assistant", "content": assistant_response})
            except Exception as exc:
                st.error(f"Ошибка агента: {exc}")
                st.exception(exc)

    st.markdown("---")
    for msg in st.session_state["chat_history"]:
        role = "👤 Вы" if msg["role"] == "user" else "🤖 Агент"
        avatar = "👤" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])


def main() -> None:
    st.set_page_config(page_title="GOST Norm Control MCP", layout="wide", page_icon="📐")
    init_state()

    if not st.session_state["files"]:
        refresh_file_list()

    col1, col2 = st.columns([1, 3])
    with col1:
        render_file_manager()
    with col2:
        # render_mcp_tester()
        st.markdown("---")
        render_chat()


if __name__ == "__main__":
    main()