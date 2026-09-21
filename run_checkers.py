#!/usr/bin/env python3
"""
Главный скрипт запуска нормоконтроля технической документации по ГОСТ.

Использование:
    python run_checkers.py input.docx
    python run_checkers.py input.docx -o output.docx --mode comments
    python run_checkers.py input.docx --verify-llm --llm-model gpt-4o-mini
    python run_checkers.py input.docx --format json --save-json ast.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# ==========================================
# Импорт парсера и AST-утилит
# ==========================================
from doc_parser.docx_ast_parser import (
    DocxASTParser,
    DocumentNode,
    HeadingNode,
    ParagraphNode,
    TableNode,
    ListNode,
    save_ast_to_json,
    ast_to_markdown,
    walk_tree,
)

# ==========================================
# Импорт всех чекеров
# ==========================================
# Форматирование (шрифты, отступы, интервалы)
from checkers.formatting import (
    FontFamilyChecker,
    FontSizeChecker,
    LineSpacingChecker,
    ParagraphIndentChecker,
    PageMarginsChecker,
    TableFontSizeChecker,
    ApplicationFontSizeChecker,
    FootnoteFontSizeChecker,
)

# Интервалы между абзацами и заголовками
from checkers.spacing import (
    HeadingSpacingChecker,
    SubheadingSpacingChecker,
    ParagraphSpacingChecker,
)

# Нумерация заголовков и списков
from checkers.numbering import (
    HeadingNumberingChecker,
    ListNumberingChecker,
)

# Структура документа
from checkers.structure import (
    HeadingCapitalizationChecker,
    HeadingDotChecker,
    HeadingBoldChecker,
    HeadingUnderlineChecker,
    HeadingHyphenationChecker,
    HeadingTwoSentencesChecker,
    HeadingNewPageChecker,
    HeadingHierarchyChecker,
    RequiredSectionsChecker,
    UnnumberedSectionsStructureChecker,
    SectionsOrderChecker,
)

# Визуализация ошибок
from doc_marker import mark_document
from doc_commenter import comment_document

# LLM-верификация
from llm_verifier import verify_with_llm
import os

from dotenv import load_dotenv
load_dotenv()

MODEL_NAME = os.getenv("MODEL", "cotype_pro_3")
BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API")

# ==========================================
# Конфигурация чекеров
# ==========================================
def build_checkers(doc_path: str) -> List:
    """
    Создаёт список всех чекеров с правильными параметрами.
    
    Порядок важен:
    1. FontSizeChecker должен идти первым, чтобы определить базовый размер
    2. Чекеры, требующие doc_path, получают его явно
    """
    checkers = []
    
    # --- 1. ФОРМАТИРОВАНИЕ ---
    checkers.append(FontSizeChecker())  # Определяет базовый размер шрифта
    checkers.append(FontFamilyChecker())
    checkers.append(LineSpacingChecker())
    checkers.append(ParagraphIndentChecker())
    checkers.append(PageMarginsChecker(doc_path=doc_path))
    checkers.append(TableFontSizeChecker())
    checkers.append(ApplicationFontSizeChecker())
    checkers.append(FootnoteFontSizeChecker(doc_path=doc_path))
    
    # --- 2. ИНТЕРВАЛЫ И ОТСТУПЫ ---
    checkers.append(HeadingSpacingChecker())
    checkers.append(SubheadingSpacingChecker())
    checkers.append(ParagraphSpacingChecker())
    
    # --- 3. НУМЕРАЦИЯ ---
    checkers.append(HeadingNumberingChecker())
    checkers.append(ListNumberingChecker())
    
    # --- 4. СТРУКТУРА ДОКУМЕНТА ---
    checkers.append(HeadingCapitalizationChecker())
    checkers.append(HeadingDotChecker())
    checkers.append(HeadingBoldChecker())
    checkers.append(HeadingUnderlineChecker())
    checkers.append(HeadingHyphenationChecker())
    checkers.append(HeadingTwoSentencesChecker())
    checkers.append(HeadingNewPageChecker())
    checkers.append(HeadingHierarchyChecker())
    checkers.append(RequiredSectionsChecker())
    checkers.append(UnnumberedSectionsStructureChecker())
    checkers.append(SectionsOrderChecker())

    # --- 5. LLM-ПРОВЕРКИ (семантические ошибки) ---
    # Импортируем LLM-чекеры
    try:
        from checkers.llm_checkers import AbbreviationsNumberingChecker
        checkers.append(AbbreviationsNumberingChecker())
        print("✅ LLM-чекеры активированы")
    except ImportError as e:
        print(f"⚠️  Не удалось загрузить LLM-чекеры: {e}")
    
    return checkers


# ==========================================
# Запуск проверок
# ==========================================
def run_all_checkers(ast_tree: DocumentNode, checkers: List) -> List:
    """
    Запускает все чекеры и собирает ошибки.
    
    Returns:
        Список всех найденных ошибок (объекты CheckError)
    """
    all_errors = []
    
    for checker in checkers:
        try:
            errors = checker.check(ast_tree)
            all_errors.extend(errors)
        except Exception as e:
            print(f"⚠️  Ошибка при работе чекера '{checker.name}': {e}", file=sys.stderr)
    
    return all_errors


# ==========================================
# Вывод отчёта
# ==========================================
def print_report(errors: List, verbose: bool = False):
    """
    Выводит отчёт об ошибках в консоль.
    
    Args:
        errors: Список ошибок
        verbose: Если True, выводит все ошибки; иначе — только сводку
    """
    # Группируем ошибки по серьёзности
    by_severity = defaultdict(list)
    for error in errors:
        severity = error.severity.value if hasattr(error.severity, 'value') else str(error.severity)
        by_severity[severity.upper()].append(error)
    
    # Группируем по типам узлов
    by_node_type = defaultdict(list)
    for error in errors:
        by_node_type[error.node_type].append(error)
    
    # --- Сводка ---
    print("\n" + "=" * 70)
    print("📋 ОТЧЁТ НОРМОКОНТРОЛЯ")
    print("=" * 70)
    print(f"\nВсего замечаний: {len(errors)}")
    print(f"  🔴 ERROR:   {len(by_severity.get('ERROR', []))}")
    print(f"  🟡 WARNING: {len(by_severity.get('WARNING', []))}")
    print(f"  🔵 INFO:    {len(by_severity.get('INFO', []))}")
    
    print(f"\nПо типам элементов:")
    for node_type, errs in sorted(by_node_type.items()):
        print(f"  • {node_type:15s}: {len(errs)}")
    
    # --- Детальный вывод ---
    if verbose:
        print("\n" + "-" * 70)
        print("📝 ДЕТАЛЬНЫЙ СПИСОК ЗАМЕЧАНИЙ")
        print("-" * 70)
        
        for severity in ['ERROR', 'WARNING', 'INFO']:
            errs = by_severity.get(severity, [])
            if not errs:
                continue
            
            icons = {'ERROR': '🔴', 'WARNING': '🟡', 'INFO': '🔵'}
            print(f"\n{icons[severity]} {severity} ({len(errs)} шт.)")
            
            for i, error in enumerate(errs, 1):
                print(f"\n  {i}. [{error.node_type}] {error.message}")
                if error.gost_ref:
                    print(f"     📖 {error.gost_ref}")
                if error.context:
                    # Ограничиваем длину контекста для читаемости
                    ctx = error.context
                    if len(ctx) > 120:
                        ctx = ctx[:117] + "..."
                    print(f"     📍 {ctx}")
    
    print("\n" + "=" * 70)


def save_errors_to_json(errors: List, output_path: str):
    """Сохраняет ошибки в JSON файл"""
    errors_data = []
    for error in errors:
        severity = error.severity.value if hasattr(error.severity, 'value') else str(error.severity)
        errors_data.append({
            'severity': severity.upper(),
            'message': error.message,
            'gost_ref': error.gost_ref,
            'context': error.context,
            'node_type': error.node_type,
        })
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(errors_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Ошибки сохранены в {output_path}")


# ==========================================
# Главная функция
# ==========================================
def main():
    parser = argparse.ArgumentParser(
        description="Нормоконтроль технической документации по ГОСТ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python run_checkers.py document.docx
  python run_checkers.py document.docx -v
  python run_checkers.py document.docx -o marked.docx --mode comments
  python run_checkers.py document.docx -o marked.docx --mode markers
  python run_checkers.py document.docx --verify-llm --llm-model gpt-4o-mini
  python run_checkers.py document.docx --save-json errors.json
  python run_checkers.py document.docx --save-ast ast.json
        """
    )
    
    # Обязательные аргументы
    parser.add_argument('input', help='Путь к входному .docx файлу')
    
    # Опции вывода
    parser.add_argument('-o', '--output', help='Путь для сохранения модифицированного документа')
    parser.add_argument('--mode', choices=['comments', 'markers', 'both'], 
                       default='comments',
                       help='Режим визуализации: comments (комментарии), markers (выделение цветом), both (оба)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Подробный вывод всех ошибок в консоль')
    
    # LLM-верификация
    parser.add_argument('--verify-llm', action='store_true',
                       help='Верифицировать ошибки через LLM (отсеивает ложные срабатывания)')
    parser.add_argument('--llm-model', default='gpt-4o-mini',
                       help='Модель LLM для верификации (по умолчанию: gpt-4o-mini)')
    parser.add_argument('--llm-batch-size', type=int, default=10,
                       help='Размер батча для LLM (по умолчанию: 10)')
    parser.add_argument('--llm-api-key', help='API-ключ OpenAI (или переменная OPENAI_API_KEY)')
    parser.add_argument('--llm-base-url', help='Базовый URL для совместимых API')
    
    # Сохранение промежуточных данных
    parser.add_argument('--save-json', help='Сохранить ошибки в JSON файл')
    parser.add_argument('--save-ast', help='Сохранить AST-дерево в JSON файл')
    parser.add_argument('--save-markdown', help='Сохранить AST в Markdown файл')
    
    # Фильтрация
    parser.add_argument('--severity', choices=['error', 'warning', 'info', 'all'],
                       default='all', help='Фильтр по уровню серьёзности')
    
    args = parser.parse_args()
    
    # --- Проверка входного файла ---
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Файл не найден: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    if not input_path.suffix.lower() == '.docx':
        print(f"⚠️  Файл не имеет расширения .docx: {input_path}", file=sys.stderr)
    
    print(f"📄 Анализ документа: {input_path}")
    
    # --- Парсинг документа ---
    print("🔍 Парсинг документа в AST-дерево...")
    try:
        doc_parser = DocxASTParser(str(input_path))
        ast_tree = doc_parser.parse()
    except Exception as e:
        print(f"❌ Ошибка при парсинге документа: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Подсчёт элементов
    nodes = list(walk_tree(ast_tree))
    headings_count = sum(1 for n in nodes if isinstance(n, HeadingNode))
    paragraphs_count = sum(1 for n in nodes if isinstance(n, ParagraphNode))
    tables_count = sum(1 for n in nodes if isinstance(n, TableNode))
    lists_count = sum(1 for n in nodes if isinstance(n, ListNode))
    
    print(f"✅ Документ разобран: {headings_count} заголовков, {paragraphs_count} абзацев, {tables_count} таблиц, {lists_count} списков")
    
    # --- Сохранение AST (если запрошено) ---
    if args.save_ast:
        print(f"💾 Сохранение AST в {args.save_ast}...")
        save_ast_to_json(ast_tree, args.save_ast, pretty=True)
    
    if args.save_markdown:
        print(f"💾 Сохранение Markdown в {args.save_markdown}...")
        md_content = ast_to_markdown(ast_tree)
        Path(args.save_markdown).parent.mkdir(parents=True, exist_ok=True)
        with open(args.save_markdown, 'w', encoding='utf-8') as f:
            f.write(md_content)
    
    # --- Запуск чекеров ---
    print("\n🔧 Запуск чекеров...")
    checkers = build_checkers(str(input_path))
    print(f"   Активировано чекеров: {len(checkers)}")
    
    all_errors = run_all_checkers(ast_tree, checkers)
    
    # --- Фильтрация по серьёзности ---
    if args.severity != 'all':
        severity_map = {
            'error': 'ERROR',
            'warning': 'WARNING',
            'info': 'INFO',
        }
        target_severity = severity_map[args.severity]
        filtered_errors = []
        for error in all_errors:
            sev = error.severity.value if hasattr(error.severity, 'value') else str(error.severity)
            if sev.upper() == target_severity:
                filtered_errors.append(error)
        all_errors = filtered_errors

    if args.verify_llm and all_errors:
        print("\n🤖 Запуск LLM-верификации...")
        
        # === ДИАГНОСТИКА ===
        print(f"   🔑 API_KEY: {'задан (' + API_KEY[:8] + '...)' if API_KEY else 'НЕ ЗАДАН (None или пустая строка)'}")
        print(f"   🌐 BASE_URL: {BASE_URL or 'НЕ ЗАДАН'}")
        print(f"   🤖 MODEL_NAME: {MODEL_NAME}")
        
        # env_key = os.environ.get('OPENAI_API_KEY', '')
        # print(f"   📦 OPENAI_API_KEY в окружении: {'задан (' + env_key[:8] + '...)' if env_key else 'НЕ ЗАДАН'}")
        # === КОНЕЦ ДИАГНОСТИКИ ===
        
        try:
            all_errors = verify_with_llm(
                errors=all_errors,
                ast_tree=ast_tree,
                model=MODEL_NAME,
                batch_size=args.llm_batch_size,
                api_key=API_KEY,
                base_url=BASE_URL,
            )
        except Exception as e:
            print(f"❌ Ошибка LLM-верификации: {e}. Продолжаем без верификации.", file=sys.stderr)
    
    # # --- LLM-верификация ---
    # if args.verify_llm and all_errors:
    #     print("\n🤖 Запуск LLM-верификации...")
    #     try:
    #         all_errors = verify_with_llm(
    #             errors=all_errors,
    #             ast_tree=ast_tree,
    #             model=MODEL_NAME,
    #             batch_size=args.llm_batch_size,
    #             api_key=API_KEY,
    #             base_url=BASE_URL,
    #         )
    #     except Exception as e:
    #         print(f"❌ Ошибка LLM-верификации: {e}. Продолжаем без верификации.", file=sys.stderr)
    
    # # --- Вывод отчёта ---
    # print_report(all_errors, verbose=args.verbose)
    
    # --- Сохранение ошибок в JSON ---
    if args.save_json:
        save_errors_to_json(all_errors, args.save_json)
    
    # --- Визуализация ошибок в документе ---
    if args.output and all_errors:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if args.mode in ('comments', 'both'):
            print(f"\n💬 Добавление комментариев в {output_path}...")
            try:
                stats = comment_document(str(input_path), str(output_path), all_errors)
                print(f"   ✅ Добавлено комментариев: {stats['commented']}")
                if stats['not_found'] > 0:
                    print(f"   ⚠️  Не найдено в документе: {stats['not_found']}")
                if stats['skipped'] > 0:
                    print(f"   ⏭️  Пропущено (документные ошибки): {stats['skipped']}")
            except Exception as e:
                print(f"   ❌ Ошибка при добавлении комментариев: {e}", file=sys.stderr)
        
        if args.mode in ('markers', 'both'):
            marker_output = output_path.with_suffix('.marked.docx') if args.mode == 'both' else output_path
            print(f"\n🎨 Выделение ошибок цветом в {marker_output}...")
            try:
                stats = mark_document(str(input_path), str(marker_output), all_errors)
                print(f"   ✅ Выделено элементов: {stats['marked']}")
                if stats['not_found'] > 0:
                    print(f"   ⚠️  Не найдено в документе: {stats['not_found']}")
            except Exception as e:
                print(f"   ❌ Ошибка при выделении цветом: {e}", file=sys.stderr)
        
        print(f"\n📁 Результат сохранён: {args.output}")
    elif args.output and not all_errors:
        print("\n🎉 Ошибок не обнаружено! Документ соответствует ГОСТ.")
    
    # --- Итог ---
    if not all_errors:
        print("\n✅ Документ полностью соответствует требованиям ГОСТ!")
        sys.exit(0)
    else:
        error_count = sum(1 for e in all_errors 
                         if (e.severity.value if hasattr(e.severity, 'value') else str(e.severity)).upper() == 'ERROR')
        if error_count > 0:
            sys.exit(1)  # Код выхода 1, если есть критические ошибки
        sys.exit(0)


if __name__ == '__main__':
    main()