from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable, Optional

from .catalog import RECOGNIZED_UNITS, lookup_profile, normalize_unit
from .types import ParsedIngredient


DATE_PATTERN = re.compile(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})")
UNIT_PATTERN = "|".join(sorted(re.escape(unit) for unit in RECOGNIZED_UNITS))
QUANTITY_FIRST_PATTERN = re.compile(
    rf"^\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{UNIT_PATTERN})?\s*(?P<name>.+?)\s*$",
    re.IGNORECASE,
)
NAME_FIRST_PATTERN = re.compile(
    rf"^\s*(?P<name>.+?)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{UNIT_PATTERN})?\s*$",
    re.IGNORECASE,
)


def parse_date_token(value: str) -> Optional[date]:
    token = value.strip().replace("/", "-")
    try:
        return datetime.strptime(token, "%Y-%m-%d").date()
    except ValueError:
        return None


def split_segments(text: str) -> list[str]:
    segments = re.split(r"[\n,，;；]+", text)
    return [segment.strip() for segment in segments if segment.strip()]


def strip_expiration_markers(text: str) -> tuple[str, Optional[date]]:
    expiry = None
    match = DATE_PATTERN.search(text)
    cleaned = text
    if match:
        expiry = parse_date_token(match.group(1))
        cleaned = cleaned.replace(match.group(0), " ")
    cleaned = re.sub(
        r"\b(expires|expiry|exp|best before|use by)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.replace("到期", " ").replace("保质期", " ")
    return " ".join(cleaned.split()), expiry


def parse_segment(segment: str, checked_in_at: datetime) -> ParsedIngredient:
    base_text, expiry = strip_expiration_markers(segment)
    quantity = None
    unit = None
    raw_name = base_text

    quantity_match = QUANTITY_FIRST_PATTERN.match(base_text)
    if quantity_match:
        quantity = float(quantity_match.group("qty"))
        unit = normalize_unit(quantity_match.group("unit"))
        raw_name = quantity_match.group("name").strip()
    else:
        name_first_match = NAME_FIRST_PATTERN.match(base_text)
        if name_first_match:
            quantity = float(name_first_match.group("qty"))
            unit = normalize_unit(name_first_match.group("unit"))
            raw_name = name_first_match.group("name").strip()

    profile = lookup_profile(raw_name, unit)
    uncertain = quantity is None

    return ParsedIngredient(
        source_text=segment,
        raw_name=raw_name,
        canonical_name=profile.canonical_name,
        display_name_en=profile.display_name_en,
        display_name_zh=profile.display_name_zh,
        quantity=quantity,
        unit=unit,
        category=profile.category,
        item_group=profile.item_group,
        freshness_type=profile.freshness_type,
        checked_in_at=checked_in_at,
        expiration_date=expiry,
        recommended_use_by=None,
        uncertain=uncertain,
    )


def parse_checkin_text(
    text: str,
    checked_in_at: Optional[datetime] = None,
) -> list[ParsedIngredient]:
    timestamp = checked_in_at or datetime.utcnow()
    return [parse_segment(segment, timestamp) for segment in split_segments(text)]


def coerce_external_item(
    name: str,
    quantity: Optional[float],
    unit: Optional[str],
    checked_in_at: Optional[datetime],
    expiration_date: Optional[date],
) -> ParsedIngredient:
    parsed = parse_segment(name, checked_in_at or datetime.utcnow())
    parsed.quantity = quantity
    parsed.unit = normalize_unit(unit)
    parsed.expiration_date = expiration_date
    parsed.uncertain = quantity is None
    profile = lookup_profile(parsed.raw_name, parsed.unit)
    parsed.canonical_name = profile.canonical_name
    parsed.display_name_en = profile.display_name_en
    parsed.display_name_zh = profile.display_name_zh
    parsed.category = profile.category
    parsed.item_group = profile.item_group
    parsed.freshness_type = profile.freshness_type
    return parsed
