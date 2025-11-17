"""
Анализ и обработка сегментов текста.

Этот модуль содержит функции для рафинирования, слияния и разделения сегментов.
"""

from __future__ import annotations
import re
import logging
from typing import List, Optional

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf  # type: ignore

from fx_translator.core.models import PageBatch, Segment
from fx_translator.utils.geometry import sort_segments_reading_order, x_overlap
from fx_translator.utils.text import clean_text_inplace


# ============================================================================
# Регулярные выражения
# ============================================================================

_BULLET_RE = re.compile(r"^(?:[•·\\-–—]\\s+|\\d+[.)]\\s+)", re.UNICODE)
_END_PUNCT_RE = re.compile(r"[:!?…]\\s*$", re.UNICODE)
_DROP_CAP_HEAD_RE = re.compile(r"^[A-ZÀ-ÖØ-Ý]\\b", re.UNICODE)


# ============================================================================
# Вспомогательные функции для проверки типов сегментов
# ============================================================================


def _looks_captionish(s: Segment) -> bool:
    """Проверяет, похож ли сегмент на подпись."""
    t = (s.text or "").strip()

    if "caption" in (s.type or "").lower():
        return True

    return (
        len(t) <= 40
        and len(t.split()) <= 6
        and (s.height < 2.8 * (s.lineheight or 12.0) or s.width < 0.35 * s.pagewidth)
    )


def _looks_headerish(s: Segment) -> bool:
    """Проверяет, похож ли сегмент на заголовок."""
    t = (s.type or "").lower()

    if ("title" in t) or ("section" in t) or ("header" in t):
        return True

    txt = (s.text or "").strip()
    return txt.endswith("?") and len(txt) < 100


def _hard_break(a: Segment, b: Segment) -> bool:
    """
    Проверяет, нужен ли жёсткий разрыв между сегментами.

    Args:
        a: Первый сегмент
        b: Второй сегмент

    Returns:
        True если между сегментами должен быть разрыв
    """
    at = (a.text or "").strip()
    bt = (b.text or "").strip()

    if not at or not bt:
        return True

    # Различие типов — разрыв только для критических ролей
    a_t = (a.type or "").lower()
    b_t = (b.type or "").lower()

    critical = {
        "title",
        "section_header",
        "caption",
        "footnote",
        "page_header",
        "page_footer",
    }

    if a_t != b_t and (a_t in critical or b_t in critical):
        return True

    # Конец предложения
    if at.endswith((".", "!", "?", "…", ":", ";")):
        return True

    return False


# ============================================================================
# Слияние сегментов
# ============================================================================


def _merge_ok(
    a: Segment,
    b: Segment,
    page_w: float,
    xtol_left: float,
    xtol_right: float,
    gaptol: float,
) -> bool:
    """
    Проверяет, можно ли объединить два сегмента.

    Args:
        a: Первый сегмент
        b: Второй сегмент
        page_w: Ширина страницы
        xtol_left: Допустимое отклонение по левой границе
        xtol_right: Допустимое отклонение по правой границе
        gaptol: Допустимый вертикальный зазор

    Returns:
        True если сегменты можно объединить
    """
    if _looks_captionish(a) or _looks_captionish(b):
        return False

    if _looks_headerish(a) or _looks_headerish(b):
        return False

    if _hard_break(a, b):
        return False

    # Монотонность по вертикали
    if b.top < a.top - 0.5:
        return False

    # Левая/правая кромки
    a_right = a.left + a.width
    b_right = b.left + b.width

    left_close = abs(a.left - b.left) <= max(xtol_left, 0.01 * page_w)
    right_close = abs(a_right - b_right) <= max(xtol_right, 0.02 * page_w)

    min_w = max(1.0, min(a.width, b.width))
    overlap_ok = x_overlap(a, b) >= 0.85 * min_w
    right_shrunk = b_right <= a_right - 0.02 * page_w

    if not left_close:
        return False

    if not (right_close or (overlap_ok and right_shrunk)):
        return False

    # Вертикальный зазор
    vgap = max(0.0, b.top - (a.top + a.height))
    if vgap > max(gaptol, 0.012 * a.pageheight):
        return False

    # Защита от случайной склейки межколоночных соседей
    center_dx = abs((a.left + 0.5 * a.width) - (b.left + 0.5 * b.width))
    if center_dx > page_w * 0.35:
        return False

    return True


