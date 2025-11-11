"""
Точка входа для FX-Translator.

Запускает GUI приложение или предоставляет информацию об использовании API.
"""

from __future__ import annotations
import sys
import logging


def setup_logging():
    """Настройка логирования."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def main():
    """Главная функция запуска приложения."""
    setup_logging()
    
    try:
        import tkinter as tk
        from fx_translator.gui.app import AppGUI
        
        root = tk.Tk()
        app = AppGUI(root)
        root.mainloop()
        
    except ImportError as e:
        logging.error(f"GUI модуль не найден: {e}")
        logging.info("=" * 60)
        logging.info("GUI не установлен. Используйте API напрямую:")
        logging.info("")
        logging.info("Пример использования:")
        logging.info("")
        logging.info("  from fx_translator.processing.pipeline import run_pipeline")
        logging.info("")
        logging.info("  run_pipeline(")
        logging.info('      inputpdf="input.pdf",')
        logging.info('      outpdfannotated="output_annotated.pdf",')
        logging.info('      outdocx="output.docx",')
        logging.info('      srclang="en",')
        logging.info('      tgtlang="ru",')
        logging.info("  )")
        logging.info("=" * 60)
        sys.exit(1)
    
    except Exception as e:
        logging.error(f"Ошибка при запуске приложения: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()