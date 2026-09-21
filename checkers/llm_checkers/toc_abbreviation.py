from typing import List, Optional
import re
from .base import BaseLLMChecker
from doc_parser.docx_ast_parser import (
    DocumentNode, HeadingNode, ParagraphNode, TableNode, walk_tree
)

import os

from dotenv import load_dotenv
load_dotenv()

MODEL_NAME = os.getenv("MODEL", "cotype_pro_3")
BASE_URL = os.getenv("BASE_URL", "") or None
API_KEY = os.getenv("API_KEY", os.getenv("API", ""))

class TOCAbbreviationChecker(BaseLLMChecker):
    """
    Проверка: в содержании не должно быть аббревиатур в названиях разделов.
    Правильно: "Квалификационные испытания"
    Неправильно: "Квалификационные испытания (КлИ)"
    Требование: ГОСТ 7.32 п. 5.2.2
    """
    
    def __init__(self, api_key: str = API_KEY, model: str = MODEL_NAME, 
                 llm_base_url: str = BASE_URL):
        super().__init__(
            name="toc_abbreviation",
            description="Проверка отсутствия аббревиатур в содержании",
            api_key=api_key,
            model=model,
            llm_base_url=llm_base_url
        )
    
    def extract_context(self, ast_tree: DocumentNode) -> str:
        """Извлекает содержание (оглавление) из документа"""
        nodes = list(walk_tree(ast_tree))
        toc_start_idx = None
        
        # 1. Ищем заголовок "СОДЕРЖАНИЕ" или "ОГЛАВЛЕНИЕ"
        # Приоритет: сначала ищем среди HeadingNode, потом среди ParagraphNode
        for i, node in enumerate(nodes):
            if isinstance(node, HeadingNode):
                text_upper = node.text.upper().strip()
                if text_upper in ("СОДЕРЖАНИЕ", "ОГЛАВЛЕНИЕ"):
                    toc_start_idx = i
                    print(f"    📍 [TOC] Найден заголовок содержания на позиции {i}: '{node.text}'")
                    break
        
        # Если не нашли среди заголовков, ищем среди параграфов
        if toc_start_idx is None:
            for i, node in enumerate(nodes):
                if isinstance(node, ParagraphNode):
                    text = node.text.strip()
                    text_upper = text.upper()
                    # Проверяем, что это именно заголовок (короткий текст, возможно жирный)
                    if (text_upper in ("СОДЕРЖАНИЕ", "ОГЛАВЛЕНИЕ") or 
                        (text_upper.startswith("СОДЕРЖАНИЕ") and len(text) < 30)):
                        # Дополнительно проверяем, что это похоже на заголовок
                        # (например, нет точки в конце, или есть жирный шрифт)
                        if not text.endswith('.') or (node.font and node.font.bold):
                            toc_start_idx = i
                            print(f"    📍 [TOC] Найден параграф содержания на позиции {i}: '{node.text}'")
                            break
        
        if toc_start_idx is None:
            # Резервный вариант: ищем таблицу содержания
            for i, node in enumerate(nodes):
                if isinstance(node, TableNode) and self._looks_like_toc_table(node):
                    print(f"    📍 [TOC] Найдена таблица содержания на позиции {i}")
                    return self._extract_table_text(node)
            print(f"    ⚠️  [TOC] Содержание не найдено!")
            return ""
        
        # 2. Собираем пункты содержания после найденного заголовка
        toc_entries = []
        limit = min(toc_start_idx + 150, len(nodes))  # Увеличили лимит
        
        for i in range(toc_start_idx + 1, limit):
            node = nodes[i]
            if not hasattr(node, 'text') or not node.text:
                continue
            
            text = node.text.strip()
            if not text:
                continue
            
            text_upper = text.upper()
            
            # Стоп-сигнал 1: начало основного текста (Введение, Глава 1 и т.д.)
            if text_upper.startswith("ВВЕДЕНИЕ") or text_upper.startswith("ВВОДНАЯ ЧАСТЬ"):
                print(f"    📍 [TOC] Достигли введения на позиции {i}, останавливаемся")
                break
            
            # Стоп-сигнал 2: если это заголовок уровня 1 с номером (например, "1 Общие положения")
            # и после него нет номеров страниц
            if isinstance(node, HeadingNode) and node.level == 1:
                # Проверяем, есть ли в тексте номер страницы в конце
                if not self._has_page_number(text):
                    print(f"    📍 [TOC] Достигли заголовка раздела без номера страницы на позиции {i}")
                    break
            
            # Стоп-сигнал 3: если это параграф с длинным текстом и без номера страницы
            if isinstance(node, ParagraphNode) and len(text) > 100:
                if not self._has_page_number(text):
                    print(f"    📍 [TOC] Достигли основного текста на позиции {i}")
                    break
            
            # Проверяем, похоже ли это на пункт содержания
            # Пункт содержания обычно: "1 Введение ......... 5" или "1.1 Общие положения .... 12"
            if self._looks_like_toc_entry(text):
                toc_entries.append(text)
            elif len(toc_entries) > 0:
                # Если уже собрали несколько пунктов, но текущий не похож на пункт содержания,
                # возможно, содержание закончилось
                if len(text) > 80 and not self._has_page_number(text):
                    print(f"    📍 [TOC] Достигли конца содержания на позиции {i}")
                    break
        
        result = "\n".join(toc_entries)
        print(f"    📄 [TOC] Извлечено {len(toc_entries)} пунктов содержания")
        return result
    
    def _has_page_number(self, text: str) -> bool:
        """Проверяет, есть ли в тексте номер страницы в конце"""
        # Ищем цифры в конце строки (возможно, после точек или пробелов)
        # Примеры: "1 Введение ......... 5", "1.1 Общие положения .... 12"
        match = re.search(r'[\s.]+(\d+)\s*$', text)
        return match is not None
    
    def _looks_like_toc_entry(self, text: str) -> bool:
        """Проверяет, похож ли текст на пункт содержания"""
        # Пункт содержания обычно начинается с цифры (номера раздела)
        # и содержит номер страницы в конце
        if not text:
            return False
        
        # Проверяем, начинается ли с цифры
        if not text[0].isdigit():
            return False
        
        # Проверяем, есть ли номер страницы в конце
        return self._has_page_number(text)
    
    def _looks_like_toc_table(self, table: TableNode) -> bool:
        """Проверяет, похожа ли таблица на содержание"""
        if not table.children or len(table.children) < 3:
            return False
        
        first_row = table.children[0]
        if len(first_row.children) != 2:
            return False
        
        numbers_found = 0
        for row in table.children[:5]:
            if len(row.children) >= 2:
                cell_text = row.children[1].text.strip()
                if re.search(r'\d+', cell_text):
                    numbers_found += 1
        
        return numbers_found >= 2
    
    def _extract_table_text(self, table: TableNode) -> str:
        """Извлекает текст из таблицы содержания"""
        entries = []
        for row in table.children:
            if len(row.children) >= 1:
                entries.append(row.children[0].text.strip())
        return "\n".join(entries)
    
    def get_system_prompt(self) -> str:
        # Убрали пробелы в JSON-ключах и упростили формат
        return """Ты — эксперт по нормоконтролю технической документации.
Твоя задача — проверить содержание (оглавление) документа на наличие аббревиатур.

Аббревиатура — это сокращённое обозначение, обычно в скобках, например:
"Квалификационные испытания (КлИ)"
"Технические требования (ТТ)"
"Испытания на надёжность (ИспН)"

В содержании НЕ ДОЛЖНО быть аббревиатур. Названия разделов должны быть полными.

Правильно: "Квалификационные испытания"
Неправильно: "Квалификационные испытания (КлИ)"

Верни JSON в формате:
{
  "errors": [
    {
      "severity": "error",
      "message": "В содержании обнаружена аббревиатура: 'Квалификационные испытания (КлИ)'. Следует использовать полное название",
      "gost_reference": "ГОСТ 7.32 п. 5.2.2",
      "context": "Квалификационные испытания (КлИ)"
    }
  ]
}

Если ошибок нет, верни:
{"errors": []}"""
    
    def get_user_prompt(self, context: str) -> str:
        # Не используем f-string, чтобы избежать проблем с фигурными скобками
        return "Проверь следующее содержание документа на наличие аббревиатур в названиях разделов.\n\n" \
               "Содержание:\n" + context + "\n\n" \
               "Найди все случаи, где в названии раздела есть аббревиатура (обычно в скобках после полного названия).\n" \
               "Верни список ошибок в формате JSON."