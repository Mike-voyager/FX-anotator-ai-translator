"""
PyMuPDF-based text extraction with advanced processing.

Этот модуль предоставляет альтернативу HURIDOCS для извлечения текста из PDF
с использованием PyMuPDF и продвинутой обработки текстовых блоков.
"""

from __future__ import annotations
import re
import logging
from typing import List, Dict, Tuple, Optional

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf  # type: ignore

from fx_translator.core.models import TextLine, TextBlock, Segment, PageBatch
from fx_translator.processing.analyzers.segments import sort_segments_reading_order


class AdvancedTextProcessor:
    """
    Продвинутый процессор текста из PDF с использованием PyMuPDF.

    Выполняет:
    - Извлечение строк с метаданными (шрифт, размер, форматирование)
    - Группировка строк в логические блоки (абзацы, заголовки и т.д.)
    - Классификация типов блоков
    - Очистка и объединение текста
    """

    def __init__(self):
        # Пороги для объединения строк в блоки
        self.line_merge_threshold = 3.0  # pts
        self.paragraph_break_threshold = 8.0  # pts
        self.font_size_variation_threshold = 0.15  # 15% разница в размере шрифта

        # Паттерны для обработки текста
        self.hyphen_patterns = [
            r"(\\w+)-\\s*\\n\\s*(\\w+)",  # обычный перенос
            r"(\\w+)—\\s*\\n\\s*(\\w+)",  # длинное тире
        ]

        # Паттерны для удаления шумового текста
        self.noise_patterns = [
            r"^\\d+$",  # только номера страниц
            r"^[IVXLCDMivxlcdm]+$",  # римские цифры
            r"^[a-zA-Z]\\)$",  # одиночные буквы с скобкой
        ]

    def extract_advanced_blocks(self, page) -> List[TextBlock]:
        """
        Извлекает продвинутые текстовые блоки из страницы PDF.

        Args:
            page: PyMuPDF page объект

        Returns:
            Список TextBlock объектов с метаданными
        """
        text_dict = page.get_text("dict")
        raw_lines: List[TextLine] = []

        # Извлекаем все строки с метаданными
        for block in text_dict["blocks"]:
            if "lines" not in block:
                continue

            for line in block["lines"]:
                if not line["spans"]:
                    continue

                # Собираем данные из всех spans в строке
                line_text = ""
                font_sizes = []
                font_names = []
                flags_list = []

                for span in line["spans"]:
                    line_text += span["text"]
                    font_sizes.append(span["size"])
                    font_names.append(span["font"])
                    flags_list.append(span["flags"])

                if not line_text.strip():
                    continue

                # Вычисляем средние значения
                avg_font_size = sum(font_sizes) / len(font_sizes)
                most_common_font = max(set(font_names), key=font_names.count)
                avg_flags = int(sum(flags_list) / len(flags_list))

                raw_lines.append(
                    TextLine(
                        text=line_text,
                        bbox=tuple(line["bbox"]),
                        font_size=avg_font_size,
                        font_name=most_common_font,
                        flags=avg_flags,
                        is_bold=bool(avg_flags & 2**4),
                        is_italic=bool(avg_flags & 2**1),
                    )
                )

        if not raw_lines:
            return []

        # Сортируем строки по позиции (сверху-вниз, слева-направо)
        raw_lines.sort(key=lambda l: (l.bbox[1], l.bbox[0]))

        # Определяем базовый размер шрифта документа
        body_font_size = self._get_body_font_size(raw_lines)

        # Группируем строки в блоки
        blocks = self._group_lines_into_blocks(raw_lines, body_font_size)

        # Объединяем и очищаем текст в блоках
        for block in blocks:
            block.merged_text = self._merge_and_clean_text(block.lines)
            block.block_type = self._classify_block_type(block, body_font_size)

        # Фильтруем значимые блоки
        return [b for b in blocks if self._is_meaningful_block(b)]

    def _get_body_font_size(self, lines: List[TextLine]) -> float:
        """Определяет медианный размер шрифта основного текста."""
        font_sizes = [line.font_size for line in lines if line.font_size > 0]
        if not font_sizes:
            return 12.0

        font_sizes.sort()
        return font_sizes[len(font_sizes) // 2]

    def _group_lines_into_blocks(
        self, lines: List[TextLine], body_font_size: float
    ) -> List[TextBlock]:
        """
        Группирует строки в логические блоки на основе:
        - Вертикальных зазоров
        - Размера шрифта
        - Выравнивания
        """
        blocks: List[TextBlock] = []
        current_block_lines: List[TextLine] = []

        for i, line in enumerate(lines):
            if not current_block_lines:
                current_block_lines.append(line)
                continue

            prev_line = current_block_lines[-1]
            vertical_gap = line.bbox[1] - prev_line.bbox[3]

            should_merge = self._should_merge_lines(
                prev_line, line, vertical_gap, body_font_size
            )

            if should_merge:
                current_block_lines.append(line)
            else:
                if current_block_lines:
                    blocks.append(self._create_block_from_lines(current_block_lines))
                current_block_lines = [line]

        # Добавляем последний блок
        if current_block_lines:
            blocks.append(self._create_block_from_lines(current_block_lines))

        return blocks

    def _should_merge_lines(
        self,
        prev_line: TextLine,
        current_line: TextLine,
        vertical_gap: float,
        body_font_size: float,
    ) -> bool:
        """Определяет, должны ли две строки быть объединены в один блок."""

        # Большой зазор = новый блок
        if vertical_gap > self.paragraph_break_threshold:
            return False

        # Маленький зазор = продолжение блока
        if vertical_gap <= self.line_merge_threshold:
            return True

        # Средний зазор: смотрим на другие признаки

        # Разница в размере шрифта
        font_size_ratio = (
            abs(current_line.font_size - prev_line.font_size) / body_font_size
        )
        if font_size_ratio > self.font_size_variation_threshold:
            return False

        # Разное выравнивание слева
        left_alignment_diff = abs(current_line.bbox[0] - prev_line.bbox[0])
        if left_alignment_diff > 12.0:
            return False

        return True

    def _create_block_from_lines(self, lines: List[TextLine]) -> TextBlock:
        """Создаёт TextBlock из списка строк."""
        if not lines:
            raise ValueError("Cannot create block from empty lines")

        # Вычисляем общий bbox
        min_x = min(line.bbox[0] for line in lines)
        min_y = min(line.bbox[1] for line in lines)
        max_x = max(line.bbox[2] for line in lines)
        max_y = max(line.bbox[3] for line in lines)

        return TextBlock(
            lines=lines,
            bbox=(min_x, min_y, max_x, max_y),
            block_type="unknown",
            merged_text="",
        )

    def _merge_and_clean_text(self, lines: List[TextLine]) -> str:
        """
        Объединяет текст из строк, учитывая:
        - Переносы слов (дефисы)
        - Мягкие переносы внутри предложений
        - Специальные символы
        """
        merged_parts: List[str] = []

        for i, line in enumerate(lines):
            text = line.text.strip()

            if i < len(lines) - 1:
                # Проверяем перенос слова
                if text.endswith("-") or text.endswith("—"):
                    merged_parts.append(text[:-1])
                    continue

                # Проверяем продолжение предложения на следующей строке
                next_line_text = lines[i + 1].text.strip()
                if (
                    text
                    and next_line_text
                    and not text.endswith((".", "!", "?", ":", ";", ","))
                    and next_line_text[0].islower()
                ):
                    merged_parts.append(text + " ")
                    continue

            merged_parts.append(text)

        result = " ".join(merged_parts)

        # Очистка специальных символов
        result = result.replace("\\u00ad", "")  # мягкий перенос
        result = result.replace("\\u00a0", " ")  # неразрывный пробел

        # Нормализация пробелов
        result = re.sub(r"\\s+", " ", result).strip()

        return result

    def _classify_block_type(self, block: TextBlock, body_font_size: float) -> str:
        """
        Классифицирует тип блока на основе:
        - Размера шрифта
        - Форматирования (жирный/курсив)
        - Содержимого текста
        - Длины текста
        """
        avg_font_size = sum(line.font_size for line in block.lines) / len(block.lines)
        text = block.merged_text.strip()

        # Заголовки и подзаголовки
        if avg_font_size > body_font_size * 1.3 and len(text) < 150:
            if text.isupper() or (text[0].isupper() and len(text.split()) <= 8):
                return (
                    "title"
                    if avg_font_size > body_font_size * 1.6
                    else "section_header"
                )

        # Вопросы как подзаголовки
        if text.endswith("?") and len(text) < 100 and avg_font_size >= body_font_size:
            return "section_header"

        # Подписи и сноски (мелкий шрифт)
        if avg_font_size < body_font_size * 0.95:
            if (block.bbox[3] - block.bbox[1]) < body_font_size * 2.5:
                return "caption"
            return "footnote"

        # Элементы списков
        if (
            re.match(r"^[•·\\-*]\\s", text)
            or re.match(r"^\\d+[.):]?\\s", text)
            or re.match(r"^[a-zA-Z][.)]\\s", text)
        ):
            return "list_item"

        # Короткие фрагменты как подписи
        if len(text) < 30 and len(text.split()) <= 6:
            return "caption"

        # Проверка на колонтитулы по позиции
        pageheight = getattr(block, "pageheight", 800)
        if block.bbox[1] < pageheight * 0.1:  # верхние 10%
            return "page_header"
        elif block.bbox[3] > pageheight * 0.9:  # нижние 10%
            return "page_footer"

        return "paragraph"

    def _is_meaningful_block(self, block: TextBlock) -> bool:
        """Проверяет, является ли блок значимым (не шум)."""
        text = block.merged_text.strip()

        # Пустой или слишком короткий текст
        if not text or len(text) < 3:
            return False

        # Проверка на шумовые паттерны
        for pattern in self.noise_patterns:
            if re.match(pattern, text):
                return False

        return True

    def process_page(self, page) -> List[Dict]:
        """
        Обрабатывает страницу PDF и возвращает список сегментов.

        Args:
            page: PyMuPDF page объект

        Returns:
            Список словарей с данными сегментов
        """
        blocks = self.extract_advanced_blocks(page)
        result = []

        for i, block in enumerate(blocks, 1):
            bbox = block.bbox
            result.append(
                {
                    "pagenumber": page.number + 1,
                    "left": bbox[0],
                    "top": bbox[1],
                    "width": bbox[2] - bbox[0],
                    "height": bbox[3] - bbox[1],
                    "pagewidth": page.rect.width,
                    "pageheight": page.rect.height,
                    "text": block.merged_text,
                    "type": block.block_type,
                    "block_id": i,
                    "confidence": block.confidence,
                }
            )

        return result


def extract_pages_pymupdf_advanced(
    pdf_path: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> List[PageBatch]:
    """
    Улучшенная версия извлечения страниц с продвинутой обработкой текста.

    Args:
        pdf_path: Путь к PDF файлу
        start_page: Начальная страница (1-indexed), None = первая
        end_page: Конечная страница (1-indexed), None = последняя

    Returns:
        Список PageBatch объектов
    """
    processor = AdvancedTextProcessor()
    doc = pymupdf.open(pdf_path)

    try:
        s = (start_page or 1) - 1
        e = (end_page or doc.page_count) - 1
        out = []

        for i in range(s, e + 1):
            page = doc[i]
            segments_data = processor.process_page(page)

            segs: List[Segment] = []
            for seg_data in segments_data:
                segs.append(
                    Segment(
                        pagenumber=seg_data["pagenumber"],
                        left=seg_data["left"],
                        top=seg_data["top"],
                        width=seg_data["width"],
                        height=seg_data["height"],
                        pagewidth=seg_data["pagewidth"],
                        pageheight=seg_data["pageheight"],
                        text=seg_data["text"],
                        type=seg_data["type"],
                        block_id=seg_data["block_id"],
                        line_height=0.0,
                    )
                )

            out.append(PageBatch(pagenumber=i + 1, segments=segs))

        return out

    finally:
        doc.close()


def extract_pages_pymupdf(
    pdf_path: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> List[PageBatch]:
    """
    Обёртка для обратной совместимости.

    Args:
        pdf_path: Путь к PDF файлу
        start_page: Начальная страница (1-indexed)
        end_page: Конечная страница (1-indexed)

    Returns:
        Список PageBatch объектов
    """
    return extract_pages_pymupdf_advanced(pdf_path, start_page, end_page)


def run_pipeline_pymupdf(
    input_pdf: str,
    out_pdf_annotated: str,
    out_docx: str,
    src_lang: str,
    tgt_lang: str,
    lms_base: str,
    lms_model: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    use_llm_grouping: bool = False,
    split_spreads_enabled: bool = True,
    force_split_spreads: bool = False,
    force_split_exceptions: str = "",
    pause_ms: int = 0,
    pause_hook: Optional[callable] = None,
) -> None:
    """
    Полный pipeline обработки PDF с использованием PyMuPDF.

    Выполняет:
    1. Извлечение текста из PDF с использованием PyMuPDF
    2. Продвинутую обработку и группировку блоков
    3. Опциональную LLM-группировку (если use_llm_grouping=True)
    4. Разделение разворотов (если split_spreads_enabled=True)
    5. Перевод текста через LM Studio
    6. Экспорт в аннотированный PDF и DOCX

    Args:
        input_pdf: Путь к входному PDF файлу
        out_pdf_annotated: Путь для сохранения аннотированного PDF
        out_docx: Путь для сохранения DOCX с переводом
        src_lang: Исходный язык (например, "en")
        tgt_lang: Целевой язык (например, "ru")
        lms_base: Базовый URL LM Studio API
        lms_model: Имя модели в LM Studio
        start_page: Начальная страница для обработки
        end_page: Конечная страница для обработки
        use_llm_grouping: Использовать LLM для группировки блоков
        split_spreads_enabled: Автоматически разделять развороты
        force_split_spreads: Принудительно делить все страницы пополам
        force_split_exceptions: Строка с номерами страниц-исключений (например, "1,3,5-7")
        pause_ms: Задержка между страницами в миллисекундах
        pause_hook: Функция для паузы/возобновления обработки
    """
    from fx_translator.processing.analyzers.layout import (
        split_spreads,
        split_spreads_force_half,
    )
    from fx_translator.api.lmstudio import lmstudio_translate_batch
    from fx_translator.export.pdf import annotate_pdf_with_segments
    from fx_translator.export.docx import export_docx
    from fx_translator.utils.text import parse_page_set
    import time

    logging.info(f"[PyMuPDF Pipeline] Начало обработки: {input_pdf}")
    logging.info(f"  Страницы: {start_page or 'начало'}-{end_page or 'конец'}")
    logging.info(f"  LLM группировка: {use_llm_grouping}")
    logging.info(f"  Разделение разворотов: {split_spreads_enabled}")

    # 1. Извлечение текста из PDF
    logging.info("[1/5] Извлечение текста из PDF...")
    pages = extract_pages_pymupdf_advanced(input_pdf, start_page, end_page)
    logging.info(f"  Извлечено {len(pages)} страниц")

    # 2. Разделение разворотов (если включено)
    if split_spreads_enabled:
        logging.info("[2/5] Разделение разворотов...")
        pages = split_spreads(pages, input_pdf)
        logging.info(f"  После разделения: {len(pages)} логических страниц")

    if force_split_spreads:
        logging.info("[2/5] Принудительное разделение пополам...")
        exceptions = parse_page_set(force_split_exceptions)
        pages = split_spreads_force_half(pages, exceptions)
        logging.info(f"  После принудительного разделения: {len(pages)} страниц")

    # 3. LLM-группировка (если включено)
    if use_llm_grouping:
        logging.warning(
            "[3/5] LLM-группировка пока не реализована для PyMuPDF pipeline"
        )
    else:
        logging.info("[3/5] LLM-группировка отключена")

    # 4. Перевод через LM Studio
    logging.info(f"[4/5] Перевод текста ({src_lang} → {tgt_lang})...")

    for i, page_batch in enumerate(pages, 1):
        if pause_hook:
            pause_hook()

        if pause_ms > 0:
            time.sleep(pause_ms / 1000.0)

        logging.info(
            f"  Обработка страницы {page_batch.pagenumber} ({i}/{len(pages)})..."
        )

        # Переводим сегменты
        for seg in page_batch.segments:
            if seg.text and seg.text.strip():
                try:
                    translated = lmstudio_translate_batch(
                        texts=[seg.text],
                        src_lang=src_lang,
                        tgt_lang=tgt_lang,
                        lms_base=lms_base,
                        lms_model=lms_model,
                    )
                    seg.translated_text = translated[0] if translated else seg.text
                except Exception as e:
                    logging.error(f"    Ошибка перевода сегмента {seg.block_id}: {e}")
                    seg.translated_text = seg.text

    logging.info("  Перевод завершён")

    # 5. Экспорт результатов
    logging.info("[5/5] Экспорт результатов...")

    # Аннотированный PDF
    try:
        annotate_pdf_with_segments(
            input_pdf,
            out_pdf_annotated,
            pages,
            use_comments=True,  # Использовать комментарии
            annotation_type="none",  # С подсветкой
            include_translation=True,  # Включить перевод
        )
        logging.info(f"  ✓ Аннотированный PDF: {out_pdf_annotated}")
    except Exception as e:
        logging.error(f"  ✗ Ошибка экспорта PDF: {e}")

    # DOCX с переводом
    try:
        export_docx(pages, out_docx, src_lang, tgt_lang)
        logging.info(f"  ✓ DOCX с переводом: {out_docx}")
    except Exception as e:
        logging.error(f"  ✗ Ошибка экспорта DOCX: {e}")

    logging.info("[PyMuPDF Pipeline] Обработка завершена успешно!")
