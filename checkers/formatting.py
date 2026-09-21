from typing import List, Set, Optional, Dict, Tuple
from collections import Counter
from .base import BaseChecker, Severity
from doc_parser.docx_ast_parser import (
    DocumentNode, HeadingNode, ParagraphNode, TableNode,
    FontProps, ParagraphProps, walk_tree
)
from .docx_footnotes import FootnoteExtractor


class FontFamilyChecker(BaseChecker):
    """
    Проверка гарнитуры шрифта (ГОСТ Р 2.105-2019)
    """
    def __init__(self, max_errors: int = 20):
        super().__init__(
            name="font_family",
            description="Проверка гарнитуры шрифта (Times New Roman или Arial)"
        )
        self.allowed_families = {"Times New Roman", "Arial", "TimesNewRoman", "Times"}
        self.max_errors = max_errors

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        used_families: Set[str] = set()
        invalid_locations: List[Tuple[str, str, str]] = []  # (family, text_preview, node_type)

        for node in walk_tree(ast_tree):
            if isinstance(node, (ParagraphNode, HeadingNode)):
                if node.font and node.font.name:
                    family = node.font.name
                    used_families.add(family)
                    
                    if family not in self.allowed_families:
                        # Определяем тип узла и получаем превью текста
                        if isinstance(node, HeadingNode):
                            node_type = "heading"
                            text_preview = node.text[:60] if node.text else "(пустой заголовок)"
                        else:
                            node_type = "paragraph"
                            text_preview = node.text[:60] if node.text else "(пустой абзац)"
                        
                        invalid_locations.append((family, text_preview, node_type))

        # Выдаём детализированные ошибки для каждого места
        for i, (family, text_preview, node_type) in enumerate(invalid_locations):
            if i >= self.max_errors:
                remaining = len(invalid_locations) - self.max_errors
                self.add_error(
                    severity=Severity.INFO,
                    message=f"И ещё {remaining} мест с недопустимой гарнитурой шрифта",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Гарнитуры шрифтов в документе",
                    node_type="document"
                )
                break
                
            self.add_error(
                severity=Severity.ERROR,
                message=f"Использована недопустимая гарнитура шрифта: '{family}'. "
                        f"ГОСТ требует Times New Roman или Arial",
                gost_ref="ГОСТ Р 2.105-2019",
                context=f"{node_type.capitalize()}: '{text_preview}...'",
                node_type=node_type
            )

        # Дополнительное предупреждение о смешении гарнитур
        if len(used_families) > 1:
            self.add_error(
                severity=Severity.WARNING,
                message=f"В документе используются различные гарнитуры: {', '.join(used_families)}. "
                        f"ГОСТ не допускает смешение гарнитур",
                gost_ref="ГОСТ Р 2.105-2019",
                context="Гарнитуры шрифтов в документе",
                node_type="document"
            )

        return self.errors


