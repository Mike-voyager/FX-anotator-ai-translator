"""
Модуль api: клиенты внешних сервисов.
"""

from fx_translator.api.base import get_http_session, HTTP
from fx_translator.api.huridocs import (
    huridocs_analyze_pdf,
    huridocs_analyze_pdf_smart,
    huridocs_visualize_pdf,
)
from fx_translator.api.lmstudio import lmstudio_translate_simple

__all__ = [
    # Base
    "get_http_session",
    "HTTP",
    # HURIDOCS
    "huridocs_analyze_pdf",
    "huridocs_analyze_pdf_smart",
    "huridocs_visualize_pdf",
    # LM Studio
    "lmstudio_translate_simple",
]
