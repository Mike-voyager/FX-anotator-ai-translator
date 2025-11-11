"""
Кастомные исключения для FX-Translator.

Этот модуль содержит специфичные для приложения исключения.
"""


class FXTranslatorError(Exception):
    """Базовое исключение для всех ошибок FX-Translator."""

    pass


class HURIDOCSError(FXTranslatorError):
    """Ошибка при работе с HURIDOCS API."""

    pass


class LMStudioError(FXTranslatorError):
    """Ошибка при работе с LM Studio API."""

    pass


class PDFProcessingError(FXTranslatorError):
    """Ошибка при обработке PDF."""

    pass


class SegmentProcessingError(FXTranslatorError):
    """Ошибка при обработке сегментов."""

    pass


class ExportError(FXTranslatorError):
    """Ошибка при экспорте результатов."""

    pass
