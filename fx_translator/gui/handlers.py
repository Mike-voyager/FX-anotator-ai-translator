"""
Custom logging handlers for GUI integration.
"""

from __future__ import annotations
import logging
from typing import Callable


class LogQueueHandler(logging.Handler):
    """
    Logging handler that forwards messages to GUI callback.
    
    Используется для интеграции системы логирования Python
    с Tkinter GUI в безопасном для потоков режиме.
    """
    
    def __init__(self, gui_callback: Callable[[str], None]):
        """
        Инициализация handler.
        
        Args:
            gui_callback: Функция для отправки сообщений в GUI
        """
        super().__init__()
        self.gui_callback = gui_callback
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Отправляет log record в GUI через callback.
        
        Args:
            record: Log record для обработки
        """
        try:
            msg = self.format(record)
            self.gui_callback(msg)
        except Exception:
            self.handleError(record)