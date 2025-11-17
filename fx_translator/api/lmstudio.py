"""
Клиент для LM Studio API (OpenAI-compatible).

Этот модуль содержит функции для работы с LM Studio для перевода текста.
"""

from __future__ import annotations
import logging
from typing import List, Dict

from fx_translator.core.config import (
    DEFAULT_LMSTUDIO_BASE,
    LMSTUDIO_CHAT_PATH,
    LMSTUDIO_MODEL,
    LMSTUDIO_API_KEY,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TRANSLATION_TIMEOUT,
)
from fx_translator.core.models import Segment
from fx_translator.api.base import HTTP


def lmstudio_translate_simple(
    model: str,
    pagenumber: int,
    segments: List[Segment],
    src_lang: str,
    tgt_lang: str,
    base_url: str = DEFAULT_LMSTUDIO_BASE,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TRANSLATION_TIMEOUT,
) -> Dict[int, str]:
    """
    Переводит список сегментов через LM Studio API.
    """

    def clean_text_input(t: str) -> str:
        """Очищает входной текст от лишних символов."""
        if not t:
            return t

        t = t.replace("\u00ad", "").replace("\u00a0", " ")

        # Ограничиваем длину
        return " ".join(t.split())[:2000]

    def clean_response(content: str) -> str:
        """Очищает ответ модели от лишних префиксов."""
        content = content.strip()

        if content.startswith("**") and content.endswith("**"):
            lines = content.split("\n")
            if len(lines) >= 2 and lines[-1].strip() == "**":
                content = "\n".join(lines[1:-1])

        # Удаляем типичные префиксы
        for prefix in ["**", "Translation:", "Перевод:", "Result:"]:
            if content.lower().startswith(prefix.lower()):
                content = content[len(prefix) :].lstrip()
                break

        return content.strip()

    url = f"{base_url.rstrip('/')}/{LMSTUDIO_CHAT_PATH}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LMSTUDIO_API_KEY}",
    }

    results: Dict[int, str] = {}

    # Фильтруем пустые сегменты
    segs_nonempty = [s for s in segments if s.text.strip()]

    if not segs_nonempty:
        return results

    for s in segs_nonempty:
        clean_input = clean_text_input(s.text)

        if len(clean_input) <= 2 and not clean_input.isalnum():
            results[s.blockid] = clean_input  # Возвращаем как есть
            continue

            # ✅ Пропускаем только пунктуацию
        if all(c in "•·–—-()[]{}.,;:!?\"'" for c in clean_input):
            results[s.blockid] = clean_input
            continue

        if not clean_input:
            results[s.blockid] = ""
            continue

        # Адаптивный max_tokens
        word_count = len(clean_input.split())
        adaptive_max_tokens = max(DEFAULT_MAX_TOKENS, word_count * 4)

        # Для коротких фраз — более строгий промпт
        if word_count <= 3:  # Вместо <= 2
            system_prompt = (
                f"Translate from {src_lang} to {tgt_lang}. "
                f"IMPORTANT: Provide ONLY the direct translation. "
                f"Do NOT transliterate. Do NOT add explanations."
            )
            adaptive_temperature = 0.4  # Выше для разнообразия
            user_content = clean_input
        else:
            system_prompt = (
                f"Переведи текст с {src_lang} на {tgt_lang}. "
                f"Отвечай только переводом, без комментариев и пояснений."
            )
            adaptive_temperature = temperature
            user_content = clean_input

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": adaptive_temperature,
            "max_tokens": adaptive_max_tokens,
        }

        try:
            resp = HTTP.post(url, headers=headers, json=body, timeout=timeout)
            resp.raise_for_status()

            data = resp.json()
            if "choices" not in data or not data["choices"]:
                logging.warning(
                    f"Страница {pagenumber}, блок {s.blockid}: LM Studio вернул пустой ответ"
                )
                results[s.blockid] = clean_input
                continue

            content = data["choices"][0]["message"].get("content", "")
            translation = clean_response(content)

            # Если перевод пустой — используем оригинал
            results[s.blockid] = translation if translation else clean_input

        except Exception as e:
            logging.warning(f"Страница {pagenumber}, блок {s.blockid}: {e}")
            results[s.blockid] = clean_input

    return results
