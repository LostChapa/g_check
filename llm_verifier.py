"""
Модуль верификации найденных ошибок через LLM.

Пайплайн:
1. Детерминированные чекеры находят ошибки
2. Для каждой ошибки извлекается контекст (секция + 2 соседние)
3. Ошибки батчами отправляются в LLM для подтверждения
4. Возвращается только подтверждённый список ошибок
"""

from typing import List, Dict, Any, Optional, Tuple
import json
import re
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from doc_parser.docx_ast_parser import (
    DocumentNode, HeadingNode, ParagraphNode, ASTNode, walk_tree
)

import os

from dotenv import load_dotenv
load_dotenv()

MODEL_NAME = os.getenv("MODEL", "cotype_pro_3")
BASE_URL = os.getenv("BASE_URL", "") or None
API_KEY = os.getenv("API_KEY", os.getenv("API", ""))

# ==========================================
# Структуры данных
# ==========================================

@dataclass
class SectionContext:
    """Контекст секции документа"""
    title: str  # Заголовок секции (или "(Без заголовка)")
    content: str  # Текст секции (ограниченный)
    level: int  # Уровень заголовка (0 для беззаголовочных)


@dataclass
class ErrorWithContext:
    """Ошибка с извлечённым контекстом"""
    error: Any  # Объект CheckError
    main_section: SectionContext
    prev_section: Optional[SectionContext]
    next_section: Optional[SectionContext]
    index: int  # Индекс для сопоставления с ответом LLM


# ==========================================
# Вспомогательные функции
# ==========================================

def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    """Универсальное извлечение поля"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _truncate_text(text: str, max_chars: int = 800) -> str:
    """Обрезает текст до указанной длины с сохранением начала и конца"""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2 - 20
    return text[:half] + "\n...[обрезано]...\n" + text[-half:]


def extract_sections(ast_tree: DocumentNode) -> List[SectionContext]:
    """
    Извлекает секции документа.
    Секция = заголовок + весь текст до следующего заголовка того же или высшего уровня.
    """
    nodes = list(walk_tree(ast_tree))
    sections: List[SectionContext] = []
    
    current_title = "(Вступление)"
    current_level = 0
    current_content_parts: List[str] = []
    
    for node in nodes:
        if isinstance(node, HeadingNode):
            # Сохраняем предыдущую секцию
            if current_content_parts or current_title != "(Вступление)":
                content = "\n".join(current_content_parts)
                sections.append(SectionContext(
                    title=current_title,
                    content=_truncate_text(content),
                    level=current_level
                ))
            
            # Начинаем новую секцию
            gost_number = _get_field(node, 'metadata', {}).get('gost_number', '')
            heading_type = _get_field(node, 'heading_type', '')
            
            if gost_number:
                current_title = f"{gost_number} {node.text}"
            else:
                current_title = node.text or "(Пустой заголовок)"
            
            current_level = node.level if heading_type == 'main_heading' else (2 if heading_type == 'subheading' else node.level)
            current_content_parts = []
        
        elif isinstance(node, ParagraphNode):
            if node.text.strip():
                current_content_parts.append(node.text.strip())
    
    # Сохраняем последнюю секцию
    if current_content_parts or current_title != "(Вступление)":
        content = "\n".join(current_content_parts)
        sections.append(SectionContext(
            title=current_title,
            content=_truncate_text(content),
            level=current_level
        ))
    
    return sections


def find_section_for_error(error: Any, sections: List[SectionContext]) -> int:
    """
    Находит индекс секции, к которой относится ошибка.
    Использует контекст ошибки для поиска по тексту.
    """
    context = _get_field(error, 'context', '')
    node_type = _get_field(error, 'node_type', '')
    
    # Извлекаем текст из контекста (в кавычках)
    matches = re.findall(r"'([^']+)'", context)
    if not matches:
        return 0  # По умолчанию — первая секция
    
    search_text = max(matches, key=len).strip()
    search_text = re.sub(r'\.{2,}$', '', search_text).strip()
    
    if len(search_text) < 3:
        return 0
    
    # Ищем секцию, содержащую этот текст
    search_lower = search_text.lower()
    for i, section in enumerate(sections):
        if search_lower in section.title.lower() or search_lower in section.content.lower():
            return i
    
    # Если не нашли — возвращаем 0
    return 0


def build_error_contexts(errors: List[Any], ast_tree: DocumentNode) -> List[ErrorWithContext]:
    """
    Строит список ошибок с контекстом.
    """
    sections = extract_sections(ast_tree)
    result: List[ErrorWithContext] = []
    
    for idx, error in enumerate(errors):
        section_idx = find_section_for_error(error, sections)
        
        main_section = sections[section_idx] if sections else SectionContext("(Пусто)", "", 0)
        prev_section = sections[section_idx - 1] if section_idx > 0 else None
        next_section = sections[section_idx + 1] if section_idx < len(sections) - 1 else None
        
        result.append(ErrorWithContext(
            error=error,
            main_section=main_section,
            prev_section=prev_section,
            next_section=next_section,
            index=idx
        ))
    
    return result


# ==========================================
# Формирование промптов
# ==========================================

SYSTEM_PROMPT = """Ты — эксперт по нормоконтролю технической документации по ГОСТ.
Тебе будут представлены ошибки, найденные автоматическими чекерами в документе, 
вместе с контекстом (секция документа и соседние секции).

