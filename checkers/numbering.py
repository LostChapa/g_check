from typing import List
import re
from collections import defaultdict
from .base import BaseChecker, Severity
from doc_parser.docx_ast_parser import (
    DocumentNode, HeadingNode, ListNode, ListItemNode, walk_tree
)

class HeadingNumberingChecker(BaseChecker):
    """
    Проверка нумерации заголовков (main_heading и subheading).
    Требования:
    - Нумерация основных разделов должна быть последовательной (1, 2, 3...).
    - Нумерация подзаголовков должна быть последовательной внутри каждого раздела (1, 2, 3...).
    - Не допускаются пропуски номеров.
    """
    def __init__(self):
        super().__init__(
            name="heading_numbering",
            description="Проверка правильности нумерации заголовков"
        )

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        
        # Собираем все заголовки с их номерами
        main_headings = []
        sub_headings = []
        
        for node in walk_tree(ast_tree):
            if not isinstance(node, HeadingNode):
                continue
            
            # Получаем номер из метаданных (парсер сохраняет его туда)
            gost_number = node.metadata.get("gost_number")
            if not gost_number:
                continue
                
            parts = gost_number.split('.')
            
            if node.heading_type == "main_heading":
                try:
                    main_headings.append((int(parts[0]), node))
                except ValueError:
                    pass
            elif node.heading_type == "subheading":
                if len(parts) == 2:
                    try:
                        sub_headings.append((int(parts[0]), int(parts[1]), node))
                    except ValueError:
                        pass

        # ==========================================
        # 1. ПРОВЕРКА ОСНОВНЫХ ЗАГОЛОВКОВ (main_heading)
        # ==========================================
        expected_main = 1
        main_heading_errors = set() # Множество номеров, которые были указаны с ошибкой
        
        for num, node in main_headings:
            if num != expected_main:
                self.add_error(
                    severity=Severity.ERROR,
                    message=f"Неправильная нумерация основного раздела: "
                            f"ожидается '{expected_main}', получено '{num}'",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context=f"Заголовок: '{num} {node.text}'",
                    node_type="heading"
                )
                # Фиксируем, что этот номер был указан с ошибкой (пропуск или опечатка)
                main_heading_errors.add(num)
                
            # Восстанавливаем последовательность: следующий ожидаемый всегда на 1 больше текущего
            expected_main = num + 1

        # ==========================================
        # 2. ПРОВЕРКА ПОДЗАГОЛОВКОВ (subheading)
        # ==========================================
        # Группируем подзаголовки по их родителю
        sub_groups = defaultdict(list)
        for parent, sub, node in sub_headings:
            sub_groups[parent].append((sub, node))
            
        for parent, subs in sub_groups.items():
            expected_sub = 1
            for sub, node in subs:
                if sub != expected_sub:
                    # ВАЖНО: Если родитель (parent) не был помечен как ошибочный 
                    # на этапе проверки main_heading, значит ошибка именно в подзаголовке.
                    # Если же родитель был "сбоем" (например, автор написал 3 вместо 2, 
                    # а подзаголовки 2.1, 2.2 оставил правильными), мы не спамим ошибками.
                    if parent not in main_heading_errors:
                        self.add_error(
                            severity=Severity.ERROR,
                            message=f"Неправильная нумерация подзаголовка в разделе '{parent}': "
                                    f"ожидается '{parent}.{expected_sub}', получено '{parent}.{sub}'",
                            gost_ref="ГОСТ Р 2.105-2019",
                            context=f"Заголовок: '{parent}.{sub} {node.text}'",
                            node_type="heading"
                        )
                
                # Восстанавливаем последовательность подзаголовков
                expected_sub = sub + 1

        return self.errors


class ListNumberingChecker(BaseChecker):
    """
    Проверка нумерации списков
    Требования:
    - Нумерованные списки должны идти по порядку (1, 2, 3 или а, б, в).
    - Не допускаются пропуски или дубликаты пунктов.
    """
    def __init__(self):
        super().__init__(
            name="list_numbering",
            description="Проверка правильности нумерации списков"
        )
        # Паттерны для распознавания нумерации в тексте пункта списка
        self.numeric_pattern = re.compile(r'^(\d+)[\.\)]\s+(.+)$')
        self.letter_pattern = re.compile(r'^([а-яё])[а-яё]*\)\s+(.+)$')
        
        # Русский алфавит для списков (БЕЗ 'ё' согласно ГОСТ)
        self.russian_list_letters = [
            'а', 'б', 'в', 'г', 'д', 'е', 'ж', 'з', 'и', 'к', 'л', 'м',
            'н', 'о', 'п', 'р', 'с', 'т', 'у', 'ф', 'х', 'ц', 'ч', 'ш',
            'щ', 'ъ', 'ы', 'ь', 'э', 'ю', 'я'
        ]

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree(ast_tree):
            if isinstance(node, ListNode):
                self._check_list(node)
        return self.errors

    def _check_list(self, list_node: ListNode):
        """Проверяет нумерацию одного списка"""
        if not list_node.children:
            return
            
        # Определяем тип списка по первому элементу
        first_item = list_node.children[0]
        is_numeric = bool(self.numeric_pattern.match(first_item.text))
        is_letter = bool(self.letter_pattern.match(first_item.text))
        
        if not (is_numeric or is_letter):
            # Список без явной нумерации (маркированный, например, тире или буллиты) — допустимо
            return
            
        # Проверяем последовательность
        for i, item in enumerate(list_node.children):
            if is_numeric:
                match = self.numeric_pattern.match(item.text)
                if match:
                    expected_num = i + 1
                    actual_num = int(match.group(1))
                    if actual_num != expected_num:
                        self.add_error(
                            severity=Severity.ERROR,
                            message=f"Неправильная нумерация списка: ожидается {expected_num}, "
                                    f"получено {actual_num}",
                            gost_ref="ГОСТ Р 2.105-2019",
                            context=f"Пункт списка: '{item.text[:50]}...'",
                            node_type="list_item"
                        )
                        
            elif is_letter:
                match = self.letter_pattern.match(item.text)
                if match:
                    # Получаем ожидаемую букву из предопределенного списка
                    if i < len(self.russian_list_letters):
                        expected_char = self.russian_list_letters[i]
                    else:
                        # Если список длиннее 31 пункта, это уже нарушение ГОСТ
                        self.add_error(
                            severity=Severity.WARNING,
                            message=f"Список содержит более 31 пункта ({i + 1}). "
                                    f"ГОСТ не предусматривает буквенную нумерацию beyond 'я'",
                            gost_ref="ГОСТ Р 2.105-2019",
                            context=f"Пункт списка: '{item.text[:50]}...'",
                            node_type="list_item"
                        )
                        continue
                    
                    actual_char = match.group(1)
                    if actual_char != expected_char:
                        self.add_error(
                            severity=Severity.ERROR,
                            message=f"Неправильная буквенная нумерация списка: "
                                    f"ожидается '{expected_char})', получено '{actual_char})'",
                            gost_ref="ГОСТ Р 2.105-2019",
                            context=f"Пункт списка: '{item.text[:50]}...'",
                            node_type="list_item"
                        )