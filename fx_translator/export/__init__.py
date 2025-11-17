"""
Модуль export: экспорт результатов.
"""

from fx_translator.export.docx import export_docx
from fx_translator.export.pdf import annotate_pdf_with_segments

__all__ = [
    "export_docx",
    "annotate_pdf_with_segments",
]
