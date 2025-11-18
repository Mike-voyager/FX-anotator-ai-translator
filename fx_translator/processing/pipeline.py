"""
Конвейеры обработки PDF документов.

Этот модуль содержит три главных конвейера обработки:
- run_pipeline() - стандартный HURIDOCS конвейер
- run_pipeline_transactional() - постраничный транзакционный конвейер
- run_pipeline_pymupdf() - конвейер с PyMuPDF экстрактором
"""

from __future__ import annotations
import os
import logging
import time
import contextlib
import requests
import tempfile
from typing import List, Dict, Tuple, Optional, Callable, Any

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf  # type: ignore

from fx_translator.core.models import PageBatch, Segment
from fx_translator.core.config import (
    DEFAULT_HURIDOCS_BASE,
    HURIDOCS_ANALYZE_PATH,
    DEFAULT_LMSTUDIO_BASE,
    LMSTUDIO_MODEL,
)
from fx_translator.api.huridocs import huridocs_analyze_pdf, huridocs_analyze_pdf_smart
from fx_translator.api.lmstudio import lmstudio_translate_simple
from fx_translator.utils.text import parse_page_set
from fx_translator.utils.geometry import sort_segments_reading_order
from fx_translator.utils.metrics import init_metrics, log_metric, Timer
from fx_translator.processing.analyzers.segments import (
    refine_huridocs_segments,
    deglue_pages_pdfaware,
)
from fx_translator.processing.analyzers.layout import (
    split_spreads,
    split_spreads_force_half,
    assert_layout_invariants,
)
from fx_translator.processing.extractors.pymupdf import extract_pages_pymupdf
from fx_translator.export.docx import export_docx
from fx_translator.export.pdf import annotate_pdf_with_segments


def build_pages(seg_json: List[Dict[str, Any]]) -> List[PageBatch]:
    """
    Преобразует JSON сегменты из HURIDOCS в PageBatch объекты.

    Args:
        seg_json: Список сегментов в JSON формате от HURIDOCS

    Returns:
        Список PageBatch с сегментами, сгруппированными по страницам
    """
    logging.debug(f"Building pages from {len(seg_json)} segments")
    pages: Dict[int, List[Segment]] = {}

    for it in seg_json:
        seg = Segment(
            pagenumber=int(it.get("pagenumber")),
            left=float(it.get("left")),
            top=float(it.get("top")),
            width=float(it.get("width")),
            height=float(it.get("height")),
            pagewidth=float(it.get("pagewidth")),
            pageheight=float(it.get("pageheight")),
            text=str(it.get("text") or "").strip(),
            type=str(it.get("type") or "Text"),
        )
        pages.setdefault(seg.pagenumber, []).append(seg)

    batches: List[PageBatch] = []
    for pno in sorted(pages.keys()):
        segs = sort_segments_reading_order(pages[pno])
        for idx, s in enumerate(segs, start=1):
            s.blockid = idx
        batches.append(PageBatch(pagenumber=pno, segments=segs))

    return batches


