from typing import List, Optional
from .base import BaseChecker, Severity
from doc_parser.docx_ast_parser import (
    DocumentNode, HeadingNode, ParagraphNode,
    walk_tree, ASTNode
)

# ==========================================
# Вспомогательная функция для детекции пустых строк
# ==========================================
def _is_empty_paragraph(node: ASTNode) -> bool:
    """
    Проверяет, является ли узел фактически пустой строкой 
    (пустым абзацем, созданным нажатием Enter).
    """
    return isinstance(node, ParagraphNode) and not node.text.strip()


class HeadingSpacingChecker(BaseChecker):
    """
    Проверка отступов после main_heading (ГОСТ 7.32 п. 6.6.6)
    Требования:
    - После заголовка раздела (main_heading) должен быть увеличенный интервал
      или пустая строка.
    """
    def __init__(self, min_spacing_pt: float = 6.0, empty_line_threshold_pt: float = 10.0):
        super().__init__(
            name="heading_spacing",
            description="Проверка отступов после основных заголовков (main_heading)"
        )
        self.min_spacing_pt = min_spacing_pt
        self.empty_line_threshold_pt = empty_line_threshold_pt

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        nodes = list(walk_tree(ast_tree))
        
        for i, node in enumerate(nodes):
            if not isinstance(node, HeadingNode) or node.heading_type != "main_heading":
                continue
            
            if i + 1 >= len(nodes):
                continue
                
            next_node = nodes[i + 1]
            
            # 1. Считаем суммарный отступ
            space_after = node.paragraph_props.space_after_pt if node.paragraph_props and node.paragraph_props.space_after_pt else 0
            space_before_next = next_node.paragraph_props.space_before_pt if next_node.paragraph_props and next_node.paragraph_props.space_before_pt else 0
            total_spacing = space_after + space_before_next
            
            # 2. Проверяем наличие "пустой строки" (любым из 3 способов)
            has_empty_line = (
                _is_empty_paragraph(next_node) or
                space_after >= self.empty_line_threshold_pt or
                space_before_next >= self.empty_line_threshold_pt
            )
            
            # Проверка через line_spacing
            if node.paragraph_props and node.paragraph_props.line_spacing:
                spacing = node.paragraph_props.line_spacing
                if isinstance(spacing, (int, float)) and spacing >= 1.9:
                    has_empty_line = True
            
            # 3. Если нет ни увеличенного интервала, ни пустой строки -> ошибка
            if total_spacing < self.min_spacing_pt and not has_empty_line:
                self.add_error(
                    severity=Severity.WARNING,
                    message=f"После основного заголовка '{node.text[:50]}' "
                            f"отсутствует требуемый увеличенный интервал или пустая строка. "
                            f"Текущий отступ: {total_spacing:.1f} пт.",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Отступы после основных заголовков",
                    node_type="heading"
                )
        return self.errors


