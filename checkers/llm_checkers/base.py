import os
from typing import List, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from checkers.base import BaseChecker, CheckError, Severity
from doc_parser.docx_ast_parser import DocumentNode


# ==========================================
# Pydantic-модели для структурированного вывода
# ==========================================

class LLMError(BaseModel):
    """Модель ошибки, возвращаемой LLM"""
    severity: str = Field(description="Критичность: 'error', 'warning' или 'info'")
    message: str = Field(description="Описание нарушения")
    gost_reference: str = Field(description="Ссылка на пункт ГОСТа")
    context: str = Field(default="", description="Контекст ошибки")


class LLMCheckResult(BaseModel):
    """Результат LLM-проверки"""
    errors: List[LLMError] = Field(default_factory=list, description="Список найденных ошибок")


# ==========================================
# Базовый класс
# ==========================================

class BaseLLMChecker(BaseChecker):
    """
    Базовый класс для проверок с использованием LLM через LangChain.
    Использует with_structured_output для гарантированного JSON-ответа.
    """
    
    def __init__(self, name: str, description: str,
                 api_key: Optional[str] = None,
                 model: str = "gpt-4o-mini",
                 temperature: float = 0.1,
                 llm_base_url: Optional[str] = None):
        super().__init__(name=name, description=description)
        
        # Инициализируем ChatOpenAI
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=llm_base_url
        )
        
        # Создаём структурированную версию LLM
        self.structured_llm = self.llm.with_structured_output(LLMCheckResult)
    
    @abstractmethod
    def extract_context(self, ast_tree: DocumentNode) -> str:
        """Извлекает релевантный контекст из AST для проверки."""
        pass
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Возвращает системный промпт для LLM."""
        pass
    
    @abstractmethod
    def get_user_prompt(self, context: str) -> str:
        """Возвращает пользовательский промпт с контекстом."""
        pass
    
    def check(self, ast_tree: DocumentNode) -> List[CheckError]:
        """Выполняет проверку с помощью LLM."""
        self.reset()
        print(f"    🔍 [{self.name}] Начинаем проверку...")
        
        # 1. Извлекаем контекст
        context = self.extract_context(ast_tree)
        if not context or not context.strip():
            print(f"    ⚠️  [{self.name}] Контекст пустой, LLM не вызывается")
            return self.errors
        
        print(f"    📄 [{self.name}] Контекст извлечён: {len(context)} символов")
        print(f"    📄 [{self.name}] Первые 300 символов:\n{context[:300]}")
        
        # 2. Формируем промпты
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(context)
        
        # 3. Вызываем LLM НАПРЯМУЮ (без ChatPromptTemplate, чтобы избежать проблем с f-string)
        try:
            print(f"    🧠 [{self.name}] Вызываем LLM (модель: {self.llm.model_name})...")
            
            # Используем прямой вызов с сообщениями
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            result: LLMCheckResult = self.structured_llm.invoke(messages)
            
            print(f"    ✅ [{self.name}] LLM вернул {len(result.errors)} ошибок")
            
            # Выводим найденные ошибки для отладки
            for i, err in enumerate(result.errors, 1):
                print(f"       {i}. [{err.severity}] {err.message[:100]}")
                
        except Exception as e:
            print(f"    ❌ [{self.name}] КРИТИЧЕСКАЯ ОШИБКА LLM: {type(e).__name__}: {e}")
            self.add_error(
                severity=Severity.WARNING,
                message=f"Ошибка при обращении к LLM: {str(e)}",
                gost_ref="LLM_CHECK_ERROR",
                context=self.name,
                node_type="llm_check"
            )
            return self.errors
        
        # 4. Конвертируем в CheckError
        for err in result.errors:
            try:
                severity_enum = Severity(err.severity.lower())
            except ValueError:
                severity_enum = Severity.WARNING  # Fallback
            
            self.add_error(
                severity=severity_enum,
                message=err.message,
                gost_ref=err.gost_reference,
                context=err.context,
                node_type="llm_check"
            )
        
        return self.errors