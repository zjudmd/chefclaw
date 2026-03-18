from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Optional


Language = str
LocaleCode = Literal["en", "zh-Hans"]
LocalizedTextMap = dict[str, str]


def _is_zh_locale(locale: str) -> bool:
    return str(locale).lower().startswith("zh")


@dataclass(frozen=True)
class LocalizationWarning:
    code: str
    message: str
    locale: Optional[LocaleCode] = None
    recipe_id: Optional[str] = None
    path: Optional[str] = None


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

    def display_name(self, locale: str) -> str:
        return self.display_name_zh if _is_zh_locale(locale) else self.display_name_en

    def aliases(self) -> tuple[str, ...]:
        return (
            self.canonical_name,
            self.display_name_en,
            self.display_name_zh,
            *self.synonyms,
        )


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

    def display_name(self, locale: str) -> str:
        return self.display_name_zh if _is_zh_locale(locale) else self.display_name_en


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

    def display_name(self, locale: str) -> str:
        return self.display_name_zh if _is_zh_locale(locale) else self.display_name_en


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

    def display_name(self, locale: str) -> str:
        return self.display_name_zh if _is_zh_locale(locale) else self.display_name_en


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
class LocalizedRecipeContent:
    title: str
    steps: list[str]


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    path: Path
    title: str
    title_translations: LocalizedTextMap
    language: str
    tags: list[str]
    proficiency: str
    source_type: str
    ingredients: list[RecipeIngredient]
    condiments: list[str]
    steps: list[LocalizedTextMap]
    macro_summary: MacroSummary
    search_hints: list[str] = field(default_factory=list)
    localization_warnings: list[LocalizationWarning] = field(default_factory=list)

    def supports_locale(self, locale: LocaleCode) -> bool:
        if not self.title_translations.get(locale):
            return False
        return all(step.get(locale) for step in self.steps)

    def localized_title(self, locale: LocaleCode) -> Optional[str]:
        return self.title_translations.get(locale)

    def localized_steps(self, locale: LocaleCode) -> Optional[list[str]]:
        if not self.supports_locale(locale):
            return None
        return [step[locale] for step in self.steps]


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

    def display_name(self, locale: str) -> str:
        return self.display_name_zh if _is_zh_locale(locale) else self.display_name_en


@dataclass
class AlertItem:
    canonical_name: str
    display_name_en: str
    display_name_zh: str
    due_date: Optional[date]
    severity: str
    reason: str

    def display_name(self, locale: str) -> str:
        return self.display_name_zh if _is_zh_locale(locale) else self.display_name_en


@dataclass
class SearchRequest:
    query: str
    locale: LocaleCode
    reason: str
    require_video: bool
    preferred_sites: list[str]
    expected_fields: list[str]
    ingredient_focus: list[str]
    search_hints: list[str]
    language: Optional[str] = None

    def __post_init__(self) -> None:
        if self.language is None:
            self.language = "zh" if self.locale == "zh-Hans" else "en"


@dataclass
class ServiceResult:
    status: str
    locale: LocaleCode
    response_markdown: str
    data: dict[str, Any]
    language: Optional[str] = None

    def __post_init__(self) -> None:
        if self.language is None:
            self.language = "zh" if self.locale == "zh-Hans" else "en"
