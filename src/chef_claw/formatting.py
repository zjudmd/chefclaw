from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from .i18n import (
    bulletize,
    format_date,
    format_quantity,
    localize_name,
    resolve_locale,
    stock_label as localized_stock_label,
)


def is_zh(language: str) -> bool:
    return resolve_locale(language) == "zh-Hans"


def display_name(obj: object, language: str) -> str:
    return localize_name(obj, resolve_locale(language))


def stock_label(
    uncertain: bool,
    quantity: Optional[float],
    unit: Optional[str],
    language: str,
) -> str:
    return localized_stock_label(resolve_locale(language), uncertain, quantity, unit)
