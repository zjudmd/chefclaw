from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional


Language = str


@dataclass(frozen=True)
class IngredientProfile:
    canonical_name: str
    display_name_en: str
    display_name_zh: str
    category: str
    item_group: str
    freshness_type: str
    default_days: Optional[int]
    synonyms: tuple[str, ...] = ()


@dataclass
class ParsedIngredient:
    source_text: str
    raw_name: str
    canonical_name: str
    display_name_en: str
    display_name_zh: str
    quantity: Optional[float]
    unit: Optional[str]
    category: str
    item_group: str
    freshness_type: str
    checked_in_at: datetime
    expiration_date: Optional[date] = None
    recommended_use_by: Optional[date] = None
    uncertain: bool = False


@dataclass
class InventoryBatch:
    batch_id: int
    household_id: str
    canonical_name: str
    display_name_en: str
    display_name_zh: str
    quantity: Optional[float]
    unit: Optional[str]
    category: str
    item_group: str
    freshness_type: str
    checked_in_at: datetime
    expiration_date: Optional[date]
    recommended_use_by: Optional[date]
    uncertain: bool
    source_text: str

    @property
    def relevant_date(self) -> Optional[date]:
        return self.expiration_date or self.recommended_use_by


@dataclass
class InventorySummaryItem:
    canonical_name: str
    display_name_en: str
    display_name_zh: str
    category: str
    item_group: str
    freshness_type: str
    total_quantity: Optional[float]
    unit: Optional[str]
    uncertain: bool
    batch_count: int
    expires_on: Optional[date]
    expiring_soon: bool
    low_stock: bool = False


@dataclass(frozen=True)
class RecipeIngredient:
    name: str
    quantity: Optional[float]
    unit: Optional[str]
    optional: bool = False


@dataclass(frozen=True)
class MacroSummary:
    protein: str
    fiber: str
    fats: str


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    path: Path
    title: str
    title_translations: dict[str, str]
    language: str
    tags: list[str]
    proficiency: str
    source_type: str
    ingredients: list[RecipeIngredient]
    condiments: list[str]
    steps: list[dict[str, str]]
    macro_summary: MacroSummary
    search_hints: list[str] = field(default_factory=list)


@dataclass
class PlanSuggestion:
    recipe_id: str
    title: str
    source_type: str
    score: float
    missing_ingredients: list[str]
    uncertain_ingredients: list[str]
    required_condiments: list[str]
    missing_condiments: list[str]
    steps: list[str]
    macro_summary: dict[str, str]


@dataclass(frozen=True)
class PantryThreshold:
    canonical_name: str
    display_name_en: str
    display_name_zh: str
    threshold_quantity: Optional[float]
    unit: Optional[str]
    category: str


@dataclass
class AlertItem:
    canonical_name: str
    display_name_en: str
    display_name_zh: str
    due_date: Optional[date]
    severity: str
    reason: str


@dataclass
class SearchRequest:
    query: str
    language: str
    reason: str
    require_video: bool
    preferred_sites: list[str]
    expected_fields: list[str]
    ingredient_focus: list[str]
    search_hints: list[str]


@dataclass
class ServiceResult:
    status: str
    language: str
    response_markdown: str
    data: dict[str, Any]
