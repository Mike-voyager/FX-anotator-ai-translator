"""LayoutLMv3 анализатор для PDF документов."""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Tuple, Optional

import torch
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
from PIL import Image
import pymupdf


# Маппинг id2label для LayoutLMv3
# Источник: https://huggingface.co/microsoft/layoutlmv3-large
LABEL_MAP = {
    0: "O",  # Outside
    1: "Text",  # B-Text
    2: "Text",  # I-Text
    3: "Title",  # B-Title
    4: "Title",  # I-Title
    5: "List",  # B-List
    6: "List",  # I-List
    7: "Table",  # B-Table
    8: "Table",  # I-Table
    9: "Figure",  # B-Figure
    10: "Figure",  # I-Figure
}


class LayoutLMv3Analyzer:
    """
    Анализатор layout PDF документов через LayoutLMv3.

    Attributes:
        device: Устройство (cuda/cpu)
        processor: Процессор для предобработки изображений
        model: Модель LayoutLMv3
    """

    def __init__(
        self,
        model_name: str = "microsoft/layoutlmv3-large",
        use_gpu: bool = True,
    ):
        """
        Инициализация анализатора.

        Args:
            model_name: Название модели на HuggingFace
            use_gpu: Использовать GPU если доступно
        """
        self.device = torch.device(
            "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
        )

        logging.info(f"Загрузка LayoutLMv3: {model_name}")

        # Загружаем processor (без OCR, используем PyMuPDF)
        self.processor = LayoutLMv3Processor.from_pretrained(
            model_name, apply_ocr=False
        )

        # Загружаем модель
        self.model = LayoutLMv3ForTokenClassification.from_pretrained(model_name).to(
            self.device
        )
        self.model.eval()

        # Получаем маппинг меток из конфига модели
        self.id2label = (
            self.model.config.id2label
            if hasattr(self.model.config, "id2label")
            else LABEL_MAP
        )

        logging.info(f"✅ LayoutLMv3 загружен на {self.device}")

    def analyze_pdf(
        self,
        pdf_path: str,
        dpi: int = 200,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Анализирует PDF и возвращает сегменты в формате HURIDOCS.

        Args:
            pdf_path: Путь к PDF файлу
            dpi: Разрешение для конвертации
            start_page: Начальная страница (1-based, опционально)
            end_page: Конечная страница (1-based, опционально)

        Returns:
            Список сегментов в формате:
            {
                "pagenumber": int,
                "left": float,
                "top": float,
                "width": float,
                "height": float,
                "pagewidth": float,
                "pageheight": float,
                "text": str,
                "type": str
            }
        """
        # Конвертируем PDF в изображения
        doc = pymupdf.open(pdf_path)

        try:
            total_pages = doc.page_count
            p_start = (start_page or 1) - 1  # 0-based
            p_end = (end_page or total_pages) - 1

            all_segments = []

            for page_idx in range(p_start, p_end + 1):
                page_num = page_idx + 1  # 1-based для вывода
                logging.info(f"Анализ страницы {page_num}/{total_pages}...")

                # Получаем изображение страницы
                page = doc[page_idx]
                image, page_width, page_height = self._page_to_image(page, dpi)

                # Извлекаем текст и bbox через PyMuPDF
                words_data = self._extract_words(page)

                # Анализируем через LayoutLMv3
                page_segments = self._analyze_page(
                    image, words_data, page_num, page_width, page_height
                )

                all_segments.extend(page_segments)

            return all_segments

        finally:
            doc.close()

    def _page_to_image(
        self, page: pymupdf.Page, dpi: int
    ) -> Tuple[Image.Image, float, float]:
        """
        Конвертирует страницу PDF в PIL изображение.

        Args:
            page: Страница PyMuPDF
            dpi: Разрешение

        Returns:
            (изображение, ширина_страницы, высота_страницы)
        """
        mat = pymupdf.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Реальные размеры страницы (в пунктах)
        rect = page.rect
        return img, rect.width, rect.height

    def _extract_words(self, page: pymupdf.Page) -> List[Dict[str, Any]]:
        """
        Извлекает слова и их bbox через PyMuPDF.

        Args:
            page: Страница PyMuPDF

        Returns:
            Список словарей с полями: text, bbox, ...
        """
        words = page.get_text(
            "words"
        )  # (x0, y0, x1, y1, "word", block_no, line_no, word_no)

        words_data = []
        for w in words:
            x0, y0, x1, y1, text, *_ = w
            words_data.append(
                {
                    "text": text,
                    "bbox": [x0, y0, x1, y1],
                }
            )

        return words_data

    def _analyze_page(
        self,
        image: Image.Image,
        words_data: List[Dict[str, Any]],
        page_num: int,
        page_width: float,
        page_height: float,
    ) -> List[Dict[str, Any]]:
        """
        Анализирует страницу через LayoutLMv3.

        Args:
            image: PIL изображение страницы
            words_data: Список слов с bbox от PyMuPDF
            page_num: Номер страницы (1-based)
            page_width: Ширина страницы в пунктах
            page_height: Высота страницы в пунктах

        Returns:
            Список сегментов
        """
        if not words_data:
            return []

        # Подготавливаем данные для LayoutLMv3
        words = [w["text"] for w in words_data]
        boxes = [
            self._normalize_bbox(w["bbox"], page_width, page_height) for w in words_data
        ]

        # Кодируем через processor
        encoding = self.processor(
            image,
            words,
            boxes=boxes,
            return_tensors="pt",
            padding="max_length",
            truncation=True,
            max_length=512,
        )

        # Перемещаем на устройство
        encoding = {k: v.to(self.device) for k, v in encoding.items()}

        # Inference
        with torch.no_grad():
            outputs = self.model(**encoding)

        # Получаем предсказания (BIO-теги)
        predictions = outputs.logits.argmax(-1).squeeze().cpu().tolist()

        # Группируем слова в сегменты по BIO-разметке
        segments = self._group_words_to_segments(
            words_data, predictions, page_num, page_width, page_height
        )

        return segments

    def _normalize_bbox(
        self, bbox: List[float], page_width: float, page_height: float
    ) -> List[int]:
        """
        Нормализует bbox в диапазон 0-1000 (формат LayoutLMv3).

        Args:
            bbox: [x0, y0, x1, y1] в пунктах
            page_width: Ширина страницы
            page_height: Высота страницы

        Returns:
            [x0, y0, x1, y1] в диапазоне 0-1000
        """
        x0, y0, x1, y1 = bbox

        norm_x0 = int((x0 / page_width) * 1000)
        norm_y0 = int((y0 / page_height) * 1000)
        norm_x1 = int((x1 / page_width) * 1000)
        norm_y1 = int((y1 / page_height) * 1000)

        return [norm_x0, norm_y0, norm_x1, norm_y1]

    def _group_words_to_segments(
        self,
        words_data: List[Dict[str, Any]],
        predictions: List[int],
        page_num: int,
        page_width: float,
        page_height: float,
    ) -> List[Dict[str, Any]]:
        """
        Группирует слова в сегменты по BIO-разметке.

        Args:
            words_data: Список слов с bbox
            predictions: Предсказанные метки (id) для каждого слова
            page_num: Номер страницы
            page_width: Ширина страницы
            page_height: Высота страницы

        Returns:
            Список сегментов в формате HURIDOCS
        """
        segments = []
        current_segment = None

        for idx, (word_info, label_id) in enumerate(zip(words_data, predictions)):
            # Пропускаем padding токены
            if idx >= len(words_data):
                break

            # Получаем тип сегмента
            label = self.id2label.get(label_id, "Text")

            # Определяем, начало ли это нового сегмента
            # B- (begin) метки нечётные: 1, 3, 5, 7, 9
            # I- (inside) метки чётные: 2, 4, 6, 8, 10
            # 0 - O (outside)
            is_begin = (label_id % 2 == 1) or (label_id == 0)

            if is_begin or current_segment is None:
                # Сохраняем предыдущий сегмент
                if current_segment:
                    segments.append(
                        self._finalize_segment(
                            current_segment, page_num, page_width, page_height
                        )
                    )

                # Создаём новый сегмент
                current_segment = {
                    "type": label if label != "O" else "Text",
                    "words": [word_info["text"]],
                    "boxes": [word_info["bbox"]],
                }
            else:
                # Продолжаем текущий сегмент
                if current_segment:
                    current_segment["words"].append(word_info["text"])
                    current_segment["boxes"].append(word_info["bbox"])

        # Добавляем последний сегмент
        if current_segment:
            segments.append(
                self._finalize_segment(
                    current_segment, page_num, page_width, page_height
                )
            )

        return segments

    def _finalize_segment(
        self,
        segment_data: Dict[str, Any],
        page_num: int,
        page_width: float,
        page_height: float,
    ) -> Dict[str, Any]:
        """
        Преобразует сырой сегмент в формат HURIDOCS.

        Args:
            segment_data: Данные сегмента (words, boxes, type)
            page_num: Номер страницы
            page_width: Ширина страницы
            page_height: Высота страницы

        Returns:
            Сегмент в формате HURIDOCS
        """
        # Объединяем слова в текст
        text = " ".join(segment_data["words"])

        # Вычисляем общий bbox
        boxes = segment_data["boxes"]
        x0 = min(box[0] for box in boxes)
        y0 = min(box[1] for box in boxes)
        x1 = max(box[2] for box in boxes)
        y1 = max(box[3] for box in boxes)

        left = x0
        top = y0
        width = x1 - x0
        height = y1 - y0

        return {
            "pagenumber": page_num,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "pagewidth": page_width,
            "pageheight": page_height,
            "text": text,
            "type": segment_data["type"],
        }


# Тестовый запуск
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    analyzer = LayoutLMv3Analyzer(model_name="microsoft/layoutlmv3-large", use_gpu=True)

    print("✅ LayoutLMv3Analyzer готов к работе!")

    # Тестовый анализ (раскомментируйте для теста)
    # segments = analyzer.analyze_pdf("test.pdf", dpi=200)
    # print(f"Найдено {len(segments)} сегментов")
    # for seg in segments[:5]:  # Первые 5
    #     print(f"  [{seg['type']}] {seg['text'][:50]}...")
