from typing import Optional, Any
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from docx.oxml.ns import qn


def resolve_paragraph_property(paragraph: Paragraph, property_name: str) -> Optional[Any]:
    """
    Рекурсивно ищет свойство абзаца в цепочке стилей.
    (Без изменений — работает корректно)
    """
    # 1. Проверяем прямое свойство параграфа
    fmt = paragraph.paragraph_format
    direct_value = getattr(fmt, property_name, None)
    if direct_value is not None:
        return direct_value
    
    # 2. Идём по цепочке стилей
    style = paragraph.style
    visited_styles = set()
    
    while style is not None:
        style_id = id(style)
        if style_id in visited_styles:
            break
        visited_styles.add(style_id)
        
        if hasattr(style, 'paragraph_format'):
            style_fmt = style.paragraph_format
            style_value = getattr(style_fmt, property_name, None)
            if style_value is not None:
                return style_value
        
        style = style.base_style
    
    # 3. Проверяем стиль Normal
    try:
        normal_style = paragraph.part.document.styles['Normal']
        if hasattr(normal_style, 'paragraph_format'):
            normal_fmt = normal_style.paragraph_format
            normal_value = getattr(normal_fmt, property_name, None)
            if normal_value is not None:
                return normal_value
    except (KeyError, AttributeError):
        pass
    
    # 4. Fallback: XML
    return _get_property_from_xml(paragraph, property_name)


def resolve_run_property(run: Run, paragraph: Paragraph, property_name: str) -> Optional[Any]:
    """
    Рекурсивно ищет свойство Run (шрифта) в цепочке стилей.
    
    Args:
        run: Объект Run из python-docx
        paragraph: Объект Paragraph, которому принадлежит Run
        property_name: Имя свойства Font (например, 'size', 'bold')
    
    Returns:
        Значение свойства или None
    """
    # 1. Прямое свойство Run
    direct_value = getattr(run.font, property_name, None)
    if direct_value is not None:
        return direct_value
    
    # 2. Идём по цепочке стилей параграфа
    style = paragraph.style
    visited_styles = set()
    
    while style is not None:
        style_id = id(style)
        if style_id in visited_styles:
            break
        visited_styles.add(style_id)
        
        # Проверяем формат шрифта стиля
        if hasattr(style, 'font'):
            style_value = getattr(style.font, property_name, None)
            if style_value is not None:
                return style_value
        
        style = style.base_style
    
    # 3. Стиль Normal
    try:
        normal_style = paragraph.part.document.styles['Normal']
        if hasattr(normal_style, 'font'):
            normal_value = getattr(normal_style.font, property_name, None)
            if normal_value is not None:
                return normal_value
    except (KeyError, AttributeError):
        pass
    
    return None


def _get_property_from_xml(paragraph: Paragraph, property_name: str) -> Optional[Any]:
    """
    Fallback: извлекает свойство напрямую из XML параграфа.
    """
    pPr = paragraph._element.find(qn('w:pPr'))
    if pPr is None:
        return None
    
    xml_mapping = {
        'first_line_indent': ('w:ind', 'w:firstLine'),
        'left_indent': ('w:ind', 'w:left'),
        'right_indent': ('w:ind', 'w:right'),
        'line_spacing': ('w:spacing', 'w:line'),
        'space_before': ('w:spacing', 'w:before'),
        'space_after': ('w:spacing', 'w:after'),
    }
    
    if property_name not in xml_mapping:
        return None
    
    tag_name, attr_name = xml_mapping[property_name]
    
    ind_elem = pPr.find(qn(tag_name))
    if ind_elem is None:
        return None
    
    value_str = ind_elem.get(qn(attr_name))
    if value_str is None:
        return None
    
    return _convert_xml_value(value_str, property_name)


def _convert_xml_value(value_str: str, property_name: str) -> Optional[float]:
    """Конвертирует значение из XML в пункты."""
    try:
        value = int(value_str)
    except ValueError:
        return None
    
    if property_name in ['first_line_indent', 'left_indent', 'right_indent']:
        return value / 20.0
    
    if property_name == 'line_spacing':
        if value > 1000:
            return value / 20.0
        else:
            return value / 240.0
    
    if property_name in ['space_before', 'space_after']:
        return value / 20.0
    
    return value

def get_run_spacing_pt(run: Run) -> Optional[float]:
    """
    Извлекает интервал между символами (разрядку) из Run.
    Возвращает значение в пунктах (pt).
    
    В XML Word значение хранится в w:val внутри w:spacing (в 1/20 пункта).
    Положительное значение = разрядка, отрицательное = сжатие.
    """
    rPr = run._element.find(qn('w:rPr'))
    if rPr is not None:
        spacing_elem = rPr.find(qn('w:spacing'))
        if spacing_elem is not None:
            val_str = spacing_elem.get(qn('w:val'))
            if val_str:
                try:
                    # Конвертируем из 1/20 пункта в пункты
                    return int(val_str) / 20.0
                except ValueError:
                    pass
    return None