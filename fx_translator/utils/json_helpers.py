"""
Утилиты для работы с JSON.

Этот модуль содержит функции для извлечения и парсинга JSON из текста.
"""

from __future__ import annotations
from typing import List, Optional


def extract_first_json_like(s: str) -> str:
    """
    Извлекает первый JSON объект или массив из строки.

    Ищет первый символ { или [, затем отслеживает вложенность скобок,
    игнорируя содержимое строк, и возвращает найденный JSON.

    Args:
        s: Строка, содержащая JSON

    Returns:
        Извлечённая JSON строка

    Raises:
        ValueError: Если JSON объект или массив не найден
    """
    s = s.strip()

    # Удаляем префиксы (например, "json\\n{...}")
    if s.startswith("\\n"):
        nl = s.find("\\n")
        if nl != -1:
            s = s[nl + 1 :]

    # Удаляем закрывающие кавычки
    if s.endswith("```"):
        s = s[:-3].strip()

    # Удаляем префикс "json"
    if s.lower().startswith("json"):
        s = s[4:].lstrip()

    start: Optional[int] = None
    stack: List[str] = []
    in_str = False
    str_q: str = ""
    esc = False

    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\\\":
                esc = True
                continue
            if ch == str_q:
                in_str = False
                str_q = ""
                continue

        if ch == '"' or ch == "'":
            in_str = True
            str_q = ch
            continue

        if ch == "{" or ch == "[":
            if start is None:
                start = i
            stack.append(ch)
            continue

        if ch == "}" or ch == "]":
            if not stack:
                continue

            top = stack[-1]
            if (top == "{" and ch == "}") or (top == "[" and ch == "]"):
                stack.pop()
                if start is not None and not stack:
                    return s[start : i + 1]

    raise ValueError("JSON object or array not found in model response")


def extract_first_json_object(s: str) -> str:
    """
    Псевдоним для extract_first_json_like.

    Args:
        s: Строка, содержащая JSON

    Returns:
        Извлечённая JSON строка
    """
    return extract_first_json_like(s)
