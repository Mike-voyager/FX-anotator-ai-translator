"""
Анализ layout PDF документов.

Этот модуль содержит функции для работы с разворотами (spreads).
"""

from __future__ import annotations
import logging
from typing import List

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf  # type: ignore

from fx_translator.core.models import PageBatch
from fx_translator.utils.geometry import sort_segments_reading_order
from fx_translator.utils.text import parse_page_set


def split_spreads(
    pages: List[PageBatch],
    pdfpath: str,
    ratio_threshold: tuple = (1.25, 1.4),
    center_image_threshold: float = 0.33,
    debug: bool = True,
) -> List[PageBatch]:
    """
    Делит развороты на отдельные страницы, учитывая центральные блоки.
    
    Если центральный широкоформатный блок пересекает середину — страницу не делим.
    В остальных случаях — делим ровно пополам.
    
    Args:
        pages: Список батчей страниц
        pdfpath: Путь к PDF файлу
        ratio_threshold: Диапазон соотношений ширины/высоты для определения разворота
        center_image_threshold: Порог ширины центрального блока (доля от ширины страницы)
        debug: Включить отладочные сообщения
        
    Returns:
        Список обработанных PageBatch (развороты разделены на L/R)
    """
    result: List[PageBatch] = []
    doc = pymupdf.open(pdfpath)
    
    try:
        for pb in pages:
            pno = pb.pagenumber - 1
            
            if pno < 0 or pno >= doc.page_count:
                if debug:
                    logging.debug(
                        f"[split] p{pb.pagenumber}: skip (no such page in PDF)"
                    )
                result.append(pb)
                continue
            
            page = doc[pno]
            w, h = page.rect.width, page.rect.height
            
            if h <= 0:
                if debug:
                    logging.debug(f"[split] p{pb.pagenumber}: skip (h<=0)")
                result.append(pb)
                continue
            
            ratio = w / h
            
            # Берём первое значение из tuple для сравнения
            min_ratio = ratio_threshold[0] if isinstance(ratio_threshold, tuple) else ratio_threshold
            
            if ratio < min_ratio:
                if debug:
                    logging.debug(
                        f"[split] p{pb.pagenumber}: no-spread (ratio {ratio:.3f} < {min_ratio})"
                    )
                result.append(pb)
                continue
            
            mid_x = w * 0.5
            
            # Ищем центральные «широкие» блоки (text blocks из PDF)
            blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
            central = []
            
            for b in blocks:
                x0, y0, x1, y1 = b[:4]
                bw = x1 - x0
                
                if bw >= w * center_image_threshold and x0 < mid_x < x1:
                    central.append((x0, y0, x1, y1))
            
            if central:
                if debug:
                    logging.debug(
                        f"[split] p{pb.pagenumber}: keep-whole (central-wide={len(central)})"
                    )
                result.append(pb)
                continue
            
            # Делим пополам (по центру), даже если мало текстовых сегментов
            left = [s for s in pb.segments if (s.left + s.width * 0.5) <= mid_x]
            right = [s for s in pb.segments if (s.left + s.width * 0.5) > mid_x]
            
            left = sort_segments_reading_order(left)
            for i, s in enumerate(left, 1):
                s.blockid = i
            
            pb_left = PageBatch(
                pagenumber=pb.pagenumber,
                segments=left,
                logicalside="L",
            )
            
            right = sort_segments_reading_order(right)
            for i, s in enumerate(right, 1):
                s.blockid = i
            
            pb_right = PageBatch(
                pagenumber=pb.pagenumber,
                segments=right,
                logicalside="R",
            )
            
            if debug:
                logging.info(
                    f"[split] p{pb.pagenumber}: split-half (ratio {ratio:.3f}, L={len(left)}, R={len(right)})"
                )
            
            result.append(pb_left)
            result.append(pb_right)
    
    finally:
        doc.close()
    
    return result


def split_spreads_force_half(
    pages: List[PageBatch],
    exceptions: set[int],
) -> List[PageBatch]:
    """
    Делит каждую физическую страницу пополам (L/R), кроме страниц из exceptions.
    
    Если на странице нет сегментов, оставляет её как есть.
    
    Args:
        pages: Список батчей страниц
        exceptions: Множество номеров страниц, которые НЕ нужно делить
        
    Returns:
        Список PageBatch с принудительно разделёнными разворотами
    """
    out: List[PageBatch] = []
    
    for pb in pages:
        if pb.pagenumber in exceptions or not pb.segments:
            out.append(pb)
            continue
        
        w = pb.segments[0].pagewidth
        mid_x = w * 0.5
        
        left = [s for s in pb.segments if (s.left + s.width * 0.5) <= mid_x]
        right = [s for s in pb.segments if (s.left + s.width * 0.5) > mid_x]
        
        left = sort_segments_reading_order(left)
        for i, s in enumerate(left, 1):
            s.blockid = i
        
        pb_left = PageBatch(
            pagenumber=pb.pagenumber,
            segments=left,
            logicalside="L",
        )
        
        right = sort_segments_reading_order(right)
        for i, s in enumerate(right, 1):
            s.blockid = i
        
        pb_right = PageBatch(
            pagenumber=pb.pagenumber,
            segments=right,
            logicalside="R",
        )
        
        out.append(pb_left)
        out.append(pb_right)
    
    return out