class FontSizeChecker(BaseChecker):
    """
    Проверка размеров шрифтов с учетом новой иерархии (main_heading, subheading, paragraph).
    """
    def __init__(self, max_errors: int = 20):
        super().__init__(
            name="font_size",
            description="Проверка размеров шрифтов и их единообразия"
        )
        self.allowed_body_sizes = {14.0, 13.0}
        self.tolerance = 0.2
        self.max_errors = max_errors

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()

        # ==========================================
        # 1. АНАЛИЗ ОСНОВНОГО ТЕКСТА (ParagraphNode)
        # ==========================================
        paragraph_sizes = set()
        invalid_paragraph_locations: List[Tuple[float, str]] = []  # (size, text_preview)

        for node in walk_tree(ast_tree):
            if isinstance(node, ParagraphNode):
                if node.font and node.font.size_pt:
                    size = round(node.font.size_pt, 1)
                    paragraph_sizes.add(size)
                    
                    is_valid = any(abs(size - allowed) <= self.tolerance for allowed in self.allowed_body_sizes)
                    if not is_valid:
                        text_preview = node.text[:60] if node.text else "(пустой абзац)"
                        invalid_paragraph_locations.append((size, text_preview))

        # Выдаём детализированные ошибки для абзацев
        for i, (size, text_preview) in enumerate(invalid_paragraph_locations):
            if i >= self.max_errors:
                remaining = len(invalid_paragraph_locations) - self.max_errors
                self.add_error(
                    severity=Severity.INFO,
                    message=f"И ещё {remaining} абзацев с недопустимым размером шрифта",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Размеры шрифтов основного текста",
                    node_type="document"
                )
                break
                
            self.add_error(
                severity=Severity.ERROR,
                message=f"Недопустимый размер шрифта в абзаце: {size} пт. "
                        f"ГОСТ требует 14 пт (допускается 13 пт)",
                gost_ref="ГОСТ Р 2.105-2019",
                context=f"Абзац: '{text_preview}...'",
                node_type="paragraph"
            )

        # Проверка единообразия: все абзацы должны быть ОДНОГО размера
        valid_paragraph_sizes = {s for s in paragraph_sizes if any(abs(s - a) <= self.tolerance for a in self.allowed_body_sizes)}
        if len(valid_paragraph_sizes) > 1:
            self.add_error(
                severity=Severity.ERROR,
                message=f"В основном тексте используются различные размеры шрифта: "
                        f"{', '.join(map(str, valid_paragraph_sizes))} пт. "
                        f"Все абзацы должны быть набраны одним размером (13 или 14 пт)",
                gost_ref="ГОСТ Р 2.105-2019",
                context="Единообразие размеров шрифта",
                node_type="document"
            )

        # Определяем базовый размер текста для дальнейших проверок заголовков
        base_text_size = 14.0 if 14.0 in valid_paragraph_sizes else (13.0 if 13.0 in valid_paragraph_sizes else 14.0)

        # ==========================================
        # 2. АНАЛИЗ ЗАГОЛОВКОВ (HeadingNode)
        # ==========================================
        main_heading_sizes = set()
        
        for node in walk_tree(ast_tree):
            if isinstance(node, HeadingNode) and node.heading_type == "main_heading":
                if node.font and node.font.size_pt:
                    main_heading_sizes.add(round(node.font.size_pt, 1))

        invalid_heading_locations: List[Tuple[str, float, str, str]] = []  # (heading_type, size, text, issue)

        for node in walk_tree(ast_tree):
            if not isinstance(node, HeadingNode):
                continue

            # --- ОБЩЕЕ ПРАВИЛО: Заголовки не должны заканчиваться точкой ---
            if node.has_trailing_dot:
                self.add_error(
                    severity=Severity.ERROR,
                    message=f"Заголовок не должен заканчиваться точкой",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context=f"Заголовок: '{node.text[:60]}'",
                    node_type="heading"
                )

            # --- ПРАВИЛА ДЛЯ MAIN_HEADING ---
            if node.heading_type == "main_heading":
                if not node.font or not node.font.bold:
                    self.add_error(
                        severity=Severity.ERROR,
                        message=f"Заголовок верхнего уровня должен быть выделен полужирным шрифтом",
                        gost_ref="ГОСТ Р 2.105-2019",
                        context=f"Заголовок: '{node.text[:60]}'",
                        node_type="heading"
                    )
                
                if node.font and node.font.size_pt:
                    size = round(node.font.size_pt, 1)
                    min_allowed = base_text_size + 1.0 - self.tolerance
                    max_allowed = base_text_size + 3.0 + self.tolerance
                    
                    if not (min_allowed <= size <= max_allowed):
                        invalid_heading_locations.append((
                            "main_heading", size, node.text[:60],
                            f"Должен быть на 1-3 пт больше основного текста ({base_text_size} пт)"
                        ))

            # --- ПРАВИЛА ДЛЯ SUBHEADING ---
            elif node.heading_type == "subheading":
                if node.font and node.font.size_pt:
                    size = round(node.font.size_pt, 1)
                    
                    if size < base_text_size - self.tolerance:
                        invalid_heading_locations.append((
                            "subheading", size, node.text[:60],
                            f"Не может быть меньше основного текста ({base_text_size} пт)"
                        ))
                    
                    if size > base_text_size + self.tolerance:
                        if main_heading_sizes:
                            min_main_size = min(main_heading_sizes)
                            if size >= min_main_size - self.tolerance:
                                invalid_heading_locations.append((
                                    "subheading", size, node.text[:60],
                                    f"Должен быть строго меньше размера main_heading ({min_main_size} пт)"
                                ))

        # Выдаём детализированные ошибки для заголовков
        for i, (h_type, size, text, issue) in enumerate(invalid_heading_locations):
            if i >= self.max_errors:
                remaining = len(invalid_heading_locations) - self.max_errors
                self.add_error(
                    severity=Severity.INFO,
                    message=f"И ещё {remaining} заголовков с неправильным размером шрифта",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Размеры шрифтов заголовков",
                    node_type="document"
                )
                break
                
            self.add_error(
                severity=Severity.ERROR,
                message=f"Неправильный размер шрифта заголовка ({h_type}): {size} пт. {issue}",
                gost_ref="ГОСТ Р 2.105-2019",
                context=f"Заголовок: '{text}...'",
                node_type="heading"
            )

        return self.errors


