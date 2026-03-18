from __future__ import annotations

from datetime import date
from typing import Iterable, Optional


def is_zh(language: str) -> bool:
    return language.lower().startswith("zh")


def display_name(obj: object, language: str) -> str:
    if is_zh(language):
        return getattr(obj, "display_name_zh", None) or getattr(obj, "display_name_en", "")
    return getattr(obj, "display_name_en", None) or getattr(obj, "display_name_zh", "")


def format_quantity(quantity: Optional[float], unit: Optional[str]) -> str:
    if quantity is None:
        return "unknown" if unit is None else f"unknown {unit}"
    if float(quantity).is_integer():
        quantity_text = str(int(quantity))
    else:
        quantity_text = f"{quantity:.1f}".rstrip("0").rstrip(".")
    return quantity_text if not unit else f"{quantity_text} {unit}"


def format_date(value: Optional[date]) -> str:
    return value.isoformat() if value else "-"


def bulletize(lines: Iterable[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def stock_label(uncertain: bool, quantity: Optional[float], unit: Optional[str], language: str) -> str:
    if uncertain:
        return "数量待确认" if is_zh(language) else "quantity needs checking"
    return format_quantity(quantity, unit)