def _merge_segments(a: Segment, b: Segment) -> Segment:
    """
    Объединяет два сегмента в один.

    Args:
        a: Первый сегмент
        b: Второй сегмент

    Returns:
        Объединённый сегмент
    """
    x0 = min(a.left, b.left)
    y0 = min(a.top, b.top)
    x1 = max(a.left + a.width, b.left + b.width)
    y1 = max(a.top + a.height, b.top + b.height)

    text = (a.text.rstrip() + "\\n" + b.text.lstrip()).strip()

    return Segment(
        pagenumber=a.pagenumber,
        left=x0,
        top=y0,
        width=x1 - x0,
        height=y1 - y0,
        pagewidth=a.pagewidth,
        pageheight=a.pageheight,
        text=text,
        type=a.type,
        blockid=a.blockid,
        lineheight=a.lineheight,
    )


# ============================================================================
# Разделение по whitespace
# ============================================================================


def _split_by_whitespace_proportional(seg: Segment) -> List[Segment]:
    """
    Разделяет сегмент по двойным переносам строк.

    Args:
        seg: Сегмент для разделения

    Returns:
        Список сегментов (или исходный сегмент если разделение невозможно)
    """
    txt = (seg.text or "").strip()
    parts = [p.strip() for p in re.split(r"\\n\\s*\\n", txt) if p.strip()]

    if len(parts) < 2:
        return [seg]

    # Защита от микрофрагментов
    def ok_piece(s: str) -> bool:
        ws = s.split()
        return len(s) >= 15 and len(ws) >= 3

    if not all(ok_piece(p) for p in parts):
        return [seg]

    # Распределяем высоту пропорционально числу строк
    part_lines = [max(1, len(p.splitlines()) or 1) for p in parts]
    total_lines = max(1, sum(part_lines))

    out: List[Segment] = []
    y = seg.top

    for lines_cnt, chunk in zip(part_lines, parts):
        frac = max(1, lines_cnt) / total_lines
        h = max(1.0, seg.height * frac)

        out.append(
            Segment(
                pagenumber=seg.pagenumber,
                left=seg.left,
                top=y,
                width=seg.width,
                height=h,
                pagewidth=seg.pagewidth,
                pageheight=seg.pageheight,
                text=chunk,
                type=seg.type,
                blockid=0,
                lineheight=seg.lineheight,
            )
        )
        y += h

    return out or [seg]


# ============================================================================
# Denoise soft linebreaks
# ============================================================================


