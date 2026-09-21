import json
from typing import List, Optional, Union, Literal, Any, Tuple
from dataclasses import dataclass, field, fields, is_dataclass # <-- добавили is_dataclass
from docx import Document
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
import json
from pathlib import Path
import re

from .style_resolver import (
    resolve_paragraph_property, 
    resolve_run_property, 
    get_run_spacing_pt  # <-- Импортируем новую функцию
)

# ==========================================
# 1. Определение узлов AST (Модели данных)
# ==========================================

@dataclass
class FontProps:
    """Свойства шрифта"""
    name: Optional[str] = None
    size_pt: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    spacing_pt: Optional[float] = None  # <-- НОВОЕ: разрядка в пунктах

@dataclass
class ParagraphProps:
    """Свойства абзаца"""
    alignment: Optional[str] = None
    first_line_indent_pt: Optional[float] = None
    line_spacing: Optional[float] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None

@dataclass
class ASTNode:
    """Базовый узел дерева"""
    node_type: str
    text: str = ""
    font: Optional[FontProps] = None
    paragraph_props: Optional[ParagraphProps] = None
    metadata: dict = field(default_factory=dict)
    children: List['ASTNode'] = field(default_factory=list)
    _source_ref: Any = field(default=None, repr=False, compare=False)  # Оставляем только здесь

@dataclass
class HeadingNode(ASTNode):
    node_type: Literal["heading"] = "heading"
    level: int = 1
    heading_type: str = "main_heading"  # <-- НОВОЕ: "main_heading" или "subheading"
    has_trailing_dot: bool = False      # Критично для ГОСТ: точка в конце заголовка

@dataclass
class ParagraphNode(ASTNode):
    node_type: Literal["paragraph"] = "paragraph"

@dataclass
class ListItemNode(ASTNode):
    node_type: Literal["list_item"] = "list_item"
    list_level: int = 0

@dataclass
class ListNode(ASTNode):
    node_type: Literal["list"] = "list"
    list_style: str = "numeric" # numeric, bullet, letter

@dataclass
class TableCellNode(ASTNode):
    node_type: Literal["table_cell"] = "table_cell"
    row_span: int = 1
    col_span: int = 1

@dataclass
class TableRowNode(ASTNode):
    node_type: Literal["table_row"] = "table_row"

@dataclass
class TableNode(ASTNode):
    node_type: Literal["table"] = "table"
    caption: Optional[str] = None # Название таблицы (обычно сверху)

@dataclass
class ImageNode(ASTNode):
    node_type: Literal["image"] = "image"
    caption: Optional[str] = None # Подпись рисунка (обычно снизу)

@dataclass
class DocumentNode(ASTNode):
    node_type: Literal["document"] = "document"
    title: Optional[str] = None

# ==========================================
# 2. Парсер DOCX -> AST
# ==========================================
def _detect_gost_heading(text: str) -> Optional[Tuple[str, int, str, str]]:
    """
    Определяет заголовок ГОСТ по нумерации.
    Возвращает кортеж: (номер, уровень, текст_заголовка, тип_заголовка) или None.
    
    Правила:
    - 1 цифра (1, 2) -> main_heading (уровень 1)
    - 2 цифры (1.1, 5.11) -> subheading (уровень 2)
    - 3 и более цифры (1.1.1) -> НЕ заголовок (возвращаем None)
    """
    if not text or text.endswith('.'):
        return None  # Заголовки не заканчиваются точкой

    # Ищем паттерн: цифры, возможно разделенные точками, затем пробел и текст
    match = re.match(r"^(?P<num>\d+(?:\.\d+)*)\s+(?P<text>.+)$", text)
    if not match:
        return None

    num_str = match.group('num')
    parts = num_str.split('.')
    heading_text = match.group('text')

    # ПРАВИЛО 1: 3 и более частей (например, 1.2.1) - это обычный текст
    if len(parts) >= 3:
        return None

    # ПРАВИЛО 2: 1 часть (например, 5) - main_heading
    if len(parts) == 1:
        # Защита от ложных срабатываний на обычный текст, начинающийся с цифры
        if len(text) < 150 and re.match(r"^[А-Яа-яЁёA-Za-z]", heading_text):
            return num_str, 1, heading_text, "main_heading"
        return None

    # ПРАВИЛО 3: 2 части (например, 5.11) - subheading
    if len(parts) == 2:
        return num_str, 2, heading_text, "subheading"

    return None

class DocxASTParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = Document(file_path)
        self.raw_elements = []

    def parse(self) -> DocumentNode:
        """Главный метод: возвращает корневой узел AST с иерархией"""
        # 1. Извлекаем плоский список элементов (включая недостающий метод _extract_raw_elements)
        self._extract_raw_elements()
        
        # 2. Группируем списки
        grouped_elements = self._group_lists(self.raw_elements)
        
        # 3. Строим иерархию заголовков
        hierarchical_elements = self._build_heading_hierarchy(grouped_elements)
        
        root = DocumentNode(text="Root")
        root.children = hierarchical_elements
        
        if root.children and isinstance(root.children[0], HeadingNode) and root.children[0].level == 1:
            root.title = root.children[0].text
            
        return root

    def _extract_raw_elements(self):
        """
        ИЗВЛЕЧЕННЫЕ ПАРАГРАФЫ И ТАБЛИЦЫ В СТРОГОМ ПОРЯДКЕ.
        (Этот метод отсутствовал в вашем коде, из-за чего была ошибка)
        """
        self.raw_elements = []
        body = self.doc.element.body
        for child in body.iterchildren():
            if child.tag == qn('w:p'):
                node = self._parse_paragraph(child)
                if node:
                    self.raw_elements.append(node)
            elif child.tag == qn('w:tbl'):
                node = self._parse_table(child)
                if node:
                    self.raw_elements.append(node)

    def _parse_paragraph(self, p_xml) -> Optional[ASTNode]:
        """Парсит XML-узел параграфа с правильным приоритетом: Списки > Заголовки по тексту > Заголовки по стилю > Текст"""
        from docx.text.paragraph import Paragraph
        p_obj = Paragraph(p_xml, self.doc)
        text = p_obj.text.strip()
        
        if not text:
            return None

        has_image = bool(
            p_xml.findall('.//' + qn('w:drawing')) or 
            p_xml.findall('.//' + qn('w:pict'))
        )

        # ==========================================
        # Извлекаем свойства шрифта и абзаца (без изменений)
        # ==========================================
        font_props = FontProps()
        if p_obj.runs:
            first_run = p_obj.runs[0]
            font_props.name = resolve_run_property(first_run, p_obj, 'name')
            size = resolve_run_property(first_run, p_obj, 'size')
            font_props.size_pt = size.pt if size else None
            font_props.bold = resolve_run_property(first_run, p_obj, 'bold')
            font_props.italic = resolve_run_property(first_run, p_obj, 'italic')
            font_props.underline = resolve_run_property(first_run, p_obj, 'underline')
            font_props.spacing_pt = get_run_spacing_pt(first_run)        

        para_props = ParagraphProps()
        alignment = resolve_paragraph_property(p_obj, 'alignment')
        para_props.alignment = str(alignment) if alignment else None
        first_indent = resolve_paragraph_property(p_obj, 'first_line_indent')
        para_props.first_line_indent_pt = first_indent.pt if first_indent else None
        left_indent = resolve_paragraph_property(p_obj, 'left_indent')
        para_props.left_indent_pt = left_indent.pt if left_indent else None
        right_indent = resolve_paragraph_property(p_obj, 'right_indent')
        para_props.right_indent_pt = right_indent.pt if right_indent else None
        line_spacing = resolve_paragraph_property(p_obj, 'line_spacing')
        para_props.line_spacing = line_spacing
        space_before = resolve_paragraph_property(p_obj, 'space_before')
        para_props.space_before_pt = space_before.pt if space_before else None
        space_after = resolve_paragraph_property(p_obj, 'space_after')
        para_props.space_after_pt = space_after.pt if space_after else None

        # Получаем имя стиля сразу, оно нужно для всех проверок
        style_name = p_obj.style.name.lower() if p_obj.style else ""

        # ==========================================
        # ШАГ 1: ЯВНАЯ ДЕТЕКЦИЯ СПИСКОВ (САМЫЙ ВЫСОКИЙ ПРИОРИТЕТ)
        # Если в XML есть тег w:numPr или стиль содержит "список/list", 
        # то это ТОЧНО список, даже если текст выглядит как "1.1 Текст".
        # ==========================================
        is_list = 'список' in style_name or 'list' in style_name
        if not is_list:
            pPr = p_xml.find(qn('w:pPr'))
            if pPr is not None and pPr.find(qn('w:numPr')) is not None:
                is_list = True

        if is_list:
            node = ListItemNode(
                text=text, 
                font=font_props, 
                paragraph_props=para_props, 
                metadata={"style": p_obj.style.name, "detected_by": "xml_or_style"}
            )
            node._source_ref = p_obj
            return node

        # ==========================================
        # ШАГ 2: ПОИСК ЗАГОЛОВКОВ ПО НУМЕРАЦИИ ГОСТ (ТОЛЬКО ДЛЯ НЕ-СПИСКОВ)
        # Сюда мы попадаем только если Word НЕ считает этот абзац списком.
        # ==========================================
        heading_data = _detect_gost_heading(text)
        if heading_data:
            num_str, level, heading_text, h_type = heading_data
            node = HeadingNode(
                text=heading_text, 
                level=level,
                heading_type=h_type,
                has_trailing_dot=heading_text.endswith('.'),
                font=font_props,
                paragraph_props=para_props,
                metadata={"style": p_obj.style.name, "gost_number": num_str}
            )
            node._source_ref = p_obj
            return node

        # ==========================================
        # ШАГ 3: ПОИСК ЗАГОЛОВКОВ ПО СТИЛЯМ WORD (Fallback)
        # ==========================================
        if 'заголовок' in style_name or 'heading' in style_name:
            level = 1
            for char in style_name:
                if char.isdigit():
                    level = int(char)
                    break
            node = HeadingNode(
                text=text,
                level=level,
                heading_type="main_heading" if level == 1 else "subheading", # Уточняем тип
                has_trailing_dot=text.endswith('.'),
                font=font_props,
                paragraph_props=para_props,
                metadata={"style": p_obj.style.name, "detected_by": "style"}
            )
            node._source_ref = p_obj
            return node

        # ==========================================
        # ШАГ 4: ИЗОБРАЖЕНИЯ И ОБЫЧНЫЕ ПАРАГРАФЫ
        # ==========================================
        if has_image and not text:
            node = ImageNode(metadata={"has_image": True})
            node._source_ref = p_obj
            return node

        if has_image and text:
            if text.lower().startswith('рис') or text.lower().startswith('figure'):
                node = ImageNode(text=text, caption=text)
                node._source_ref = p_obj
                return node

        node = ParagraphNode(
            text=text, 
            font=font_props, 
            paragraph_props=para_props, 
            metadata={"style": p_obj.style.name}
        )
        node._source_ref = p_obj
        return node

    def _build_heading_hierarchy(self, flat_nodes: List[ASTNode]) -> List[ASTNode]:
        """
        Превращает плоский список узлов в иерархическое дерево.
        """
        root_nodes = []
        stack = {} # Стек текущих заголовков: {level: HeadingNode}
        
        for node in flat_nodes:
            if isinstance(node, HeadingNode):
                level = node.level
                
                # Удаляем из стека заголовки текущего и более глубокого уровня
                for lvl in list(stack.keys()):
                    if lvl >= level:
                        del stack[lvl]
                
                # Ищем родителя
                parent_level = level - 1
                if parent_level in stack:
                    stack[parent_level].children.append(node)
                else:
                    root_nodes.append(node)
                    
                stack[level] = node
            else:
                # Обычный узел добавляем к самому глубокому текущему заголовку
                if stack:
                    max_lvl = max(stack.keys())
                    stack[max_lvl].children.append(node)
                else:
                    root_nodes.append(node)
                    
        return root_nodes

    def _parse_table(self, tbl_xml) -> TableNode:
        """Парсит XML-узел таблицы"""
        from docx.table import Table
        tbl_obj = Table(tbl_xml, self.doc)
        table_node = TableNode()
        
        header_fonts = set()
        body_fonts = set()
        
        for row_idx, row in enumerate(tbl_obj.rows):
            row_node = TableRowNode()
            for cell in row.cells:
                cell_text = cell.text.strip()
                cell_fonts = self._extract_cell_fonts(cell)
                
                if row_idx == 0:
                    header_fonts.update(cell_fonts)
                else:
                    body_fonts.update(cell_fonts)
                    
                cell_node = TableCellNode(
                    text=cell_text,
                    metadata={
                        "fonts": list(cell_fonts),
                        "is_header_row": row_idx == 0
                    }
                )
                row_node.children.append(cell_node)
            table_node.children.append(row_node)
            
        table_node.metadata["header_fonts"] = list(header_fonts)
        table_node.metadata["body_fonts"] = list(body_fonts)
        table_node._source_ref = tbl_obj   
        return table_node

    def _extract_cell_fonts(self, cell) -> set:
        """Извлекает размеры шрифтов из ячейки таблицы"""
        fonts = set()
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                size = self._resolve_font_size(run)
                if size is not None:
                    fonts.add(size)
        return fonts

    def _group_lists(self, elements: List[ASTNode]) -> List[ASTNode]:
        """
        Группирует последовательные ListItemNode в единый ListNode.
        
        ВАЖНО: Игнорирует пустые абзацы (пустые строки) внутри списка,
        так как в технической документации авторы часто разделяют пункты
        списка пустыми строками, что не должно разрывать логический список.
        """
        grouped = []
        current_list = None
        pending_empty_paras = [] # Буфер для пустых абзацев, встретившихся внутри списка

        for el in elements:
            if isinstance(el, ListItemNode):
                if current_list is None:
                    current_list = ListNode()
                current_list.children.append(el)
                # Пункт списка найден, сбрасываем буфер пустых абзацев
                pending_empty_paras = [] 
                
            elif isinstance(el, ParagraphNode) and not el.text.strip():
                # Это пустой абзац (пустая строка)
                if current_list is not None:
                    # Если мы уже внутри списка, просто запоминаем пустой абзац,
                    # но НЕ закрываем список.
                    pending_empty_paras.append(el)
                else:
                    # Если списка нет, добавляем пустой абзац в общий поток как обычно
                    grouped.append(el)
                    
            else:
                # Любой другой элемент (обычный параграф с текстом, таблица, заголовок)
                if current_list is not None:
                    grouped.append(current_list)
                    current_list = None
                    # Возвращаем накопленные пустые абзацы в общий поток
                    grouped.extend(pending_empty_paras)
                    pending_empty_paras = []
                grouped.append(el)

        # Финализация: если документ заканчивается списком
        if current_list is not None:
            grouped.append(current_list)
        grouped.extend(pending_empty_paras)

        return grouped

    def _resolve_font_size(self, run) -> Optional[float]:
        """Определяет размер шрифта с учётом наследования стилей."""
        if run.font.size:
            return run.font.size.pt
        
        paragraph = run._element.getparent()
        if paragraph is not None:
            try:
                from docx.text.paragraph import Paragraph
                p_obj = Paragraph(paragraph, self.doc)
                style = p_obj.style
                while style:
                    if style.font.size:
                        return style.font.size.pt
                    style = style.base_style
            except Exception:
                pass
                
        try:
            default_style = self.doc.styles['Normal']
            if default_style.font.size:
                return default_style.font.size.pt
        except Exception:
            pass
        return None


