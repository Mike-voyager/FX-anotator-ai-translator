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


def annotate_pdf_with_segments(
    input_pdf: str,
    out_pdf: str,
    pages: List[PageBatch],
    use_comments: bool = True,
    annotation_type: str = "highlight",
    include_translation: bool = True,
    show_highlights: bool = True,
) -> None:
    """
    Создаёт аннотированный PDF с комментариями и опциональной подсветкой.

    Основная функция для создания аннотированного PDF. Создаёт:
    - FreeText аннотации с номерами блоков (один объект = один комментарий)
    - Highlight подсветку текста (опционально, если show_highlights=True)
    - Всплывающие комментарии с деталями

    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf: Путь для сохранения аннотированного PDF
        pages: Список батчей страниц с сегментами
        use_comments: Использовать комментарии (deprecated, всегда True)
        annotation_type: Тип подсветки ("highlight", "underline", "squiggly", "strikeout", "none")
        include_translation: Включать перевод в комментарии
        show_highlights: Показывать подсветку текста (по умолчанию True)
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

                # ✅ ОПЦИОНАЛЬНАЯ ПОДСВЕТКА ТЕКСТА
                if show_highlights and annotation_type != "none":
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

                    # Комментарий для подсветки
                    comment_lines = [
                        f"Block #{s.blockid}",
                        f"Type: {s.type or 'text'}",
                        f"Page: {pb.pagenumber}{side}",
                    ]

                    if s.text:
                        comment_lines.append(f"\nOriginal:\n{s.text[:150]}")

                    if hasattr(s, "translated_text") and s.translated_text:
                        comment_lines.append(
                            f"\nTranslation:\n{s.translated_text[:150]}"
                        )

                    annot.info["content"] = "\n".join(comment_lines)
                    annot.info["title"] = f"Segment {s.blockid}"
                    annot.info["subject"] = s.type or "Text"
                    annot.update()

                # ✅ ЛЕЙБЛ С НОМЕРОМ БЛОКА (FreeText по центру блока)

                label_size = 24

                # ✅ ЦЕНТРИРУЕМ лейбл относительно блока текста
                center_x = s.left + s.width / 2
                center_y = s.top + s.height / 2

                label_x = center_x - label_size / 2
                label_y = center_y - label_size / 2

                label_rect = pymupdf.Rect(
                    label_x, label_y, label_x + label_size, label_y + label_size
                )

                # ✅ FreeText аннотация (один объект = один комментарий)
                freetext = page.add_freetext_annot(
                    rect=label_rect,
                    text=str(s.blockid),
                    fontsize=12,
                    fontname="helv",
                    text_color=(0, 0.4, 0),  # Тёмно-зелёный текст
                    fill_color=(0.85, 1, 0.85),  # Светло-зелёный фон
                    align=1,  # Центрирование
                )

                # Настройка границы (стандартный цвет)
                freetext.set_border(width=1.5, dashes=None)
                freetext.set_opacity(1.0)

                # Метаданные
                freetext.info["title"] = f"Block {s.blockid}"
                freetext.info["subject"] = f"Block Number ({s.type})"

                # Детальный комментарий в popup
                detail_lines = [
                    f"Block #{s.blockid}",
                    f"Type: {s.type or 'Text'}",
                    f"Page: {pb.pagenumber}{side}",
                ]

                if s.text:
                    detail_lines.append(f"\nOriginal:\n{s.text[:200]}")

                if (
                    include_translation
                    and hasattr(s, "translated_text")
                    and s.translated_text
                ):
                    detail_lines.append(f"\nTranslation:\n{s.translated_text[:200]}")

                freetext.info["content"] = "\n".join(detail_lines)
                freetext.update()

        doc.save(out_pdf, garbage=4, deflate=True)

    finally:
        doc.close()
