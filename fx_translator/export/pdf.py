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
    page_no: int, side: str, blockid: int, seg_type: str, fmt: str
) -> List[str]:
    """
    Форматирует текст лейбла по шаблону.

    Args:
        page_no: Номер страницы
        side: Сторона страницы ("L", "R" или "")
        blockid: ID блока
        seg_type: Тип сегмента
        fmt: Шаблон форматирования (поддерживает {p}, {s}, {b}, {t})
             Вертикальная черта | разделяет строки

    Returns:
        Список строк для лейбла
    """
    payload = {
        "p": page_no,
        "s": side if side in ("L", "R") else "",
        "b": blockid,
        "t": seg_type or "",
    }

    s = fmt.format(**payload)
    return [ln.strip() for ln in s.split("|") if ln.strip()]


def annotate_pdf_with_comments(
    input_pdf: str,
    out_pdf: str,
    pages: List[PageBatch],
    comment_format: str = "Segment {b}: {t}\nOriginal: {orig}\nTranslated: {trans}",
    include_translation: bool = True,
) -> None:
    """
    Создаёт аннотированный PDF с комментариями вместо визуального редактирования.

    Добавляет PDF аннотации (комментарии), которые видны в панели "Комментарии"
    в Adobe Acrobat и других PDF-ридерах.

    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf: Путь для сохранения PDF с комментариями
        pages: Список батчей страниц с сегментами
        comment_format: Шаблон формата комментария (поддерживает {b}, {t}, {orig}, {trans}, {p}, {s})
        include_translation: Включать перевод в комментарий
    """
    doc = pymupdf.open(input_pdf)

    try:
        for pb in pages:
            pno = pb.pagenumber - 1

            if pno < 0 or pno >= doc.page_count:
                continue

            page = doc[pno]
            side = getattr(pb, "logical_side", "")

            for s in sort_segments_reading_order(pb.segments):
                # Координаты сегмента
                rect = pymupdf.Rect(s.left, s.top, s.left + s.width, s.top + s.height)

                # Подготовка данных для комментария
                payload = {
                    "b": s.blockid,
                    "t": s.type or "text",
                    "orig": (s.text or "").strip()[:200],  # Ограничиваем длину
                    "trans": (
                        (getattr(s, "translated_text", "") or "").strip()[:200]
                        if include_translation
                        else ""
                    ),
                    "p": pb.pagenumber,
                    "s": side if side in ("L", "R") else "",
                }

                # Формируем текст комментария
                comment_text = comment_format.format(**payload)

                # Создаём текстовую аннотацию (всплывающую заметку)
                # Тип: "Text" - это стандартный "sticky note" комментарий
                annot = page.add_text_annot(
                    point=(rect.x0, rect.y0),  # Позиция иконки комментария
                    text=comment_text,
                )

                # Настройка внешнего вида комментария
                annot.set_colors(stroke=(1, 0.8, 0))  # Жёлтый цвет иконки
                annot.set_opacity(0.9)

                # Устанавливаем автора и дату
                annot.info["title"] = f"Segment {s.blockid}"
                annot.info["subject"] = s.type or "Text Block"

                # Обновляем аннотацию
                annot.update()

                # Опционально: добавляем highlight (подсветку) области текста
                # Это создаст визуальную подсветку + комментарий
                highlight = page.add_highlight_annot(rect)
                highlight.set_colors(stroke=(1, 1, 0))  # Жёлтая подсветка
                highlight.set_opacity(0.3)
                highlight.info["content"] = f"Block {s.blockid}: {s.type}"
                highlight.update()

        # Сохраняем с комментариями
        doc.save(out_pdf, garbage=4, deflate=True)

    finally:
        doc.close()