def run_pipeline(
    input_pdf: str,
    out_pdf_annotated: str,
    out_docx: str,
    src_lang: str = "it",
    tgt_lang: str = "ru",
    huridocs_base: str = DEFAULT_HURIDOCS_BASE,
    huridocs_analyze_path: str = HURIDOCS_ANALYZE_PATH,
    huridocs_visualize_path: Optional[str] = None,
    lms_base: str = DEFAULT_LMSTUDIO_BASE,
    lms_model: str = LMSTUDIO_MODEL,
    batch_size: int = 15,
    force_split_spreads: bool = False,
    force_split_exceptions: str = "",
    page_limit: Optional[int] = None,
    pause_ms: int = 0,
    pause_hook: Optional[Callable[[], None]] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    split_spreads_enabled: bool = True,
    fast=False,
) -> None:
    """
    Стандартный конвейер обработки PDF через HURIDOCS.

    Этапы:
    1. Анализ PDF через HURIDOCS API (все страницы сразу)
    2. Обработка и рафинирование сегментов
    3. Разделение разворотов (опционально)
    4. Deglue операции для слипшихся блоков
    5. Перевод через LM Studio
    6. Экспорт в DOCX и аннотированный PDF

    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf_annotated: Путь для сохранения аннотированного PDF
        out_docx: Путь для сохранения DOCX с переводом
        src_lang: Исходный язык (например, "en")
        tgt_lang: Целевой язык (например, "ru")
        huridocs_base: URL HURIDOCS API
        huridocs_analyze_path: Путь endpoint анализа
        huridocs_visualize_path: Путь endpoint визуализации (опционально)
        lms_base: URL LM Studio API
        lms_model: Название модели в LM Studio

        batch_size: Размер батча для обработки
        force_split_spreads: Принудительно делить развороты пополам
        force_split_exceptions: Страницы-исключения для split (формат: "1,3-5,10")
        page_limit: Ограничение количества страниц (для тестирования)
        pause_ms: Пауза между страницами в мс
        pause_hook: Callback функция для паузы
        start_page: Начальная страница (1-based)
        end_page: Конечная страница (1-based)
        split_spreads_enabled: Включить разделение разворотов
    """
    init_metrics(out_docx)

    logging.info("Шаг 1/3: Анализ макета через HURIDOCS...")
    seg_json = huridocs_analyze_pdf(
        input_pdf, huridocs_base, huridocs_analyze_path, fast=False
    )
    pages = build_pages(seg_json)

    # Мягкая волна обработки до сплита
    pages = [refine_huridocs_segments(pb) for pb in pages]
    pages = deglue_pages_pdfaware(pages, pdf_path=input_pdf)

    # Ограничение диапазона страниц
    if start_page is not None and end_page is not None:
        pages = pages[start_page - 1 : end_page]
    elif page_limit and len(pages) > page_limit:
        pages = pages[:page_limit]

    # Разделение разворотов
    if split_spreads_enabled:
        total_pages = max((pb.pagenumber for pb in pages), default=0)
        if force_split_spreads:
            ex = parse_page_set(force_split_exceptions, total_pages)
            pages = split_spreads_force_half(pages, ex)
            logging.info(
                "После сплита (force-half, исключения=%s) логических страниц: %d.",
                sorted(list(ex)) if ex else "∅",
                len(pages),
            )
        else:
            pages = split_spreads(pages, pdf_path=input_pdf, debug=True)
            logging.info("После сплита (auto) логических страниц: %d.", len(pages))

    # Мягкая волна обработки после сплита
    pages = [refine_huridocs_segments(pb, xtol=9.0, gaptol=10.0) for pb in pages]
    pages = deglue_pages_pdfaware(pages, pdf_path=input_pdf)

    # Шаг 2: Перевод
    logging.info("Шаг 2/3: Перевод страниц через LM Studio...")
    translations: Dict[Tuple[int, str, int], str] = {}

    for page_batch in pages:
        if pause_hook:
            pause_hook()

        segs_nonempty = [s for s in page_batch.segments if s.text.strip()]
        if not segs_nonempty:
            if pause_ms > 0:
                time.sleep(pause_ms / 1000.0)
            continue

        page_map = lmstudio_translate_simple(
            model=lms_model,
            pagenumber=page_batch.pagenumber,
            segments=segs_nonempty,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            base_url=lms_base,
        )

        side = getattr(page_batch, "logical_side", "")
        for s in segs_nonempty:
            translations[(page_batch.pagenumber, side, s.blockid)] = page_map.get(
                s.blockid, ""
            )

        if pause_ms > 0:
            time.sleep(pause_ms / 1000.0)

    # Шаг 3: Вывод
    logging.info("Шаг 3/3: Генерация вывода (PDF + DOCX)...")
    assert_layout_invariants(pages)
    annotate_pdf_with_segments(
        input_pdf,
        out_pdf_annotated,
        pages,
        use_comments=True,  # Использовать комментарии
        annotation_type="none",  # С подсветкой
        include_translation=True,  # Включить перевод
    )

    export_docx(pages, translations, out_docx, title=os.path.basename(input_pdf))

    logging.info(f"Готово: {out_pdf_annotated} и {out_docx}")


