"""
Модуль core: базовые модели, типы и конфигурация.
"""

from fx_translator.core.models import TextLine, TextBlock, Segment, PageBatch
from fx_translator.core.types import BlockType, logical_side, BBox
from fx_translator.core.config import (
    DEFAULT_HURIDOCS_BASE,
    DEFAULT_LMSTUDIO_BASE,
    LMSTUDIO_MODEL,
    MAX_RETRIES,
    TIMEOUT,
)
from fx_translator.core.exceptions import (
    FXTranslatorError,
    HURIDOCSError,
    LMStudioError,
    PDFProcessingError,
    SegmentProcessingError,
    ExportError,
)

__all__ = [
    # Models
    "TextLine",
    "TextBlock",
    "Segment",
    "PageBatch",
    # Types
    "BlockType",
    "logical_side",
    "BBox",
    # Config
    "DEFAULT_HURIDOCS_BASE",
    "DEFAULT_LMSTUDIO_BASE",
    "LMSTUDIO_MODEL",
    "MAX_RETRIES",
    "TIMEOUT",
    # Exceptions
    "FXTranslatorError",
    "HURIDOCSError",
    "LMStudioError",
    "PDFProcessingError",
    "SegmentProcessingError",
    "ExportError",
]
