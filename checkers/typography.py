from typing import List
import re
from .base import BaseChecker, Severity
from doc_parser.docx_ast_parser import DocumentNode, ParagraphNode, walk_tree
from docx.oxml.ns import qn


def _get_run_spacing_pt(run) -> float:
    """
    Надежно получает разрядку (интервал между символами) в пунктах для конкретного Run.
    Сначала пробует стандартные свойства python-docx, затем fallback в прямой парсинг XML.
    """
    # 1. Пробуем стандартный атрибут python-docx
    if hasattr(run.font, 'spacing') and run.font.spacing is not None:
        return run.font.spacing.pt
    
    # 2. Fallback: прямой парсинг XML (самый надежный способ)
    try:
        rPr = run._element.find(qn('w:rPr'))
        if rPr is not None:
            spacing_elem = rPr.find(qn('w:spacing'))
            if spacing_elem is not None:
                val = spacing_elem.get(qn('w:val'))
                if val:
                    # В Word w:val для spacing хранится в half-points (1/20 пункта)
                    return int(val) / 20.0
    except Exception:
        pass
        
    return 0.0


class TextSpacingChecker(BaseChecker):
    """
    Проверка разрядки в служебных словах.
    Требование: слова "ПРИМЕЧАНИЕ" и "ТАБЛИЦА" должны быть написаны с разрядкой.
    """
    def __init__(self, min_spacing_pt: float = 1.0):
        super().__init__(
            name="text_spacing",
            description="Проверка разрядки (интервала) в словах ПРИМЕЧАНИЕ и ТАБЛИЦА"
        )
        self.target_words = ["ПРИМЕЧАНИЕ", "ТАБЛИЦА"]
        self.min_spacing_pt = min_spacing_pt

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree(ast_tree):
            if isinstance(node, ParagraphNode):
                self._check_paragraph(node)
        return self.errors

    def _check_paragraph(self, node: ParagraphNode):
        text = node.text.strip().upper()
        if not text:
            return

        for word in self.target_words:
            if text.startswith(word) or text.startswith(word + " ") or text.startswith(word + "-") or text.startswith(word + "—"):
                # Проверяем разрядку на уровне конкретных Run'ов через _source_ref
                has_spacing = False
                if hasattr(node, '_source_ref') and node._source_ref is not None:
                    p_obj = node._source_ref
                    for run in p_obj.runs:
                        run_text = run.text.strip().upper()
                        if word in run_text:
                            if _get_run_spacing_pt(run) >= self.min_spacing_pt:
                                has_spacing = True
                                break
                
                # Fallback на свойства параграфа из AST, если _source_ref недоступен
                if not has_spacing and node.font and node.font.spacing_pt is not None:
                    if node.font.spacing_pt >= self.min_spacing_pt:
                        has_spacing = True

                if not has_spacing:
                    self.add_error(
                        severity=Severity.WARNING,
                        message=f"Слово '{word}' должно быть написано с разрядкой "
                                f"(увеличенным интервалом между символами).",
                        gost_ref="ГОСТ Р 2.105-2019",
                        context=f"Текст: '{node.text[:80]}...'",
                        node_type="paragraph"
                    )
                break # Проверяем только первое совпадающее слово в параграфе


class AbbreviationSpacingChecker(BaseChecker):
    """
    Проверка разрядки в дополнительных служебных словах (ПРИЛОЖЕНИЕ, РИСУНОК).
    """
    def __init__(self, min_spacing_pt: float = 1.0):
        super().__init__(
            name="abbreviation_spacing",
            description="Проверка разрядки в словах ПРИЛОЖЕНИЕ и РИСУНОК"
        )
        self.words_to_check = ["ПРИЛОЖЕНИЕ", "РИСУНОК"]
        self.min_spacing_pt = min_spacing_pt

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree(ast_tree):
            if isinstance(node, ParagraphNode):
                self._check_paragraph(node)
        return self.errors

    def _check_paragraph(self, node: ParagraphNode):
        text = node.text.strip().upper()
        if not text:
            return

        for word in self.words_to_check:
            if text.startswith(word) or text.startswith(word + " ") or text.startswith(word + "-") or text.startswith(word + "—"):
                has_spacing = False
                if hasattr(node, '_source_ref') and node._source_ref is not None:
                    p_obj = node._source_ref
                    for run in p_obj.runs:
                        run_text = run.text.strip().upper()
                        if word in run_text:
                            if _get_run_spacing_pt(run) >= self.min_spacing_pt:
                                has_spacing = True
                                break
                
                if not has_spacing and node.font and node.font.spacing_pt is not None:
                    if node.font.spacing_pt >= self.min_spacing_pt:
                        has_spacing = True

                if not has_spacing:
                    self.add_error(
                        severity=Severity.INFO,
                        message=f"Слово '{word}' рекомендуется писать с разрядкой",
                        gost_ref="ГОСТ Р 2.105-2019",
                        context=f"Текст: '{node.text[:80]}...'",
                        node_type="paragraph"
                    )
                break


class ProhibitedSpacingChecker(BaseChecker):
    """
    Проверка отсутствия разрядки в обычном тексте.
    Проверяет ВСЕ параграфы и ВСЕ run внутри них.
    Разрядка допускается ТОЛЬКО если run содержит исключительно служебное слово 
    (например, "ПРИМЕЧАНИЕ", "ПРИМЕЧАНИЕ -", "ТАБЛИЦА 1").
    """
    def __init__(self, max_allowed_spacing_pt: float = 0.5):
        super().__init__(
            name="prohibited_spacing",
            description="Проверка отсутствия недопустимой разрядки в обычном тексте"
        )
        self.allowed_words = ["ПРИМЕЧАНИЕ", "ТАБЛИЦА", "ПАРАМЕТРЫ", "ИНДЕКСЫ", "СОКРАЩЕНИЯ"]
        # Порог 0.5 пт защищает от ложных срабатываний из-за погрешностей float
        self.max_allowed_spacing_pt = max_allowed_spacing_pt

    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        for node in walk_tree(ast_tree):
            if isinstance(node, ParagraphNode):
                self._check_paragraph(node)
        return self.errors

    def _check_paragraph(self, node: ParagraphNode):
        if not hasattr(node, '_source_ref') or node._source_ref is None:
            return
        
        p_obj = node._source_ref
        for run in p_obj.runs:
            spacing = _get_run_spacing_pt(run)
            
            if spacing is not None and spacing > self.max_allowed_spacing_pt:
                run_text = run.text.strip().upper()
                if not run_text:
                    continue
                
                # Проверяем, является ли этот run допустимым (только служебное слово с возможным номером/тире)
                is_allowed = False
                for word in self.allowed_words:
                    # Регулярка разрешает: "СЛОВО", "СЛОВО ", "СЛОВО -", "СЛОВО 1", "СЛОВО - 1"
                    # Но запрещает: "СЛОВО - какой-то длинный текст с разрядкой"
                    pattern = rf"^{re.escape(word)}(\s*[\-—]?\s*\d*)?\s*$"
                    if re.match(pattern, run_text):
                        is_allowed = True
                        break
                
                if not is_allowed:
                    self.add_error(
                        severity=Severity.WARNING,
                        message=f"Обнаружена недопустимая разрядка (интервал {spacing:.1f} пт). "
                                f"Разрядка допускается только для служебных слов: {', '.join(self.allowed_words)}.",
                        gost_ref="ГОСТ Р 2.105-2019",
                        context=f"Текст: '{run.text[:80]}...'",
                        node_type="paragraph"
                    )
                    break # Одна ошибка на параграф, чтобы не спамить отчет