class LineSpacingChecker(BaseChecker):
    """
    Проверка межстрочного интервала (ГОСТ 7.32 п. 5.1.2)
    """
    def __init__(self, max_errors: int = 20):
        super().__init__(
            name="line_spacing",
            description="Проверка межстрочного интервала"
        )
        self.allowed_spacings = {1.5, 2.0}
        self.tolerance = 0.1
        self.max_errors = max_errors

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        invalid_locations: List[Tuple[float, str, str]] = []  # (spacing, text_preview, node_type)

        for node in walk_tree(ast_tree):
            if isinstance(node, (ParagraphNode, HeadingNode)):
                if node.paragraph_props and node.paragraph_props.line_spacing:
                    spacing = node.paragraph_props.line_spacing
                    if isinstance(spacing, (int, float)) and spacing > 10:
                        continue
                    
                    rounded_spacing = round(spacing, 1)
                    is_valid = any(abs(rounded_spacing - allowed) <= self.tolerance for allowed in self.allowed_spacings)
                    if not is_valid:
                        if isinstance(node, HeadingNode):
                            node_type = "heading"
                            text_preview = node.text[:60] if node.text else "(пустой заголовок)"
                        else:
                            node_type = "paragraph"
                            text_preview = node.text[:60] if node.text else "(пустой абзац)"
                        
                        invalid_locations.append((rounded_spacing, text_preview, node_type))

        # Выдаём детализированные ошибки
        for i, (spacing, text_preview, node_type) in enumerate(invalid_locations):
            if i >= self.max_errors:
                remaining = len(invalid_locations) - self.max_errors
                self.add_error(
                    severity=Severity.INFO,
                    message=f"И ещё {remaining} мест с недопустимым межстрочным интервалом",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Межстрочные интервалы в документе",
                    node_type="document"
                )
                break
                
            self.add_error(
                severity=Severity.ERROR,
                message=f"Недопустимый межстрочный интервал: {spacing}. "
                        f"ГОСТ требует полуторный (1.5) или двойной (2.0)",
                gost_ref="ГОСТ Р 2.105-2019",
                context=f"{node_type.capitalize()}: '{text_preview}...'",
                node_type=node_type
            )

        return self.errors


class ParagraphIndentChecker(BaseChecker):
    """
    Проверка абзацного отступа
    Требование: 12.5-17 мм (≈ 35.4-48.2 пт). Проверяем ТОЛЬКО обычные абзацы.
    """
    def __init__(self, max_errors: int = 10):
        super().__init__(
            name="paragraph_indent",
            description="Проверка абзацного отступа (12.5-17 мм)"
        )
        self.min_indent_pt = 35.0
        self.max_indent_pt = 48.5
        self.max_errors = max_errors

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        invalid_locations: List[Tuple[float, str]] = []  # (indent, text_preview)

        for node in walk_tree(ast_tree):
            if isinstance(node, ParagraphNode):
                if node.paragraph_props and node.paragraph_props.first_line_indent_pt is not None:
                    indent = node.paragraph_props.first_line_indent_pt
                    
                    if indent < self.min_indent_pt or indent > self.max_indent_pt:
                        text_preview = node.text[:60] if node.text else "(пустой абзац)"
                        invalid_locations.append((indent, text_preview))

        # Выдаём детализированные ошибки
        for i, (indent, text_preview) in enumerate(invalid_locations):
            if i >= self.max_errors:
                remaining = len(invalid_locations) - self.max_errors
                self.add_error(
                    severity=Severity.INFO,
                    message=f"И ещё {remaining} абзацев с неправильным отступом",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Абзацные отступы",
                    node_type="document"
                )
                break
                
            self.add_error(
                severity=Severity.WARNING,
                message=f"Абзацный отступ {indent:.1f} пт не соответствует "
                        f"требованиям ГОСТ (12.5-17 мм или 35.4-48.2 пт)",
                gost_ref="ГОСТ Р 2.105-2019",
                context=f"Абзац: '{text_preview}...'",
                node_type="paragraph"
            )

        return self.errors


# ==========================================
# Остальные классы оставлены без изменений
# ==========================================

