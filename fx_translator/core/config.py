"""
Конфигурация приложения FX-Translator.

Этот модуль содержит все константы конфигурации и настройки окружения.
"""

import os
from typing import Optional


# ============================================================================
# HURIDOCS Configuration
# ============================================================================

DEFAULT_HURIDOCS_BASE = os.environ.get("HURIDOCS_BASE", "http://localhost:5060")
HURIDOCS_ANALYZE_PATH = os.environ.get("HURIDOCS_ANALYZE_PATH", "")
HURIDOCS_VISUALIZE_PATH = os.environ.get("HURIDOCS_VISUALIZE_PATH", "visualize")


# ============================================================================
# LM Studio Configuration
# ============================================================================

DEFAULT_LMSTUDIO_BASE = os.environ.get("DEFAULT_LMSTUDIO_BASE", "http://127.0.0.1:1234")
LMSTUDIO_CHAT_PATH = "v1/chat/completions"
LMSTUDIO_MODEL = os.environ.get("LMSTUDIO_MODEL", "google/gemma-3-4b")
LMSTUDIO_API_KEY = os.environ.get("LMS_API_KEY", "lm-studio")


# ============================================================================
# HTTP Configuration
# ============================================================================

MAX_RETRIES = 5
TIMEOUT = 180
BACKOFF_FACTOR = 0.8


# ============================================================================
# Text Processing Configuration
# ============================================================================

# Font size threshold для определения типа блока
FONT_SIZE_THRESHOLD = 1.3  # Для заголовков

# Threshold для слияния строк в блоки
LINE_MERGE_THRESHOLD = 3.0
PARAGRAPH_BREAK_THRESHOLD = 8.0
FONT_SIZE_VARIATION_THRESHOLD = 0.15

# Tolerance для выравнивания при merge сегментов
DEFAULT_XTOL = 4.0
DEFAULT_GAPTOL = 6.0
DEFAULT_YTOL = 4.0


# ============================================================================
# Layout Analysis Configuration
# ============================================================================

# Threshold для определения разворотов
SPREAD_RATIO_THRESHOLD = (1.25, 1.4)
CENTER_IMAGE_THRESHOLD = 0.33  # 33% от ширины страницы


# ============================================================================
# Translation Configuration
# ============================================================================

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TRANSLATION_TIMEOUT = 180


# ============================================================================
# Metrics Configuration
# ============================================================================

METRICS_PATH: Optional[str] = None


# ============================================================================
# GUI Configuration
# ============================================================================

# Docker configuration defaults
DEFAULT_HURIDOCS_IMAGE = "huridocs/pdf-segmenter:latest"
DEFAULT_HURIDOCS_PORT = 5060
DEFAULT_HURIDOCS_INTERNAL_PORT = 5060


# ============================================================================
# Color Configuration (for PDF annotations)
# ============================================================================

ACCENT_GREEN = (0.2, 0.8, 0.3)
ACCENT_GREEN_DARK = (0.15, 0.6, 0.2)
TEXT_DARK = (0.1, 0.1, 0.1)

# Big label configuration
BIG_LBL_BG = (0.00, 0.88, 0.30)
BIG_LBL_FG = TEXT_DARK
BIG_LBL_BR = ACCENT_GREEN_DARK
BIG_LBL_FS = 12.0
BIG_LBL_PAD = 4.0
BIG_LBL_MARG = 8.0
BIG_LBL_RND = 2.0


# ============================================================================
# Regex Patterns
# ============================================================================

# Patterns для определения типов блоков
HYPHEN_PATTERNS = [r"‐", r"‑"]
NOISE_PATTERNS = [r"^\\s*$", r"^[IVXLCDM\\.ivxlcdm]+$", r"^[a-zA-Z]$"]

# Bullet point и end punctuation patterns
BULLET_RE_PATTERN = r"^[•\\-–—]\\s"
END_PUNCT_RE_PATTERN = r"[.!?]$"

# Dropcap pattern
DROPCAP_HEAD_RE_PATTERN = r"^[A-Z][A-Z‐–—-]+"