def analyze_pdf_transactional(
    input_pdf: str,
    huridocs_base: Optional[str] = None,
    analyze_path: str = HURIDOCS_ANALYZE_PATH,
    orchestrator: Optional[Any] = None,
    restart_every: int = 0,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    per_page_timeout: int = 1200,
    fast: bool = False,
) -> List[PageBatch]:
    """
    Постраничный анализ с умным управлением контейнером.

    Обрабатывает каждую страницу отдельно:
    - Извлекает одну страницу в временный PDF
    - Отправляет на анализ в HURIDOCS
    - Управляет перезапуском контейнера при необходимости

    Args:
        input_pdf: Путь к входному PDF файлу
        huridocs_base: URL HURIDOCS API
        analyze_path: Путь endpoint анализа
        orchestrator: Объект Orchestrator для управления контейнером
        restart_every: Перезапуск контейнера каждые N страниц (0 = отключено)
        start_page: Начальная страница (1-based)
        end_page: Конечная страница (1-based)
        per_page_timeout: Таймаут на обработку одной страницы

    Returns:
        Список PageBatch объектов
    """
    doc = pymupdf.open(input_pdf)

    try:
        total_pages = doc.page_count
        p_start = start_page or 1
        p_end = end_page or total_pages

        if not (1 <= p_start <= p_end <= total_pages):
            raise ValueError(
                f"Неверный диапазон страниц: {p_start}..{p_end} из {total_pages}"
            )

        base_url = huridocs_base or (
            f"http://localhost:{orchestrator.huridocs_port}"
            if orchestrator
            else DEFAULT_HURIDOCS_BASE
        )

        # Запускаем контейнер если нужно
        if orchestrator:
            orchestrator.start_huridocs(lambda m: None)
            base_url = orchestrator.get_base_url()

        out_batches: List[PageBatch] = []

        for idx, pno in enumerate(range(p_start, p_end + 1), 1):
            # Перезапуск контейнера каждые N страниц
            if (
                orchestrator
                and restart_every > 0
                and idx > 1
                and (idx - 1) % restart_every == 0
            ):
                with contextlib.suppress(Exception):
                    orchestrator.stop_huridocs(lambda m: None)
                    orchestrator.start_huridocs(lambda m: None)
                    base_url = orchestrator.get_base_url()

            tmp_path: Optional[str] = None

            try:
                # Извлекаем одну страницу
                page_idx = pno - 1
                page = doc[page_idx]
                pw, ph = page.rect.width, page.rect.height

                # Создаём временный PDF с одной страницей
                out_doc = pymupdf.open()
                out_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)

                import tempfile

                fd, tmp_path = tempfile.mkstemp(prefix=f"page-{pno}-", suffix=".pdf")
                os.close(fd)

                out_doc.save(tmp_path, garbage=4, deflate=True)
                out_doc.close()

                # Анализируем через HURIDOCS
                seg_json = huridocs_analyze_pdf_smart(
                    tmp_path,
                    base_url=base_url,
                    analyze_path=analyze_path,
                    timeout=per_page_timeout,
                    fast=fast,
                )

                # Корректируем номера страниц
                for it in seg_json:
                    it["pagenumber"] = pno
                    it["pagewidth"] = pw
                    it["pageheight"] = ph

                batches = build_pages(seg_json)
                if batches:
                    out_batches.append(batches[0])

            except (requests.Timeout, requests.ConnectionError) as e:
                logging.warning(
                    f"Страница {pno}: таймаут/ошибка соединения HURIDOCS. Попытка перезапуска..."
                )
                if orchestrator and orchestrator.maybe_restart_on_failure(
                    lambda m: None, err=e
                ):
                    base_url = orchestrator.get_base_url()
                    continue

            except requests.HTTPError as e:
                status_code = getattr(e.response, "status_code", None)
                logging.warning(
                    f"Страница {pno}: HTTP ошибка {status_code} от HURIDOCS. Попытка перезапуска..."
                )
                if orchestrator and orchestrator.maybe_restart_on_failure(
                    lambda m: None, status_code=status_code
                ):
                    base_url = orchestrator.get_base_url()
                    continue

            except Exception as e:
                logging.warning(f"Страница {pno}: общая ошибка анализа — {e}")
                continue

            finally:
                if tmp_path and os.path.exists(tmp_path):
                    with contextlib.suppress(Exception):
                        os.remove(tmp_path)

        # Останавливаем контейнер после обработки
        if orchestrator:
            with contextlib.suppress(Exception):
                orchestrator.stop_huridocs(lambda m: None)

        return out_batches

    finally:
        doc.close()