class PageMarginsChecker(BaseChecker):
    def __init__(self, doc_path: Optional[str] = None):
        super().__init__(name="page_margins", description="Проверка полей страницы")
        self.doc_path = doc_path
        self.min_left_right_pt = 8.5
        self.min_top_bottom_pt = 28.3

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        if not self.doc_path:
            self.add_error(severity=Severity.INFO, message="Проверка полей страницы пропущена (не указан путь к документу)", gost_ref="ГОСТ 7.32 п. 5.1.3", context="Поля страницы", node_type="document")
            return self.errors
        try:
            from docx import Document
            doc = Document(self.doc_path)
            for section in doc.sections:
                left_pt = section.left_margin.pt if section.left_margin else 0
                right_pt = section.right_margin.pt if section.right_margin else 0
                top_pt = section.top_margin.pt if section.top_margin else 0
                bottom_pt = section.bottom_margin.pt if section.bottom_margin else 0
                if left_pt < self.min_left_right_pt:
                    self.add_error(severity=Severity.ERROR, message=f"Левое поле {left_pt:.1f} пт меньше допустимого (≥ 3 мм)", gost_ref="ГОСТ 7.32 п. 5.1.3", context="Поля страницы", node_type="document")
                if right_pt < self.min_left_right_pt:
                    self.add_error(severity=Severity.ERROR, message=f"Правое поле {right_pt:.1f} пт меньше допустимого (≥ 3 мм)", gost_ref="ГОСТ 7.32 п. 5.1.3", context="Поля страницы", node_type="document")
                if top_pt < self.min_top_bottom_pt:
                    self.add_error(severity=Severity.ERROR, message=f"Верхнее поле {top_pt:.1f} пт меньше допустимого (≥ 10 мм)", gost_ref="ГОСТ 7.32 п. 5.1.3", context="Поля страницы", node_type="document")
                if bottom_pt < self.min_top_bottom_pt:
                    self.add_error(severity=Severity.ERROR, message=f"Нижнее поле {bottom_pt:.1f} пт меньше допустимого (≥ 10 мм)", gost_ref="ГОСТ 7.32 п. 5.1.3", context="Поля страницы", node_type="document")
                break
        except Exception as e:
            self.add_error(severity=Severity.INFO, message=f"Не удалось проверить поля страницы: {str(e)}", gost_ref="ГОСТ 7.32 п. 5.1.3", context="Поля страницы", node_type="document")
        return self.errors


class TableFontSizeChecker(BaseChecker):
    def __init__(self, body_font_size: float = 14.0):
        super().__init__(name="table_font_size", description="Проверка размеров шрифтов в таблицах")
        self.body_font_size = body_font_size
        self.min_allowed = body_font_size - 2.0
        self.max_allowed = body_font_size - 1.0
        self.tolerance = 0.5

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        table_index = 0
        for node in walk_tree(ast_tree):
            if isinstance(node, TableNode):
                table_index += 1
                self._check_table_fonts(node, table_index)
        return self.errors

    def _check_table_fonts(self, table_node: TableNode, table_index: int):
        header_fonts = table_node.metadata.get("header_fonts", [])
        body_fonts = table_node.metadata.get("body_fonts", [])
        for font_size in header_fonts:
            if font_size > self.body_font_size + self.tolerance:
                self.add_error(severity=Severity.ERROR, message=f"Размер шрифта в заголовках таблицы ({font_size} пт) больше основного текста ({self.body_font_size} пт)", gost_ref="ГОСТ 7.32 п. 5.1.1", context=f"Таблица #{table_index}", node_type="table")
            elif abs(font_size - self.body_font_size) <= self.tolerance:
                self.add_error(severity=Severity.INFO, message=f"Заголовки колонок таблицы набраны шрифтом того же размера, что и основной текст. Рекомендуется уменьшить на 1-2 пт", gost_ref="ГОСТ 7.32 п. 5.1.1", context=f"Таблица #{table_index}", node_type="table")
        for font_size in body_fonts:
            if font_size < self.min_allowed - self.tolerance or font_size > self.max_allowed + self.tolerance:
                if abs(font_size - self.body_font_size) <= self.tolerance:
                    self.add_error(severity=Severity.WARNING, message=f"Размер шрифта в теле таблицы ({font_size} пт) совпадает с основным текстом. Должен быть на 1-2 пт меньше", gost_ref="ГОСТ 7.32 п. 5.1.1", context=f"Таблица #{table_index}", node_type="table")
                else:
                    self.add_error(severity=Severity.WARNING, message=f"Размер шрифта в теле таблицы ({font_size} пт) не соответствует требованиям. Должен быть в диапазоне {self.min_allowed}-{self.max_allowed} пт", gost_ref="ГОСТ 7.32 п. 5.1.1", context=f"Таблица #{table_index}", node_type="table")


