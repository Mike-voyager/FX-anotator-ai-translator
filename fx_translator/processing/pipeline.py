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
from typing import List, Dict, Tuple, Optional, Callable, Any

from fx_translator.core.models import PageBatch, Segment
from fx_translator.core.config import (
    DEFAULT_HURIDOCS_BASE,
    HURIDOCS_ANALYZE_PATH,
    DEFAULT_LMSTUDIO_BASE,
    LMSTUDIO_MODEL,
)
from fx_translator.api.huridocs import huridocs_analyze_pdf
from fx_translator.api.lmstudio import lmstudio_translate_simple
from fx_translator.utils.text import parse_page_set
from fx_translator.utils.geometry import sort_segments_reading_order
from fx_translator.utils.metrics import init_metrics
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
    pages: Dict[int, List[Segment]] = {}
    
    for it in seg_json:
        seg = Segment(
            pagenumber=int(it.get("page_number")),
            left=float(it.get("left")),
            top=float(it.get("top")),
            width=float(it.get("width")),
            height=float(it.get("height")),
            pagewidth=float(it.get("page_width")),
            pageheight=float(it.get("page_height")),
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
    inputpdf: str,
    outpdfannotated: str,
    outdocx: str,
    srclang: str = "en",
    tgtlang: str = "ru",
    huridocsbase: str = DEFAULT_HURIDOCS_BASE,
    huridocsanalyzepath: str = HURIDOCS_ANALYZE_PATH,
    huridocsvisualizepath: Optional[str] = None,
    lmsbase: str = DEFAULT_LMSTUDIO_BASE,
    lmsmodel: str = LMSTUDIO_MODEL,
    batchsize: int = 15,
    forcesplitspreads: bool = False,
    forcesplitexceptions: str = "",
    pagelimit: Optional[int] = None,
    pausems: int = 0,
    pausehook: Optional[Callable[[], None]] = None,
    startpage: Optional[int] = None,
    endpage: Optional[int] = None,
    splitspreads_enabled: bool = True,
) -> None:
    """
    Стандартный конвейер обработки PDF через HURIDOCS.
    
    Этапы:
    1. Анализ PDF через HURIDOCS API
    2. Обработка и рафинирование сегментов
    3. Разделение разворотов (опционально)
    4. Deglue операции для слипшихся блоков
    5. Перевод через LM Studio
    6. Экспорт в DOCX и аннотированный PDF
    
    Args:
        inputpdf: Путь к входному PDF файлу
        outpdfannotated: Путь для сохранения аннотированного PDF
        outdocx: Путь для сохранения DOCX с переводом
        srclang: Исходный язык (например, "en")
        tgtlang: Целевой язык (например, "ru")
        huridocsbase: URL HURIDOCS API
        huridocsanalyzepath: Путь endpoint анализа
        huridocsvisualizepath: Путь endpoint визуализации (опционально)
        lmsbase: URL LM Studio API
        lmsmodel: Название модели в LM Studio
        batchsize: Размер батча для обработки
        forcesplitspreads: Принудительно делить развороты пополам
        forcesplitexceptions: Страницы-исключения для split (формат: "1,3-5,10")
        pagelimit: Ограничение количества страниц (для тестирования)
        pausems: Пауза между страницами в мс
        pausehook: Callback функция для паузы
        startpage: Начальная страница (1-based)
        endpage: Конечная страница (1-based)
        splitspreads_enabled: Включить разделение разворотов
    """
    from fx_translator.processing.analyzers.segments import refine_huridocs_segments, deglue_pages_pdfaware
    from fx_translator.processing.analyzers.layout import split_spreads, split_spreads_force_half
    
    init_metrics(outdocx)
    
    logging.info("Шаг 1/3: Анализ макета через HURIDOCS...")
    segjson = huridocs_analyze_pdf(inputpdf, huridocsbase, huridocsanalyzepath)
    pages = build_pages(segjson)
    
    # Мягкая волна обработки до сплита
    pages = [refine_huridocs_segments(pb) for pb in pages]
    pages = deglue_pages_pdfaware(pages, pdfpath=inputpdf)
    
    # Ограничение диапазона страниц
    if startpage is not None and endpage is not None:
        pages = pages[startpage - 1:endpage]
    elif pagelimit and len(pages) > pagelimit:
        pages = pages[:pagelimit]
    
    # Разделение разворотов
    if splitspreads_enabled:
        totalpages = max((pb.pagenumber for pb in pages), default=0)
        if forcesplitspreads:
            ex = parse_page_set(forcesplitexceptions, totalpages)
            pages = split_spreads_force_half(pages, ex)
            logging.info(
                f"После сплита (force-half, исключения={sorted(list(ex)) if ex else '∅'}) "
                f"логических страниц: {len(pages)}."
            )
        else:
            pages = split_spreads(pages, pdfpath=inputpdf, debug=True)
            logging.info(f"После сплита (auto) логических страниц: {len(pages)}.")
    
    # Мягкая волна обработки после сплита
    pages = [refine_huridocs_segments(pb, xtol=9.0, gaptol=10.0) for pb in pages]
    pages = deglue_pages_pdfaware(pages, pdfpath=inputpdf)
    
    # Шаг 2: Перевод
    logging.info("Шаг 2/3: Перевод страниц через LM Studio...")
    translations: Dict[Tuple[int, str, int], str] = {}
    
    for pagebatch in pages:
        if pausehook:
            pausehook()
        
        segsnonempty = [s for s in pagebatch.segments if s.text.strip()]
        if not segsnonempty:
            if pausems > 0:
                time.sleep(pausems / 1000.0)
            continue
        
        pagemap = lmstudio_translate_simple(
            model=lmsmodel,
            page_number=pagebatch.pagenumber,
            segments=segsnonempty,
            src_lang=srclang,
            tgt_lang=tgtlang,
            base_url=lmsbase,
        )
        
        side = getattr(pagebatch, "logicalside", "")
        for s in segsnonempty:
            translations[(pagebatch.pagenumber, side, s.blockid)] = pagemap.get(
                s.blockid, ""
            )
        
        if pausems > 0:
            time.sleep(pausems / 1000.0)
    
    # Шаг 3: Вывод
    logging.info("Шаг 3/3: Генерация вывода (PDF + DOCX)...")
    annotate_pdf_with_segments(inputpdf, outpdfannotated, pages)
    export_docx(pages, translations, outdocx, title=os.path.basename(inputpdf))
    
    logging.info(f"Готово: {outpdfannotated} и {outdocx}")