# ==========================================
# 3. Утилиты для работы с AST
# ==========================================

def ast_to_dict(obj: Any) -> Any:
    """
    Рекурсивно конвертирует AST и все вложенные датаклассы (FontProps, ParagraphProps) 
    в словари для сериализации в JSON.
    Игнорирует поле _source_ref и конвертирует set в list.
    """
    # 1. Если это датакласс (ASTNode, FontProps, ParagraphProps и т.д.)
    if is_dataclass(obj):
        result = {}
        for f in fields(obj):
            # Полностью игнорируем ссылку на исходный объект docx/lxml
            if f.name == '_source_ref':
                continue
                
            value = getattr(obj, f.name)
            result[f.name] = ast_to_dict(value)
            
        # Убираем пустые списки и словари для чистоты и экономии места в JSON
        if not result.get('children'):
            result.pop('children', None)
        if not result.get('metadata'):
            result.pop('metadata', None)
            
        return result
        
    # 2. Рекурсивная обработка списков
    elif isinstance(obj, list):
        return [ast_to_dict(item) for item in obj]
        
    # 3. Рекурсивная обработка словарей
    elif isinstance(obj, dict):
        return {k: ast_to_dict(v) for k, v in obj.items()}
        
    # 4. Обработка множеств (на случай, если где-то затесался set, json его не ест)
    elif isinstance(obj, set):
        return list(obj)
        
    # 5. Базовые типы (str, int, float, bool, None) возвращаем как есть
    else:
        return obj