class SubheadingSpacingChecker(BaseChecker):
    """
    Проверка отступов до и после subheading
    Требования:
    - Интервалы до и после subheading должны быть увеличенными (или через пустую строку).
    - Интервалы до и после subheading должны быть ОДИНАКОВЫМИ (симметричными).
    """
    def __init__(self, min_spacing_pt: float = 6.0, tolerance_pt: float = 2.0, empty_line_threshold_pt: float = 10.0):
        super().__init__(
            name="subheading_spacing",
            description="Проверка симметрии и размера отступов вокруг подзаголовков (subheading)"
        )
        self.min_spacing_pt = min_spacing_pt
        self.tolerance_pt = tolerance_pt
        self.empty_line_threshold_pt = empty_line_threshold_pt

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        nodes = list(walk_tree(ast_tree))
        
        for i, node in enumerate(nodes):
            if not isinstance(node, HeadingNode) or node.heading_type != "subheading":
                continue
            
            prev_node = nodes[i - 1] if i > 0 else None
            next_node = nodes[i + 1] if i + 1 < len(nodes) else None
            
            # --- Расчет общих интервалов ---
            space_after_prev = prev_node.paragraph_props.space_after_pt if prev_node and prev_node.paragraph_props and prev_node.paragraph_props.space_after_pt else 0
            space_before_node = node.paragraph_props.space_before_pt if node.paragraph_props and node.paragraph_props.space_before_pt else 0
            spacing_before = space_after_prev + space_before_node
            
            space_after_node = node.paragraph_props.space_after_pt if node.paragraph_props and node.paragraph_props.space_after_pt else 0
            space_before_next = next_node.paragraph_props.space_before_pt if next_node and next_node.paragraph_props and next_node.paragraph_props.space_before_pt else 0
            spacing_after = space_after_node + space_before_next
            
            # --- Детекция "пустых строк" ДО и ПОСЛЕ ---
            has_empty_line_before = (
                _is_empty_paragraph(prev_node) or
                space_after_prev >= self.empty_line_threshold_pt or
                space_before_node >= self.empty_line_threshold_pt
            )
            has_empty_line_after = (
                _is_empty_paragraph(next_node) or
                space_after_node >= self.empty_line_threshold_pt or
                space_before_next >= self.empty_line_threshold_pt
            )
            
            # Альтернатива: двойной line_spacing
            if node.paragraph_props and node.paragraph_props.line_spacing:
                spacing = node.paragraph_props.line_spacing
                if isinstance(spacing, (int, float)) and spacing >= 1.9:
                    has_empty_line_before = True
                    has_empty_line_after = True

            # 1. Проверяем, что интервалы достаточные
            if not has_empty_line_before and spacing_before < self.min_spacing_pt:
                self.add_error(
                    severity=Severity.WARNING,
                    message=f"Интервал перед подзаголовком '{node.text[:40]}' "
                            f"({spacing_before:.1f} пт) меньше требуемого ({self.min_spacing_pt} пт)",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Интервалы вокруг подзаголовков",
                    node_type="heading"
                )
                
            if not has_empty_line_after and spacing_after < self.min_spacing_pt:
                self.add_error(
                    severity=Severity.WARNING,
                    message=f"Интервал после подзаголовка '{node.text[:40]}' "
                            f"({spacing_after:.1f} пт) меньше требуемого ({self.min_spacing_pt} пт)",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context="Интервалы вокруг подзаголовков",
                    node_type="heading"
                )
            
            # 2. Проверяем СИММЕТРИЮ
            # Если автор использовал "костыли" в виде пустых абзацев, 
            # не ругаемся на асимметрию собственных отступов (space_before/space_after)
            used_empty_paragraph_before = prev_node and _is_empty_paragraph(prev_node)
            used_empty_paragraph_after = next_node and _is_empty_paragraph(next_node)
            
            if not (used_empty_paragraph_before or used_empty_paragraph_after):
                node_space_before = node.paragraph_props.space_before_pt if node.paragraph_props and node.paragraph_props.space_before_pt else 0
                node_space_after = node.paragraph_props.space_after_pt if node.paragraph_props and node.paragraph_props.space_after_pt else 0
                
                if abs(node_space_before - node_space_after) > self.tolerance_pt:
                    self.add_error(
                        severity=Severity.WARNING,
                        message=f"Отступы до ({node_space_before:.1f} пт) и после "
                                f"({node_space_after:.1f} пт) подзаголовка '{node.text[:40]}' "
                                f"различаются более чем на {self.tolerance_pt} пт. "
                                f"Они должны быть симметричными.",
                        gost_ref="ГОСТ Р 2.105-2019",
                        context="Симметрия интервалов подзаголовков",
                        node_type="heading"
                    )
        return self.errors