def run_pipeline_transactional(
    inputpdf: str,
    outpdfannotated: str,
    outdocx: str,
    srclang: str = "en",
    tgtlang: str = "ru",
    huridocsbase: Optional[str] = None,
    huridocsanalyzepath: str = HURIDOCS_ANALYZE_PATH,
    lmsbase: str = DEFAULT_LMSTUDIO_BASE,
    lmsmodel: str = LMSTUDIO_MODEL,
    batchsize: int = 15,
    forcesplitspreads: bool = False,
    forcesplitexceptions: str = "",
    orchestrator: Optional[Any] = None,
    restartevery: int = 0,
    startpage: Optional[int] = None,
    endpage: Optional[int] = None,
    pausems: int = 0,
    pausehook: Optional[Callable[[], None]] = None,
    splitspreads_enabled: bool = True,
) -> None:
    """
    Транзакционный постраничный конвейер с управлением контейнером.
    
    TODO: Требует:
    - analyze_pdf_transactional() из processing/extractors/
    - Orchestrator из orchestration/
    - Полные analyzers функции
    
    Для минимальной версии используем стандартный конвейер.
    """
    logging.warning("run_pipeline_transactional: используется fallback на run_pipeline")
    run_pipeline(
        inputpdf=inputpdf,
        outpdfannotated=outpdfannotated,
        outdocx=outdocx,
        srclang=srclang,
        tgtlang=tgtlang,
        lmsbase=lmsbase,
        lmsmodel=lmsmodel,
        startpage=startpage,
        endpage=endpage,
        pausems=pausems,
        pausehook=pausehook,
        splitspreads_enabled=splitspreads_enabled,
    )


def run_pipeline_pymupdf(
    inputpdf: str,
    outpdfannotated: str,
    outdocx: str,
    srclang: str = "en",
    tgtlang: str = "ru",
    lmsbase: str = DEFAULT_LMSTUDIO_BASE,
    lmsmodel: str = LMSTUDIO_MODEL,
    batchsize: int = 15,
    splitspreads_enabled: bool = True,
    forcesplitspreads: bool = False,
    forcesplitexceptions: str = "",
    startpage: Optional[int] = None,
    endpage: Optional[int] = None,
    use_llm_grouping: bool = False,
    pausems: int = 0,
    pausehook: Optional[Callable[[], None]] = None,
) -> None:
    """
    Конвейер с PyMuPDF экстрактором (без HURIDOCS).
    
    TODO: Требует:
    - extract_pages_pymupdf() из processing/extractors/pymupdf.py
    - AdvancedTextProcessor class
    - featurize_segments_for_llm(), llm_group_segments(), apply_llm_groups()
    
    Для минимальной версии используем стандартный конвейер.
    """
    logging.warning("run_pipeline_pymupdf: используется fallback на run_pipeline")
    run_pipeline(
        inputpdf=inputpdf,
        outpdfannotated=outpdfannotated,
        outdocx=outdocx,
        srclang=srclang,
        tgtlang=tgtlang,
        lmsbase=lmsbase,
        lmsmodel=lmsmodel,
        startpage=startpage,
        endpage=endpage,
        pausems=pausems,
        pausehook=pausehook,
        splitspreads_enabled=splitspreads_enabled,
    )
'''

with open(os.path.join(processing_dir, "pipeline.py"), "w", encoding="utf-8") as f:
    f.write(pipeline_full)

# Обновляем __init__.py
init_content = '''"""
Модуль processing: обработка PDF документов.
"""

from fx_translator.processing.pipeline import (
    run_pipeline,
    run_pipeline_transactional,
    run_pipeline_pymupdf,
    build_pages,
)

__all__ = [
    "run_pipeline",
    "run_pipeline_transactional",
    "run_pipeline_pymupdf",
    "build_pages",
]