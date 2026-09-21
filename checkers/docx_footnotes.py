from typing import List, Dict, Optional
from docx import Document
from docx.oxml.ns import qn


class FootnoteExtractor:
    """
    Извлечение сносок из DOCX документа.
    
    Сноски в OOXML хранятся в word/footnotes.xml (нижние) 
    и word/endnotes.xml (концевые).
    """
    
    def __init__(self, doc_path: str):
        self.doc_path = doc_path
        self.doc = Document(doc_path)
    
    def extract_footnotes(self) -> List[Dict]:
        """
        Извлекает все нижние сноски из документа.
        
        Returns:
            Список сносок:
            [
                {
                    "id": 1,
                    "text": "Текст сноски",
                    "fonts": [10.0, 10.0],  # размеры шрифтов в пунктах
                    "paragraphs": ["Текст параграфа 1", "Текст параграфа 2"]
                },
                ...
            ]
        """
        return self._extract_from_part("footnotes")
    
    def extract_endnotes(self) -> List[Dict]:
        """Извлекает все концевые сноски"""
        return self._extract_from_part("endnotes")
    
    def _extract_from_part(self, part_type: str) -> List[Dict]:
        """
        Извлекает сноски/концевые сноски из соответствующей части пакета.
        
        Args:
            part_type: "footnotes" или "endnotes"
        """
        results = []
        
        try:
            # Получаем доступ к XML-части со сносками
            footnotes_part = self._get_part(part_type)
            if footnotes_part is None:
                return results
            
            root = footnotes_part.element
            
            # Определяем тег элемента сноски
            if part_type == "footnotes":
                footnote_tag = qn('w:footnote')
            else:
                footnote_tag = qn('w:endnote')
            
            # Проходим по всем сноскам
            for footnote_elem in root.findall(footnote_tag):
                # Получаем ID сноски
                footnote_id = footnote_elem.get(qn('w:id'))
                if footnote_id is None:
                    continue
                
                # Пропускаем служебные сноски (ID 0 и -1 — разделители)
                try:
                    fid = int(footnote_id)
                    if fid <= 0:
                        continue
                except ValueError:
                    continue
                
                # Извлекаем текст и шрифты
                paragraphs = []
                fonts = []
                
                for para_elem in footnote_elem.findall(qn('w:p')):
                    para_text = ""
                    
                    for run_elem in para_elem.findall(qn('w:r')):
                        # Извлекаем текст
                        text_elem = run_elem.find(qn('w:t'))
                        if text_elem is not None and text_elem.text:
                            para_text += text_elem.text
                        
                        # Извлекаем размер шрифта
                        rPr = run_elem.find(qn('w:rPr'))
                        if rPr is not None:
                            sz = rPr.find(qn('w:sz'))
                            if sz is not None:
                                # В OOXML размер хранится в полу-пунктах
                                sz_val = sz.get(qn('w:val'))
                                if sz_val:
                                    try:
                                        half_pt = int(sz_val)
                                        fonts.append(half_pt / 2.0)
                                    except ValueError:
                                        pass
                    
                    if para_text.strip():
                        paragraphs.append(para_text.strip())
                
                if paragraphs or fonts:
                    results.append({
                        "id": fid,
                        "text": " ".join(paragraphs),
                        "fonts": fonts,
                        "paragraphs": paragraphs
                    })
        
        except Exception as e:
            print(f"Warning: не удалось извлечь {part_type}: {e}")
        
        return results
    
    def _get_part(self, part_type: str):
        """
        Получает доступ к части пакета (footnotes.xml или endnotes.xml).
        """
        try:
            # В python-docx доступ к связанным частям через relationships
            # Ищем relationship по типу
            if part_type == "footnotes":
                rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
            else:
                rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes"
            
            # Получаем часть через main document part
            main_part = self.doc.part
            
            for rel in main_part.rels.values():
                if rel.reltype == rel_type:
                    return rel.target_part
            
            return None
        
        except Exception as e:
            print(f"Warning: не удалось получить часть {part_type}: {e}")
            return None


# ==========================================
# Пример использования
# ==========================================

if __name__ == "__main__":
    extractor = FootnoteExtractor("test_document.docx")
    
    print("=== Нижние сноски ===")
    footnotes = extractor.extract_footnotes()
    for fn in footnotes:
        print(f"\nСноска #{fn['id']}:")
        print(f"  Текст: {fn['text'][:100]}")
        print(f"  Шрифты: {fn['fonts']}")
    
    print("\n=== Концевые сноски ===")
    endnotes = extractor.extract_endnotes()
    for en in endnotes:
        print(f"\nСноска #{en['id']}:")
        print(f"  Текст: {en['text'][:100]}")
        print(f"  Шрифты: {en['fonts']}")