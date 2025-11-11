"""
Клиент для HURIDOCS PDF Segmenter API.

Этот модуль содержит функции для работы с HURIDOCS API для анализа PDF.
"""

from __future__ import annotations
import os
import io
import logging
from typing import List, Dict, Any, Optional

from fx_translator.core.config import (
    DEFAULT_HURIDOCS_BASE,
    HURIDOCS_ANALYZE_PATH,
    HURIDOCS_VISUALIZE_PATH,
    TIMEOUT,
)
from fx_translator.api.base import HTTP
from fx_translator.utils.metrics import Timer, log_metric


def huridocs_analyze_pdf_smart(
    pdf_path: str,
    base_url: str,
    analyze_path: str,
    timeout: int = TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Умный анализ PDF через HURIDOCS с автоматическим поиском рабочего endpoint.

    Пробует различные варианты endpoint пути, пока не найдёт работающий.

    Args:
        pdf_path: Путь к PDF файлу
        base_url: Базовый URL HURIDOCS API
        analyze_path: Предпочитаемый путь анализа
        timeout: Таймаут запроса в секундах

    Returns:
        Список сегментов в JSON формате

    Raises:
        RuntimeError: Если все endpoints недоступны
    """
    candidates: List[str] = []

    # Добавляем предпочитаемый путь
    if analyze_path:
        candidates.append(analyze_path)

    # Добавляем стандартные варианты
    for p in ["", "analyze", "predict"]:
        if p not in candidates:
            candidates.append(p)

    fsize = os.path.getsize(pdf_path)
    last_err: Optional[Exception] = None

    for ap in candidates:
        try:
            url = f"{base_url.rstrip('/')}/{ap}" if ap else base_url.rstrip("/")
            logging.info(f"HURIDOCS POST {url} ({fsize} bytes)")

            with open(pdf_path, "rb") as f:
                files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
                resp = HTTP.post(url, files=files, timeout=timeout)

            # Пропускаем недоступные endpoints
            if resp.status_code == 404 or resp.status_code == 405:
                logging.warning(f"HURIDOCS endpoint '{ap}' → {resp.status_code}")
                continue

            resp.raise_for_status()
            data = resp.json()

            # Проверяем формат ответа
            if isinstance(data, dict) and "segments" in data:
                return data["segments"]

            if isinstance(data, list):
                return data

            raise ValueError(f"Unexpected response type: {type(data)}")

        except Exception as e:
            last_err = e
            logging.warning(f"HURIDOCS '{ap}': {e}")
            continue

    raise RuntimeError(
        f"HURIDOCS: все endpoints недоступны, последняя ошибка: {last_err}"
    )


def huridocs_analyze_pdf(
    pdf_path: str,
    base_url: str = DEFAULT_HURIDOCS_BASE,
    analyze_path: str = HURIDOCS_ANALYZE_PATH,
    timeout: int = TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Анализирует PDF через HURIDOCS API.

    Args:
        pdf_path: Путь к PDF файлу
        base_url: Базовый URL HURIDOCS API
        analyze_path: Путь endpoint для анализа
        timeout: Таймаут запроса в секундах

    Returns:
        Список сегментов в JSON формате

    Raises:
        requests.HTTPError: При HTTP ошибках
        ValueError: При неожиданном формате ответа
    """
    url = (
        f"{base_url.rstrip('/')}/{analyze_path}"
        if analyze_path
        else base_url.rstrip("/")
    )

    with open(pdf_path, "rb") as f:
        data = f.read()

    t = Timer()
    files = {"file": (os.path.basename(pdf_path), io.BytesIO(data), "application/pdf")}
    resp = HTTP.post(url, files=files, timeout=timeout)
    dur = t.ms()

    log_metric("huridocs_analyze", None, "POST", dur, None, len(data), url)

    resp.raise_for_status()
    data_json = resp.json()

    # Проверяем формат ответа
    if isinstance(data_json, dict) and "segments" in data_json:
        return data_json["segments"]

    if isinstance(data_json, list):
        return data_json

    raise ValueError("HURIDOCS response missing 'segments' key")


def huridocs_visualize_pdf(
    pdf_path: str,
    out_pdf_path: str,
    base_url: str = DEFAULT_HURIDOCS_BASE,
    visualize_path: str = HURIDOCS_VISUALIZE_PATH,
    timeout: int = TIMEOUT,
) -> None:
    """
    Создаёт визуализацию разметки PDF через HURIDOCS API.

    Args:
        pdf_path: Путь к входному PDF файлу
        out_pdf_path: Путь для сохранения визуализированного PDF
        base_url: Базовый URL HURIDOCS API
        visualize_path: Путь endpoint для визуализации
        timeout: Таймаут запроса в секундах

    Raises:
        requests.HTTPError: При HTTP ошибках
    """
    url = f"{base_url.rstrip('/')}/{visualize_path}"

    with open(pdf_path, "rb") as f:
        data = f.read()

    t = Timer()
    files = {"file": (os.path.basename(pdf_path), io.BytesIO(data), "application/pdf")}
    resp = HTTP.post(url, files=files, timeout=timeout)
    dur = t.ms()

    log_metric("huridocs_visualize", None, "POST", dur, None, len(data), url)

    resp.raise_for_status()

    with open(out_pdf_path, "wb") as out:
        out.write(resp.content)
