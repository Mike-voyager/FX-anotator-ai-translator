"""
Аннотация PDF с визуализацией сегментов.

Этот модуль содержит функции для создания аннотированного PDF с разметкой сегментов.
"""

from __future__ import annotations
import math
from typing import List, Tuple

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf  # type: ignore

from fx_translator.core.models import PageBatch
from fx_translator.core.config import (
    ACCENT_GREEN,
    ACCENT_GREEN_DARK,
    TEXT_DARK,
    BIG_LBL_BG,
    BIG_LBL_FG,
    BIG_LBL_BR,
    BIG_LBL_FS,
    BIG_LBL_PAD,
    BIG_LBL_MARG,
    BIG_LBL_RND,
)
from fx_translator.utils.geometry import sort_segments_reading_order


def _nearest_points(
    a: "pymupdf.Rect", b: "pymupdf.Rect"
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Находит ближайшие точки между двумя прямоугольниками.
    
    Args:
        a: Первый прямоугольник
        b: Второй прямоугольник
        
    Returns:
        Кортеж из двух точек: (точка на a, точка на b)
    """
    # Центры сторон прямоугольника a
    ca = [
        (a.x0, (a.y0 + a.y1) / 2),  # левая
        (a.x1, (a.y0 + a.y1) / 2),  # правая
        ((a.x0 + a.x1) / 2, a.y0),  # верхняя
        ((a.x0 + a.x1) / 2, a.y1),  # нижняя
    ]
    
    # Центры сторон прямоугольника b
    cb = [
        (b.x0, (b.y0 + b.y1) / 2),
        (b.x1, (b.y0 + b.y1) / 2),
        ((b.x0 + b.x1) / 2, b.y0),
        ((b.x0 + b.x1) / 2, b.y1),
    ]
    
    best = None
    best_dist = 1e18
    
    for p in ca:
        for q in cb:
            dist = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
            if dist < best_dist:
                best_dist, best = dist, (p, q)
    
    return best


def _draw_leader(
    page,
    rect_label: "pymupdf.Rect",
    rect_box: "pymupdf.Rect",
    color=ACCENT_GREEN,
    width: float = 0.8,
    dot_radius: float = 1.6,
) -> None:
    """
    Рисует соединительную линию (leader) между лейблом и блоком.
    
    Args:
        page: PyMuPDF страница
        rect_label: Прямоугольник лейбла
        rect_box: Прямоугольник блока
        color: Цвет линии
        width: Толщина линии
        dot_radius: Радиус точки на конце линии
    """
    (p_x, p_y), (q_x, q_y) = _nearest_points(rect_label, rect_box)
    
    # Рисуем линию
    page.draw_line(p1=(p_x, p_y), p2=(q_x, q_y), color=color, width=width)
    
    # Рисуем точку на конце
    page.draw_circle(
        center=(q_x, q_y), radius=dot_radius, color=color, fill=color, width=0
    )


def _measure_text_w(page, text: str, fontsize: float) -> float:
    """
    Измеряет ширину текста на странице.
    
    Args:
        page: PyMuPDF страница
        text: Текст для измерения
        fontsize: Размер шрифта
        
    Returns:
        Ширина текста в пунктах
    """
    try:
        return page.get_text_length(text, fontsize=fontsize)
    except Exception:
        # Грубая оценка, если шрифт не замерен
        return max(10.0, len(text) * fontsize * 0.55)


def _choose_label_slot(
    page_rect: "pymupdf.Rect",
    box: "pymupdf.Rect",
    w: float,
    h: float,
    margin: float,
) -> "pymupdf.Rect":
    """
    Выбирает оптимальную позицию для лейбла рядом с блоком.
    
    Пытается разместить лейбл слева, справа, сверху, снизу или внутри блока.
    
    Args:
        page_rect: Прямоугольник страницы
        box: Прямоугольник блока
        w: Ширина лейбла
        h: Высота лейбла
        margin: Отступ от краёв
        
    Returns:
        Прямоугольник для размещения лейбла
    """
    # Пытаемся слева
    x = box.x0 - margin - w
    y = max(page_rect.y0 + margin, box.y0)
    if x >= page_rect.x0 + margin and y + h <= page_rect.y1 - margin:
        return pymupdf.Rect(x, y, x + w, y + h)
    
    # Справа
    x = box.x1 + margin
    y = max(page_rect.y0 + margin, box.y0)
    if x + w <= page_rect.x1 - margin and y + h <= page_rect.y1 - margin:
        return pymupdf.Rect(x, y, x + w, y + h)
    
    # Сверху
    x = max(page_rect.x0 + margin, min(box.x0, page_rect.x1 - margin - w))
    y = box.y0 - margin - h
    if y >= page_rect.y0 + margin:
        return pymupdf.Rect(x, y, x + w, y + h)
    
    # Снизу
    x = max(page_rect.x0 + margin, min(box.x0, page_rect.x1 - margin - w))
    y = box.y1 + margin
    if y + h <= page_rect.y1 - margin:
        return pymupdf.Rect(x, y, x + w, y + h)
    
    # Внутрь (левый верхний угол)
    x = min(box.x0 + margin, page_rect.x1 - margin - w)
    y = min(box.y0 + margin, page_rect.y1 - margin - h)
    return pymupdf.Rect(x, y, x + w, y + h)


def _draw_big_label(
    page,
    target_box: "pymupdf.Rect",
    text_lines: List[str],
    fontsize: float = BIG_LBL_FS,
    pad: float = BIG_LBL_PAD,
    bg=BIG_LBL_BG,
    fg=BIG_LBL_FG,
    br=BIG_LBL_BR,
    margin: float = BIG_LBL_MARG,
) -> "pymupdf.Rect":
    """
    Рисует большой лейбл рядом с блоком.
    
    Args:
        page: PyMuPDF страница
        target_box: Прямоугольник блока
        text_lines: Список строк текста для лейбла
        fontsize: Размер шрифта
        pad: Отступ внутри лейбла
        bg: Цвет фона
        fg: Цвет текста
        br: Цвет границы
        margin: Отступ от блока
        
    Returns:
        Прямоугольник размещённого лейбла
    """
    # Измеряем размер текста
    tw = max(_measure_text_w(page, ln, fontsize) for ln in text_lines)
    th = fontsize * 1.2
    
    box_w = tw + pad * 2
    box_h = th * len(text_lines) + pad * 2
    
    # Выбираем позицию
    page_box = page.rect
    rect = _choose_label_slot(page_box, target_box, box_w, box_h, margin)
    
    # Рисуем фон с границей
    sh = page.new_shape()
    sh.draw_rect(rect)
    sh.finish(width=1, color=br, fill=bg, fill_opacity=1.0, stroke_opacity=1.0)
    sh.commit()
    
    # Пишем текст
    x = rect.x0 + pad
    y = rect.y0 + pad + fontsize
    
    for ln in text_lines:
        page.insert_text((x, y), ln, fontsize=fontsize, color=fg)
        y += th
    
    return rect


def _format_big_label(
    page_no: int, side: str, block_id: int, seg_type: str, fmt: str
) -> List[str]:
    """
    Форматирует текст лейбла по шаблону.
    
    Args:
        page_no: Номер страницы
        side: Сторона страницы ("L", "R" или "")
        block_id: ID блока
        seg_type: Тип сегмента
        fmt: Шаблон форматирования (поддерживает {p}, {s}, {b}, {t})
             Вертикальная черта | разделяет строки
        
    Returns:
        Список строк для лейбла
    """
    payload = {
        "p": page_no,
        "s": side if side in ("L", "R") else "",
        "b": block_id,
        "t": seg_type or "",
    }
    
    s = fmt.format(**payload)
    return [ln.strip() for ln in s.split("|") if ln.strip()]


def annotate_pdf_with_segments(
    input_pdf: str,
    out_pdf: str,
    pages: List[PageBatch],
    big_labels: bool = True,
    big_label_fmt: str = "P{p}{s}:{b}",
    big_label_fontsize: float = BIG_LBL_FS,
) -> None:
    """
    Создаёт аннотированный PDF с визуальной разметкой сегментов.
    
    Рисует рамки вокруг сегментов и добавляет информационные лейблы.
    
    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf: Путь для сохранения аннотированного PDF
        pages: Список батчей страниц с сегментами
        big_labels: Рисовать большие лейблы
        big_label_fmt: Шаблон формата лейбла (поддерживает {p}, {s}, {b}, {t})
        big_label_fontsize: Размер шрифта лейбла
    """
    doc = pymupdf.open(input_pdf)
    
    try:
        for pb in pages:
            pno = pb.pagenumber - 1
            
            if pno < 0 or pno >= doc.page_count:
                continue
            
            page = doc[pno]
            side = getattr(pb, "logicalside", "")
            
            for s in sort_segments_reading_order(pb.segments):
                # Рамка сегмента
                box = pymupdf.Rect(s.left, s.top, s.left + s.width, s.top + s.height)
                
                shape = page.new_shape()
                shape.draw_rect(box)
                shape.finish(width=0.8, color=(0.9, 0.1, 0.1), fill=None)
                shape.commit()
                
                # Маленький бейдж с ID в углу рамки
                id_text = f"{s.blockid}"
                page.insert_text(
                    (box.x0 + 2, box.y0 + 2 + 8),
                    id_text,
                    fontsize=8,
                    color=(0.9, 0.1, 0.1),
                )
                
                # Большой лейбл
                if big_labels:
                    lines = _format_big_label(
                        pb.pagenumber, side, s.blockid, s.type, big_label_fmt
                    )
                    
                    if lines:
                        lbl_rect = _draw_big_label(
                            page, box, lines, fontsize=big_label_fontsize
                        )
                        
                        # Соединительная линия
                        _draw_leader(page, lbl_rect, box)
        
        doc.save(out_pdf)
    
    finally:
        doc.close()