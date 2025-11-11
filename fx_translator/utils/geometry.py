"""
Утилиты для геометрических расчётов.

Этот модуль содержит функции для работы с координатами и bounding boxes.
"""

from __future__ import annotations
from typing import List

from fx_translator.core.models import Segment


def x_overlap(s1: Segment, s2: Segment) -> float:
    """
    Вычисляет горизонтальное перекрытие между двумя сегментами.

    Args:
        s1: Первый сегмент
        s2: Второй сегмент

    Returns:
        Длина перекрытия по оси X
    """
    left1, right1 = s1.left, s1.left + s1.width
    left2, right2 = s2.left, s2.left + s2.width

    overlap_start = max(left1, left2)
    overlap_end = min(right1, right2)

    return max(0.0, overlap_end - overlap_start)


def sort_segments_reading_order(segments: List[Segment]) -> List[Segment]:
    """
    Сортирует сегменты в порядке чтения (сверху вниз, слева направо).

    Args:
        segments: Список сегментов для сортировки

    Returns:
        Отсортированный список сегментов
    """
    return sorted(segments, key=lambda s: (s.top, s.left))


def merge_segments(s1: Segment, s2: Segment) -> Segment:
    """
    Объединяет два сегмента в один.

    Args:
        s1: Первый сегмент
        s2: Второй сегмент

    Returns:
        Объединённый сегмент
    """
    # Вычисляем новый bbox
    left = min(s1.left, s2.left)
    top = min(s1.top, s2.top)
    right = max(s1.left + s1.width, s2.left + s2.width)
    bottom = max(s1.top + s1.height, s2.top + s2.height)

    # Объединяем текст
    combined_text = (s1.text + " " + s2.text).strip()

    return Segment(
        pagenumber=s1.pagenumber,
        left=left,
        top=top,
        width=right - left,
        height=bottom - top,
        pagewidth=s1.pagewidth,
        pageheight=s1.pageheight,
        text=combined_text,
        type=s1.type,  # Берём тип первого сегмента
        blockid=s1.blockid,
        lineheight=max(s1.lineheight, s2.lineheight),
    )
