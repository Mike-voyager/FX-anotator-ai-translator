"""
Утилиты для обработки текста.

Этот модуль содержит функции для очистки, нормализации и обработки текстового контента.
"""

from __future__ import annotations
import re
from typing import Optional, List

from fx_translator.core.models import Segment


def sanitize_model_content(s: str) -> str:
    """
    Очищает ответ модели от лишних префиксов и форматирования.

    Args:
        s: Текст ответа модели

    Returns:
        Очищенный текст
    """
    s = s.strip()

    # Удаляем типичные префиксы
    bad_prefixes = [
        "**",
        "Response:",
        "Here is",
        "Here are",
        "```",
        "JSON:",
    ]

    for bp in bad_prefixes:
        if s.lower().startswith(bp.lower()):
            s = s[len(bp) :].lstrip()

    # Удаляем начальный перевод строки
    if s.startswith("\\n"):
        nl = s.find("\\n")
        if nl != -1:
            s = s[nl + 1 :]

    # Удаляем закрывающие тройные кавычки
    if s.endswith("```"):
        s = s[:-3].strip()

    return s


def clean_text_inplace(text: str) -> str:
    """
    Очищает текст от мягких переносов и лишних пробелов.

    Args:
        text: Исходный текст

    Returns:
        Очищенный текст
    """
    if not text:
        return text

    # Удаляем мягкий перенос (U+00AD) и неразрывный пробел (U+00A0)
    text = text.replace("\\u00ad", "").replace("\\u00a0", " ")

    # Нормализуем пробелы (заменяем множественные на один)
    return " ".join(text.split())


def denoise_soft_linebreaks(
    seg: Segment,
    prevlenthresh: Optional[int] = None,
    punctbreakre: re.Pattern = re.compile(r"[.!?]$"),
    listmarkerre: re.Pattern = re.compile(r"^[•–—0-9.\-]\s"),
) -> Segment:
    """
    Удаляет мягкие переносы строк внутри сегмента, объединяя строки,
    которые, вероятно, были разорваны только для форматирования.

    Args:
        seg: Сегмент для обработки
        prevlenthresh: Опциональный порог длины строки
        punctbreakre: Regex для определения конца предложения
        listmarkerre: Regex для определения маркеров списка

    Returns:
        Сегмент с объединёнными строками
    """
    text = seg.text or ""
    lines = [ln.rstrip() for ln in text.splitlines()]

    if not lines:
        return seg

    # Вычисляем медианную длину строк
    lens = [len(ln.strip()) for ln in lines if ln.strip()]
    if lens:
        med = sorted(lens)[len(lens) // 2]
    else:
        med = 60

    base = max(30, int(0.9 * med))
    thresh = (
        prevlenthresh if isinstance(prevlenthresh, int) and prevlenthresh > 0 else base
    )

    out: List[str] = []
    for i, ln in enumerate(lines):
        if i > 0 and ln and out and out[-1]:
            prev = out[-1]

            # Проверяем, нужно ли объединить с предыдущей строкой
            shouldmerge = (
                len(prev) < thresh
                and not punctbreakre.search(prev)
                and not listmarkerre.match(ln)
                and not prev.strip().isdigit()
                and not ln.strip().isdigit()
                and len(ln) > 3
            )

            if shouldmerge:
                out[-1] = prev.rstrip() + " " + ln.lstrip()
                continue

        out.append(ln)

    seg.text = "\\n".join(out)
    return seg


def looks_captionish(text: str) -> bool:
    """
    Определяет, похож ли текст на подпись к изображению/таблице.

    Args:
        text: Текст для анализа

    Returns:
        True если текст похож на подпись
    """
    text = text.strip().lower()

    # Типичные префиксы подписей
    caption_prefixes = ["fig", "figure", "table", "схема", "рисунок", "таблица"]

    for prefix in caption_prefixes:
        if text.startswith(prefix):
            return True

    # Короткие тексты в конце страницы часто являются подписями
    if len(text) < 100 and any(kw in text for kw in [":", "—"]):
        return True

    return False


def looks_headerish(text: str, fontsize: float = 0.0) -> bool:
    """
    Определяет, похож ли текст на заголовок.

    Args:
        text: Текст для анализа
        fontsize: Размер шрифта (если известен)

    Returns:
        True если текст похож на заголовок
    """
    text = text.strip()

    # Короткий текст с большим шрифтом
    if fontsize > 14.0 and len(text) < 150:
        return True

    # Заглавные буквы
    if text.isupper() and len(text) < 100:
        return True

    # Текст без точки в конце (но не слишком длинный)
    if not text.endswith(".") and len(text) < 80 and len(text.split()) <= 10:
        return True

    return False


def parse_page_set(spec: str, total_pages: int) -> set[int]:
    """
    Парсит спецификацию страниц вида "1,3-5,10".

    Args:
        spec: Спецификация страниц (например, "1,3-5,10")
        total_pages: Общее количество страниц в документе

    Returns:
        Множество номеров страниц
    """
    out: set[int] = set()

    if not spec:
        return out

    for part in spec.replace(" ", "").split(","):
        if not part:
            continue

        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo
                for p in range(max(1, lo), min(total_pages, hi) + 1):
                    out.add(p)
        elif part.isdigit():
            p = int(part)
            if 1 <= p <= total_pages:
                out.add(p)

    return out