def _denoise_soft_linebreaks(
    seg: Segment,
    prev_len_thresh: Optional[int] = None,
    punct_break_re=re.compile(r"[.!?…:;]$"),
    list_marker_re=re.compile(r"^(?:[•·\\-–—]|[0-9]+[.)])"),
) -> Segment:
    """
    Удаляет мягкие переносы строк внутри сегмента.

    Args:
        seg: Сегмент для обработки
        prev_len_thresh: Пороговая длина строки
        punct_break_re: Regex для конца предложения
        list_marker_re: Regex для маркеров списка

    Returns:
        Обработанный сегмент
    """
    text = seg.text or ""
    lines = [ln.rstrip() for ln in text.splitlines()]

    if not lines:
        return seg

    lens = [len(ln.strip()) for ln in lines if ln.strip()]
    med = sorted(lens)[len(lens) // 2] if lens else 60

    base = max(30, int(0.9 * med))
    thresh = (
        prev_len_thresh
        if isinstance(prev_len_thresh, int) and prev_len_thresh > 0
        else base
    )

    out: List[str] = []
    for i, ln in enumerate(lines):
        if i > 0 and ln and out and out[-1]:
            prev = out[-1]
            should_merge = (
                len(prev) < thresh
                and not punct_break_re.search(prev)
                and not list_marker_re.match(ln)
                and not prev.strip().isdigit()
                and not ln.strip().isdigit()
                and len(ln) > 3
            )

            if should_merge:
                out[-1] = prev.rstrip() + " " + ln.lstrip()
                continue

        out.append(ln)

    seg.text = "\\n".join(out)
    return seg


# ============================================================================
# Refine HURIDOCS segments
# ============================================================================


def refine_huridocs_segments(
    page_batch: PageBatch, xtol: float = 4.0, gaptol: float = 6.0, ytol: float = 4.0
) -> PageBatch:
    """
    Рафинирует сегменты HURIDOCS: очистка, слияние, разделение.

    Args:
        page_batch: Батч страницы с сегментами
        xtol: Допуск по горизонтали для слияния
        gaptol: Допуск по вертикальному зазору
        ytol: Допуск по вертикали

    Returns:
        Обработанный PageBatch
    """
    segs = sort_segments_reading_order(page_batch.segments)

    if not segs:
        return page_batch

    page_w = segs[0].pagewidth

    # 1. Очистка текста
    cleaned: List[Segment] = []
    for s in segs:
        s.text = clean_text_inplace(s.text)
        s = _denoise_soft_linebreaks(s)
        cleaned.append(s)

    # 2. Слияние близких сегментов
    merged: List[Segment] = []
    merge_cnt = 0

    for s in cleaned:
        if merged and _merge_ok(merged[-1], s, page_w, xtol, max(8.0, xtol), gaptol):
            merged[-1] = _merge_segments(merged[-1], s)
            merge_cnt += 1
        else:
            merged.append(s)

    # 3. Разделение по whitespace
    refined: List[Segment] = []
    split_cnt = 0

    for s in merged:
        parts = _split_by_whitespace_proportional(s)
        split_cnt += max(0, len(parts) - 1)
        refined.extend(parts)

    # 4. Финальная сортировка и фильтрация
    refined = sort_segments_reading_order(
        [p for p in refined if (p.text or "").strip()]
    )

    # 5. Перенумерация blockid
    for i, s in enumerate(refined, 1):
        s.blockid = i

    if merge_cnt > 5 or split_cnt > 5:
        logging.warning(
            f"[refine] p{page_batch.pagenumber}: merges={merge_cnt}, splits={split_cnt}"
        )

    return PageBatch(
        pagenumber=page_batch.pagenumber,
        segments=refined,
        logicalside=getattr(page_batch, "logicalside", ""),
    )


# ============================================================================
# PDF-aware deglue функции
# ============================================================================


def _line_metrics_from_clip(page, rect: "pymupdf.Rect"):
    """
    Извлекает метрики строк внутри прямоугольника.

    Args:
        page: PyMuPDF страница
        rect: Прямоугольник для извлечения

    Returns:
        Список кортежей (y0, y1, x0, x1, text, avg_size, is_bold)
    """
    data = page.get_text("dict", clip=rect)
    lines = []

    for blk in data.get("blocks", []):
        for ln in blk.get("lines", []):
            spans = ln.get("spans") or []
            if not spans:
                continue

            y0, x0, x1 = ln["bbox"][1], ln["bbox"][0], ln["bbox"][2]
            y1 = ln["bbox"][3]
            txt = "".join(sp.get("text", "") for sp in spans)

            sizes = [
                float(sp.get("size", 0)) for sp in spans if float(sp.get("size", 0)) > 0
            ]
            flags = [int(sp.get("flags", 0)) for sp in spans]

            avg_size = sum(sizes) / len(sizes) if sizes else 0.0
            is_bold = any((f & (1 << 4)) != 0 for f in flags)

            lines.append((y0, y1, x0, x1, txt, avg_size, is_bold))

    lines.sort(key=lambda t: (t[0], t[2]))
    return lines


def _looks_like_dropcap(page, seg: Segment) -> bool:
    """
    Проверяет, является ли сегмент буквицей (drop cap).

    Args:
        page: PyMuPDF страница
        seg: Сегмент для проверки

    Returns:
        True если сегмент похож на буквицу
    """
    rect = pymupdf.Rect(seg.left, seg.top, seg.left + seg.width, seg.top + seg.height)
    lines = _line_metrics_from_clip(page, rect)

    if len(lines) < 2:
        return False

    (y0a, y1a, x0a, x1a, ta, sa, ba) = lines[0]
    (y0b, y1b, x0b, x1b, tb, sb, bb) = lines[1]

    line_h_a = max(1.0, y1a - y0a)
    line_h_b = max(1.0, y1b - y0b)

    tall_enough = line_h_a >= line_h_b * 1.5
    big_font = sa > 0 and sb > 0 and sa >= sb * 1.6
    starts_with_single = bool(_DROP_CAP_HEAD_RE.match((ta or "").strip()))

    return (tall_enough or big_font) and starts_with_single


def _local_median_gap(gaps: List[float], idx: int, k: int = 5) -> float:
    """
    Вычисляет локальную медиану зазоров в окне.

    Args:
        gaps: Список зазоров между строками
        idx: Индекс текущего зазора
        k: Размер окна (±k элементов)

    Returns:
        Медианное значение в окне
    """
    L = max(0, idx - k)
    R = min(len(gaps) - 1, idx + k)
    window = gaps[L : R + 1] if L <= R else []

    if not window:
        return 0.0

    s = sorted(window)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def _should_break_local(
    prev,
    curr,
    gaps,
    idx,
    indent_tol: float = 10.0,
    size_drop: float = 0.12,
    gap_factor: float = 1.8,
):
    """
    Проверяет, нужен ли разрыв между строками на основе локальных метрик.

    Args:
        prev: Предыдущая строка (кортеж метрик)
        curr: Текущая строка (кортеж метрик)
        gaps: Список всех зазоров
        idx: Индекс текущего зазора
        indent_tol: Допуск для отступа
        size_drop: Допуск для изменения размера шрифта
        gap_factor: Множитель для большого зазора

    Returns:
        True если нужен разрыв
    """
    (py0, py1, px0, px1, pt, ps, pb) = prev
    (cy0, cy1, cx0, cx1, ct, cs, cb) = curr

    gap = max(0.0, cy0 - py1)
    loc_med = _local_median_gap(gaps, idx, k=5)

    # Сильные признаки разрыва
    big_gap = loc_med > 0 and gap > max(loc_med * gap_factor, 2.5)
    punct_break = _END_PUNCT_RE.search(pt or "") and gap >= max(loc_med * 1.2, 2.0)
    size_jump = ps > 0 and cs > 0 and (abs(cs - ps) / max(ps, cs) > size_drop)
    bold_flip = pb != cb and (pb or cb)
    indent_jump = abs(cx0 - px0) > indent_tol

    # Если предыдущая строка закончилась переносом - точно НЕ резать
    if (pt or "").rstrip().endswith(("-", "–", "—")):
        return False

    # Резать только при большом зазоре И хотя бы одном структурном сигнале
    return bool(big_gap and (punct_break or size_jump or bold_flip or indent_jump))


def _deglue_segment_with_pdf(page, seg: Segment) -> List[Segment]:
    """
    Разрезает слипшийся сегмент по реальным строкам PyMuPDF.

    Args:
        page: PyMuPDF страница
        seg: Сегмент для разделения

    Returns:
        Список разделённых сегментов
    """
    try:
        rect = pymupdf.Rect(
            seg.left, seg.top, seg.left + seg.width, seg.top + seg.height
        )
        lines = _line_metrics_from_clip(page, rect)
    except Exception:
        return [seg]

    if not lines or len(lines) < 2:
        return [seg]

    # Вычисляем зазоры между строками
    gaps = []
    for i in range(1, len(lines)):
        py0, py1, *_ = lines[i - 1]
        cy0, cy1, *_ = lines[i]
        gaps.append(max(0.0, cy0 - py1))

    # Разделяем на части
    parts: List[List[tuple]] = []
    cur: List[tuple] = [lines[0]]

    for i in range(1, len(lines)):
        prev = lines[i - 1]
        curr = lines[i]

        if _should_break_local(prev, curr, gaps, i - 1):
            parts.append(cur)
            cur = [curr]
        else:
            cur.append(curr)

    if cur:
        parts.append(cur)

    if len(parts) <= 1:
        return [seg]

    # Создаём новые сегменты из частей
    out: List[Segment] = []
    for block_lines in parts:
        y0 = min(l[0] for l in block_lines)
        y1 = max(l[1] for l in block_lines)
        x0 = min(l[2] for l in block_lines)
        x1 = max(l[3] for l in block_lines)
        text = "\\n".join((l[4] or "").rstrip() for l in block_lines).strip()

        if not text:
            continue

        out.append(
            Segment(
                pagenumber=seg.pagenumber,
                left=float(x0),
                top=float(y0),
                width=float(x1 - x0),
                height=float(y1 - y0),
                pagewidth=seg.pagewidth,
                pageheight=seg.pageheight,
                text=text,
                type=seg.type,
                blockid=0,
                lineheight=seg.lineheight,
            )
        )

    return out or [seg]


# ============================================================================
# Deglue pages
# ============================================================================


def deglue_pages_pdfaware(pages: List[PageBatch], pdf_path: str) -> List[PageBatch]:
    """
    Нарезает слипшиеся сегменты на основе реальных строк PyMuPDF.

    Args:
        pages: Список батчей страниц
        pdf_path: Путь к PDF файлу

    Returns:
        Обработанный список батчей
    """
    doc = pymupdf.open(pdf_path)
    out: List[PageBatch] = []

    try:
        for pb in pages:
            pno = pb.pagenumber - 1
            if pno < 0 or pno >= doc.page_count:
                out.append(pb)
                continue

            page = doc[pno]
            new_segs: List[Segment] = []

            for s in sort_segments_reading_order(pb.segments):
                # Пропускаем буквицы
                try:
                    if _looks_like_dropcap(page, s):
                        new_segs.append(s)
                        continue
                except Exception:
                    pass

                text_len = len((s.text or ""))
                many_chars = text_len > 120
                tall = s.height > max(24.0, 2.2 * (s.lineheight or 10.0))
                very_wide = (s.width > (0.8 * s.pagewidth)) and (text_len > 80)

                # Deglue только большие/высокие блоки
                if (many_chars and tall) or very_wide:
                    parts = _deglue_segment_with_pdf(page, s)
                    new_segs.extend(parts)
                else:
                    new_segs.append(s)

            # Финальная сортировка и перенумерация
            new_segs = sort_segments_reading_order(
                [x for x in new_segs if (x.text or "").strip()]
            )

            for i, seg in enumerate(new_segs, 1):
                seg.blockid = i

            out.append(
                PageBatch(
                    pagenumber=pb.pagenumber,
                    segments=new_segs,
                    logicalside=getattr(pb, "logicalside", ""),
                )
            )
    finally:
        doc.close()

    return out


"""

with open(os.path.join(analyzers_dir, "segments.py"), "w", encoding="utf-8") as f:
    f.write(segments_code)

# Создаём __init__.py для analyzers
analyzers_init = """ """
Модуль analyzers: анализ layout и сегментов.
"""

from fx_translator.processing.analyzers.segments import (
    refine_huridocs_segments,
    deglue_pages_pdfaware,
)

__all__ = [
    "refine_huridocs_segments",
    "deglue_pages_pdfaware",
]