def ast_to_markdown(node: ASTNode, level=0) -> str:
    indent = "  " * level
    md = ""
    
    if isinstance(node, DocumentNode):
        for child in node.children:
            md += ast_to_markdown(child, level)
            
    elif isinstance(node, HeadingNode):
        # Добавляем пометку типа заголовка в квадратные скобки
        type_mark = f"[{node.heading_type.upper()}]"
        dot_warning = " [ВНИМАНИЕ: есть точка в конце]" if node.has_trailing_dot else ""
        md += f"{indent}{'#' * node.level} {type_mark} {node.text}{dot_warning}\n"
        
    elif isinstance(node, ParagraphNode):
        md += f"{indent}{node.text}\n"
        
    elif isinstance(node, ListNode):
        md += f"{indent}[LIST START]\n"
        for i, item in enumerate(node.children):
            md += ast_to_markdown(item, level + 1)
        md += f"{indent}[LIST END]\n"
    elif isinstance(node, ListItemNode):
        md += f"{indent}- {node.text}\n"
    elif isinstance(node, TableNode):
        md += f"{indent}[TABLE {len(node.children)} rows x {len(node.children[0].children) if node.children else 0} cols]\n"
    elif isinstance(node, ImageNode):
        md += f"{indent}[IMAGE] {node.caption or node.text}\n"
    else:
        if node.text:
            md += f"{indent}{node.text}\n"
    return md