Твоя задача — проверить каждую ошибку и определить, является ли она валидной 
(действительно нарушение ГОСТ) или ложной (ошибка чекера, допустимое исключение).

Ошибка валидна если она действительно нарушает указанный пункт ГОСТ и из контекста не видна ошибка чекера.
Ошибка невалидна, если:
- Это особенность документа (например, специальная терминология);
- Контекст показывает, что нарушения на самом деле нет;
- Чекер неправильно интерпретировал структуру.

Возможные ошибки чекеров:
- Неправильная интерпретация структуры документа - заголовок указан как параграф, параграф или пункт списка указан как подзаголовок или заголовок и т. д.;
- Ошибки нумерации - чекер указывает, что в нумерации списка есть ошибка, но из контекста видно, что нумерация верная;
- Элементы нумерованных списков могут быть приняты за заголовки или подзаголовки;
- Библиография может быть записана шрифтом меньше основного текста (обычно 12 пт.);
- 

ВАЖНО: при оценке ошибки учитывай полный контекст, в т. ч. текстовое содержание.

Отвечай СТРОГО в формате JSON без дополнительного текста:
{
  "verdicts": [
    {"id": 0, "valid": true, "reason": "краткое обоснование"},
    {"id": 1, "valid": false, "reason": "краткое обоснование"}
  ]
}

