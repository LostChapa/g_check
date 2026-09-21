from typing import List, Dict, Optional
from .base import BaseChecker, CheckError, Severity
from .formatting import (
    FontFamilyChecker, FontSizeChecker, LineSpacingChecker,
    ParagraphIndentChecker, PageMarginsChecker, TableFontSizeChecker,
    ApplicationFontSizeChecker, FootnoteFontSizeChecker
)
from .structure import (
    HeadingCapitalizationChecker, HeadingDotChecker, HeadingBoldChecker,
    HeadingUnderlineChecker, HeadingHyphenationChecker,
    HeadingTwoSentencesChecker, HeadingNewPageChecker,
    HeadingHierarchyChecker, RequiredSectionsChecker, UnnumberedSectionsStructureChecker,
    SectionsOrderChecker
)
from .numbering import HeadingNumberingChecker, ListNumberingChecker
from .references import FigureReferenceChecker, TableReferenceChecker
from doc_parser.docx_ast_parser import DocumentNode
from .typography import TextSpacingChecker, AbbreviationSpacingChecker, ProhibitedSpacingChecker

from .spacing import HeadingSpacingChecker, ParagraphSpacingChecker, SubheadingSpacingChecker

# from rag_checkers.heading_rag import HeadingRAGChecker
# from rag_checkers.list_rag import ListRAGChecker
# from rag_checkers.table_rag import TableRAGChecker

# from llm_checkers.toc_abbreviation import TOCAbbreviationChecker

# from gost_to_vb.vector_store import GOSTVectorStore

