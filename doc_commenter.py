from typing import List, Dict, Optional, Any
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree
import re
from datetime import datetime


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    """Универсальное извлечение поля из объекта или словаря"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class DocumentCommenter:
    """
    Модуль для добавления комментариев к ошибкам в документе.
    """
    
    # Namespace для работы с XML
    W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    
    def __init__(self, input_path: str, errors: List[Any]):
        self.input_path = input_path
        self.doc = Document(input_path)
        self.errors = errors
        
        self.stats = {
            'total': len(errors),
            'commented': 0,
            'not_found': 0,
            'skipped': 0,
        }
        
        self.comment_id = 0
        self.comments_part = None
        self.comments_root = None
        
        # Инициализируем часть комментариев
        self._init_comments_part()
    
    def _init_comments_part(self):
        """Инициализирует часть комментариев в документе"""
        try:
            # Пытаемся найти существующую часть комментариев
            for rel in self.doc.part.rels.values():
                if 'comments' in rel.reltype:
                    self.comments_part = rel.target_part
                    self.comments_root = etree.fromstring(self.comments_part.blob)
                    return
        except Exception:
            pass
        
        # Создаём новую часть комментариев
        try:
            from docx.opc.part import Part
            from docx.opc.packuri import PackURI
            
            comments_xml = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
                b' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                b'</w:comments>'
            )
            
            self.comments_part = Part(
                PackURI('/word/comments.xml'),
                'application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml',
                comments_xml,
                self.doc.part.package
            )
            
            self.comments_root = etree.fromstring(comments_xml)
            
            # Добавляем связь
            self.doc.part.relate_to(
                self.comments_part,
                'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'
            )
        except Exception as e:
            print(f"Warning: Could not initialize comments part: {e}")
    
    def comment_and_save(self, output_path: str) -> Dict:
        """Добавляет комментарии и сохраняет документ"""
        for error in self.errors:
            self._add_comment_for_error(error)
        
        # Сохраняем обновлённые комментарии
        if self.comments_part and self.comments_root is not None:
            self.comments_part._blob = etree.tostring(
                self.comments_root, 
                xml_declaration=True, 
                encoding='UTF-8', 
                standalone=True
            )
        
        self.doc.save(output_path)
        return self.stats
    
    def _get_severity_str(self, error: Any) -> str:
        """Преобразует severity в строку"""
        severity = _get_field(error, 'severity', 'info')
        if hasattr(severity, 'value'):
            return str(severity.value).upper()
        return str(severity).upper()
    
    def _extract_text_from_context(self, context: str) -> Optional[str]:
        """Извлекает текст элемента из контекста ошибки"""
        # Ищем все тексты в одинарных кавычках
        matches = re.findall(r"'([^']+)'", context)
        if not matches:
            return None
        
        # Берём самый длинный текст (обычно это текст элемента)
        text = max(matches, key=len)
        
        # Убираем "..." в конце
        text = re.sub(r'\.{2,}$', '', text).strip()
        
        # Если текст слишком короткий, вероятно, это не то
        if len(text) < 3:
            return None
        
        return text
    
    def _find_paragraph_by_text(self, search_text: str) -> Optional[Any]:
        """
        Ищет параграф по тексту с улучшенной логикой.
        """
        search_text = search_text.strip()
        if not search_text:
            return None
        
        # Сначала ищем точное совпадение
        for para in self.doc.paragraphs:
            if para.text.strip() == search_text:
                return para
        
        # Затем ищем по вхождению подстроки (начало текста)
        for para in self.doc.paragraphs:
            para_text = para.text.strip()
            if para_text.startswith(search_text[:min(50, len(search_text))]):
                return para
        
        # Наконец, ищем по любому вхождению
        for para in self.doc.paragraphs:
            para_text = para.text.strip()
            if search_text in para_text:
                return para
        
        return None
    
    def _add_comment_to_paragraph(self, paragraph, comment_text: str, author: str = "Нормоконтроль"):
        """Добавляет комментарий к параграфу"""
        self.comment_id += 1
        comment_id = self.comment_id
        
        # 1. Создаём комментарий в части комментариев
        self._add_comment_to_comments_part(comment_id, comment_text, author)
        
        # 2. Добавляем маркеры комментария в параграф
        self._add_comment_markers_to_paragraph(paragraph, comment_id)
    
    def _add_comment_to_comments_part(self, comment_id: int, text: str, author: str):
        """Добавляет комментарий в XML части комментариев"""
        if self.comments_root is None:
            return
        
        # Создаём новый комментарий с правильными namespace
        comment_elem = etree.SubElement(self.comments_root, f'{{{self.W_NS}}}comment')
        comment_elem.set(f'{{{self.W_NS}}}id', str(comment_id))
        comment_elem.set(f'{{{self.W_NS}}}author', author)
        comment_elem.set(f'{{{self.W_NS}}}date', datetime.now().isoformat())
        comment_elem.set(f'{{{self.W_NS}}}initials', "НК")
        
        # Добавляем параграф с текстом комментария
        p_elem = etree.SubElement(comment_elem, f'{{{self.W_NS}}}p')
        r_elem = etree.SubElement(p_elem, f'{{{self.W_NS}}}r')
        t_elem = etree.SubElement(r_elem, f'{{{self.W_NS}}}t')
        t_elem.text = text
        t_elem.set(f'{{{self.W_NS}}}space', 'preserve')
    
    def _add_comment_markers_to_paragraph(self, paragraph, comment_id: int):
        """Добавляет маркеры начала и конца комментария в параграф"""
        p_elem = paragraph._element
        
        # Создаём маркер начала комментария
        comment_range_start = OxmlElement('w:commentRangeStart')
        comment_range_start.set(qn('w:id'), str(comment_id))
        
        # Создаём маркер конца комментария
        comment_range_end = OxmlElement('w:commentRangeEnd')
        comment_range_end.set(qn('w:id'), str(comment_id))
        
        # Создаём ссылку на комментарий
        comment_reference_run = OxmlElement('w:r')
        rpr = OxmlElement('w:rPr')
        rstyle = OxmlElement('w:rStyle')
        rstyle.set(qn('w:val'), 'CommentReference')
        rpr.append(rstyle)
        comment_reference_run.append(rpr)
        
        comment_ref_elem = OxmlElement('w:commentReference')
        comment_ref_elem.set(qn('w:id'), str(comment_id))
        comment_reference_run.append(comment_ref_elem)
        
        # Вставляем маркеры в правильные позиции
        # Начало — после pPr (если есть) или в начало
        pPr = p_elem.find(qn('w:pPr'))
        if pPr is not None:
            # Вставляем после pPr, но перед первым run
            pPr.addnext(comment_range_start)
        else:
            # Вставляем в самое начало
            p_elem.insert(0, comment_range_start)
        
        # Конец — в конец параграфа, перед bookmarkStart (если есть)
        # Находим последний элемент, который не является commentRangeStart
        insert_position = len(p_elem)
        for i in range(len(p_elem) - 1, -1, -1):
            child = p_elem[i]
            if child.tag not in [qn('w:commentRangeStart'), qn('w:commentRangeEnd')]:
                insert_position = i + 1
                break
        
        p_elem.insert(insert_position, comment_range_end)
        p_elem.insert(insert_position + 1, comment_reference_run)
    
    def _add_comment_for_error(self, error: Any):
        """Добавляет комментарий для одной ошибки"""
        node_type = _get_field(error, 'node_type', '')
        context = _get_field(error, 'context', '')
        message = _get_field(error, 'message', '')
        gost_ref = _get_field(error, 'gost_ref', '')
        severity = self._get_severity_str(error)
        
        # === LLM-метка (если есть) ===
        llm_verified = getattr(error, 'llm_verified', None)
        llm_reason = getattr(error, 'llm_reason', '')
        
        # Формируем текст комментария
        if llm_verified is True:
            comment_text = f"[{severity}] ✅ {message}"
            if llm_reason:
                comment_text += f"\n\n💬 LLM: {llm_reason}"
        elif llm_verified is False:
            comment_text = f"[{severity}] ❌ {message}"
            if llm_reason:
                comment_text += f"\n\n💬 LLM: {llm_reason}"
        else:
            comment_text = f"[{severity}] {message}"
        
        if gost_ref:
            comment_text += f"\n📖 {gost_ref}"
        
        # === НОВОЕ: Обработка node_type="llm_check" ===
        # Для LLM-чекеров пытаемся найти параграф по контексту, как для обычных ошибок
        if node_type == 'llm_check':
            text = self._extract_text_from_context(context)
            if text:
                paragraph = self._find_paragraph_by_text(text)
                if paragraph:
                    self._add_comment_to_paragraph(paragraph, comment_text)
                    self.stats['commented'] += 1
                else:
                    # Если не нашли по тексту, добавляем к первому параграфу
                    if self.doc.paragraphs:
                        self._add_comment_to_paragraph(self.doc.paragraphs[0], comment_text)
                        self.stats['commented'] += 1
                    else:
                        self.stats['skipped'] += 1
            else:
                # Если контекст пустой, добавляем к первому параграфу
                if self.doc.paragraphs:
                    self._add_comment_to_paragraph(self.doc.paragraphs[0], comment_text)
                    self.stats['commented'] += 1
                else:
                    self.stats['skipped'] += 1
            return
        
        # === Остальная логика без изменений ===
        # --- Параграфы, заголовки, пункты списков ---
        if node_type in ('heading', 'paragraph', 'list_item'):
            text = self._extract_text_from_context(context)
            if text:
                paragraph = self._find_paragraph_by_text(text)
                if paragraph:
                    self._add_comment_to_paragraph(paragraph, comment_text)
                    self.stats['commented'] += 1
                else:
                    self.stats['not_found'] += 1
            else:
                self.stats['skipped'] += 1
        
        # --- Таблицы ---
        elif node_type == 'table':
            table_idx_match = re.search(r'Таблица\s*#(\d+)', context)
            if table_idx_match:
                table_idx = int(table_idx_match.group(1)) - 1
                tables = self.doc.tables
                if 0 <= table_idx < len(tables):
                    table = tables[table_idx]
                    if table.rows and table.rows[0].cells:
                        first_cell = table.rows[0].cells[0]
                        if first_cell.paragraphs:
                            self._add_comment_to_paragraph(first_cell.paragraphs[0], comment_text)
                            self.stats['commented'] += 1
                        else:
                            self.stats['skipped'] += 1
                else:
                    self.stats['not_found'] += 1
            else:
                self.stats['skipped'] += 1
        
        # --- Документные ошибки ---
        elif node_type == 'document':
            if self.doc.paragraphs:
                self._add_comment_to_paragraph(self.doc.paragraphs[0], comment_text)
                self.stats['commented'] += 1
            else:
                self.stats['skipped'] += 1
        
        # --- Сноски ---
        elif node_type == 'footnote':
            self.stats['skipped'] += 1
        
        # --- Неизвестный тип ---
        else:
            self.stats['skipped'] += 1


def comment_document(input_path: str, output_path: str, errors: List[Any]) -> Dict:
    """
    Быстрая функция для добавления комментариев к ошибкам в документе.
    """
    commenter = DocumentCommenter(input_path, errors)
    return commenter.comment_and_save(output_path)