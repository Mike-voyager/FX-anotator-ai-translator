"""
Базовые классы для API клиентов.

Этот модуль содержит HTTP сессию с retry логикой и базовые утилиты для API.
"""

from __future__ import annotations
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fx_translator.core.config import MAX_RETRIES, BACKOFF_FACTOR, TIMEOUT


def get_http_session(
    total: int = MAX_RETRIES,
    backoff: float = BACKOFF_FACTOR,
) -> requests.Session:
    """
    Создаёт HTTP сессию с настроенной retry логикой.

    Args:
        total: Максимальное количество повторных попыток
        backoff: Коэффициент экспоненциальной задержки между попытками

    Returns:
        Настроенная requests.Session с retry адаптером
    """
    status = [413, 429, 500, 502, 503, 504]
    methods = frozenset(["DELETE", "GET", "HEAD", "OPTIONS", "PUT", "TRACE", "POST"])

    retry = Retry(
        total=total,
        backoff_factor=backoff,
        status_forcelist=status,
        allowed_methods=methods,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)

    s = requests.Session()
    s.mount("http://", adapter)
    s.mount("https://", adapter)

    return s


# Глобальная HTTP сессия с retry логикой
HTTP = get_http_session()
