from typing import List, Optional
import re
from .base import BaseChecker, Severity
from doc_parser.docx_ast_parser import (
    DocumentNode, HeadingNode, ParagraphNode,
    FontProps, walk_tree, walk_tree_by_type
)


class HeadingCapitalizationChecker(BaseChecker):
    """
    Проверка: заголовки с прописной буквы (ГОСТ 7.32 п. 6.6.2)
    Требование: заголовки следует печатать с прописной буквы.
    """
    def __init__(self):
        super().__init__(
            name="heading_capitalization",
            description="Проверка начала заголовка с прописной буквы"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree_by_type(ast_tree, HeadingNode):
            text = node.text.strip()
            if not text:
                continue
            # В новом парсере номер уже убран из node.text,
            # поэтому первая буква текста — это и есть первая буква заголовка
            first_letter = None
            for ch in text:
                if ch.isalpha():
                    first_letter = ch
                    break
            if first_letter and not first_letter.isupper():
                self.add_error(
                    severity=Severity.ERROR,
                    message=f"Заголовок должен начинаться с прописной буквы",
                    gost_ref="ГОСТ 7.32 п. 6.6.2",
                    context=f"Заголовок: '{text[:80]}'",
                    node_type="heading"
                )
        return self.errors


class HeadingDotChecker(BaseChecker):
    """
    Проверка: без точки в конце заголовка (ГОСТ 7.32 п. 6.6.2)
    Примечание: эта проверка также выполняется в FontSizeChecker (formatting.py).
    Оставлена здесь для полноты структурных проверок.
    """
    def __init__(self):
        super().__init__(
            name="heading_dot",
            description="Проверка отсутствия точки в конце заголовка"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree_by_type(ast_tree, HeadingNode):
            text = node.text.strip()
            if not text:
                continue
            # Используем поле has_trailing_dot из нового парсера
            if node.has_trailing_dot:
                self.add_error(
                    severity=Severity.ERROR,
                    message="Заголовок не должен заканчиваться точкой",
                    gost_ref="ГОСТ 7.32 п. 6.6.2",
                    context=f"Заголовок: '{text[:80]}'",
                    node_type="heading"
                )
        return self.errors


class HeadingBoldChecker(BaseChecker):
    """
    Проверка: заголовки разделов полужирным шрифтом (ГОСТ 7.32 п. 6.6.2)
    Требование: только main_heading печатают полужирным шрифтом.
    """
    def __init__(self):
        super().__init__(
            name="heading_bold",
            description="Проверка полужирного начертания заголовков разделов"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree_by_type(ast_tree, HeadingNode):
            # ИСПРАВЛЕНО: используем heading_type вместо level
            if node.heading_type != "main_heading":
                continue
            if not node.text.strip():
                continue
            if not node.font or node.font.bold is not True:
                self.add_error(
                    severity=Severity.ERROR,
                    message="Заголовок раздела должен быть выделен полужирным шрифтом",
                    gost_ref="ГОСТ 7.32 п. 6.6.2",
                    context=f"Заголовок: '{node.text[:80]}'",
                    node_type="heading"
                )
        return self.errors


class HeadingUnderlineChecker(BaseChecker):
    """
    Проверка: заголовки не подчёркивать (ГОСТ 7.32 п. 6.6.2)
    """
    def __init__(self):
        super().__init__(
            name="heading_underline",
            description="Проверка отсутствия подчёркивания в заголовках"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree_by_type(ast_tree, HeadingNode):
            if not node.text.strip():
                continue
            if node.font and node.font.underline is True:
                self.add_error(
                    severity=Severity.ERROR,
                    message="Заголовок не должен быть подчёркнут",
                    gost_ref="ГОСТ 7.32 п. 6.6.2",
                    context=f"Заголовок: '{node.text[:80]}'",
                    node_type="heading"
                )
        return self.errors


class HeadingHyphenationChecker(BaseChecker):
    """
    Проверка: переносы слов в заголовках не допускаются (ГОСТ 7.32 п. 6.6.2)
    """
    def __init__(self):
        super().__init__(
            name="heading_hyphenation",
            description="Проверка отсутствия переносов слов в заголовках"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree_by_type(ast_tree, HeadingNode):
            if '\u00AD' in node.text:
                self.add_error(
                    severity=Severity.ERROR,
                    message="Переносы слов в заголовках не допускаются",
                    gost_ref="ГОСТ 7.32 п. 6.6.2",
                    context=f"Заголовок: '{node.text[:80]}'",
                    node_type="heading"
                )
        return self.errors


class HeadingTwoSentencesChecker(BaseChecker):
    """
    Проверка: два предложения в заголовке разделяют точкой (ГОСТ 7.32 п. 6.6.2)
    """
    def __init__(self):
        super().__init__(
            name="heading_two_sentences",
            description="Проверка разделения предложений в заголовке точкой"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree_by_type(ast_tree, HeadingNode):
            text = node.text.strip()
            if not text:
                continue
            # ИСПРАВЛЕНО: убран бесполезный regex для удаления номера.
            # В новом парсере node.text уже не содержит номера.
            if len(text) > 120 and '.' not in text:
                self.add_error(
                    severity=Severity.WARNING,
                    message="Заголовок очень длинный и, возможно, состоит из двух "
                            "предложений. Если это так, их следует разделить точкой",
                    gost_ref="ГОСТ 7.32 п. 6.6.2",
                    context=f"Заголовок: '{text[:80]}...'",
                    node_type="heading"
                )
        return self.errors


class HeadingNewPageChecker(BaseChecker):
    """
    Проверка: каждый раздел рекомендуется начинать с нового листа (ГОСТ 7.32 п. 6.6.5)
    """
    def __init__(self):
        super().__init__(
            name="heading_new_page",
            description="Проверка начала разделов с нового листа (рекомендация)"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        nodes = list(walk_tree(ast_tree))
        for i, node in enumerate(nodes):
            if not isinstance(node, HeadingNode):
                continue
            # ИСПРАВЛЕНО: используем heading_type вместо level
            if node.heading_type != "main_heading":
                continue
            if not node.text.strip():
                continue

            has_page_break = False
            if node.metadata.get("page_break_before"):
                has_page_break = True
            if i > 0:
                prev_node = nodes[i - 1]
                if hasattr(prev_node, 'text') and '\f' in prev_node.text:
                    has_page_break = True
                if prev_node.metadata.get("has_page_break"):
                    has_page_break = True

            if not has_page_break:
                self.add_error(
                    severity=Severity.INFO,
                    message="Раздел рекомендуется начинать с нового листа (страницы)",
                    gost_ref="ГОСТ 7.32 п. 6.6.5",
                    context=f"Заголовок раздела: '{node.text[:80]}'",
                    node_type="heading"
                )
        return self.errors


class HeadingHierarchyChecker(BaseChecker):
    """
    Проверка иерархии заголовков.
    В новом парсере всего 2 уровня (main_heading и subheading),
    а заголовки 3+ уровня считаются обычным текстом.
    Поэтому проверяем только:
    1. Первый заголовок должен быть main_heading.
    2. subheading не должен идти до первого main_heading.
    """
    def __init__(self):
        super().__init__(
            name="heading_hierarchy",
            description="Проверка правильности иерархии заголовков"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        headings = list(walk_tree_by_type(ast_tree, HeadingNode))
        if not headings:
            return self.errors

        # ИСПРАВЛЕНО: используем heading_type
        if headings[0].heading_type != "main_heading":
            self.add_error(
                severity=Severity.ERROR,
                message=f"Первый заголовок должен быть основным разделом (main_heading), "
                        f"но обнаружен '{headings[0].heading_type}'",
                gost_ref="ГОСТ 7.32 п. 5.2.1",
                context=f"Заголовок: '{headings[0].text[:80]}'",
                node_type="heading"
            )

        seen_main_heading = False
        for h in headings:
            if h.heading_type == "main_heading":
                seen_main_heading = True
            elif h.heading_type == "subheading" and not seen_main_heading:
                self.add_error(
                    severity=Severity.ERROR,
                    message=f"Подзаголовок '{h.text[:50]}' встречается до первого "
                            f"основного заголовка",
                    gost_ref="ГОСТ 7.32 п. 5.2.1",
                    context=f"Заголовок: '{h.text[:80]}'",
                    node_type="heading"
                )
        return self.errors


class RequiredSectionsChecker(BaseChecker):
    """
    Проверка наличия обязательных разделов (ГОСТ 7.32 п. 5.1).
    """
    # ИСПРАВЛЕНО: init -> __init__
    def __init__(self, debug: bool = False):
        super().__init__(
            name="required_sections",
            description="Проверка наличия обязательных разделов в документе"
        )
        self.debug = debug
        self.required_sections = {
            "Содержание": [
                r'^содержание\b',
                r'^оглавление\b',
                r'\bсодержание\b',
                r'\bоглавление\b'
            ],
            "Вводная часть": [
                r'^вводная\s+часть\b',
                r'^введение\b',
                r'\bвводная\s+часть\b',
                r'\bвведение\b'
            ],
            "Библиография": [
                r'^библиография\b',
                r'^список\s+использованных\s+источников',
                r'^список\s+литературы',
                r'^список\s+источников',
                r'\bбиблиография\b',
                r'\bсписок\s+использованных\s+источников',
                r'\bсписок\s+литературы'
            ]
        }

    def _normalize_text(self, text: str) -> str:
        text = text.replace('\xa0', ' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        all_texts = []
        for node in walk_tree(ast_tree):
            if isinstance(node, (HeadingNode, ParagraphNode)):
                raw_text = node.text
                normalized_text = self._normalize_text(raw_text).lower()
                if normalized_text:
                    all_texts.append({
                        'raw': raw_text,
                        'normalized': normalized_text,
                        'node_type': type(node).__name__
                    })

        for section_name, patterns in self.required_sections.items():
            found = False
            for text_item in all_texts:
                normalized = text_item['normalized']
                for pattern in patterns:
                    if re.search(pattern, normalized):
                        found = True
                        break
                if found:
                    break
                keywords = self._get_keywords_for_section(section_name)
                for keyword in keywords:
                    if keyword in normalized:
                        found = True
                        break
                if found:
                    break

            if not found:
                self.add_error(
                    severity=Severity.ERROR,
                    message=f"Отсутствует обязательный раздел: '{section_name}'",
                    gost_ref="ГОСТ 7.32 п. 5.1",
                    context="Структура документа",
                    node_type="document"
                )
        return self.errors

    def _get_keywords_for_section(self, section_name: str) -> List[str]:
        keywords_map = {
            "Содержание": ["содержание", "оглавление"],
            "Вводная часть": ["вводная часть", "введение"],
            "Библиография": [
                "библиография",
                "список использованных источников",
                "список литературы"
            ]
        }
        return keywords_map.get(section_name, [])


class UnnumberedSectionsStructureChecker(BaseChecker):
    """
    Проверка структуры ненумеруемых разделов (ГОСТ 7.32).
    Целевые разделы: Содержание, Вводная часть, Перечень сокращений,
    Библиография, Приложения.
    """
    # ИСПРАВЛЕНО: init -> __init__
    def __init__(self):
        super().__init__(
            name="unnumbered_sections_structure",
            description="Проверка отсутствия нумерации в ненумеруемых разделах"
        )
        self.section_patterns = [
            r'^содержание\b',
            r'^вводная\s+часть\b',
            r'^(перечень\s+)?сокращени[еяй]\b',
            r'^(библиография|список\s+использованных\s+источников|список\s+литературы)\b',
            r'^приложени[ея]\b'
        ]

    def _is_target_section(self, text: str) -> bool:
        text_lower = text.lower().strip()
        for pattern in self.section_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        in_unnumbered_section = False
        current_section_name = ""

        for node in walk_tree(ast_tree):
            if isinstance(node, HeadingNode):
                if node.heading_type == "main_heading":
                    if self._is_target_section(node.text):
                        in_unnumbered_section = True
                        current_section_name = node.text.strip()

                        # ИСПРАВЛЕНО: проверяем наличие номера через metadata,
                        # а не через regex по тексту (номер убран из node.text)
                        gost_number = node.metadata.get("gost_number")
                        if gost_number:
                            self.add_error(
                                severity=Severity.ERROR,
                                message=f"Раздел '{current_section_name}' не должен нумероваться",
                                gost_ref="ГОСТ 7.32 п. 5.2.1, 6.1.1",
                                context=f"Заголовок: '{node.text[:80]}'",
                                node_type="heading"
                            )
                    else:
                        in_unnumbered_section = False
                        current_section_name = ""

                elif in_unnumbered_section and node.heading_type == "subheading":
                    # ИСПРАВЛЕНО: проверяем через metadata
                    gost_number = node.metadata.get("gost_number")
                    if gost_number:
                        self.add_error(
                            severity=Severity.ERROR,
                            message=f"Подразделы в разделе '{current_section_name}' "
                                    f"не должны иметь числовой нумерации",
                            gost_ref="ГОСТ 7.32 п. 5.2.1",
                            context=f"Заголовок: '{node.text[:80]}'",
                            node_type="heading"
                        )
        return self.errors


class SectionsOrderChecker(BaseChecker):
    """
    Проверка последовательности разделов документа (ГОСТ 7.32 п. 5.1).
    """
    # ИСПРАВЛЕНО: init -> __init__
    def __init__(self, debug: bool = False):
        super().__init__(
            name="sections_order",
            description="Проверка последовательности разделов документа"
        )
        self.debug = debug
        self.expected_order = [
            ("Содержание", [
                r'^содержание\b', r'^оглавление\b',
                r'\bсодержание\b', r'\bоглавление\b'
            ]),
            ("Вводная часть", [
                r'^вводная\s+часть\b', r'^введение\b',
                r'\bвводная\s+часть\b', r'\bвведение\b'
            ]),
            ("Приложения", [
                r'^приложени[ея]\b',
                r'^приложени[ея]\s+[а-яa-z]',
                r'\bприложени[ея]\b'
            ]),
            ("Библиография", [
                r'^библиография\b',
                r'^список\s+использованных\s+источников',
                r'^список\s+литературы',
                r'\bбиблиография\b',
                r'\bсписок\s+использованных\s+источников',
                r'\bсписок\s+литературы'
            ])
        ]

    def _normalize_text(self, text: str) -> str:
        text = text.replace('\xa0', ' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _matches_section(self, text: str, patterns: List[str]) -> bool:
        normalized = self._normalize_text(text).lower()
        for pattern in patterns:
            if re.search(pattern, normalized):
                return True
        return False

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        headings = list(walk_tree_by_type(ast_tree, HeadingNode))
        # ИСПРАВЛЕНО: фильтруем по heading_type
        level1_headings = [h for h in headings if h.heading_type == "main_heading"]

        if not level1_headings:
            return self.errors

        found_positions = {}
        for i, heading in enumerate(level1_headings):
            text = heading.text.strip()
            if not text:
                continue
            for section_name, patterns in self.expected_order:
                if section_name not in found_positions:
                    if self._matches_section(text, patterns):
                        found_positions[section_name] = i
                        break

        last_position = -1
        last_section_name = None
        for section_name, _ in self.expected_order:
            if section_name in found_positions:
                current_position = found_positions[section_name]
                if current_position < last_position:
                    self.add_error(
                        severity=Severity.ERROR,
                        message=f"Нарушена последовательность разделов: "
                                f"'{section_name}' (позиция {current_position + 1}) "
                                f"должен идти после '{last_section_name}' "
                                f"(позиция {last_position + 1})",
                        gost_ref="ГОСТ 7.32 п. 5.1",
                        context=f"Раздел: '{section_name}'",
                        node_type="heading"
                    )
                last_position = current_position
                last_section_name = section_name
        return self.errors