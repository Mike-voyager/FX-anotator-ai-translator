"""
Модуль analyzers: анализ layout и сегментов.
"""

from fx_translator.processing.analyzers.segments import (
    refine_huridocs_segments,
    deglue_pages_pdfaware,
)
from fx_translator.processing.analyzers.layout import (
    split_spreads,
    split_spreads_force_half,
)

__all__ = [
    "refine_huridocs_segments",
    "deglue_pages_pdfaware",
    "split_spreads",
    "split_spreads_force_half",
]