class ApplicationFontSizeChecker(BaseChecker):
    def __init__(self, body_font_size: float = 14.0):
        super().__init__(name="application_font_size", description="Проверка размеров шрифтов приложений, примечаний и примеров")
        self.body_font_size = body_font_size
        self.expected_app_size = 12.0 if body_font_size >= 13.0 else (10.0 if body_font_size >= 10.5 else None)
        self.tolerance = 0.5
        self.checked_paragraphs = set()

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        if self.expected_app_size is None:
            self.add_error(severity=Severity.INFO, message=f"Не удалось определить ожидаемый размер шрифта для приложений", gost_ref="ГОСТ 7.32 п. 5.1.1", context="Приложения", node_type="document")
            return self.errors
        nodes = list(walk_tree(ast_tree))
        self._check_applications(nodes)
        return self.errors

    def _check_applications(self, nodes: List):
        for i, node in enumerate(nodes):
            if not isinstance(node, HeadingNode) or node.level != 1: continue
            text_upper = node.text.upper().strip()
            if not text_upper.startswith("ПРИЛОЖЕНИЕ"): continue
            if len(text_upper) > len("ПРИЛОЖЕНИЕ"):
                next_char = text_upper[len("ПРИЛОЖЕНИЕ")]
                if not (next_char.isspace() or next_char.isdigit() or next_char.isalpha()): continue
            self._check_section_content(nodes, i + 1, "приложение")

    def _check_section_content(self, nodes: List, start_idx: int, section_type: str):
        section_heading = nodes[start_idx - 1]
        section_level = section_heading.level if isinstance(section_heading, HeadingNode) else 1
        for i in range(start_idx, len(nodes)):
            node = nodes[i]
            if isinstance(node, HeadingNode) and node.level <= section_level: break
            if isinstance(node, ParagraphNode):
                node_id = id(node)
                if node_id in self.checked_paragraphs: continue
                self.checked_paragraphs.add(node_id)
                self._check_paragraph_font(node, section_type)

    def _check_paragraph_font(self, node: ParagraphNode, context_type: str):
        if not node.font or not node.font.size_pt: return
        actual_size = node.font.size_pt
        if abs(actual_size - self.expected_app_size) > self.tolerance:
            self.add_error(severity=Severity.WARNING, message=f"Размер шрифта в {context_type} ({actual_size} пт) не соответствует ожидаемому ({self.expected_app_size} пт)", gost_ref="ГОСТ 7.32 п. 5.1.1", context=f"Текст: '{node.text[:60]}...'", node_type="paragraph")


class FootnoteFontSizeChecker(BaseChecker):
    def __init__(self, body_font_size: float = 14.0, doc_path: Optional[str] = None):
        super().__init__(name="footnote_font_size", description="Проверка размеров шрифтов сносок")
        self.body_font_size = body_font_size
        self.doc_path = doc_path
        self.expected_size = 12.0 if body_font_size >= 13.0 else (10.0 if body_font_size >= 10.5 else None)
        self.tolerance = 0.5

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        if self.expected_size is None:
            self.add_error(severity=Severity.INFO, message=f"Не удалось определить ожидаемый размер шрифта для сносок", gost_ref="ГОСТ 7.32 п. 5.1.1", context="Сноски", node_type="document")
            return self.errors
        if not self.doc_path:
            self.add_error(severity=Severity.INFO, message="Проверка сносок пропущена (не указан путь к документу)", gost_ref="ГОСТ 7.32 п. 5.1.1", context="Сноски", node_type="document")
            return self.errors
        try:
            extractor = FootnoteExtractor(self.doc_path)
            footnotes = extractor.extract_footnotes()
            self._check_footnotes(footnotes, "нижняя сноска")
            endnotes = extractor.extract_endnotes()
            self._check_footnotes(endnotes, "концевая сноска")
        except Exception as e:
            self.add_error(severity=Severity.INFO, message=f"Не удалось проверить сноски: {str(e)}", gost_ref="ГОСТ 7.32 п. 5.1.1", context="Сноски", node_type="document")
        return self.errors

    def _check_footnotes(self, footnotes: List[Dict], footnote_type: str):
        for fn in footnotes:
            fonts = fn.get("fonts", [])
            if not fonts: continue
            for font_size in fonts:
                if abs(font_size - self.expected_size) > self.tolerance:
                    self.add_error(severity=Severity.WARNING, message=f"Размер шрифта {footnote_type} #{fn['id']} ({font_size} пт) не соответствует ожидаемому ({self.expected_size} пт)", gost_ref="ГОСТ 7.32 п. 5.1.1", context=f"Текст сноски: '{fn['text'][:60]}...'", node_type="footnote")