def annotate_pdf_with_markup_annotations(
    input_pdf: str,
    out_pdf: str,
    pages: List[PageBatch],
    annotation_type: str = "highlight",
    show_popup: bool = True,
) -> None:
    """
    Создаёт PDF с markup-аннотациями и редактируемыми FreeText номерами блоков.
    """
    doc = pymupdf.open(input_pdf)

    try:
        for pb in pages:
            pno = pb.pagenumber - 1

            if pno < 0 or pno >= doc.page_count:
                continue

            page = doc[pno]
            side = getattr(pb, "logical_side", "")

            for s in sort_segments_reading_order(pb.segments):
                rect = pymupdf.Rect(s.left, s.top, s.left + s.width, s.top + s.height)

                # ✅ Зелёный highlight
                if annotation_type == "highlight":
                    annot = page.add_highlight_annot(rect)
                elif annotation_type == "underline":
                    annot = page.add_underline_annot(rect)
                elif annotation_type == "squiggly":
                    annot = page.add_squiggly_annot(rect)
                elif annotation_type == "strikeout":
                    annot = page.add_strikeout_annot(rect)
                else:
                    annot = page.add_highlight_annot(rect)

                annot.set_colors(stroke=(0.5, 1, 0.5))  # Приятный зелёный
                annot.set_opacity(0.35)

                # Комментарий для всплывающей заметки
                comment_lines = [
                    f"Block #{s.blockid}",
                    f"Type: {s.type or 'text'}",
                    f"Page: {pb.pagenumber}{side}",
                ]

                if s.text:
                    comment_lines.append(f"\nOriginal:\n{s.text[:150]}")

                if hasattr(s, "translated_text") and s.translated_text:
                    comment_lines.append(f"\nTranslation:\n{s.translated_text[:150]}")

                annot.info["content"] = "\n".join(comment_lines)
                annot.info["title"] = f"Segment {s.blockid}"
                annot.info["subject"] = s.type or "Text"
                annot.update()

                # ✅ ✅ ✅ НОМЕР БЛОКА ЧЕРЕЗ SHAPE + FREETEXT ✅ ✅ ✅

                # Размер и позиция лейбла
                label_size = 20  # Размер квадрата
                label_x = rect.x0
                label_y = rect.y0 - label_size - 2  # Над блоком

                # Если выходит за границы страницы — рисуем внутри блока
                if label_y < 0:
                    label_y = rect.y0 + 2

                label_rect = pymupdf.Rect(
                    label_x, label_y, label_x + label_size, label_y + label_size
                )

                # ✅ Рисуем фон и границу через Shape
                sh = page.new_shape()
                sh.draw_rect(label_rect)
                sh.finish(
                    color=(0, 0.6, 0),  # Тёмно-зелёная граница
                    fill=(0.85, 1, 0.85),  # Светло-зелёный фон
                    width=1.5,
                )
                sh.commit()

                # ✅ Создаём FreeText БЕЗ фона (прозрачный, только текст)
                freetext = page.add_freetext_annot(
                    rect=label_rect,
                    text=str(s.blockid),
                    fontsize=11,
                    fontname="helv",
                    text_color=(0, 0.4, 0),  # Тёмно-зелёный текст
                    fill_color=None,  # ✅ Прозрачный фон (фон уже нарисован через Shape)
                    align=1,  # Центрирование: 0=left, 1=center, 2=right
                )

                # Устанавливаем прозрачность
                freetext.set_opacity(1.0)

                # Добавляем метаданные для панели комментариев
                freetext.info["title"] = f"Block {s.blockid}"
                freetext.info["subject"] = f"Block Number ({s.type})"
                freetext.info["content"] = f"Block #{s.blockid} - {s.type or 'Text'}"

                freetext.update()

        doc.save(out_pdf, garbage=4, deflate=True)

    finally:
        doc.close()


def annotate_pdf_with_segments(
    input_pdf: str,
    out_pdf: str,
    pages: List[PageBatch],
    use_comments: bool = True,
    annotation_type: str = "highlight",
    include_translation: bool = True,
) -> None:
    """
    Создаёт аннотированный PDF с комментариями и подсветкой.

    Основная функция для создания аннотированного PDF. По умолчанию использует
    комментарии (sticky notes) вместо визуального редактирования документа.

    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf: Путь для сохранения аннотированного PDF
        pages: Список батчей страниц с сегментами
        use_comments: Использовать комментарии вместо визуального редактирования (по умолчанию True)
        annotation_type: Тип подсветки ("highlight", "underline", "squiggly", "strikeout", "none")
        include_translation: Включать перевод в комментарии
    """
    # Просто вызываем функцию с markup аннотациями
    # Она создаёт и подсветку, и комментарии
    annotate_pdf_with_markup_annotations(
        input_pdf=input_pdf,
        out_pdf=out_pdf,
        pages=pages,
        annotation_type=annotation_type,
        show_popup=True,
    )