def run_pipeline_transactional(
    input_pdf: str,
    out_pdf_annotated: str,
    out_docx: str,
    src_lang: str = "it",
    tgt_lang: str = "ru",
    huridocs_base: Optional[str] = None,
    huridocs_analyze_path: str = HURIDOCS_ANALYZE_PATH,
    lms_base: str = DEFAULT_LMSTUDIO_BASE,
    lms_model: str = LMSTUDIO_MODEL,
    batch_size: int = 15,
    force_split_spreads: bool = False,
    force_split_exceptions: str = "",
    orchestrator: Optional[Any] = None,
    restart_every: int = 0,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    pause_ms: int = 0,
    pause_hook: Optional[Callable[[], None]] = None,
    split_spreads_enabled: bool = True,
    fast: bool = False,
) -> None:
    """
    Транзакционный постраничный конвейер с управлением контейнером.

    Отличия от стандартного конвейера:
    - Каждая страница обрабатывается отдельно (analyze_pdf_transactional)
    - Автоматический перезапуск контейнера при сбоях
    - Периодический перезапуск каждые N страниц
    - Только мягкие правки сегментов (без переклассификации)

    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf_annotated: Путь для сохранения аннотированного PDF
        out_docx: Путь для сохранения DOCX с переводом
        src_lang: Исходный язык
        tgt_lang: Целевой язык
        huridocs_base: URL HURIDOCS API
        huridocs_analyze_path: Путь endpoint анализа
        lms_base: URL LM Studio API
        LMSTUDIO_MODEL: Название модели
        batch_size: Размер батча для обработки
        force_split_spreads: Принудительное деление разворотов
        force_split_exceptions: Страницы-исключения для split
        orchestrator: Объект Orchestrator для управления контейнером
        restart_every: Перезапуск контейнера каждые N страниц
        start_page: Начальная страница
        end_page: Конечная страница
        pause_ms: Пауза между страницами
        pause_hook: Callback для паузы
        split_spreads_enabled: Включить разделение разворотов
    """
    init_metrics(out_docx)

    logging.info("Шаг 1/4: постраничный анализ через HURIDOCS...")
    pages = analyze_pdf_transactional(
        input_pdf=input_pdf,
        huridocs_base=huridocs_base,
        analyze_path=huridocs_analyze_path,
        orchestrator=orchestrator,
        restart_every=restart_every,
        start_page=start_page,
        end_page=end_page,
        per_page_timeout=1200,
        fast=fast,
    )

    # Мягкая волна до сплита
    pages = [refine_huridocs_segments(pb) for pb in pages]
    pages = deglue_pages_pdfaware(pages, pdf_path=input_pdf)

    # Сплит разворотов
    if split_spreads_enabled:
        total_pages = max((pb.pagenumber for pb in pages), default=0)
        if force_split_spreads:
            ex = parse_page_set(force_split_exceptions, total_pages)
            pages = split_spreads_force_half(pages, ex)
            logging.info(
                "После сплита (force-half, исключения=%s) логических страниц: %d.",
                sorted(list(ex)) if ex else "∅",
                len(pages),
            )
        else:
            pages = split_spreads(pages, pdf_path=input_pdf, debug=True)
            logging.info("После сплита (auto) логических страниц: %d.", len(pages))

    # Мягкая волна после сплита
    pages = [refine_huridocs_segments(pb, xtol=9.0, gaptol=10.0) for pb in pages]
    pages = deglue_pages_pdfaware(pages, pdf_path=input_pdf)

    # Перевод (фильтруем минимально значимые сегменты)
    logging.info("Шаг 3/4: перевод через LM Studio...")
    translations: Dict[Tuple[int, str, int], str] = {}

    for page_batch in pages:
        if pause_hook:
            pause_hook()

        def _for_translation(s: Segment) -> bool:
            t = (s.text or "").strip()

            if not t:
                return False

            # ✅ Переводим ВСЕ заголовки
            if s.type in ("title", "section_header", "caption", "page_header"):
                return True

            # Пропускаем только номера страниц
            if t.isdigit() and s.type == "page_footer":
                return False

            # Переводим всё остальное
            return True

        segs_for_translation = [s for s in page_batch.segments if _for_translation(s)]

        page_map = lmstudio_translate_simple(
            model=lms_model,
            pagenumber=page_batch.pagenumber,
            segments=segs_for_translation,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            base_url=lms_base,
        )

        side = getattr(page_batch, "logical_side", "")
        for s in segs_for_translation:
            logging.info(
                f"Block {s.blockid}: original text = '{s.text}' (type: {s.type})"
            )
            translations[(page_batch.pagenumber, side, s.blockid)] = page_map.get(
                s.blockid, ""
            )

        if pause_ms > 0:
            time.sleep(pause_ms / 1000.0)

    # Вывод
    logging.info("Шаг 4/4: генерация аннотированного PDF и DOCX...")
    assert_layout_invariants(pages)
    annotate_pdf_with_segments(
        input_pdf,
        out_pdf_annotated,
        pages,
        use_comments=True,  # Использовать комментарии
        annotation_type="none",  # С подсветкой
        include_translation=True,  # Включить перевод
    )
    # Отладочный вывод
    logging.info(f"Total translations: {len(translations)}")

    # Группируем по страницам
    from collections import defaultdict

    by_page = defaultdict(dict)

    for (pno, side, blockid), trans_text in translations.items():
        by_page[(pno, side)][blockid] = trans_text

    # Логируем по страницам
    for (pno, side), trans_dict in by_page.items():
        logging.info(f"Page ({pno}, {side}): {len(trans_dict)} translations")
        for blockid, trans_text in trans_dict.items():
            logging.info(f"  Block {blockid}: {trans_text[:50]}...")

    export_docx(pages, translations, out_docx, title=os.path.basename(input_pdf))


