"""
Модели данных для FX-Translator.

Этот модуль содержит все dataclass модели, используемые в приложении.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class TextLine:
    """
    Строка текста с метаданными о шрифте и позиции.

    Attributes:
        text: Текстовое содержимое строки
        bbox: Ограничивающий прямоугольник (x0, y0, x1, y1)
        fontsize: Размер шрифта
        fontname: Название шрифта
        flags: Флаги форматирования (битовая маска)
        isbold: Является ли текст жирным
        isitalic: Является ли текст курсивом
    """

    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    fontsize: float
    fontname: str
    flags: int
    isbold: bool
    isitalic: bool


@dataclass
class TextBlock:
    """
    Блок текста, состоящий из нескольких строк.

    Attributes:
        lines: Список строк текста в блоке
        bbox: Ограничивающий прямоугольник блока
        blocktype: Тип блока (paragraph, heading, caption, и т.д.)
        mergedtext: Объединённый текст всех строк
        confidence: Уровень уверенности в классификации (0.0-1.0)
    """

    lines: List[TextLine]
    bbox: tuple[float, float, float, float]
    blocktype: str  # "paragraph", "heading", "caption", "footnote", etc.
    mergedtext: str
    confidence: float = 1.0


@dataclass
class Segment:
    """
    Сегмент текста на странице PDF.

    Attributes:
        pagenumber: Номер страницы (1-based)
        left: Левая координата сегмента
        top: Верхняя координата сегмента
        width: Ширина сегмента
        height: Высота сегмента
        pagewidth: Ширина страницы
        pageheight: Высота страницы
        text: Текстовое содержимое сегмента
        type: Тип сегмента (Text, Title, и т.д.)
        blockid: Идентификатор блока
        lineheight: Высота строки (для PyMuPDF)
    """

    pagenumber: int
    left: float
    top: float
    width: float
    height: float
    pagewidth: float
    pageheight: float
    text: str
    type: str
    blockid: int = 0
    lineheight: float = 0.0  # pt (PyMuPDF)


@dataclass
class PageBatch:
    """
    Пакет сегментов для одной страницы.

    Attributes:
        pagenumber: Номер страницы (1-based)
        segments: Список сегментов на странице
        logicalside: Логическая сторона страницы ("L", "R" или пусто для обычных страниц)
    """

    pagenumber: int
    segments: List[Segment] = field(default_factory=list)
    logicalside: str = ""  # "L", "R", или пусто