def save_ast_to_json(ast_tree: DocumentNode, output_path: str, pretty: bool = True) -> None:
    """
    Сохраняет AST-дерево в JSON файл.
    
    Args:
        ast_tree: Корневой узел AST (DocumentNode)
        output_path: Путь к выходному файлу
        pretty: Если True, форматирует JSON с отступами для читаемости
    """
    # Конвертируем AST в словарь
    ast_dict = ast_to_dict(ast_tree)
    
    # Параметры сериализации
    kwargs = {
        'ensure_ascii': False,  # Сохраняем кириллицу как есть, а не \uXXXX
        'indent': 2 if pretty else None,  # Красивый вывод или компактный
    }
    
    # Создаем директорию, если её нет
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем в файл
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ast_dict, f, **kwargs)
    
    print(f"AST сохранен в {output_path}")


def load_ast_from_json(json_path: str) -> dict:
    """
    Загружает AST из JSON файла обратно в словарь.
    (Обратите внимание: загружается dict, а не объекты ASTNode)
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ==========================================
# 4. Утилиты для работы с AST
# ==========================================

def walk_tree(node: ASTNode):
    """
    Рекурсивный обход AST-дерева.
    Возвращает все узлы дерева в порядке обхода (depth-first).
    
    Args:
        node: Начальный узел (обычно корневой DocumentNode)
    
    Yields:
        Каждый узел дерева (включая сам начальный узел)
    
    Example:
        for node in walk_tree(ast_tree):
            if isinstance(node, HeadingNode):
                print(node.text)
    """
    yield node
    for child in node.children:
        yield from walk_tree(child)


def walk_tree_by_type(node: ASTNode, node_type: type):
    """
    Обход дерева с фильтрацией по типу узла.
    
    Args:
        node: Начальный узел
        node_type: Тип узла для фильтрации (например, HeadingNode)
    
    Yields:
        Только узлы указанного типа
    
    Example:
        for heading in walk_tree_by_type(ast_tree, HeadingNode):
            print(f"Заголовок: {heading.text}")
    """
    for n in walk_tree(node):
        if isinstance(n, node_type):
            yield n

# ==========================================
# 4. Пример использования
# ==========================================

if __name__ == "__main__":
    # Предположим, у нас есть файл test_gost.docx
    parser = DocxASTParser("input/test.docx")
    ast_tree = parser.parse()
    save_ast_to_json(ast_tree, "output/ast_tree.json", pretty=True)

    
    print("--- JSON AST (фрагмент) ---")
    print(json.dumps(ast_to_dict(ast_tree.children[40]), indent=2, ensure_ascii=False))
    
    print("\n--- Markdown для LLM (фрагмент) ---")
    print(ast_to_markdown(ast_tree)[:2000])
    pass