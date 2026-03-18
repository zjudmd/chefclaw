from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from .types import IngredientProfile, PantryThreshold


UNIT_ALIASES = {
    "pc": "piece",
    "pcs": "piece",
    "piece": "piece",
    "pieces": "piece",
    "个": "piece",
    "颗": "piece",
    "只": "piece",
    "bunch": "bunch",
    "把": "bunch",
    "bag": "bag",
    "袋": "bag",
    "box": "box",
    "盒": "box",
    "carton": "carton",
    "瓶": "bottle",
    "bottle": "bottle",
    "jar": "jar",
    "罐": "can",
    "can": "can",
    "pack": "pack",
    "packet": "pack",
    "包": "pack",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "克": "g",
    "kg": "kg",
    "公斤": "kg",
    "千克": "kg",
    "ml": "ml",
    "毫升": "ml",
    "l": "l",
    "升": "l",
}

RECOGNIZED_UNITS = set(UNIT_ALIASES)
PACKAGED_UNITS = {"bag", "box", "carton", "bottle", "can", "pack", "jar"}

INGREDIENT_PROFILES = [
    IngredientProfile(
        canonical_name="tomato",
        display_name_en="Tomato",
        display_name_zh="西红柿",
        category="produce",
        item_group="vegetable",
        freshness_type="fresh",
        default_days=5,
        synonyms=("tomatoes", "番茄"),
    ),
    IngredientProfile(
        canonical_name="spinach",
        display_name_en="Spinach",
        display_name_zh="菠菜",
        category="produce",
        item_group="leafy_green",
        freshness_type="fresh",
        default_days=4,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="bok choy",
        display_name_en="Bok Choy",
        display_name_zh="青江菜",
        category="produce",
        item_group="leafy_green",
        freshness_type="fresh",
        default_days=4,
        synonyms=("上海青",),
    ),
    IngredientProfile(
        canonical_name="broccoli",
        display_name_en="Broccoli",
        display_name_zh="西兰花",
        category="produce",
        item_group="vegetable",
        freshness_type="fresh",
        default_days=5,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="mushroom",
        display_name_en="Mushroom",
        display_name_zh="蘑菇",
        category="produce",
        item_group="vegetable",
        freshness_type="fresh",
        default_days=5,
        synonyms=("mushrooms",),
    ),
    IngredientProfile(
        canonical_name="cucumber",
        display_name_en="Cucumber",
        display_name_zh="黄瓜",
        category="produce",
        item_group="vegetable",
        freshness_type="fresh",
        default_days=6,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="garlic",
        display_name_en="Garlic",
        display_name_zh="大蒜",
        category="produce",
        item_group="aromatic",
        freshness_type="fresh",
        default_days=14,
        synonyms=("蒜",),
    ),
    IngredientProfile(
        canonical_name="scallion",
        display_name_en="Scallion",
        display_name_zh="葱",
        category="produce",
        item_group="aromatic",
        freshness_type="fresh",
        default_days=7,
        synonyms=("green onion", "葱花"),
    ),
    IngredientProfile(
        canonical_name="chicken breast",
        display_name_en="Chicken Breast",
        display_name_zh="鸡胸肉",
        category="protein",
        item_group="meat",
        freshness_type="fresh",
        default_days=2,
        synonyms=("chicken", "鸡肉"),
    ),
    IngredientProfile(
        canonical_name="beef",
        display_name_en="Beef",
        display_name_zh="牛肉",
        category="protein",
        item_group="meat",
        freshness_type="fresh",
        default_days=3,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="salmon",
        display_name_en="Salmon",
        display_name_zh="三文鱼",
        category="protein",
        item_group="seafood",
        freshness_type="fresh",
        default_days=2,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="shrimp",
        display_name_en="Shrimp",
        display_name_zh="虾",
        category="protein",
        item_group="seafood",
        freshness_type="fresh",
        default_days=2,
        synonyms=("prawn",),
    ),
    IngredientProfile(
        canonical_name="egg",
        display_name_en="Egg",
        display_name_zh="鸡蛋",
        category="protein",
        item_group="protein",
        freshness_type="packaged",
        default_days=None,
        synonyms=("eggs",),
    ),
    IngredientProfile(
        canonical_name="milk",
        display_name_en="Milk",
        display_name_zh="牛奶",
        category="dairy",
        item_group="dairy",
        freshness_type="packaged",
        default_days=None,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="yogurt",
        display_name_en="Yogurt",
        display_name_zh="酸奶",
        category="dairy",
        item_group="dairy",
        freshness_type="packaged",
        default_days=None,
        synonyms=("yoghurt",),
    ),
    IngredientProfile(
        canonical_name="tofu",
        display_name_en="Tofu",
        display_name_zh="豆腐",
        category="protein",
        item_group="protein",
        freshness_type="packaged",
        default_days=None,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="rice",
        display_name_en="Rice",
        display_name_zh="大米",
        category="staple",
        item_group="grain",
        freshness_type="packaged",
        default_days=None,
        synonyms=("米饭", "米"),
    ),
    IngredientProfile(
        canonical_name="soy sauce",
        display_name_en="Soy Sauce",
        display_name_zh="酱油",
        category="condiment",
        item_group="condiment",
        freshness_type="packaged",
        default_days=None,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="cooking oil",
        display_name_en="Cooking Oil",
        display_name_zh="食用油",
        category="condiment",
        item_group="condiment",
        freshness_type="packaged",
        default_days=None,
        synonyms=("oil", "植物油"),
    ),
    IngredientProfile(
        canonical_name="salt",
        display_name_en="Salt",
        display_name_zh="盐",
        category="condiment",
        item_group="condiment",
        freshness_type="packaged",
        default_days=None,
        synonyms=(),
    ),
    IngredientProfile(
        canonical_name="black pepper",
        display_name_en="Black Pepper",
        display_name_zh="黑胡椒",
        category="condiment",
        item_group="condiment",
        freshness_type="packaged",
        default_days=None,
        synonyms=("pepper",),
    ),
    IngredientProfile(
        canonical_name="sesame oil",
        display_name_en="Sesame Oil",
        display_name_zh="香油",
        category="condiment",
        item_group="condiment",
        freshness_type="packaged",
        default_days=None,
        synonyms=("麻油",),
    ),
]

