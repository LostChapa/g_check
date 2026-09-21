from typing import List, Optional
import re
from .base import BaseLLMChecker
from doc_parser.docx_ast_parser import (
    DocumentNode, HeadingNode, ParagraphNode, ListNode, ListItemNode, walk_tree
)

import os

from dotenv import load_dotenv
load_dotenv()

MODEL_NAME = os.getenv("MODEL", "cotype_pro_3")
BASE_URL = os.getenv("BASE_URL", "") or None
API_KEY = os.getenv("API_KEY", os.getenv("API", ""))

class AbbreviationsNumberingChecker(BaseLLMChecker):
    """
    Проверка: раздел "Обозначения и сокращения" не должен быть нумерован.
    Внутри него пункты "Сокращения", "Индексы" и "Параметры" тоже не должны нумероваться.
    """
    
    def __init__(self, api_key: str = API_KEY, model: str = MODEL_NAME, 
                     llm_base_url: str = BASE_URL):
        super().__init__(
            name="abbreviations_numbering",
            description="Проверка отсутствия нумерации в разделе 'Обозначения и сокращения'",
            api_key=api_key,
            model=model,
            llm_base_url=llm_base_url
        )
    
    def extract_context(self, ast_tree: DocumentNode) -> str:
        """Извлекает раздел 'Обозначения и сокращения' из документа"""
        nodes = list(walk_tree(ast_tree))
        
        print(f"    🔎 [ABBREV] Всего узлов в дереве: {len(nodes)}")
        
        # === ШАГ 1: Ищем заголовок раздела среди ВСЕХ типов узлов ===
        section_idx = None
        section_node = None
        
        for i, node in enumerate(nodes):
            # Проверяем, есть ли у узла текст
            if not hasattr(node, 'text') or not node.text:
                continue
            
            text = node.text.strip()
            if not text:
                continue
            
            text_lower = text.lower()
            
            # Ищем по точному совпадению или вхождению ключевого слова
            is_match = False
            if "обозначени" in text_lower and "сокращен" in text_lower:
                is_match = True
            elif "перечень сокращен" in text_lower:
                is_match = True
            elif text_lower == "сокращения" or text_lower == "обозначения":
                is_match = True
            
            if is_match:
                section_idx = i
                section_node = node
                node_type = type(node).__name__
                print(f"    ✅ [ABBREV] НАЙДЕН раздел на позиции {i}!")
                print(f"       Тип узла: {node_type}")
                print(f"       Текст: '{text}'")
                
                # Выводим свойства для отладки
                if hasattr(node, 'font') and node.font:
                    print(f"       Шрифт: {node.font.name}, {node.font.size_pt} пт, bold={node.font.bold}")
                if hasattr(node, 'metadata') and node.metadata:
                    gost_number = node.metadata.get('gost_number', '')
                    if gost_number:
                        print(f"       Номер ГОСТ: {gost_number}")
                break
        
        if section_idx is None:
            print(f"    ❌ [ABBREV] Раздел НЕ НАЙДЕН!")
            return ""
        
        # === ШАГ 2: Собираем содержимое раздела ===
        section_content = []
        limit = min(section_idx + 100, len(nodes))
        
        for i in range(section_idx, limit):
            node = nodes[i]
            
            if not hasattr(node, 'text') or not node.text:
                continue
            
            text = node.text.strip()
            if not text:
                continue
            
            # Если это HeadingNode уровня 1 (кроме самого первого) — конец раздела
            if isinstance(node, HeadingNode) and i > section_idx and node.level == 1:
                print(f"    📍 [ABBREV] Конец раздела: достигнут HeadingNode уровня 1 на позиции {i}")
                break
            
            # Если это ListNode — пропускаем (это может быть сам раздел или список внутри)
            if isinstance(node, ListNode):
                continue
            
            # Формируем строку для контекста
            if i == section_idx:
                # Сам заголовок раздела
                # Проверяем наличие номера
                number = ""
                if hasattr(node, 'metadata') and node.metadata:
                    number = node.metadata.get('gost_number', '')
                
                if not number:
                    # Пытаемся извлечь номер из текста
                    number_match = re.match(r'^(\d+(?:\.\d+)*)\s+', text)
                    if number_match:
                        number = number_match.group(1)
                
                if number:
                    section_content.append(f"[ЗАГОЛОВОК РАЗДЕЛА] {number} {text}")
                else:
                    section_content.append(f"[ЗАГОЛОВОК РАЗДЕЛА] {text}")
            
            elif isinstance(node, HeadingNode):
                # Подзаголовок как HeadingNode
                number = node.metadata.get('gost_number', '') if hasattr(node, 'metadata') else ''
                if number:
                    section_content.append(f"[ПОДЗАГОЛОВОК] {number} {text}")
                else:
                    # Пытаемся извлечь номер из текста
                    number_match = re.match(r'^(\d+(?:\.\d+)*)\s+', text)
                    if number_match:
                        number = number_match.group(1)
                        section_content.append(f"[ПОДЗАГОЛОВОК] {number} {text}")
                    else:
                        section_content.append(f"[ПОДЗАГОЛОВОК] {text}")
            
            elif isinstance(node, ListItemNode):
                # Пункт списка внутри раздела
                # Проверяем, похож ли на подзаголовок (жирный, короткий)
                is_heading_like = False
                if hasattr(node, 'font') and node.font:
                    if node.font.bold is True:
                        is_heading_like = True
                    if node.font.size_pt and node.font.size_pt >= 15.0:
                        is_heading_like = True
                
                if is_heading_like and len(text) < 100:
                    # Это подзаголовок
                    number_match = re.match(r'^(\d+(?:\.\d+)*)\s+', text)
                    if number_match:
                        number = number_match.group(1)
                        section_content.append(f"[ПОДЗАГОЛОВОК] {number} {text}")
                    else:
                        section_content.append(f"[ПОДЗАГОЛОВОК] {text}")
                else:
                    # Обычный пункт списка
                    section_content.append(text)
            
            elif isinstance(node, ParagraphNode):
                # Параграф
                # Проверяем, похож ли на подзаголовок
                is_heading_like = False
                if hasattr(node, 'font') and node.font:
                    if node.font.bold is True:
                        is_heading_like = True
                    if node.font.size_pt and node.font.size_pt >= 15.0:
                        is_heading_like = True
                if hasattr(node, 'paragraph_props') and node.paragraph_props:
                    if node.paragraph_props.alignment and 'CENTER' in str(node.paragraph_props.alignment).upper():
                        is_heading_like = True
                
                if is_heading_like and len(text) < 100 and not text.endswith('.'):
                    # Это подзаголовок
                    number_match = re.match(r'^(\d+(?:\.\d+)*)\s+', text)
                    if number_match:
                        number = number_match.group(1)
                        section_content.append(f"[ПОДЗАГОЛОВОК] {number} {text}")
                    else:
                        section_content.append(f"[ПОДЗАГОЛОВОК] {text}")
                else:
                    # Обычный параграф
                    section_content.append(text)
        
        result = "\n".join(section_content)
        print(f"    📄 [ABBREV] Извлечено {len(section_content)} строк содержимого")
        return result
    
    def get_system_prompt(self) -> str:
        return """Ты — эксперт по нормоконтролю технической документации.
Твоя задача — проверить раздел "Обозначения и сокращения" на наличие нумерации.

Согласно ГОСТ 7.32 п. 5.2.1, раздел "Обозначения и сокращения" является структурным 
элементом документа и НЕ ДОЛЖЕН нумероваться.

Также внутри этого раздела подпункты "Сокращения", "Индексы" и "Параметры" НЕ ДОЛЖНЫ 
иметь числовой нумерации.

Верни JSON в формате:
{
  "errors": [
    {
      "severity": "error",
      "message": "Раздел 'Обозначения и сокращения' не должен нумероваться, но имеет номер '5'",
      "gost_reference": "ГОСТ 7.32 п. 5.2.1",
      "context": "5 Обозначения и сокращения"
    }
  ]
}

Если ошибок нет, верни:
{"errors": []}"""
    
    def get_user_prompt(self, context: str) -> str:
        return "Проверь следующий раздел документа на наличие нумерации:\n\n" + \
               context + "\n\n" + \
               "Найди все случаи, где:\n" + \
               "1. Заголовок раздела 'Обозначения и сокращения' имеет числовой номер\n" + \
               "2. Подпункты внутри этого раздела ('Сокращения', 'Индексы', 'Параметры') имеют числовые номера\n\n" + \
               "Верни список ошибок в формате JSON."