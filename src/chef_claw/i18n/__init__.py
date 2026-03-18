from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Optional

from ..types import LocalizedRecipeContent, LocalizationWarning, LocaleCode, Recipe


DEFAULT_LOCALE: LocaleCode = "en"
SUPPORTED_LOCALES: tuple[LocaleCode, ...] = ("en", "zh-Hans")
LEGACY_LANGUAGE_BY_LOCALE: dict[LocaleCode, str] = {"en": "en", "zh-Hans": "zh"}

MESSAGES: dict[LocaleCode, dict[str, str]] = {
    "en": {
        "alerts.expiry_reason": "Use by {date}.",
        "alerts.no_expiry": "No upcoming expiry alerts.",
        "alerts.no_restock": "No staples need restocking.",
        "alerts.restock_reason": "Below the restock threshold of {threshold}.",
        "checkin.follow_up_header": "Need expiration dates for:",
        "checkin.packaged_follow_up": "Please provide the expiration date for the {item_name}.",
        "checkin.recorded_count": "Recorded {count} inventory item(s).",
        "fallback.default_reason": "Local recipes are insufficient.",
        "fallback.line": "OpenClaw should run an online search for a recipe with a video tutorial.",
        "inventory.header": "Current inventory",
        "inventory.item_line": "{name}: {quantity}",
        "inventory.item_line_with_date": "{name}: {quantity} | use by {date}",
        "inventory.no_filter_match": "No inventory matched the filter.",
        "inventory.no_match": "No matching inventory found.",
        "macro.fats": "fats",
        "macro.fiber": "fiber",
        "macro.high": "high",
        "macro.low": "low",
        "macro.medium": "medium",
        "macro.protein": "protein",
        "plan.day.grocery": "Grocery add-ons: {items}",
        "plan.day.missing_condiments": "Missing condiments: {items}",
        "plan.day.no_local_match": "Current local recipes are a weak match. Online video search is needed.",
        "plan.day.recipe_line": "{title}: protein {protein} / fiber {fiber} / fats {fats}",
        "plan.day.snacks": "Snack ideas: {items}",
        "query.buy_no": "no need to buy yet",
        "query.buy_yes": "buy more soon",
        "query.not_confirmed": "not confirmed in stock",
        "recipes.created": "Created recipe: {title}",
        "recipes.list_line": "{title}",
        "recipes.list_line_with_tags": "{title}: {tags}",
        "recipes.none": "No recipes matched the filter.",
        "recipes.reload": "Reloaded {count} recipe(s); {warnings} localization warning(s).",
        "search.query.default_focus": "available ingredients",
        "search.query.template": "easy home recipe video using {focus}",
        "search.hint.home_style": "prioritize home-style recipes",
        "search.hint.video": "include a concise video tutorial link",
        "snack.apple": "apple slices",
        "snack.apple_nuts": "apple slices + nuts",
        "snack.cucumber": "cucumber sticks",
        "snack.nuts": "a handful of mixed nuts",
        "snack.yogurt": "plain yogurt",
        "stock.unknown_quantity": "quantity needs checking",
        "weekend.no_extra_groceries": "No extra groceries needed yet.",
        "weekend.no_prep_match": "No strong local prep match yet.",
        "weekend.next_week_groceries": "Next-week groceries: {items}",
        "weekend.prep_ideas": "Prep ideas: {items}",
        "weekend.regular_rotation": "Weekend prep can follow the regular rotation.",
        "weekend.use_first": "Use first this weekend: {items}",
    },
    "zh-Hans": {
        "alerts.expiry_reason": "请在 {date} 前使用。",
        "alerts.no_expiry": "暂无临期食材。",
        "alerts.no_restock": "暂无需要补货的常备品。",
        "alerts.restock_reason": "当前低于补货线 {threshold}。",
        "checkin.follow_up_header": "还需要补充以下到期日期：",
        "checkin.packaged_follow_up": "请提供 {item_name} 的到期日期。",
        "checkin.recorded_count": "已记录 {count} 项库存。",
        "fallback.default_reason": "本地菜谱不足。",
        "fallback.line": "需要 OpenClaw 联网搜索带视频教程的新菜谱。",
        "inventory.header": "当前库存",
        "inventory.item_line": "{name}: {quantity}",
        "inventory.item_line_with_date": "{name}: {quantity} | 最晚 {date} 前使用",
        "inventory.no_filter_match": "暂无符合条件的库存。",
        "inventory.no_match": "没有找到符合条件的库存。",
        "macro.fats": "脂肪",
        "macro.fiber": "纤维",
        "macro.high": "高",
        "macro.low": "低",
        "macro.medium": "中",
        "macro.protein": "蛋白质",
        "plan.day.grocery": "待采购: {items}",
        "plan.day.missing_condiments": "缺少调味料: {items}",
        "plan.day.no_local_match": "当前本地菜谱匹配度不足，需要联网搜索新菜视频。",
        "plan.day.recipe_line": "{title}: 蛋白质 {protein} / 纤维 {fiber} / 脂肪 {fats}",
        "plan.day.snacks": "加餐建议: {items}",
        "query.buy_no": "暂时不用买",
        "query.buy_yes": "建议购买",
        "query.not_confirmed": "当前没有确认库存",
        "recipes.created": "已创建菜谱: {title}",
        "recipes.list_line": "{title}",
        "recipes.list_line_with_tags": "{title}: {tags}",
        "recipes.none": "没有匹配的菜谱。",
        "recipes.reload": "已重新加载 {count} 个菜谱，发现 {warnings} 个本地化警告。",
        "search.query.default_focus": "家常菜",
        "search.query.template": "{focus} 家常做法 视频",
        "search.hint.home_style": "优先选择家常做法",
        "search.hint.video": "附带简洁视频教程链接",
        "snack.apple": "苹果片",
        "snack.apple_nuts": "苹果 + 坚果",
        "snack.cucumber": "黄瓜条",
        "snack.nuts": "一小把坚果",
        "snack.yogurt": "无糖酸奶",
        "stock.unknown_quantity": "数量待确认",
        "weekend.no_extra_groceries": "下周暂无新增采购项。",
        "weekend.no_prep_match": "暂无强匹配菜谱。",
        "weekend.next_week_groceries": "下周采购清单: {items}",
        "weekend.prep_ideas": "备餐建议: {items}",
        "weekend.regular_rotation": "周末可按常规备餐。",
        "weekend.use_first": "周末优先处理: {items}",
    },
}

PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def resolve_locale(raw: Optional[str]) -> LocaleCode:
    if not raw:
        return DEFAULT_LOCALE
    token = raw.strip().lower()
    if token.startswith("zh"):
        return "zh-Hans"
    return "en"


def legacy_language(locale: LocaleCode) -> str:
    return LEGACY_LANGUAGE_BY_LOCALE[locale]


def t(locale: LocaleCode, key: str, **params: object) -> str:
    return MESSAGES[locale][key].format(**params)


def message_placeholders(locale: LocaleCode, key: str) -> set[str]:
    return set(PLACEHOLDER_PATTERN.findall(MESSAGES[locale][key]))


def bulletize(lines: Iterable[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def join_display_list(locale: LocaleCode, items: Iterable[str]) -> str:
    values = [item for item in items if item]
    separator = "、" if locale == "zh-Hans" else ", "
    return separator.join(values)


def format_date(value: Optional[date]) -> str:
    return value.isoformat() if value else "-"


def format_quantity(quantity: Optional[float], unit: Optional[str]) -> str:
    if quantity is None:
        return "unknown" if unit is None else f"unknown {unit}"
    if float(quantity).is_integer():
        quantity_text = str(int(quantity))
    else:
        quantity_text = f"{quantity:.1f}".rstrip("0").rstrip(".")
    return quantity_text if not unit else f"{quantity_text} {unit}"


def stock_label(
    locale: LocaleCode,
    uncertain: bool,
    quantity: Optional[float],
    unit: Optional[str],
) -> str:
    if uncertain:
        return t(locale, "stock.unknown_quantity")
    return format_quantity(quantity, unit)


def localize_name(obj: object, locale: LocaleCode) -> str:
    if hasattr(obj, "display_name") and callable(getattr(obj, "display_name")):
        return getattr(obj, "display_name")(locale)
    if locale == "zh-Hans":
        return getattr(obj, "display_name_zh", None) or getattr(obj, "display_name_en", "")
    return getattr(obj, "display_name_en", None) or getattr(obj, "display_name_zh", "")


def macro_label(locale: LocaleCode, value: str) -> str:
    return t(locale, f"macro.{value}")


def localize_recipe(
    recipe: Recipe,
    locale: LocaleCode,
) -> tuple[Optional[LocalizedRecipeContent], list[LocalizationWarning]]:
    warnings = [
        warning
        for warning in recipe.localization_warnings
        if warning.locale in (None, locale)
    ]
    if not recipe.supports_locale(locale):
        return None, warnings
    return (
        LocalizedRecipeContent(
            title=recipe.localized_title(locale) or recipe.title,
            steps=recipe.localized_steps(locale) or [],
        ),
        warnings,
    )


def build_search_query(locale: LocaleCode, focus_items: list[str]) -> str:
    focus = join_display_list(locale, focus_items) or t(locale, "search.query.default_focus")
    return t(locale, "search.query.template", focus=focus)


def default_search_hints(locale: LocaleCode) -> list[str]:
    return [
        t(locale, "search.hint.home_style"),
        t(locale, "search.hint.video"),
    ]