Если не уверен — считай ошибку валидной (консервативный подход)."""


def format_error_for_llm(error_ctx: ErrorWithContext) -> str:
    """Форматирует одну ошибку для промпта"""
    error = error_ctx.error
    
    severity = _get_field(error, 'severity', 'unknown')
    if hasattr(severity, 'value'):
        severity = severity.value
    severity = str(severity).upper()
    
    message = _get_field(error, 'message', '')
    gost_ref = _get_field(error, 'gost_ref', '')
    context = _get_field(error, 'context', '')
    node_type = _get_field(error, 'node_type', '')
    
    parts = [f"### Ошибка #{error_ctx.index}"]
    parts.append(f"- **Тип**: {node_type}")
    parts.append(f"- **Серьёзность**: {severity}")
    parts.append(f"- **Описание**: {message}")
    if gost_ref:
        parts.append(f"- **Ссылка на ГОСТ**: {gost_ref}")
    if context:
        parts.append(f"- **Контекст ошибки**: {context}")
    
    parts.append("\n#### Основная секция:")
    parts.append(f"**{error_ctx.main_section.title}**")
    parts.append(error_ctx.main_section.content)
    
    if error_ctx.prev_section:
        parts.append("\n#### Предыдущая секция:")
        parts.append(f"**{error_ctx.prev_section.title}**")
        parts.append(error_ctx.prev_section.content)
    
    if error_ctx.next_section:
        parts.append("\n#### Следующая секция:")
        parts.append(f"**{error_ctx.next_section.title}**")
        parts.append(error_ctx.next_section.content)
    
    return "\n".join(parts)


def build_batch_prompt(errors_batch: List[ErrorWithContext]) -> str:
    """Строит промпт для батча ошибок"""
    parts = [f"Проверь следующие {len(errors_batch)} ошибок:\n"]
    for error_ctx in errors_batch:
        parts.append(format_error_for_llm(error_ctx))
        parts.append("\n" + "=" * 50 + "\n")
    
    parts.append("\nВерни JSON с вердиктами по каждой ошибке.")
    return "\n".join(parts)


# ==========================================
# Основной класс верификатора
# ==========================================

class LLMVerifier:
    """
    Верификатор ошибок через LLM.
    
    Использование:
        verifier = LLMVerifier()
        verified_errors = verifier.verify(errors, ast_tree)
    """
    
    def __init__(
        self,
        model: str = MODEL_NAME,
        temperature: float = 0.0,
        batch_size: int = 10,
        max_retries: int = 2,
        api_key: str = API_KEY,
        base_url: str = BASE_URL,
    ):
        """
        Args:
            model: Название модели (gpt-4o-mini, gpt-4o, gpt-3.5-turbo и т.д.)
            temperature: Температура (0 для детерминированности)
            batch_size: Размер батча для обработки за один запрос
            max_retries: Количество повторных попыток при ошибке
            api_key: API-ключ OpenAI (или из переменной окружения OPENAI_API_KEY)
            base_url: Базовый URL для совместимых API
        """
        client_kwargs = {
            "model": model,
            "base_url": base_url,
            "api_key": api_key,
            "temperature": temperature,
            "max_retries": max_retries,
        }
        # if api_key:
        #     client_kwargs["api_key"] = api_key
        # if base_url:
        #     client_kwargs["base_url"] = base_url
        
        self.llm = ChatOpenAI(**client_kwargs)
        self.batch_size = batch_size
        self.model = model
        
        # Статистика
        self.stats = {
            'total_checked': 0,
            'confirmed': 0,
            'rejected': 0,
            'failed': 0,  # Ошибки, где LLM не смог ответить
            'batches': 0,
        }
    
    def verify(self, errors: List[Any], ast_tree: DocumentNode) -> List[Any]:
        """
        Верифицирует список ошибок через LLM.
        
        Args:
            errors: Список ошибок от чекеров
            ast_tree: AST-дерево документа для извлечения контекста
            
        Returns:
            Список подтверждённых ошибок
        """
        if not errors:
            return []
        
        print(f"\n🤖 Запуск LLM-верификации ({len(errors)} ошибок, модель: {self.model})")
        
        # 1. Строим контексты
        print("   📖 Извлечение контекста секций...")
        error_contexts = build_error_contexts(errors, ast_tree)
        
        # 2. Разбиваем на батчи
        batches = [
            error_contexts[i:i + self.batch_size]
            for i in range(0, len(error_contexts), self.batch_size)
        ]
        
        print(f"   📦 Обработка в {len(batches)} батчах (по {self.batch_size} ошибок)")
        
        # 3. Обрабатываем батчи
        confirmed_errors: List[Any] = []
        
        for batch_idx, batch in enumerate(batches, 1):
            print(f"   ⏳ Батч {batch_idx}/{len(batches)}...")
            self.stats['batches'] += 1
            
            verdicts = self._verify_batch(batch)
            
            for error_ctx, verdict in zip(batch, verdicts):
                self.stats['total_checked'] += 1
                
                if verdict is None:
                    # LLM не смог ответить — считаем ошибку подтверждённой (консервативно)
                    confirmed_errors.append(error_ctx.error)
                    self.stats['failed'] += 1
                elif verdict.get('valid', True):
                    confirmed_errors.append(error_ctx.error)
                    self.stats['confirmed'] += 1
                else:
                    self.stats['rejected'] += 1
        
        print(f"\n✅ LLM-верификация завершена:")
        print(f"   • Подтверждено: {self.stats['confirmed']}")
        print(f"   • Отклонено: {self.stats['rejected']}")
        print(f"   • Не удалось проверить: {self.stats['failed']}")
        print(f"   • Итого в отчёте: {len(confirmed_errors)}")
        
        return confirmed_errors
    
    def _verify_batch(self, batch: List[ErrorWithContext]) -> List[Optional[Dict]]:
        """
        Отправляет батч в LLM и парсит ответ.
        
        Returns:
            Список вердиктов (None, если не удалось распарсить)
        """
        prompt = build_batch_prompt(batch)
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ])
            
            content = response.content.strip()
            
            # Пытаемся извлечь JSON из ответа
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                print(f"      ⚠️  LLM не вернул JSON, используем консервативный подход")
                return [None] * len(batch)
            
            json_str = json_match.group(0)
            data = json.loads(json_str)
            
            verdicts_raw = data.get('verdicts', [])
            
            # Сопоставляем вердикты с ошибками по id
            verdicts_map = {v.get('id'): v for v in verdicts_raw}
            
            result = []
            for error_ctx in batch:
                verdict = verdicts_map.get(error_ctx.index)
                result.append(verdict)
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"      ⚠️  Ошибка парсинга JSON: {e}")
            return [None] * len(batch)
        except Exception as e:
            print(f"      ❌ Ошибка LLM: {e}")
            return [None] * len(batch)


# ==========================================
# Функция-обёртка
# ==========================================

def verify_with_llm(
    errors: List[Any], 
    ast_tree: DocumentNode,
    model: str = MODEL_NAME,
    batch_size: int = 10,
    api_key: str = API_KEY,
    base_url: str = BASE_URL,
) -> List[Any]:
    """
    Быстрая функция для верификации ошибок через LLM.
    
    Args:
        errors: Список ошибок от чекеров
        ast_tree: AST-дерево документа
        model: Название модели
        batch_size: Размер батча
        api_key: API-ключ (опционально)
        base_url: Базовый URL (опционально)
        
    Returns:
        Список подтверждённых ошибок
    """
    verifier = LLMVerifier(
        model=model,
        batch_size=batch_size,
        api_key=api_key,
        base_url=base_url,
    )
    return verifier.verify(errors, ast_tree)