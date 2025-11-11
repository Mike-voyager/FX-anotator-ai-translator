"""
Утилиты для сбора метрик и профилирования.

Этот модуль содержит инструменты для измерения времени выполнения и логирования метрик.
"""

from __future__ import annotations
import time
import csv
from typing import Optional

# Глобальный путь к файлу метрик
METRICS_PATH: Optional[str] = None


class Timer:
    """
    Простой таймер для измерения времени выполнения.

    Example:
        timer = Timer()
        # ... код ...
        duration_ms = timer.ms()
    """

    def __init__(self) -> None:
        """Инициализирует таймер с текущим временем."""
        self.t0 = time.perf_counter()

    def ms(self) -> int:
        """
        Возвращает прошедшее время в миллисекундах.

        Returns:
            Количество миллисекунд с момента создания таймера
        """
        return int((time.perf_counter() - self.t0) * 1000)


def init_metrics(out_docx: str) -> None:
    """
    Инициализирует файл метрик на основе выходного DOCX файла.

    Создаёт CSV файл с именем {base}.metrics.csv и записывает заголовок.

    Args:
        out_docx: Путь к выходному DOCX файлу
    """
    global METRICS_PATH

    import os

    base, _ = os.path.splitext(out_docx)
    METRICS_PATH = f"{base}.metrics.csv"

    with open(METRICS_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["ts", "stage", "page", "sub", "duration_ms", "count", "size_bytes", "info"]
        )


def log_metric(
    stage: str,
    page: Optional[int] = None,
    sub: str = "",
    duration_ms: Optional[int] = None,
    count: Optional[int] = None,
    size_bytes: Optional[int] = None,
    info: str = "",
) -> None:
    """
    Записывает метрику в CSV файл.

    Args:
        stage: Название этапа (например, "huridocs", "translation")
        page: Номер страницы (опционально)
        sub: Подкатегория (опционально)
        duration_ms: Длительность в миллисекундах (опционально)
        count: Количество элементов (опционально)
        size_bytes: Размер в байтах (опционально)
        info: Дополнительная информация (опционально)
    """
    if not METRICS_PATH:
        return

    with open(METRICS_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                time.strftime("%Y-%m-%d %H:%M:%S"),
                stage,
                page if page is not None else "",
                sub,
                duration_ms if duration_ms is not None else "",
                count if count is not None else "",
                size_bytes if size_bytes is not None else "",
                info,
            ]
        )
