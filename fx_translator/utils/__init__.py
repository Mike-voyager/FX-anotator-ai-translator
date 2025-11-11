"""
Модуль utils: вспомогательные утилиты.
"""

from fx_translator.utils.text import (
    sanitize_model_content,
    clean_text_inplace,
    denoise_soft_linebreaks,
    looks_captionish,
    looks_headerish,
    parse_page_set,
)
from fx_translator.utils.geometry import (
    x_overlap,
    sort_segments_reading_order,
    merge_segments,
)
from fx_translator.utils.json_helpers import (
    extract_first_json_like,
    extract_first_json_object,
)
from fx_translator.utils.metrics import (
    Timer,
    init_metrics,
    log_metric,
    METRICS_PATH,
)

__all__ = [
    # Text utilities
    "sanitize_model_content",
    "clean_text_inplace",
    "denoise_soft_linebreaks",
    "looks_captionish",
    "looks_headerish",
    "parse_page_set",
    # Geometry utilities
    "x_overlap",
    "sort_segments_reading_order",
    "merge_segments",
    # JSON utilities
    "extract_first_json_like",
    "extract_first_json_object",
    # Metrics utilities
    "Timer",
    "init_metrics",
    "log_metric",
    "METRICS_PATH",
]
