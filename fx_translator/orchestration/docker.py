"""
Docker orchestration for HURIDOCS service.

Этот модуль управляет Docker контейнером HURIDOCS для автоматического
запуска, остановки и перезапуска сервиса при необходимости.
"""

from __future__ import annotations
import time
import logging
import subprocess
import contextlib
from typing import Optional, Callable

import requests

from fx_translator.core.config import (
    DEFAULT_HURIDOCS_BASE,
    DEFAULT_LMSTUDIO_BASE,
    LMSTUDIO_MODEL,
)


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """
    Выполняет команду и возвращает код, stdout, stderr.

    Args:
        cmd: Список аргументов команды
        timeout: Таймаут выполнения в секундах

    Returns:
        Кортеж (return_code, stdout, stderr)
    """
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False
    )

    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        proc.kill()
        return 124, "", "Timeout"


def wait_http_ready(url: str, timeout_sec: int = 60, interval: float = 1.0) -> bool:
    """
    Ожидает готовности HTTP сервиса.

    Args:
        url: URL для проверки
        timeout_sec: Максимальное время ожидания
        interval: Интервал между проверками

    Returns:
        True если сервис готов, False при таймауте
    """
    start = time.time()
    url = url.rstrip("/")
    probes = (url, url + "/docs")

    while time.time() - start < timeout_sec:
        for u in probes:
            try:
                r = requests.get(u, timeout=5)
                if 200 <= r.status_code < 300:
                    return True
            except Exception:
                pass
        time.sleep(interval)

    return False


class Orchestrator:
    """
    Управление Docker контейнером HURIDOCS.

    Возможности:
    - Запуск контейнера с настройкой портов и GPU
    - Остановка и удаление контейнера
    - Проверка готовности HTTP API
    - Автоматический перезапуск при сбоях
    """

    def __init__(
        self,
        huridocs_image: str = "huridocs/pdf-document-layout-analysis:v0.0.31",
        huridocs_container: str = "huridocs",
        huridocs_port: int = 5060,
        huridocs_internal_port: int = 5060,
        use_gpu: bool = True,
        lms_base: str = DEFAULT_LMSTUDIO_BASE,
        LMSTUDIO_MODEL: str = LMSTUDIO_MODEL,
    ):
        """
        Инициализация orchestrator.

        Args:
            huridocs_image: Docker образ HURIDOCS
            huridocs_container: Имя контейнера
            huridocs_port: Порт на хосте
            huridocs_internal_port: Внутренний порт контейнера
            use_gpu: Использовать GPU (--gpus all)
            lms_base: Base URL для LM Studio
            LMSTUDIO_MODEL: Модель LM Studio
        """
        self.huridocs_image = huridocs_image
        self.huridocs_container = huridocs_container
        self.huridocs_port = huridocs_port
        self.huridocs_internal_port = huridocs_internal_port
        self.use_gpu = use_gpu
        self.lms_base = lms_base
        self.lms_model = LMSTUDIO_MODEL

        self.huridocs_base_url: Optional[str] = None

    def start_huridocs(self, log: Callable[[str], None]) -> bool:
        """
        Запускает контейнер HURIDOCS.

        Args:
            log: Функция для логирования (например, print или gui_log)

        Returns:
            True если контейнер успешно запущен и готов
        """
        log("Подтягиваем образ HURIDOCS (docker pull)...")
        code, out, err = run_cmd(["docker", "pull", self.huridocs_image], timeout=600)

        if code != 0:
            log(f"Предупреждение pull: {err.strip() or out.strip()}")

        log("Запускаем контейнер HURIDOCS...")

        # Удаляем старый контейнер если есть
        run_cmd(["docker", "rm", "-f", self.huridocs_container], timeout=60)

        # Формируем команду запуска
        base_cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.huridocs_container,
            "-p",
            f"{self.huridocs_port}:{self.huridocs_internal_port}",
            self.huridocs_image,
        ]

        # Добавляем GPU если нужно
        if self.use_gpu:
            base_cmd.insert(2, "--gpus")
            base_cmd.insert(3, "all")

        code, out, err = run_cmd(base_cmd, timeout=180)

        if code != 0:
            log(f"Ошибка запуска HURIDOCS: {err.strip() or out.strip()}")
            return False

        # Ждём готовности HTTP API
        base = f"http://localhost:{self.huridocs_port}"
        if wait_http_ready(base, timeout_sec=90):
            self.huridocs_base_url = base
            log(f"HURIDOCS готов на {base}")
            return True

        log("HURIDOCS не ответил за отведенное время.")
        return False

    def stop_huridocs(self, log: Callable[[str], None]) -> None:
        """
        Останавливает и удаляет контейнер HURIDOCS.

        Args:
            log: Функция для логирования
        """
        log("Останавливаем контейнер HURIDOCS...")
        run_cmd(["docker", "stop", self.huridocs_container], timeout=60)
        run_cmd(["docker", "rm", self.huridocs_container], timeout=60)
        log("HURIDOCS остановлен.")
        self.huridocs_base_url = None

    def get_base_url(self) -> str:
        """
        Возвращает base URL для HURIDOCS API.

        Returns:
            URL в формате http://localhost:port
        """
        return self.huridocs_base_url or f"http://localhost:{self.huridocs_port}"

    def maybe_restart_on_failure(
        self,
        log: Callable[[str], None],
        err: Optional[BaseException] = None,
        status_code: Optional[int] = None,
    ) -> bool:
        """
        Пытается перезапустить контейнер при определённых ошибках.

        Перезапускает только при:
        - Timeout или ConnectionError
        - HTTP 5xx ошибках

        Args:
            log: Функция для логирования
            err: Исключение (если есть)
            status_code: HTTP статус код (если есть)

        Returns:
            True если контейнер успешно перезапущен
        """
        should_restart = False

        # Проверяем тип ошибки
        if err and isinstance(err, (requests.Timeout, requests.ConnectionError)):
            should_restart = True
            log(f"Обнаружен таймаут/ошибка соединения: {err}")

        # Проверяем HTTP статус
        if status_code and 500 <= int(status_code) < 600:
            should_restart = True
            log(f"Обнаружена серверная ошибка HTTP {status_code}")

        if not should_restart:
            return False

        log("Пытаемся перезапустить HURIDOCS...")

        # Останавливаем с подавлением ошибок
        with contextlib.suppress(Exception):
            self.stop_huridocs(log)

        # Запускаем заново
        ok = self.start_huridocs(log)

        if ok:
            log("✅ HURIDOCS успешно перезапущен.")
        else:
            log("❌ HURIDOCS: перезапуск не удался.")

        return ok

    def is_running(self) -> bool:
        """
        Проверяет, запущен ли контейнер.

        Returns:
            True если контейнер запущен
        """
        code, out, err = run_cmd(
            [
                "docker",
                "ps",
                "--filter",
                f"name={self.huridocs_container}",
                "--format",
                "{{.Names}}",
            ],
            timeout=10,
        )

        return code == 0 and self.huridocs_container in out

    def get_container_logs(self, tail: int = 50) -> str:
        """
        Получает логи контейнера.

        Args:
            tail: Количество последних строк

        Returns:
            Строка с логами
        """
        code, out, err = run_cmd(
            ["docker", "logs", "--tail", str(tail), self.huridocs_container], timeout=30
        )

        if code == 0:
            return out
        return f"Ошибка получения логов: {err}"
