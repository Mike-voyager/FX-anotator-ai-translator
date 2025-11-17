"""
Tkinter GUI application for FX-Translator.

Предоставляет графический интерфейс для управления конвейером обработки PDF:
- Выбор файлов и настройка параметров
- Управление Docker контейнером HURIDOCS
- Мониторинг процесса обработки
- Пауза/продолжение выполнения
"""

from __future__ import annotations
import os
import time
import logging
import threading
import queue
from typing import Optional, Callable

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import requests

from fx_translator.core.config import (
    DEFAULT_HURIDOCS_BASE,
    DEFAULT_LMSTUDIO_BASE,
    LMSTUDIO_MODEL,
    HURIDOCS_ANALYZE_PATH,
    HURIDOCS_VISUALIZE_PATH,
)
from fx_translator.orchestration.docker import Orchestrator
from fx_translator.processing.pipeline import (
    run_pipeline_transactional,
    run_pipeline,
)
from fx_translator.processing.extractors.pymupdf import run_pipeline_pymupdf
from fx_translator.gui.handlers import LogQueueHandler


class AppGUI:
    """
    Главное приложение GUI на Tkinter.

    Функционал:
    - Выбор входных/выходных файлов
    - Настройка параметров обработки
    - Управление Docker контейнером HURIDOCS
    - Мониторинг логов в реальном времени
    - Пауза/продолжение обработки
    """

    def __init__(self, master: tk.Tk):
        """
        Инициализация GUI приложения.

        Args:
            master: Корневой Tk объект
        """
        self.master = master
        master.title("FX-Translator: PDF → AI Translation")

        # Основные параметры
        self.pdf_path = tk.StringVar()
        self.out_pdf = tk.StringVar()
        self.out_docx = tk.StringVar()
        self.src_lang = tk.StringVar(value="en")
        self.tgt_lang = tk.StringVar(value="ru")
        self.force_split = tk.IntVar(value=1)
        self.force_split_excl = tk.StringVar(value="")

        # Источник блоков и LLM-группировка
        self.source_mode = tk.StringVar(value="huridocs")  # "pymupdf" | "huridocs"
        self.use_llm_grouping = tk.BooleanVar(value=False)

        # HURIDOCS параметры
        self.manage_huridocs = tk.BooleanVar(value=False)
        self.huridocs_base = tk.StringVar(value=DEFAULT_HURIDOCS_BASE)
        self.huridocs_image = tk.StringVar(
            value="huridocs/pdf-document-layout-analysis:v0.0.31"
        )
        self.huridocs_port = tk.IntVar(value=5060)
        self.huridocs_internal_port = tk.IntVar(value=5060)
        self.huridocs_analyze_path = tk.StringVar(value=HURIDOCS_ANALYZE_PATH)
        self.huridocs_visualize_path = tk.StringVar(value=HURIDOCS_VISUALIZE_PATH)
        self.use_gpu = tk.BooleanVar(value=True)

        # LM Studio параметры
        self.lms_base = tk.StringVar(value=DEFAULT_LMSTUDIO_BASE)
        self.LMSTUDIO_MODEL = tk.StringVar(value=LMSTUDIO_MODEL)
        self.lms_batch_size = tk.IntVar(value=15)

        # Режимы обработки
        self.transactional = tk.BooleanVar(value=True)
        self.split_spreads_enabled = tk.BooleanVar(value=True)
        self.restart_every = tk.IntVar(value=0)

        # Тестовые параметры
        self.page_limit = tk.IntVar(value=5)
        self.test_start_page = tk.IntVar(value=1)
        self.test_end_page = tk.IntVar(value=5)

        # Управление паузой
        self.pause_flag = threading.Event()
        self.pause_flag.set()

        self.use_pdf_comments = tk.BooleanVar(value=True)
        self.pdf_annotation_type = tk.StringVar(value="highlight")

        # Orchestrator
        self._orchestrator: Optional[Orchestrator] = None

        # Очередь логов
        self.log_queue: queue.Queue = queue.Queue()

        # Строим UI
        self._build_ui()

        # Настраиваем логирование
        self._setup_logging()

    def _build_ui(self):
        """Создаёт интерфейс пользователя."""
        frm = ttk.Frame(self.master, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        row = 0

        # === ФАЙЛЫ ===
        ttk.Label(frm, text="PDF:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.pdf_path, width=60).grid(
            row=row, column=1, sticky="ew"
        )
        ttk.Button(frm, text="...", command=self.pick_pdf).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        ttk.Label(frm, text="Выход annotated PDF:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.out_pdf, width=60).grid(
            row=row, column=1, sticky="ew"
        )
        ttk.Button(frm, text="...", command=self.pick_out_pdf).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        ttk.Label(frm, text="Выход DOCX:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.out_docx, width=60).grid(
            row=row, column=1, sticky="ew"
        )
        ttk.Button(frm, text="...", command=self.pick_out_docx).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        # === ЯЗЫКИ ===
        ttk.Label(frm, text="Исходный язык:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.src_lang, width=10).grid(
            row=row, column=1, sticky="w"
        )
        ttk.Label(frm, text="Целевой язык:").grid(row=row, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.tgt_lang, width=10).grid(
            row=row, column=3, sticky="w"
        )
        row += 1

        # === ИСТОЧНИК БЛОКОВ ===
        ttk.Label(frm, text="Источник блоков:").grid(row=row, column=0, sticky="w")
        self.src_combo = ttk.Combobox(
            frm,
            values=["huridocs", "pymupdf"],
            textvariable=self.source_mode,
            width=12,
            state="readonly",
        )
        self.src_combo.grid(row=row, column=1, sticky="w")
        ttk.Checkbutton(
            frm, text="LLM-группировка (PyMuPDF)", variable=self.use_llm_grouping
        ).grid(row=row, column=2, columnspan=2, sticky="w")
        row += 1

        # === HURIDOCS ===
        ttk.Checkbutton(
            frm,
            text="Управлять контейнером HURIDOCS из приложения",
            variable=self.manage_huridocs,
        ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        ttk.Label(frm, text="HURIDOCS base URL:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.huridocs_base, width=40).grid(
            row=row, column=1, sticky="ew"
        )
        row += 1

        ttk.Label(frm, text="HURIDOCS image:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.huridocs_image, width=40).grid(
            row=row, column=1, sticky="ew"
        )
        row += 1

        ttk.Label(frm, text="Host port:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.huridocs_port, width=10).grid(
            row=row, column=1, sticky="w"
        )
        ttk.Label(frm, text="Container port:").grid(row=row, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.huridocs_internal_port, width=10).grid(
            row=row, column=3, sticky="w"
        )
        row += 1

        ttk.Checkbutton(frm, text="GPU", variable=self.use_gpu).grid(
            row=row, column=0, sticky="w"
        )
        row += 1

        # === LM STUDIO ===
        ttk.Label(frm, text="LM Studio base:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.lms_base, width=40).grid(
            row=row, column=1, sticky="ew"
        )
        row += 1

        ttk.Label(frm, text="LM Studio model:").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.LMSTUDIO_MODEL, width=40).grid(
            row=row, column=1, sticky="ew"
        )
        row += 1

        # === РЕЖИМЫ ===
        ttk.Checkbutton(
            frm, text="Транзакционный режим (HURIDOCS)", variable=self.transactional
        ).grid(row=row, column=0, sticky="w")
        ttk.Checkbutton(
            frm, text="Split spreads", variable=self.split_spreads_enabled
        ).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Checkbutton(
            frm, text="Разделять развороты пополам", variable=self.force_split
        ).grid(row=row, column=0, sticky="w")
        ttk.Label(frm, text="Исключения (стр.):").grid(row=row, column=1, sticky="e")
        ttk.Entry(frm, textvariable=self.force_split_excl, width=22).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        # === ТЕСТОВЫЕ ПАРАМЕТРЫ ===
        ttk.Label(frm, text="Старт. страница (тест):").grid(
            row=row, column=0, sticky="w"
        )
        ttk.Entry(frm, textvariable=self.test_start_page, width=6).grid(
            row=row, column=1, sticky="w"
        )
        ttk.Label(frm, text="Финиш. страница (тест):").grid(
            row=row, column=2, sticky="e"
        )
        ttk.Entry(frm, textvariable=self.test_end_page, width=6).grid(
            row=row, column=3, sticky="w"
        )
        row += 1

        # === КНОПКИ ===
        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=4, sticky="w", pady=4)

        self.btn_run = ttk.Button(btns, text="Запустить конвейер", command=self.on_run)
        self.btn_run.pack(side=tk.LEFT, padx=4)

        self.btn_test = ttk.Button(btns, text="Тестовый запуск", command=self.on_test)
        self.btn_test.pack(side=tk.LEFT, padx=4)

        self.btn_pause = ttk.Button(btns, text="Пауза", command=self.on_pause)
        self.btn_pause.pack(side=tk.LEFT, padx=4)

        self.btn_resume = ttk.Button(
            btns, text="Продолжить", command=self.on_resume, state="disabled"
        )
        self.btn_resume.pack(side=tk.LEFT, padx=4)

        self.btn_huri_start = ttk.Button(
            btns, text="Старт HURIDOCS", command=self.on_huri_start
        )
        self.btn_huri_start.pack(side=tk.LEFT, padx=12)

        self.btn_huri_stop = ttk.Button(
            btns, text="Стоп HURIDOCS", command=self.on_huri_stop
        )
        self.btn_huri_stop.pack(side=tk.LEFT, padx=4)

        row += 1

        ttk.Checkbutton(
            frm,
            text="Использовать комментарии (вместо визуального редактирования)",
            variable=self.use_pdf_comments,
        ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        ttk.Label(frm, text="Тип подсветки:").grid(row=row, column=0, sticky="w")
        ttk.Combobox(
            frm,
            values=["highlight", "underline", "squiggly", "none"],
            textvariable=self.pdf_annotation_type,
            width=12,
            state="readonly",
        ).grid(row=row, column=1, sticky="w")
        row += 1

        # === ЛОГИ ===
        self.txt = tk.Text(frm, height=16)
        self.txt.grid(row=row, column=0, columnspan=4, sticky="nsew")
        frm.rowconfigure(row, weight=1)
        frm.columnconfigure(1, weight=1)

        # Запускаем обработку очереди логов
        self.master.after(100, self.flush_logs)

    def _setup_logging(self):
        """Настраивает логирование в GUI."""
        handler = LogQueueHandler(self.gui_log)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def gui_log(self, msg: str):
        """Добавляет сообщение в очередь логов."""
        self.log_queue.put(msg)

    def flush_logs(self):
        """Периодически читает очередь логов и выводит в текстовый виджет."""
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.txt.insert("end", msg + "\\n")
            self.txt.see("end")
        self.master.after(100, self.flush_logs)

        # === FILE PICKERS ===

    def pick_pdf(self):
        """Выбор входного PDF файла."""
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if p:
            self.pdf_path.set(p)
            # Автозаполнение выходных файлов
            base = os.path.splitext(p)[0]
            self.out_pdf.set(base + ".annotated.pdf")
            self.out_docx.set(base + ".translation.docx")

    def pick_out_pdf(self):
        """Выбор выходного PDF файла."""
        p = filedialog.asksaveasfilename(defaultextension=".pdf")
        if p:
            self.out_pdf.set(p)

    def pick_out_docx(self):
        """Выбор выходного DOCX файла."""
        p = filedialog.asksaveasfilename(defaultextension=".docx")
        if p:
            self.out_docx.set(p)

    # === PAUSE / RESUME ===

    def on_pause(self):
        """Приостанавливает обработку."""
        self.pause_flag.clear()
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="normal")
        self.gui_log("⏸️ Пауза: обработка приостановится после текущей страницы.")

    def on_resume(self):
        """Возобновляет обработку."""
        self.pause_flag.set()
        self.btn_pause.config(state="normal")
        self.btn_resume.config(state="disabled")
        self.gui_log("▶️ Продолжено.")

    def wait_if_paused(self):
        """Ожидает снятия паузы (для использования в pipeline)."""
        while not self.pause_flag.is_set():
            time.sleep(0.2)

    # === ORCHESTRATOR MANAGEMENT ===

    def _build_orchestrator(self) -> Optional[Orchestrator]:
        """Создаёт Orchestrator если управление контейнером включено."""
        if not self.manage_huridocs.get():
            return None

        return Orchestrator(
            huridocs_image=self.huridocs_image.get(),
            huridocs_container="huridocs",
            huridocs_port=self.huridocs_port.get(),
            huridocs_internal_port=self.huridocs_internal_port.get(),
            use_gpu=self.use_gpu.get(),
            lms_base=self.lms_base.get(),
            LMSTUDIO_MODEL=self.LMSTUDIO_MODEL.get(),
        )

    def on_huri_start(self):
        """Запускает контейнер HURIDOCS."""
        if not self.manage_huridocs.get():
            messagebox.showinfo(
                "HURIDOCS",
                "Управление контейнером отключено. Запустите docker compose up -d вручную.",
            )
            return

        try:
            if self._orchestrator is None:
                self._orchestrator = self._build_orchestrator()

            if self._orchestrator and self._orchestrator.start_huridocs(self.gui_log):
                self.gui_log("✅ HURIDOCS успешно запущен.")
        except Exception as e:
            self._safe_show_error("HURIDOCS", f"Не удалось запустить: {e}")

    def on_huri_stop(self):
        """Останавливает контейнер HURIDOCS."""
        if not self.manage_huridocs.get():
            messagebox.showinfo(
                "HURIDOCS",
                "Управление контейнером отключено. Остановите docker compose stop вручную.",
            )
            return

        try:
            if self._orchestrator is not None:
                self._orchestrator.stop_huridocs(self.gui_log)
                self.gui_log("✅ HURIDOCS остановлен.")
        except Exception as e:
            self._safe_show_error("HURIDOCS", f"Не удалось остановить: {e}")

    # === SERVICE CHECKS ===

    def _check_lm_studio(self) -> bool:
        """Проверяет доступность LM Studio API."""
        try:
            url = self.lms_base.get().rstrip("/") + "/models"
            r = requests.get(url, timeout=5)
            if r.status_code >= 400:
                self._safe_show_error(
                    "LM Studio", f"API отвечает ошибкой {r.status_code} на {url}"
                )
                return False
            return True
        except Exception as e:
            self._safe_show_error("LM Studio", f"API недоступен: {e}")
            return False

    def _check_huridocs(self) -> bool:
        """Проверяет доступность HURIDOCS API."""
        try:
            base = self.huridocs_base.get().rstrip("/")
            r = requests.get(base, timeout=60)  # Увеличили до 60 секунд
            if 200 <= r.status_code < 300:
                return True

            # Пробуем /docs
            r2 = requests.get(base + "/docs", timeout=60)  # Увеличили до 60 секунд
            if 200 <= r2.status_code < 300:
                return True

            self._safe_show_error(
                "HURIDOCS",
                f"API недоступен. Проверьте, что контейнер запущен на {base}",
            )
            return False
        except Exception as e:
            self._safe_show_error("HURIDOCS", f"API недоступен: {e}")
            return False

    def _safe_show_error(self, title: str, msg: str):
        """Показывает ошибку безопасно из потока."""
        self.master.after(0, lambda: messagebox.showerror(title, msg))
        # === RUN BUTTONS ===

    def on_test(self):
        """Запускает тестовый конвейер (диапазон страниц)."""
        start = self.test_start_page.get()
        end = self.test_end_page.get()
        threading.Thread(
            target=lambda: self._execute_range(start, end), daemon=True
        ).start()

    def on_run(self):
        """Запускает полный конвейер."""
        if not self.pdf_path.get() or not os.path.exists(self.pdf_path.get()):
            self._safe_show_error("Ошибка", "Выберите входной PDF файл.")
            return

        threading.Thread(
            target=self._execute_range, args=(None, None), daemon=True
        ).start()

    def _execute_range(self, start: Optional[int] = None, end: Optional[int] = None):
        """
        Выполняет конвейер обработки.

        Args:
            start: Начальная страница (None = с начала)
            end: Конечная страница (None = до конца)
        """
        self._set_buttons_enabled(False)

        try:
            mode = self.source_mode.get().strip().lower()

            # Проверяем сервисы
            if mode != "pymupdf":
                if not self._check_huridocs():
                    return

            if not self._check_lm_studio():
                return

            self.gui_log("🚀 Запуск конвейера...")

            transactional = self.transactional.get()
            split_spreads_enabled = self.split_spreads_enabled.get()
            restart_every = self.restart_every.get()
            start_page = int(start) if start else None
            end_page = int(end) if end else None
            batch_size = self.lms_batch_size.get()

            # Выбор конвейера
            if mode == "pymupdf":
                # PyMuPDF pipeline
                run_pipeline_pymupdf(
                    input_pdf=self.pdf_path.get(),
                    out_pdf_annotated=self.out_pdf.get(),
                    out_docx=self.out_docx.get(),
                    src_lang=self.src_lang.get(),
                    tgt_lang=self.tgt_lang.get(),
                    lms_base=self.lms_base.get(),
                    LMSTUDIO_MODEL=self.LMSTUDIO_MODEL.get(),
                    start_page=start_page,
                    end_page=end_page,
                    use_llm_grouping=self.use_llm_grouping.get(),
                    split_spreads_enabled=split_spreads_enabled,
                    force_split_spreads=bool(self.force_split.get()),
                    force_split_exceptions=self.force_split_excl.get(),
                    pause_ms=0,
                    pause_hook=self.wait_if_paused,
                )
            else:
                # HURIDOCS pipeline
                if transactional:
                    orch = self._build_orchestrator()
                    run_pipeline_transactional(
                        input_pdf=self.pdf_path.get(),
                        out_pdf_annotated=self.out_pdf.get(),
                        out_docx=self.out_docx.get(),
                        src_lang=self.src_lang.get(),
                        tgt_lang=self.tgt_lang.get(),
                        huridocs_base=self.huridocs_base.get(),
                        huridocs_analyze_path=self.huridocs_analyze_path.get(),
                        lms_base=self.lms_base.get(),
                        LMSTUDIO_MODEL=self.LMSTUDIO_MODEL.get(),
                        force_split_exceptions=self.force_split_excl.get(),
                        force_split_spreads=bool(self.force_split.get()),
                        batch_size=batch_size,
                        orchestrator=orch,
                        restart_every=restart_every,
                        start_page=start_page,
                        end_page=end_page,
                        pause_ms=0,
                        pause_hook=self.wait_if_paused,
                        split_spreads_enabled=split_spreads_enabled,
                    )
                else:
                    run_pipeline(
                        input_pdf=self.pdf_path.get(),
                        out_pdf_annotated=self.out_pdf.get(),
                        out_docx=self.out_docx.get(),
                        src_lang=self.src_lang.get(),
                        tgt_lang=self.tgt_lang.get(),
                        huridocs_base=self.huridocs_base.get(),
                        huridocs_analyze_path=self.huridocs_analyze_path.get(),
                        huridocs_visualize_path=self.huridocs_visualize_path.get()
                        or None,
                        lms_base=self.lms_base.get(),
                        LMSTUDIO_MODEL=self.LMSTUDIO_MODEL.get(),
                        split_spreads_enabled=split_spreads_enabled,
                        batch_size=batch_size,
                        page_limit=(
                            self.page_limit.get() if self.page_limit.get() else None
                        ),
                        pause_ms=0,
                        force_split_exceptions=self.force_split_excl.get(),
                        force_split_spreads=bool(self.force_split.get()),
                        pause_hook=self.wait_if_paused,
                        start_page=start_page,
                        end_page=end_page,
                    )

            self.gui_log("✅ Готово!")

        except Exception as e:
            self.gui_log(f"❌ Критическая ошибка: {e}")
            self._safe_show_error("Ошибка", str(e))
            import traceback

            traceback.print_exc()

        finally:
            self._set_buttons_enabled(True)

    def _set_buttons_enabled(self, enabled: bool):
        """
        Включает/выключает кнопки управления.

        Args:
            enabled: True для включения, False для отключения
        """
        state = "normal" if enabled else "disabled"
        for btn in (
            self.btn_run,
            self.btn_test,
            self.btn_pause,
            self.btn_huri_start,
            self.btn_huri_stop,
        ):
            try:
                btn.config(state=state)
            except Exception:
                pass
