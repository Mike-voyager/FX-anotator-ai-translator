"""
Типы данных и enums для FX-Translator.

Этот модуль содержит базовые типы и константы, используемые во всём приложении.
"""

from __future__ import annotations
from enum import Enum
from typing import Literal


# Enum для типов блоков
class BlockType(str, Enum):
    """Типы блоков текста в документе."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TITLE = "title"
    SECTION_HEADER = "sectionheader"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    LIST_ITEM = "listitem"
    PAGE_HEADER = "pageheader"
    PAGE_FOOTER = "pagefooter"
    UNKNOWN = "unknown"


# Type alias для логической стороны страницы
logical_side = Literal["L", "R", "BOTH"]

# Type aliases для улучшения читаемости
BBox = tuple[float, float, float, float]  # (x0, y0, x1, y1)