DEFAULT_PROFILE = IngredientProfile(
    canonical_name="unknown",
    display_name_en="Unknown Ingredient",
    display_name_zh="未知食材",
    category="unknown",
    item_group="unknown",
    freshness_type="unknown",
    default_days=None,
    synonyms=(),
)

PROFILE_INDEX: dict[str, IngredientProfile] = {}
for profile in INGREDIENT_PROFILES:
    PROFILE_INDEX[profile.canonical_name.lower()] = profile
    PROFILE_INDEX[profile.display_name_en.lower()] = profile
    PROFILE_INDEX[profile.display_name_zh.lower()] = profile
    for synonym in profile.synonyms:
        PROFILE_INDEX[synonym.lower()] = profile

DEFAULT_PANTRY_THRESHOLDS = [
    PantryThreshold("milk", "Milk", "牛奶", 1, "carton", "dairy"),
    PantryThreshold("egg", "Egg", "鸡蛋", 6, "piece", "protein"),
    PantryThreshold("rice", "Rice", "大米", 1, "kg", "staple"),
    PantryThreshold("soy sauce", "Soy Sauce", "酱油", 1, "bottle", "condiment"),
    PantryThreshold("cooking oil", "Cooking Oil", "食用油", 1, "bottle", "condiment"),
    PantryThreshold("salt", "Salt", "盐", 1, "pack", "condiment"),
]


def normalize_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    return UNIT_ALIASES.get(unit.strip().lower(), unit.strip().lower())


def singularize_english(name: str) -> str:
    if name.endswith("oes"):
        return name[:-2]
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def lookup_profile(raw_name: str, unit: Optional[str] = None) -> IngredientProfile:
    cleaned = " ".join(raw_name.strip().lower().split())
    if not cleaned:
        return DEFAULT_PROFILE
    if cleaned in PROFILE_INDEX:
        return PROFILE_INDEX[cleaned]
    singular = singularize_english(cleaned)
    if singular in PROFILE_INDEX:
        return PROFILE_INDEX[singular]
    normalized_unit = normalize_unit(unit)
    if normalized_unit in PACKAGED_UNITS:
        return IngredientProfile(
            canonical_name=cleaned,
            display_name_en=cleaned.title(),
            display_name_zh=cleaned,
            category="unknown",
            item_group="unknown",
            freshness_type="packaged",
            default_days=None,
            synonyms=(),
        )
    return IngredientProfile(
        canonical_name=cleaned,
        display_name_en=cleaned.title(),
        display_name_zh=cleaned,
        category="unknown",
        item_group="unknown",
        freshness_type="fresh" if normalized_unit in {"piece", "bunch", "g", "kg"} else "unknown",
        default_days=4 if normalized_unit in {"piece", "bunch"} else None,
        synonyms=(),
    )


def get_threshold_payloads() -> list[dict[str, object]]:
    return [asdict(item) for item in DEFAULT_PANTRY_THRESHOLDS]


def profile_aliases(profile: IngredientProfile) -> tuple[str, ...]:
    seen: set[str] = set()
    aliases: list[str] = []
    for alias in profile.aliases():
        normalized = alias.strip().lower()
        if not normalized or normalized in seen:
            continue
        aliases.append(normalized)
        seen.add(normalized)
    return tuple(aliases)


def find_profile_mentioned(text: str) -> Optional[IngredientProfile]:
    normalized = text.lower()
    for profile in INGREDIENT_PROFILES:
        if any(alias in normalized for alias in profile_aliases(profile)):
            return profile
    return None