def featurize_segments_for_llm(pb: PageBatch) -> Dict[str, Any]:
    """
    Готовит компактный JSON-пейлоад для возможной группировки LLM.

    Args:
        pb: PageBatch для обработки

    Returns:
        Словарь с данными сегментов для LLM
    """
    feats = []
    for s in sort_segments_reading_order(pb.segments):
        feats.append(
            {
                "blockid": s.blockid,
                "bbox": [s.left, s.top, s.left + s.width, s.top + s.height],
                "type": s.type,
                "text": (s.text or "")[:400],  # ограничим длину
            }
        )
    return {"pagenumber": pb.pagenumber, "segments": feats}


def llm_group_segments(
    model: str, lms_base: str, page_payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Безопасная реализация: возвращает текущие типы без изменений.

    Позже можно заменить на реальный запрос в LM Studio для
    переклассификации типов сегментов через LLM.

    Args:
        model: Название модели LM Studio
        lms_base: Base URL LM Studio API
        page_payload: Данные страницы от featurize_segments_for_llm()

    Returns:
        Словарь с группами сегментов
    """
    return {
        "groups": [
            {"blockid": it["blockid"], "type": it.get("type", "paragraph")}
            for it in page_payload.get("segments", [])
        ]
    }


def apply_llm_groups(pb: PageBatch, grouping: Dict[str, Any]) -> PageBatch:
    """
    Применяет типы из группировки LLM к сегментам.

    Args:
        pb: PageBatch для обновления
        grouping: Результат от llm_group_segments()

    Returns:
        Обновлённый PageBatch
    """
    by_id = {s.blockid: s for s in pb.segments}

    for g in grouping.get("groups", []):
        bid = int(g.get("blockid", 0))
        new_type = str(g.get("type", "")).strip()
        if bid in by_id and new_type:
            by_id[bid].type = new_type

    # Возвращаем исходный порядок/нумерацию
    segs = sort_segments_reading_order(list(by_id.values()))
    for i, s in enumerate(segs, 1):
        s.blockid = i

    return PageBatch(
        pagenumber=pb.pagenumber,
        segments=segs,
        logical_side=getattr(pb, "logical_side", ""),
    )


def run_pipeline_pymupdf(
    input_pdf: str,
    out_pdf_annotated: str,
    out_docx: str,
    src_lang: str = "en",
    tgt_lang: str = "ru",
    lms_base: str = DEFAULT_LMSTUDIO_BASE,
    lms_model: str = LMSTUDIO_MODEL,
    batch_size: int = 15,
    split_spreads_enabled: bool = True,
    force_split_spreads: bool = False,
    force_split_exceptions: str = "",
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    use_llm_grouping: bool = False,
    pause_ms: int = 0,
    pause_hook: Optional[Callable[[], None]] = None,
) -> None:
    """
    Конвейер с PyMuPDF экстрактором (без HURIDOCS).

    Этапы:
    1. Извлечение текста через PyMuPDF AdvancedTextProcessor
    2. Разделение разворотов (опционально)
    3. LLM-группировка типов (опционально)
    4. Перевод через LM Studio
    5. Экспорт в DOCX и аннотированный PDF

    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf_annotated: Путь для сохранения аннотированного PDF
        out_docx: Путь для сохранения DOCX с переводом
        src_lang: Исходный язык
        tgt_lang: Целевой язык
        lms_base: URL LM Studio API
        LMSTUDIO_MODEL: Название модели
        batch_size: Размер батча для обработки
        split_spreads_enabled: Включить разделение разворотов
        force_split_spreads: Принудительное деление разворотов
        force_split_exceptions: Страницы-исключения для split
        start_page: Начальная страница (1-based)
        end_page: Конечная страница (1-based)
        use_llm_grouping: Использовать LLM для группировки сегментов
        pause_ms: Пауза между страницами
        pause_hook: Callback для паузы
    """
    init_metrics(out_docx)

    logging.info("PyMuPDF: шаг 1/4 — извлечение и сборка абзацев...")
    pages = extract_pages_pymupdf(input_pdf, start_page=start_page, end_page=end_page)
    logging.info("Извлечено %d страниц (до сплита).", len(pages))

    # Разделение разворотов
    if split_spreads_enabled:
        if force_split_spreads:
            total_pages = max((pb.pagenumber for pb in pages), default=0)
            ex = parse_page_set(force_split_exceptions, total_pages)
            pages = split_spreads_force_half(pages, ex)
            logging.info(
                "После сплита (force-half, исключения=%s) логических страниц: %d.",
                sorted(list(ex)) if ex else "∅",
                len(pages),
            )
        else:
            pages = split_spreads(pages, pdf_path=input_pdf, debug=True)
            logging.info("После сплита (auto) логических страниц: %d.", len(pages))

    # Дополнительная LLM-группировка ролей (опционально)
    if use_llm_grouping:
        logging.info("PyMuPDF: шаг 2/4 — LLM-группировка ролей и блоков...")
        grouped: List[PageBatch] = []
        for pb in pages:
            try:
                payload = featurize_segments_for_llm(pb)
                grouping = llm_group_segments(
                    model=lms_model, lms_base=lms_base, page_payload=payload
                )
                grouped.append(apply_llm_groups(pb, grouping))
            except Exception as e:
                logging.warning(
                    f"LLM grouping failed on page {pb.pagenumber}: {e} — using passthrough"
                )
                grouped.append(pb)
        pages = grouped

    # Перевод
    logging.info("PyMuPDF: шаг 3/4 — перевод через LM Studio...")
    translations: Dict[Tuple[int, str, int], str] = {}

    for pb in pages:
        if pause_hook:
            pause_hook()

        segs = [s for s in pb.segments if s.text.strip()]
        if not segs:
            if pause_ms > 0:
                time.sleep(pause_ms / 1000.0)
            continue

        page_map = lmstudio_translate_simple(
            model=lms_model,
            pagenumber=pb.pagenumber,
            segments=segs,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            base_url=lms_base,
        )

        side = getattr(pb, "logical_side", "")
        for s in segs:
            translations[(pb.pagenumber, side, s.blockid)] = page_map.get(s.blockid, "")

        if pause_ms > 0:
            time.sleep(pause_ms / 1000.0)

    # Вывод
    logging.info("PyMuPDF: шаг 4/4 — выпуск аннотированного PDF и DOCX...")
    assert_layout_invariants(pages)
    annotate_pdf_with_segments(
        input_pdf,
        out_pdf_annotated,
        pages,
        use_comments=True,  # Использовать комментарии
        annotation_type="none",  # С подсветкой
        include_translation=True,  # Включить перевод
    )
    export_docx(pages, translations, out_docx, title=os.path.basename(input_pdf))

    logging.info("Готово: %s и %s", out_pdf_annotated, out_docx)


def run_pipeline_layoutlmv3(
    input_pdf: str,
    out_pdf_annotated: str,
    out_docx: str,
    src_lang: str = "it",
    tgt_lang: str = "ru",
    lms_base: str = DEFAULT_LMSTUDIO_BASE,
    lms_model: str = LMSTUDIO_MODEL,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    split_spreads_enabled: bool = True,
    force_split_spreads: bool = False,
    force_split_exceptions: str = "",
    use_gpu: bool = True,
    dpi: int = 200,
    pause_ms: int = 0,
    pause_hook: Optional[Callable[[], None]] = None,
) -> None:
    """
    Конвейер обработки PDF через LayoutLMv3.

    Этапы:
    1. Анализ PDF через LayoutLMv3 (постраничный с GPU)
    2. Постобработка сегментов (refine + deglue)
    3. Разделение разворотов (опционально)
    4. Перевод через LM Studio
    5. Экспорт в DOCX и аннотированный PDF

    Args:
        input_pdf: Путь к входному PDF
        out_pdf_annotated: Путь для аннотированного PDF
        out_docx: Путь для DOCX
        src_lang: Исходный язык (например, "it")
        tgt_lang: Целевой язык (например, "ru")
        lms_base: URL LM Studio API
        lms_model: Название модели LM Studio
        start_page: Начальная страница (1-based)
        end_page: Конечная страница (1-based)
        split_spreads_enabled: Разделение разворотов
        force_split_spreads: Принудительное деление пополам
        force_split_exceptions: Страницы-исключения для split
        use_gpu: Использовать GPU для LayoutLMv3
        dpi: DPI для конвертации PDF → изображение
        pause_ms: Пауза между страницами (мс)
        pause_hook: Callback функция для паузы
    """
    from fx_translator.api.layoutlmv3 import LayoutLMv3Analyzer

    init_metrics(out_docx)

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info("🚀 LayoutLMv3 Pipeline")
    logging.info(f"   PDF: {input_pdf}")
    logging.info(f"   DPI: {dpi}")
    logging.info(f"   GPU: {'Включено' if use_gpu else 'Отключено'}")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Шаг 1: Анализ через LayoutLMv3
    logging.info("Шаг 1/4: Анализ макета через LayoutLMv3...")

    analyzer = LayoutLMv3Analyzer(
        model_name="microsoft/layoutlmv3-large", use_gpu=use_gpu
    )

    seg_json = analyzer.analyze_pdf(
        pdf_path=input_pdf,
        dpi=dpi,
        start_page=start_page,
        end_page=end_page,
    )

    logging.info(f"Получено {len(seg_json)} сегментов от LayoutLMv3")

    # Преобразуем в PageBatch
    pages = build_pages(seg_json)
    logging.info(f"Создано {len(pages)} страниц")

    # Шаг 2: Постобработка (мягкая волна)
    logging.info("Шаг 2/4: Постобработка сегментов...")

    # Первая волна - мягкое уточнение
    pages = [refine_huridocs_segments(pb, xtol=3.0, gaptol=4.0) for pb in pages]

    # Deglue для разделения слипшихся блоков
    pages = deglue_pages_pdfaware(pages, pdf_path=input_pdf)

    # Разделение разворотов
    if split_spreads_enabled:
        total_pages = max((pb.pagenumber for pb in pages), default=0)

        if force_split_spreads:
            ex = parse_page_set(force_split_exceptions, total_pages)
            pages = split_spreads_force_half(pages, ex)
            logging.info(
                f"После сплита (force-half, исключения={sorted(list(ex)) if ex else '∅'}) "
                f"логических страниц: {len(pages)}"
            )
        else:
            pages = split_spreads(pages, pdf_path=input_pdf, debug=True)
            logging.info(f"После сплита (auto) логических страниц: {len(pages)}")

    # Вторая волна постобработки после сплита
    pages = [refine_huridocs_segments(pb, xtol=3.0, gaptol=4.0) for pb in pages]
    pages = deglue_pages_pdfaware(pages, pdf_path=input_pdf)

    # Шаг 3: Перевод
    logging.info("Шаг 3/4: Перевод через LM Studio...")
    translations: Dict[Tuple[int, str, int], str] = {}

    for page_batch in pages:
        if pause_hook:
            pause_hook()

        segs_nonempty = [s for s in page_batch.segments if s.text.strip()]
        if not segs_nonempty:
            if pause_ms > 0:
                time.sleep(pause_ms / 1000.0)
            continue

        page_map = lmstudio_translate_simple(
            model=lms_model,
            pagenumber=page_batch.pagenumber,
            segments=segs_nonempty,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            base_url=lms_base,
        )

        side = getattr(page_batch, "logical_side", "")
        for s in segs_nonempty:
            translations[(page_batch.pagenumber, side, s.blockid)] = page_map.get(
                s.blockid, ""
            )

        if pause_ms > 0:
            time.sleep(pause_ms / 1000.0)

    # Шаг 4: Экспорт
    logging.info("Шаг 4/4: Генерация вывода (PDF + DOCX)...")
    assert_layout_invariants(pages)

    annotate_pdf_with_segments(
        input_pdf,
        out_pdf_annotated,
        pages,
        use_comments=True,
        annotation_type="none",
        include_translation=True,
    )

    export_docx(pages, translations, out_docx, title=os.path.basename(input_pdf))

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"✅ Готово!")
    logging.info(f"   PDF: {out_pdf_annotated}")
    logging.info(f"   DOCX: {out_docx}")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