class DocumentChecker:
    def __init__(self, doc_path: Optional[str] = None,
                #  enable_rag_checks: bool = False,
                #  vector_store: Optional[GOSTVectorStore] = None,
                 llm_api_key: Optional[str] = None,
                 llm_base_url: Optional[str] = None,
                 llm_model: Optional[str] = None,
                #  enable_llm_checks: bool = False
                ):
        self.checkers: List[BaseChecker] = []
        self.doc_path = doc_path
        # self.enable_rag_checks = enable_rag_checks
        # self.vector_store = vector_store
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        # self.enable_llm_checks = enable_llm_checks
        self._register_default_checkers()

    def _register_default_checkers(self):
        """Регистрирует все стандартные проверки"""
        
        body_font_size = 14.0
        
        # --- Форматирование ---
        self.checkers.append(FontFamilyChecker())
        self.checkers.append(FontSizeChecker())
        self.checkers.append(LineSpacingChecker())
        self.checkers.append(ParagraphIndentChecker())
        self.checkers.append(PageMarginsChecker(self.doc_path))
        
        # --- Таблицы ---
        self.checkers.append(TableFontSizeChecker(body_font_size))
        
        # --- Приложения, примечания, сноски, примеры ---
        self.checkers.append(ApplicationFontSizeChecker(body_font_size))
        self.checkers.append(FootnoteFontSizeChecker(body_font_size, self.doc_path))
        
        # --- Заголовки ---
        self.checkers.append(HeadingCapitalizationChecker())
        self.checkers.append(HeadingDotChecker())
        self.checkers.append(HeadingBoldChecker())
        self.checkers.append(HeadingUnderlineChecker())
        # self.checkers.append(HeadingFontSizeChecker(body_font_size))
        self.checkers.append(HeadingHyphenationChecker())
        self.checkers.append(HeadingTwoSentencesChecker())
        self.checkers.append(HeadingSpacingChecker(body_font_size))
        self.checkers.append(HeadingNewPageChecker())
        
        # --- Структура ---
        self.checkers.append(HeadingHierarchyChecker())
        self.checkers.append(RequiredSectionsChecker())
        self.checkers.append(UnnumberedSectionsStructureChecker())
        self.checkers.append(SectionsOrderChecker())
        
        # --- Нумерация ---
        self.checkers.append(HeadingNumberingChecker())
        self.checkers.append(ListNumberingChecker())
        
        # --- Ссылки ---
        self.checkers.append(FigureReferenceChecker())
        self.checkers.append(TableReferenceChecker())
        
        # --- Типографика (разрядка) ---
        self.checkers.append(TextSpacingChecker(min_spacing_pt=1.0))
        # self.checkers.append(AbbreviationSpacingChecker())
        self.checkers.append(ProhibitedSpacingChecker(max_allowed_spacing_pt=0.5))

        self.checkers.append(HeadingSpacingChecker())
        # self.checkers.append(SubheadingSpacingChecker())
        self.checkers.append(ParagraphSpacingChecker())


        # if self.enable_llm_checks:
        #     try:
        #         self.checkers.append(TOCAbbreviationChecker(
        #             api_key=self.llm_api_key,
        #             model=self.llm_model,          # <-- ДОБАВИТЬ: передача модели
        #             llm_base_url=self.llm_base_url # <-- ДОБАВИТЬ: передача вашего BASE_URL
        #         ))
        #         print("  ✅ LLM-проверки включены")
        #     except Exception as e:
        #         print(f"  ⚠️  Не удалось инициализировать LLM-проверки: {e}")

        # # --- RAG-проверки (с векторной БД) ---
        # if self.enable_rag_checks and self.vector_store:
        #     try:
        #         self.checkers.append(HeadingRAGChecker(
        #             vector_store=self.vector_store,
        #             api_key=self.llm_api_key,
        #             llm_base_url=self.llm_base_url
        #         ))
        #         self.checkers.append(ListRAGChecker(
        #             vector_store=self.vector_store,
        #             api_key=self.llm_api_key,
        #             llm_base_url=self.llm_base_url
        #         ))
        #         self.checkers.append(TableRAGChecker(
        #             vector_store=self.vector_store,
        #             api_key=self.llm_api_key,
        #             llm_base_url=self.llm_base_url
        #         ))
        #         print("  ✅ RAG-проверки включены")
        #     except Exception as e:
        #         print(f"  ⚠️  Не удалось инициализировать RAG-проверки: {e}")
    
    def add_checker(self, checker: BaseChecker):
        """Добавляет пользовательский чекер"""
        self.checkers.append(checker)
    
    def check(self, ast_tree: DocumentNode, enabled_checkers: List[str] = None) -> Dict:
        """
        Выполняет все проверки документа.
        """
        all_errors: List[CheckError] = []
        by_checker: Dict[str, List[dict]] = {}  # ← Изменили тип на List[dict]
        
        for checker in self.checkers:
            if enabled_checkers and checker.name not in enabled_checkers:
                continue
            
            print(f"  Проверка: {checker.name}...")
            errors = checker.check(ast_tree)
            
            if errors:
                # Конвертируем объекты CheckError в словари
                by_checker[checker.name] = [e.to_dict() for e in errors]
                all_errors.extend(errors)
        
        # Формируем сводку
        summary = {
            "total": len(all_errors),
            "errors": sum(1 for e in all_errors if e.severity == Severity.ERROR),
            "warnings": sum(1 for e in all_errors if e.severity == Severity.WARNING),
            "info": sum(1 for e in all_errors if e.severity == Severity.INFO)
        }
        
        return {
            "summary": summary,
            "by_checker": by_checker,  # Теперь здесь словари, а не объекты
            "all_errors": [e.to_dict() for e in all_errors]
        }
    
    def print_report(self, results: Dict):
        """Выводит отчёт о проверке в консоль"""
        summary = results["summary"]
        
        print("\n" + "=" * 60)
        print("ОТЧЁТ О ПРОВЕРКЕ ДОКУМЕНТА")
        print("=" * 60)
        print(f"\nВсего найдено: {summary['total']}")
        print(f"  Ошибок: {summary['errors']}")
        print(f"  Предупреждений: {summary['warnings']}")
        print(f"  Информационных: {summary['info']}")
        
        if summary['total'] == 0:
            print("\n✅ Документ соответствует требованиям!")
            return
        
        print("\n" + "-" * 60)
        print("ДЕТАЛЬНЫЙ ОТЧЁТ")
        print("-" * 60)
        
        for checker_name, errors in results["by_checker"].items():
            print(f"\n[{checker_name.upper()}] ({len(errors)} проблем)")
            
            for i, error in enumerate(errors[:5], 1):
                # Теперь error — это словарь, а не объект
                severity_icon = {
                    "error": "❌",
                    "warning": "⚠️",
                    "info": "ℹ️"
                }[error["severity"]]
                
                print(f"  {severity_icon} {error['message']}")
                print(f"     {error['gost_reference']}")
                if error.get("context"):
                    print(f"     Контекст: {error['context']}")
            
            # if len(errors) > 5:
            #     print(f"  ... и ещё {len(errors) - 5} проблем")
        
        print("\n" + "=" * 60)


# ==========================================
# Пример использования
# ==========================================

if __name__ == "__main__":
    from doc_parser.docx_ast_parser import DocxASTParser
    
    # Парсим документ
    parser = DocxASTParser("test_document.docx")
    ast_tree = parser.parse()
    
    # Создаём чекер и запускаем проверки
    checker = DocumentChecker()
    results = checker.check(ast_tree)
    
    # Выводим отчёт
    checker.print_report(results)
    
    # Опционально: сохраняем результаты в JSON
    import json
    with open("check_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)