class ParagraphSpacingChecker(BaseChecker):
    """
    Проверка интервалов между обычными абзацами (paragraph)
    Требования:
    - Межстрочный интервал (line_spacing) должен быть строго 1.5 или 2.0.
    - КАТЕГОРИЧЕСКИ НЕ ДОПУСКАЮТСЯ пустые строки между абзацами
      (ни пустые абзацы, ни большие space_before/space_after).
    """
    def __init__(self, max_extra_spacing_pt: float = 4.0):
        super().__init__(
            name="paragraph_spacing",
            description="Проверка межстрочного интервала и отсутствия пустых строк между абзацами"
        )
        self.allowed_spacings = {1.5, 2.0}
        self.tolerance = 0.1
        self.max_extra_spacing_pt = max_extra_spacing_pt

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        nodes = list(walk_tree(ast_tree))
        invalid_line_spacings = set()
        
        for i, node in enumerate(nodes):
            if not isinstance(node, ParagraphNode):
                continue
                
            # 1. ЖЕСТКАЯ ПРОВЕРКА: Пустые абзацы между текстом запрещены
            if _is_empty_paragraph(node):
                # Находим контекст: что было до и после пустого абзаца
                prev_text = ""
                next_text = ""
                if i > 0 and hasattr(nodes[i-1], 'text'):
                    prev_text = nodes[i-1].text[:50] if nodes[i-1].text else ""
                if i + 1 < len(nodes) and hasattr(nodes[i+1], 'text'):
                    next_text = nodes[i+1].text[:50] if nodes[i+1].text else ""
                
                context_parts = []
                if prev_text:
                    context_parts.append(f"после: '{prev_text}...'")
                if next_text:
                    context_parts.append(f"перед: '{next_text}...'")
                context_str = ", ".join(context_parts) if context_parts else "в основном тексте"
                
                self.add_error(
                    severity=Severity.WARNING,
                    message=f"Обнаружен пустой абзац (пустая строка) между текстом. "
                            f"Между обычными абзацами не должно быть пустых строк.",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context=context_str,
                    node_type="paragraph"
                )
                continue  # Пропускаем дальнейшие проверки для пустого абзаца
                
            # 2. Проверяем line_spacing (должен быть 1.5 или 2.0)
            if node.paragraph_props and node.paragraph_props.line_spacing:
                spacing = node.paragraph_props.line_spacing
                if isinstance(spacing, (int, float)) and spacing <= 10:
                    rounded_spacing = round(spacing, 1)
                    is_valid = any(abs(rounded_spacing - allowed) <= self.tolerance 
                                   for allowed in self.allowed_spacings)
                    if not is_valid:
                        invalid_line_spacings.add(rounded_spacing)
            
            # 3. Проверяем отсутствие "скрытых пустых строк" (больших отступов)
            if node.paragraph_props:
                space_before = node.paragraph_props.space_before_pt or 0
                space_after = node.paragraph_props.space_after_pt or 0
                text_preview = node.text[:50] if node.text else "(пустой абзац)"
                
                if space_before > self.max_extra_spacing_pt:
                    self.add_error(
                        severity=Severity.WARNING,
                        message=f"Обнаружена 'пустая строка' перед абзацем "
                                f"(space_before = {space_before:.1f} пт). "
                                f"Между абзацами не должно быть пустых строк.",
                        gost_ref="ГОСТ Р 2.105-2019",
                        context=f"Абзац: '{text_preview}...'",
                        node_type="paragraph"
                    )
                    
                if space_after > self.max_extra_spacing_pt:
                    self.add_error(
                        severity=Severity.WARNING,
                        message=f"Обнаружена 'пустая строка' после абзаца "
                                f"(space_after = {space_after:.1f} пт). "
                                f"Между абзацами не должно быть пустых строк.",
                        gost_ref="ГОСТ Р 2.105-2019",
                        context=f"Абзац: '{text_preview}...'",
                        node_type="paragraph"
                    )
        
        # Сводная ошибка по недопустимому line_spacing
        if invalid_line_spacings:
            self.add_error(
                severity=Severity.ERROR,
                message=f"В абзацах используются недопустимые межстрочные интервалы: "
                        f"{', '.join(map(str, invalid_line_spacings))}. "
                        f"ГОСТ требует строго 1.5 или 2.0",
                gost_ref="ГОСТ Р 2.105-2019",
                context="Межстрочные интервалы в абзацах",
                node_type="document"
            )
            
        return self.errors