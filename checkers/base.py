from dataclasses import dataclass, field
from typing import List, Optional, Literal
from enum import Enum


class Severity(Enum):
    """Критичность ошибки"""
    ERROR = "error"      # Критическая ошибка (нарушение ГОСТа)
    WARNING = "warning"  # Предупреждение (возможное нарушение)
    INFO = "info"        # Информационное сообщение


@dataclass
class CheckError:
    """Описание найденной ошибки"""
    severity: Severity
    message: str
    gost_reference: str
    context: str = ""    # Контекст ошибки (текст/описание узла)
    node_type: str = ""  # Тип узла AST (heading, paragraph, и т.д.)
    line_hint: Optional[int] = None  # Подсказка по номеру строки (если есть)
    
    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "message": self.message,
            "gost_reference": self.gost_reference,
            "context": self.context,
            "node_type": self.node_type,
            "line_hint": self.line_hint
        }


class BaseChecker:
    """
    Базовый класс для всех проверок.
    Каждая проверка наследуется от этого класса и реализует метод check().
    """
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.errors: List[CheckError] = []
    
    def check(self, ast_tree) -> List[CheckError]:
        """
        Выполняет проверку AST-дерева.
        Должен быть переопределён в наследниках.
        
        Args:
            ast_tree: Корневой узел AST (DocumentNode)
        
        Returns:
            Список найденных ошибок
        """
        raise NotImplementedError("Метод check() должен быть реализован в наследнике")
    
    def add_error(self, severity: Severity, message: str, gost_ref: str,
                  context: str = "", node_type: str = "", line_hint: int = None):
        """Добавляет ошибку в список"""
        self.errors.append(CheckError(
            severity=severity,
            message=message,
            gost_reference=gost_ref,
            context=context,
            node_type=node_type,
            line_hint=line_hint
        ))
    
    def reset(self):
        """Очищает список ошибок"""
        self.errors = []