from typing import List, Dict, Set
import re
from .base import BaseChecker, Severity
from doc_parser.docx_ast_parser import (
    DocumentNode, ParagraphNode, TableNode, ImageNode, walk_tree
)

class FigureReferenceChecker(BaseChecker):
    """Проверка ссылок на рисунки"""
    
    def __init__(self):
        super().__init__(
            name="figure_references",
            description="Проверка ссылок на рисунки в тексте"
        )
        self.reference_pattern = re.compile(r'рис\.?\s*(\d+)', re.IGNORECASE)
        self.figure_pattern = re.compile(r'Рисунок\s*(\d+)', re.IGNORECASE)
    
    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        
        # Собираем все ссылки на рисунки в тексте
        referenced_figures: Set[int] = set()
        defined_figures: Set[int] = set()
        
        for node in walk_tree(ast_tree):
            if isinstance(node, ParagraphNode):
                # Ищем ссылки "рис. 1", "рис.2" и т.д.
                matches = self.reference_pattern.findall(node.text)
                for match in matches:
                    referenced_figures.add(int(match))
            
            elif isinstance(node, ImageNode):
                # Ищем подписи "Рисунок 1", "Рисунок 2" и т.д.
                if node.caption:
                    matches = self.figure_pattern.findall(node.caption)
                    for match in matches:
                        defined_figures.add(int(match))
        
        # Проверяем соответствие
        for fig_num in referenced_figures:
            if fig_num not in defined_figures:
                self.add_error(
                    severity=Severity.ERROR,
                    message=f"В тексте есть ссылка на Рисунок {fig_num}, "
                            f"но он не определён в документе",
                    gost_ref="ГОСТ Р 2.105-20195",
                    context=f"Ссылка: 'рис. {fig_num}'",
                    node_type="reference"
                )
        
        for fig_num in defined_figures:
            if fig_num not in referenced_figures:
                self.add_error(
                    severity=Severity.WARNING,
                    message=f"Рисунок {fig_num} определён, но на него нет ссылок в тексте",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context=f"Рисунок: 'Рисунок {fig_num}'",
                    node_type="figure"
                )
        
        return self.errors


class TableReferenceChecker(BaseChecker):
    """Проверка ссылок на таблицы"""
    
    def __init__(self):
        super().__init__(
            name="table_references",
            description="Проверка ссылок на таблицы в тексте"
        )
        self.reference_pattern = re.compile(r'табл\.?\s*(\d+)', re.IGNORECASE)
        self.table_pattern = re.compile(r'Таблица\s*(\d+)', re.IGNORECASE)
    
    def check(self, ast_tree: DocumentNode) -> List:
        self.reset()
        
        referenced_tables: Set[int] = set()
        defined_tables: Set[int] = set()
        
        for node in walk_tree(ast_tree):
            if isinstance(node, ParagraphNode):
                matches = self.reference_pattern.findall(node.text)
                for match in matches:
                    referenced_tables.add(int(match))
            
            elif isinstance(node, TableNode):
                if node.caption:
                    matches = self.table_pattern.findall(node.caption)
                    for match in matches:
                        defined_tables.add(int(match))
        
        for tbl_num in referenced_tables:
            if tbl_num not in defined_tables:
                self.add_error(
                    severity=Severity.ERROR,
                    message=f"В тексте есть ссылка на Таблицу {tbl_num}, "
                            f"но она не определена в документе",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context=f"Ссылка: 'табл. {tbl_num}'",
                    node_type="reference"
                )
        
        for tbl_num in defined_tables:
            if tbl_num not in referenced_tables:
                self.add_error(
                    severity=Severity.WARNING,
                    message=f"Таблица {tbl_num} определена, но на неё нет ссылок в тексте",
                    gost_ref="ГОСТ Р 2.105-2019",
                    context=f"Таблица: 'Таблица {tbl_num}'",
                    node_type="table"
                )
        
        return self.errors