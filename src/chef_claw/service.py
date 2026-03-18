from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .catalog import DEFAULT_PANTRY_THRESHOLDS, INGREDIENT_PROFILES, lookup_profile
from .config import Settings, get_settings
from .db import Database
from .formatting import bulletize, display_name, format_date, format_quantity, is_zh, stock_label
from .parser import coerce_external_item, parse_checkin_text
from .recipes import RecipeRepository
from .types import (
    AlertItem,
    InventoryBatch,
    InventorySummaryItem,
    PantryThreshold,
    PlanSuggestion,
    Recipe,
    SearchRequest,
    ServiceResult,
)


class KitchenService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db = Database(self.settings.database_path)
        self.recipe_repository = RecipeRepository(self.settings.recipes_dir)
        self._sync_thresholds()
        self.db.replace_recipe_cache(self.recipe_repository.recipes)

    def _sync_thresholds(self) -> None:
        thresholds_path = self.settings.pantry_thresholds_path
        thresholds_path.parent.mkdir(parents=True, exist_ok=True)
        if thresholds_path.exists():
            payload = json.loads(thresholds_path.read_text(encoding="utf-8"))
            thresholds = [PantryThreshold(**item) for item in payload]
        else:
            thresholds = list(DEFAULT_PANTRY_THRESHOLDS)
        self.db.replace_thresholds(thresholds)

    def _language(self, language: str) -> str:
        return "zh" if is_zh(language) else "en"

    def _today(self) -> date:
        return date.today()

    def _name(self, obj: object, language: str) -> str:
        return display_name(obj, self._language(language))

    def _compute_recommended_use_by(self, item_name: str, freshness_type: str, checked_in_at: datetime) -> Optional[date]:
        profile = lookup_profile(item_name)
        if freshness_type != "fresh" or profile.default_days is None:
            return None
        return (checked_in_at + timedelta(days=profile.default_days)).date()

    def _packaged_follow_up(self, item_name: str, language: str) -> str:
        if self._language(language) == "zh":
            return f"请提供 {item_name} 的到期日期。"
        return f"Please provide the expiration date for the {item_name}."

    def _serialize_batch(self, batch: InventoryBatch, language: str) -> dict[str, object]:
        return {
            "batch_id": batch.batch_id,
            "name": self._name(batch, language),
            "canonical_name": batch.canonical_name,
            "quantity": batch.quantity,
            "unit": batch.unit,
            "quantity_label": stock_label(batch.uncertain, batch.quantity, batch.unit, language),
            "category": batch.category,
            "item_group": batch.item_group,
            "freshness_type": batch.freshness_type,
            "checked_in_at": batch.checked_in_at.isoformat(),
            "expiration_date": format_date(batch.expiration_date),
            "recommended_use_by": format_date(batch.recommended_use_by),
            "uncertain": batch.uncertain,
        }

    def _batches_to_summary(
        self,
        household_id: str,
        language: str,
        category: Optional[str] = None,
        expiring_within_days: Optional[int] = None,
        only_available: bool = True,
    ) -> list[InventorySummaryItem]:
        today = self._today()
        summary: dict[str, InventorySummaryItem] = {}
        for batch in self.db.list_batches(household_id):
            relevant_date = batch.relevant_date
            if only_available and relevant_date and relevant_date < today:
                continue
            if category and batch.category != category and batch.item_group != category:
                continue
            existing = summary.get(batch.canonical_name)
            if not existing:
                existing = InventorySummaryItem(
                    canonical_name=batch.canonical_name,
                    display_name_en=batch.display_name_en,
                    display_name_zh=batch.display_name_zh,
                    category=batch.category,
                    item_group=batch.item_group,
                    freshness_type=batch.freshness_type,
                    total_quantity=batch.quantity,
                    unit=batch.unit,
                    uncertain=batch.uncertain,
                    batch_count=1,
                    expires_on=relevant_date,
                    expiring_soon=False,
                )
                summary[batch.canonical_name] = existing
            else:
                existing.batch_count += 1
                existing.uncertain = existing.uncertain or batch.uncertain
                if existing.unit != batch.unit:
                    existing.total_quantity = None
                    existing.unit = None
                elif existing.total_quantity is not None and batch.quantity is not None:
                    existing.total_quantity += batch.quantity
                else:
                    existing.total_quantity = None
                if relevant_date and (
                    existing.expires_on is None or relevant_date < existing.expires_on
                ):
                    existing.expires_on = relevant_date

        items = list(summary.values())
        threshold_map = {
            threshold.canonical_name: threshold for threshold in self.db.list_thresholds()
        }
        for item in items:
            if expiring_within_days is not None and item.expires_on:
                item.expiring_soon = item.expires_on <= today + timedelta(days=expiring_within_days)
            elif item.expires_on:
                item.expiring_soon = item.expires_on <= today + timedelta(days=2)
            threshold = threshold_map.get(item.canonical_name)
            if threshold and threshold.unit == item.unit and item.total_quantity is not None:
                item.low_stock = item.total_quantity <= (threshold.threshold_quantity or 0)

        items.sort(key=lambda entry: (entry.expires_on or date.max, entry.canonical_name))
        return items

    def _summary_to_payload(self, item: InventorySummaryItem, language: str) -> dict[str, object]:
        return {
            "name": self._name(item, language),
            "canonical_name": item.canonical_name,
            "category": item.category,
            "item_group": item.item_group,
            "freshness_type": item.freshness_type,
            "quantity": item.total_quantity,
            "unit": item.unit,
            "quantity_label": stock_label(item.uncertain, item.total_quantity, item.unit, language),
            "uncertain": item.uncertain,
            "batch_count": item.batch_count,
            "expires_on": format_date(item.expires_on),
            "expiring_soon": item.expiring_soon,
            "low_stock": item.low_stock,
        }

    def _ingredient_available(self, recipe_item_name: str, inventory_map: dict[str, InventorySummaryItem]) -> tuple[bool, bool, Optional[InventorySummaryItem]]:
        profile = lookup_profile(recipe_item_name)
        item = inventory_map.get(profile.canonical_name)
        if not item:
            return False, False, None
        if item.uncertain or item.total_quantity is None:
            return False, True, item
        return item.total_quantity > 0, False, item

    def _localized_recipe_title(self, recipe: Recipe, language: str) -> str:
        lang = self._language(language)
        return recipe.title_translations.get(lang, recipe.title)

    def _localized_steps(self, recipe: Recipe, language: str) -> list[str]:
        lang = self._language(language)
        steps: list[str] = []
        for step in recipe.steps:
            steps.append(step.get(lang) or step.get("en") or next(iter(step.values())))
        return steps

    def _build_suggestion(
        self,
        recipe: Recipe,
        inventory_map: dict[str, InventorySummaryItem],
        language: str,
    ) -> tuple[PlanSuggestion, float, float]:
        missing: list[str] = []
        uncertain: list[str] = []
        matched = 0
        expiring_bonus = 0
        required_count = 0

        for ingredient in recipe.ingredients:
            if ingredient.optional:
                continue
            required_count += 1
            available, is_uncertain, inventory_item = self._ingredient_available(
                ingredient.name, inventory_map
            )
            ingredient_profile = lookup_profile(ingredient.name)
            ingredient_name = (
                ingredient_profile.display_name_zh
                if self._language(language) == "zh"
                else ingredient_profile.display_name_en
            )
            if available:
                matched += 1
                if inventory_item and inventory_item.expiring_soon:
                    expiring_bonus += 1
            elif is_uncertain:
                uncertain.append(ingredient_name)
            else:
                missing.append(ingredient_name)

        missing_condiments: list[str] = []
        for condiment_name in recipe.condiments:
            available, is_uncertain, _ = self._ingredient_available(condiment_name, inventory_map)
            condiment_profile = lookup_profile(condiment_name)
            label = (
                condiment_profile.display_name_zh
                if self._language(language) == "zh"
                else condiment_profile.display_name_en
            )
            if not available or is_uncertain:
                missing_condiments.append(label)

        coverage = matched / required_count if required_count else 1.0
        score = (
            (40 if recipe.source_type == "personal" else 0)
            + (10 if recipe.proficiency == "established" else 0)
            + coverage * 50
            + expiring_bonus * 6
            - len(missing) * 18
            - len(uncertain) * 8
            - len(missing_condiments) * 6
        )

        suggestion = PlanSuggestion(
            recipe_id=recipe.recipe_id,
            title=self._localized_recipe_title(recipe, language),
            source_type=recipe.source_type,
            score=round(score, 1),
            missing_ingredients=missing,
            uncertain_ingredients=uncertain,
            required_condiments=[
                lookup_profile(name).display_name_zh
                if self._language(language) == "zh"
                else lookup_profile(name).display_name_en
                for name in recipe.condiments
            ],
            missing_condiments=missing_condiments,
            steps=self._localized_steps(recipe, language),
            macro_summary=asdict(recipe.macro_summary),
        )
        return suggestion, coverage, score

    def _rank_recipes(
        self,
        household_id: str,
        language: str,
        limit: int = 2,
    ) -> tuple[list[PlanSuggestion], list[InventorySummaryItem], list[tuple[Recipe, float, float]]]:
        inventory = self._batches_to_summary(household_id, language)
        inventory_map = {item.canonical_name: item for item in inventory}
        ranked: list[tuple[Recipe, PlanSuggestion, float, float]] = []
        for recipe in self.recipe_repository.recipes:
            suggestion, coverage, score = self._build_suggestion(recipe, inventory_map, language)
            ranked.append((recipe, suggestion, coverage, score))
        ranked.sort(key=lambda item: (item[2] >= 0.6, item[3], item[0].source_type == "personal"), reverse=True)
        suggestions = [item[1] for item in ranked[:limit]]
        return suggestions, inventory, [(item[0], item[2], item[3]) for item in ranked]

    def _snack_suggestions(self, suggestions: list[PlanSuggestion], language: str) -> list[str]:
        if not suggestions:
            return ["苹果 + 坚果" if self._language(language) == "zh" else "apple slices + nuts"]
        highest = suggestions[0].macro_summary
        snacks: list[str] = []
        if highest["protein"] == "low":
            snacks.append("无糖酸奶" if self._language(language) == "zh" else "plain yogurt")
        if highest["fiber"] in {"low", "medium"}:
            snacks.append("苹果片" if self._language(language) == "zh" else "apple slices")
        if highest["fats"] == "low":
            snacks.append("一小把坚果" if self._language(language) == "zh" else "a handful of mixed nuts")
        return snacks or (["黄瓜条" if self._language(language) == "zh" else "cucumber sticks"])

    def _grocery_items(self, suggestions: list[PlanSuggestion]) -> list[str]:
        items: list[str] = []
        for suggestion in suggestions:
            items.extend(suggestion.missing_ingredients)
            items.extend(suggestion.missing_condiments)
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            if item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped

    def _fallback_request(
        self,
        household_id: str,
        language: str,
        reason: str,
        preferred_ingredients: Optional[list[str]] = None,
    ) -> SearchRequest:
        inventory = self._batches_to_summary(household_id, language, expiring_within_days=3)
        focus = preferred_ingredients or [
            self._name(item, language)
            for item in inventory
            if item.expiring_soon
        ][:3]
        if not focus:
            focus = [self._name(item, language) for item in inventory[:3]]
        lang = self._language(language)
        if lang == "zh":
            query = f"{' '.join(focus or ['家常菜'])} 家常做法 视频"
        else:
            query = f"easy home recipe video using {' '.join(focus or ['available ingredients'])}"
        return SearchRequest(
            query=query.strip(),
            language=lang,
            reason=reason,
            require_video=True,
            preferred_sites=["YouTube", "Bilibili"],
            expected_fields=["title", "video_url", "source_url", "ingredients", "steps_summary"],
            ingredient_focus=focus,
            search_hints=["prioritize home-style recipes", "include a concise video tutorial link"],
        )

    def checkin(
        self,
        text: str,
        language: str = "en",
        household_id: str = "default",
        checked_in_at: Optional[datetime] = None,
        parsed_items: Optional[list[dict[str, object]]] = None,
    ) -> ServiceResult:
        timestamp = checked_in_at or datetime.utcnow()
        items = (
            [
                coerce_external_item(
                    str(item["name"]),
                    item.get("quantity"),
                    item.get("unit"),
                    timestamp,
                    item.get("expiration_date"),
                )
                for item in (parsed_items or [])
            ]
            if parsed_items
            else parse_checkin_text(text, timestamp)
        )

        recorded: list[dict[str, object]] = []
        follow_ups: list[dict[str, str]] = []

        for item in items:
            if item.freshness_type == "packaged" and item.expiration_date is None:
                follow_ups.append(
                    {
                        "item_name": self._name(item, language),
                        "question": self._packaged_follow_up(self._name(item, language), language),
                    }
                )
                continue
            if item.freshness_type == "fresh" and item.expiration_date is None:
                item.recommended_use_by = self._compute_recommended_use_by(
                    item.canonical_name,
                    item.freshness_type,
                    item.checked_in_at,
                )
            batch_id = self.db.insert_batch(item, household_id)
            self.db.record_event(
                household_id,
                "checkin",
                item.canonical_name,
                {
                    "batch_id": batch_id,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "expiration_date": format_date(item.expiration_date),
                    "recommended_use_by": format_date(item.recommended_use_by),
                },
            )
            batch = next(
                batch
                for batch in self.db.list_batches(household_id)
                if batch.batch_id == batch_id
            )
            recorded.append(self._serialize_batch(batch, language))

        status = "needs_user_input" if follow_ups else "ok"
        if self._language(language) == "zh":
            lines = []
            if recorded:
                lines.append(f"已记录 {len(recorded)} 项库存。")
            if follow_ups:
                lines.append("还需要补充以下到期日期：")
                lines.extend(question["question"] for question in follow_ups)
        else:
            lines = []
            if recorded:
                lines.append(f"Recorded {len(recorded)} inventory item(s).")
            if follow_ups:
                lines.append("Need expiration dates for:")
                lines.extend(question["question"] for question in follow_ups)

        return ServiceResult(
            status=status,
            language=self._language(language),
            response_markdown=bulletize(lines) if lines else "",
            data={
                "recorded_items": recorded,
                "follow_up_questions": follow_ups,
            },
        )

    def get_inventory(
        self,
        language: str = "en",
        household_id: str = "default",
        category: Optional[str] = None,
        expiring_within_days: Optional[int] = None,
        only_available: bool = True,
    ) -> ServiceResult:
        items = self._batches_to_summary(
            household_id=household_id,
            language=language,
            category=category,
            expiring_within_days=expiring_within_days,
            only_available=only_available,
        )
        if self._language(language) == "zh":
            header = "当前库存"
            lines = [
                f"{self._name(item, language)}: {stock_label(item.uncertain, item.total_quantity, item.unit, language)}"
                + (f" | 最晚 {format_date(item.expires_on)} 前使用" if item.expires_on else "")
                for item in items
            ] or ["暂无符合条件的库存。"]
        else:
            header = "Current inventory"
            lines = [
                f"{self._name(item, language)}: {stock_label(item.uncertain, item.total_quantity, item.unit, language)}"
                + (f" | use by {format_date(item.expires_on)}" if item.expires_on else "")
                for item in items
            ] or ["No inventory matched the filter."]
        return ServiceResult(
            status="ok",
            language=self._language(language),
            response_markdown=f"**{header}**\n{bulletize(lines)}",
            data={"items": [self._summary_to_payload(item, language) for item in items]},
        )

    def query_inventory(
        self,
        question: str,
        language: str = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        question_lower = question.lower()
        inventory = self._batches_to_summary(household_id, language)
        inventory_map = {item.canonical_name: item for item in inventory}

        target_category = None
        if any(token in question_lower for token in ("vegetable", "vegetables", "veggie", "蔬菜")):
            target_category = {"vegetable", "leafy_green", "aromatic"}
        elif any(token in question_lower for token in ("condiment", "condiments", "调料", "调味")):
            target_category = {"condiment"}

        mentioned_profile = None
        for profile in INGREDIENT_PROFILES:
            aliases = {profile.canonical_name, profile.display_name_en.lower(), profile.display_name_zh.lower(), *[alias.lower() for alias in profile.synonyms]}
            if any(alias in question_lower for alias in aliases):
                mentioned_profile = profile
                break

        if any(token in question_lower for token in ("need to buy", "buy", "买吗", "要买")) and mentioned_profile:
            item = inventory_map.get(mentioned_profile.canonical_name)
            should_buy = item is None or item.low_stock or item.uncertain
            if self._language(language) == "zh":
                line = f"{mentioned_profile.display_name_zh}: {'建议购买' if should_buy else '暂时不用买'}。"
            else:
                line = f"{mentioned_profile.display_name_en}: {'buy more soon' if should_buy else 'no need to buy yet'}."
            return ServiceResult(
                status="ok",
                language=self._language(language),
                response_markdown=bulletize([line]),
                data={"should_buy": should_buy, "item": mentioned_profile.canonical_name},
            )

        if mentioned_profile:
            item = inventory_map.get(mentioned_profile.canonical_name)
            if item:
                line = (
                    f"{mentioned_profile.display_name_zh}: {stock_label(item.uncertain, item.total_quantity, item.unit, language)}。"
                    if self._language(language) == "zh"
                    else f"{mentioned_profile.display_name_en}: {stock_label(item.uncertain, item.total_quantity, item.unit, language)}."
                )
            else:
                line = (
                    f"{mentioned_profile.display_name_zh}: 当前没有确认库存。"
                    if self._language(language) == "zh"
                    else f"{mentioned_profile.display_name_en}: not confirmed in stock."
                )
            return ServiceResult(
                status="ok",
                language=self._language(language),
                response_markdown=bulletize([line]),
                data={"item": mentioned_profile.canonical_name},
            )

        filtered = [
            item
            for item in inventory
            if target_category is None or item.item_group in target_category or item.category in target_category
        ]
        if self._language(language) == "zh":
            lines = [
                f"{self._name(item, language)}: {stock_label(item.uncertain, item.total_quantity, item.unit, language)}"
                for item in filtered
            ] or ["没有找到符合条件的库存。"]
        else:
            lines = [
                f"{self._name(item, language)}: {stock_label(item.uncertain, item.total_quantity, item.unit, language)}"
                for item in filtered
            ] or ["No matching inventory found."]
        return ServiceResult(
            status="ok",
            language=self._language(language),
            response_markdown=bulletize(lines),
            data={"items": [self._summary_to_payload(item, language) for item in filtered]},
        )

    def plan_day(
        self,
        language: str = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        suggestions, _, ranked = self._rank_recipes(household_id, language, limit=2)
        if not ranked or ranked[0][1] < 0.6:
            fallback = asdict(
                self._fallback_request(
                    household_id=household_id,
                    language=language,
                    reason="No strong personal-recipe match from current inventory.",
                )
            )
            lines = (
                ["当前本地菜谱匹配度不足，需要联网搜索新菜视频。"]
                if self._language(language) == "zh"
                else ["Current local recipes are a weak match. Online video search is needed."]
            )
            return ServiceResult(
                status="needs_web_search",
                language=self._language(language),
                response_markdown=bulletize(lines),
                data={"suggestions": [], "fallback_request": fallback},
            )

        grocery_items = self._grocery_items(suggestions)
        snack_suggestions = self._snack_suggestions(suggestions, language)
        lines = []
        for suggestion in suggestions:
            if self._language(language) == "zh":
                lines.append(
                    f"{suggestion.title}: 蛋白质 {suggestion.macro_summary['protein']} / 纤维 {suggestion.macro_summary['fiber']} / 脂肪 {suggestion.macro_summary['fats']}"
                )
                if suggestion.missing_condiments:
                    lines.append(f"缺少调味料: {', '.join(suggestion.missing_condiments)}")
            else:
                lines.append(
                    f"{suggestion.title}: protein {suggestion.macro_summary['protein']} / fiber {suggestion.macro_summary['fiber']} / fats {suggestion.macro_summary['fats']}"
                )
                if suggestion.missing_condiments:
                    lines.append(f"Missing condiments: {', '.join(suggestion.missing_condiments)}")

        if self._language(language) == "zh":
            lines.append(f"加餐建议: {', '.join(snack_suggestions)}")
            if grocery_items:
                lines.append(f"待采购: {', '.join(grocery_items)}")
        else:
            lines.append(f"Snack ideas: {', '.join(snack_suggestions)}")
            if grocery_items:
                lines.append(f"Grocery add-ons: {', '.join(grocery_items)}")

        return ServiceResult(
            status="ok",
            language=self._language(language),
            response_markdown=bulletize(lines),
            data={
                "suggestions": [asdict(item) for item in suggestions],
                "snack_suggestions": snack_suggestions,
                "grocery_items": grocery_items,
            },
        )

    def plan_weekend(
        self,
        language: str = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        suggestions, inventory, _ = self._rank_recipes(household_id, language, limit=2)
        expiring_focus = [self._name(item, language) for item in inventory if item.expiring_soon][:4]
        grocery_items = self._grocery_items(suggestions)
        restock_items = [alert["canonical_name"] for alert in self.restock_alerts(language, household_id).data["alerts"]]
        grocery_items.extend(
            [
                lookup_profile(name).display_name_zh
                if self._language(language) == "zh"
                else lookup_profile(name).display_name_en
                for name in restock_items
            ]
        )
        deduped_grocery = []
        seen = set()
        for item in grocery_items:
            if item not in seen:
                deduped_grocery.append(item)
                seen.add(item)

        if self._language(language) == "zh":
            lines = [
                f"周末优先处理: {', '.join(expiring_focus)}" if expiring_focus else "周末可按常规备餐。",
                f"备餐建议: {', '.join(suggestion.title for suggestion in suggestions)}" if suggestions else "暂无强匹配菜谱。",
                f"下周采购清单: {', '.join(deduped_grocery)}" if deduped_grocery else "下周暂无新增采购项。",
            ]
        else:
            lines = [
                f"Use first this weekend: {', '.join(expiring_focus)}" if expiring_focus else "Weekend prep can follow the regular rotation.",
                f"Prep ideas: {', '.join(suggestion.title for suggestion in suggestions)}" if suggestions else "No strong local prep match yet.",
                f"Next-week groceries: {', '.join(deduped_grocery)}" if deduped_grocery else "No extra groceries needed yet.",
            ]
        return ServiceResult(
            status="ok",
            language=self._language(language),
            response_markdown=bulletize(lines),
            data={
                "prep_recipes": [asdict(item) for item in suggestions],
                "expiring_focus": expiring_focus,
                "grocery_items": deduped_grocery,
            },
        )

    def expiry_alerts(
        self,
        language: str = "en",
        household_id: str = "default",
        days_threshold: int = 2,
    ) -> ServiceResult:
        today = self._today()
        alerts: list[AlertItem] = []
        for item in self._batches_to_summary(
            household_id=household_id,
            language=language,
            expiring_within_days=days_threshold,
        ):
            if not item.expires_on or item.expires_on > today + timedelta(days=days_threshold):
                continue
            severity = "expired" if item.expires_on < today else "soon"
            reason = (
                f"请在 {format_date(item.expires_on)} 前使用。"
                if self._language(language) == "zh"
                else f"Use by {format_date(item.expires_on)}."
            )
            alerts.append(
                AlertItem(
                    canonical_name=item.canonical_name,
                    display_name_en=item.display_name_en,
                    display_name_zh=item.display_name_zh,
                    due_date=item.expires_on,
                    severity=severity,
                    reason=reason,
                )
            )

        lines = [f"{self._name(alert, language)}: {alert.reason}" for alert in alerts]
        if not lines:
            lines = ["暂无临期食材。" if self._language(language) == "zh" else "No upcoming expiry alerts."]
        return ServiceResult(
            status="ok",
            language=self._language(language),
            response_markdown=bulletize(lines),
            data={"alerts": [asdict(alert) for alert in alerts]},
        )

    def restock_alerts(
        self,
        language: str = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        inventory_map = {
            item.canonical_name: item
            for item in self._batches_to_summary(household_id, language)
        }
        alerts: list[AlertItem] = []
        for threshold in self.db.list_thresholds():
            inventory_item = inventory_map.get(threshold.canonical_name)
            is_low = inventory_item is None or inventory_item.uncertain
            if inventory_item and not is_low:
                if (
                    threshold.unit == inventory_item.unit
                    and inventory_item.total_quantity is not None
                    and threshold.threshold_quantity is not None
                ):
                    is_low = inventory_item.total_quantity <= threshold.threshold_quantity
            if not is_low:
                continue
            reason = (
                f"当前低于补货线 {format_quantity(threshold.threshold_quantity, threshold.unit)}。"
                if self._language(language) == "zh"
                else f"Below the restock threshold of {format_quantity(threshold.threshold_quantity, threshold.unit)}."
            )
            alerts.append(
                AlertItem(
                    canonical_name=threshold.canonical_name,
                    display_name_en=threshold.display_name_en,
                    display_name_zh=threshold.display_name_zh,
                    due_date=None,
                    severity="low",
                    reason=reason,
                )
            )
        lines = [f"{self._name(alert, language)}: {alert.reason}" for alert in alerts]
        if not lines:
            lines = ["暂无需要补货的常备品。" if self._language(language) == "zh" else "No staples need restocking."]
        return ServiceResult(
            status="ok",
            language=self._language(language),
            response_markdown=bulletize(lines),
            data={"alerts": [asdict(alert) for alert in alerts]},
        )

    def fallback_search_request(
        self,
        language: str = "en",
        household_id: str = "default",
        preferred_ingredients: Optional[list[str]] = None,
        reason: str = "Local recipes are insufficient.",
    ) -> ServiceResult:
        request = asdict(
            self._fallback_request(
                household_id=household_id,
                language=language,
                reason=reason,
                preferred_ingredients=preferred_ingredients,
            )
        )
        line = (
            "需要 OpenClaw 联网搜索带视频教程的新菜谱。"
            if self._language(language) == "zh"
            else "OpenClaw should run an online search for a recipe with a video tutorial."
        )
        return ServiceResult(
            status="needs_web_search",
            language=self._language(language),
            response_markdown=bulletize([line]),
            data={"search_request": request},
        )
