from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Optional

from .catalog import (
    DEFAULT_PANTRY_THRESHOLDS,
    find_profile_mentioned,
    lookup_profile,
    normalize_unit,
)
from .config import Settings, get_settings
from .db import Database
from .i18n import (
    bulletize,
    build_search_query,
    default_search_hints,
    format_date,
    format_quantity,
    join_display_list,
    legacy_language,
    localize_name,
    localize_recipe,
    macro_label,
    resolve_locale,
    stock_label,
    t,
)
from .parser import coerce_external_item, parse_checkin_text
from .recipes import RecipeRepository, normalize_recipe_tag
from .types import (
    AlertItem,
    InventoryBatch,
    InventorySummaryItem,
    LocaleCode,
    PantryThreshold,
    PlanSuggestion,
    SearchRequest,
    ServiceResult,
)


class KitchenService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db = Database(self.settings.database_path)
        self.recipe_repository = RecipeRepository(self.settings.recipes_dir)
        self._sync_thresholds()
        self._refresh_recipe_index()

    def _sync_thresholds(self) -> None:
        thresholds_path = self.settings.pantry_thresholds_path
        thresholds_path.parent.mkdir(parents=True, exist_ok=True)
        if thresholds_path.exists():
            payload = json.loads(thresholds_path.read_text(encoding="utf-8"))
            thresholds = [PantryThreshold(**item) for item in payload]
        else:
            thresholds = list(DEFAULT_PANTRY_THRESHOLDS)
        self.db.replace_thresholds(thresholds)

    def _refresh_recipe_index(self) -> None:
        self.db.replace_recipe_cache(self.recipe_repository.recipes)

    def _resolve_locale(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = None,
    ) -> LocaleCode:
        return resolve_locale(locale or language)

    def _result(
        self,
        status: str,
        locale: LocaleCode,
        response_markdown: str,
        data: dict[str, object],
    ) -> ServiceResult:
        return ServiceResult(
            status=status,
            locale=locale,
            language=legacy_language(locale),
            response_markdown=response_markdown,
            data=data,
        )

    def _today(self) -> date:
        return date.today()

    def _name(self, obj: object, locale: LocaleCode) -> str:
        return localize_name(obj, locale)

    def _compute_recommended_use_by(
        self,
        item_name: str,
        freshness_type: str,
        checked_in_at: datetime,
    ) -> Optional[date]:
        profile = lookup_profile(item_name)
        if freshness_type != "fresh" or profile.default_days is None:
            return None
        return (checked_in_at + timedelta(days=profile.default_days)).date()

    def _serialize_batch(self, batch: InventoryBatch, locale: LocaleCode) -> dict[str, object]:
        return {
            "batch_id": batch.batch_id,
            "name": self._name(batch, locale),
            "canonical_name": batch.canonical_name,
            "quantity": batch.quantity,
            "unit": batch.unit,
            "quantity_label": stock_label(locale, batch.uncertain, batch.quantity, batch.unit),
            "category": batch.category,
            "item_group": batch.item_group,
            "freshness_type": batch.freshness_type,
            "checked_in_at": batch.checked_in_at.isoformat(),
            "expiration_date": format_date(batch.expiration_date),
            "recommended_use_by": format_date(batch.recommended_use_by),
            "uncertain": batch.uncertain,
        }

    def _serialize_recipe(self, recipe, locale: LocaleCode) -> dict[str, object]:
        localized_recipe, warnings = localize_recipe(recipe, locale)
        return {
            "recipe_id": recipe.recipe_id,
            "title": localized_recipe.title if localized_recipe else recipe.title,
            "tags": recipe.tags,
            "proficiency": recipe.proficiency,
            "source_type": recipe.source_type,
            "ingredients": [asdict(item) for item in recipe.ingredients],
            "condiments": recipe.condiments,
            "steps": localized_recipe.steps if localized_recipe else [],
            "macro_summary": asdict(recipe.macro_summary),
            "search_hints": recipe.search_hints,
            "path": str(recipe.path),
            "supports_locale": localized_recipe is not None,
            "localization_warnings": [asdict(item) for item in warnings],
        }

    def _filtered_batches(
        self,
        household_id: str,
        category: Optional[str] = None,
        expiring_within_days: Optional[int] = None,
        only_available: bool = True,
        canonical_name: Optional[str] = None,
    ) -> list[InventoryBatch]:
        today = self._today()
        batches: list[InventoryBatch] = []
        for batch in self.db.list_batches(household_id):
            relevant_date = batch.relevant_date
            if only_available and relevant_date and relevant_date < today:
                continue
            if only_available and batch.quantity is not None and batch.quantity <= 0:
                continue
            if canonical_name and batch.canonical_name != canonical_name:
                continue
            if category and batch.category != category and batch.item_group != category:
                continue
            if expiring_within_days is not None:
                if relevant_date is None or relevant_date > today + timedelta(days=expiring_within_days):
                    continue
            batches.append(batch)
        return batches

    def _get_batch_or_raise(self, batch_id: int, household_id: str) -> InventoryBatch:
        batch = self.db.get_batch(batch_id, household_id)
        if batch is None:
            raise LookupError(f"Batch {batch_id} was not found for household '{household_id}'.")
        return batch

    def _batches_to_summary(
        self,
        household_id: str,
        locale: LocaleCode,
        category: Optional[str] = None,
        expiring_within_days: Optional[int] = None,
        only_available: bool = True,
    ) -> list[InventorySummaryItem]:
        today = self._today()
        summary: dict[str, InventorySummaryItem] = {}
        for batch in self._filtered_batches(
            household_id=household_id,
            category=category,
            expiring_within_days=expiring_within_days,
            only_available=only_available,
        ):
            relevant_date = batch.relevant_date
            existing = summary.get(batch.canonical_name)
            if not existing:
                summary[batch.canonical_name] = InventorySummaryItem(
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
                    batch_ids=[batch.batch_id],
                    expires_on=relevant_date,
                    expiring_soon=False,
                )
                continue

            existing.batch_count += 1
            existing.batch_ids.append(batch.batch_id)
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

    def _summary_to_payload(
        self,
        item: InventorySummaryItem,
        locale: LocaleCode,
    ) -> dict[str, object]:
        return {
            "name": self._name(item, locale),
            "canonical_name": item.canonical_name,
            "category": item.category,
            "item_group": item.item_group,
            "freshness_type": item.freshness_type,
            "quantity": item.total_quantity,
            "unit": item.unit,
            "quantity_label": stock_label(locale, item.uncertain, item.total_quantity, item.unit),
            "uncertain": item.uncertain,
            "batch_count": item.batch_count,
            "batch_ids": item.batch_ids,
            "expires_on": format_date(item.expires_on),
            "expiring_soon": item.expiring_soon,
            "low_stock": item.low_stock,
        }

    def _ingredient_available(
        self,
        recipe_item_name: str,
        inventory_map: dict[str, InventorySummaryItem],
    ) -> tuple[bool, bool, Optional[InventorySummaryItem]]:
        profile = lookup_profile(recipe_item_name)
        item = inventory_map.get(profile.canonical_name)
        if not item:
            return False, False, None
        if item.uncertain or item.total_quantity is None:
            return False, True, item
        return item.total_quantity > 0, False, item

    def _build_suggestion(
        self,
        recipe,
        inventory_map: dict[str, InventorySummaryItem],
        locale: LocaleCode,
    ) -> tuple[PlanSuggestion, float, float]:
        localized_recipe, _ = localize_recipe(recipe, locale)
        if localized_recipe is None:
            raise ValueError(f"Recipe {recipe.recipe_id} is not localized for {locale}")

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
            ingredient_name = lookup_profile(ingredient.name).display_name(locale)
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
            label = lookup_profile(condiment_name).display_name(locale)
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
            title=localized_recipe.title,
            source_type=recipe.source_type,
            score=round(score, 1),
            missing_ingredients=missing,
            uncertain_ingredients=uncertain,
            required_condiments=[
                lookup_profile(name).display_name(locale) for name in recipe.condiments
            ],
            missing_condiments=missing_condiments,
            steps=localized_recipe.steps,
            macro_summary=asdict(recipe.macro_summary),
        )
        return suggestion, coverage, score

    def _rank_recipes(
        self,
        household_id: str,
        locale: LocaleCode,
        limit: int = 2,
    ) -> tuple[list[PlanSuggestion], list[InventorySummaryItem], list[tuple[str, float, float]]]:
        inventory = self._batches_to_summary(household_id, locale)
        inventory_map = {item.canonical_name: item for item in inventory}
        ranked: list[tuple[str, PlanSuggestion, float, float]] = []
        for recipe in self.recipe_repository.recipes_for_locale(locale):
            suggestion, coverage, score = self._build_suggestion(recipe, inventory_map, locale)
            ranked.append((recipe.recipe_id, suggestion, coverage, score))
        ranked.sort(
            key=lambda item: (item[2] >= 0.6, item[3], item[1].source_type == "personal"),
            reverse=True,
        )
        suggestions = [item[1] for item in ranked[:limit]]
        return suggestions, inventory, [(item[0], item[2], item[3]) for item in ranked]

    def _snack_suggestions(
        self,
        suggestions: list[PlanSuggestion],
        locale: LocaleCode,
    ) -> list[str]:
        if not suggestions:
            return [t(locale, "snack.apple_nuts")]
        highest = suggestions[0].macro_summary
        snacks: list[str] = []
        if highest["protein"] == "low":
            snacks.append(t(locale, "snack.yogurt"))
        if highest["fiber"] in {"low", "medium"}:
            snacks.append(t(locale, "snack.apple"))
        if highest["fats"] == "low":
            snacks.append(t(locale, "snack.nuts"))
        return snacks or [t(locale, "snack.cucumber")]

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
        locale: LocaleCode,
        reason: str,
        preferred_ingredients: Optional[list[str]] = None,
    ) -> SearchRequest:
        inventory = self._batches_to_summary(
            household_id=household_id,
            locale=locale,
            expiring_within_days=3,
        )
        focus = preferred_ingredients or [
            self._name(item, locale)
            for item in inventory
            if item.expiring_soon
        ][:3]
        if not focus:
            focus = [self._name(item, locale) for item in inventory[:3]]
        return SearchRequest(
            query=build_search_query(locale, focus).strip(),
            locale=locale,
            language=legacy_language(locale),
            reason=reason,
            require_video=True,
            preferred_sites=["YouTube", "Bilibili"],
            expected_fields=["title", "video_url", "source_url", "ingredients", "steps_summary"],
            ingredient_focus=focus,
            search_hints=default_search_hints(locale),
        )

    def checkin(
        self,
        text: str,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
        checked_in_at: Optional[datetime] = None,
        parsed_items: Optional[list[dict[str, object]]] = None,
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
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
                        "item_name": self._name(item, resolved_locale),
                        "question": t(
                            resolved_locale,
                            "checkin.packaged_follow_up",
                            item_name=self._name(item, resolved_locale),
                        ),
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
            recorded.append(self._serialize_batch(batch, resolved_locale))

        lines: list[str] = []
        if recorded:
            lines.append(
                t(resolved_locale, "checkin.recorded_count", count=len(recorded))
            )
        if follow_ups:
            lines.append(t(resolved_locale, "checkin.follow_up_header"))
            lines.extend(question["question"] for question in follow_ups)

        return self._result(
            status="needs_user_input" if follow_ups else "ok",
            locale=resolved_locale,
            response_markdown=bulletize(lines) if lines else "",
            data={
                "recorded_items": recorded,
                "follow_up_questions": follow_ups,
            },
        )

    def get_inventory(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
        category: Optional[str] = None,
        expiring_within_days: Optional[int] = None,
        only_available: bool = True,
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        batches = self._filtered_batches(
            household_id=household_id,
            category=category,
            expiring_within_days=expiring_within_days,
            only_available=only_available,
        )
        items = self._batches_to_summary(
            household_id=household_id,
            locale=resolved_locale,
            category=category,
            expiring_within_days=expiring_within_days,
            only_available=only_available,
        )
        lines = [
            t(
                resolved_locale,
                "inventory.item_line_with_date" if item.expires_on else "inventory.item_line",
                name=self._name(item, resolved_locale),
                quantity=stock_label(
                    resolved_locale,
                    item.uncertain,
                    item.total_quantity,
                    item.unit,
                ),
                date=format_date(item.expires_on),
            )
            for item in items
        ] or [t(resolved_locale, "inventory.no_filter_match")]
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=f"**{t(resolved_locale, 'inventory.header')}**\n{bulletize(lines)}",
            data={
                "items": [self._summary_to_payload(item, resolved_locale) for item in items],
                "batches": [self._serialize_batch(batch, resolved_locale) for batch in batches],
            },
        )

    def query_inventory(
        self,
        question: str,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        question_lower = question.lower()
        inventory = self._batches_to_summary(household_id, resolved_locale)
        inventory_map = {item.canonical_name: item for item in inventory}

        target_category = None
        if any(token in question_lower for token in ("vegetable", "vegetables", "veggie", "蔬菜")):
            target_category = {"vegetable", "leafy_green", "aromatic"}
        elif any(token in question_lower for token in ("condiment", "condiments", "调料", "调味")):
            target_category = {"condiment"}

        mentioned_profile = find_profile_mentioned(question_lower)
        punctuation = "。" if resolved_locale == "zh-Hans" else "."

        if any(token in question_lower for token in ("need to buy", "buy", "买吗", "要买")) and mentioned_profile:
            item = inventory_map.get(mentioned_profile.canonical_name)
            should_buy = item is None or item.low_stock or item.uncertain
            line = (
                f"{mentioned_profile.display_name(resolved_locale)}: "
                f"{t(resolved_locale, 'query.buy_yes' if should_buy else 'query.buy_no')}{punctuation}"
            )
            return self._result(
                status="ok",
                locale=resolved_locale,
                response_markdown=bulletize([line]),
                data={"should_buy": should_buy, "item": mentioned_profile.canonical_name},
            )

        if mentioned_profile:
            item = inventory_map.get(mentioned_profile.canonical_name)
            status_text = (
                stock_label(resolved_locale, item.uncertain, item.total_quantity, item.unit)
                if item
                else t(resolved_locale, "query.not_confirmed")
            )
            line = f"{mentioned_profile.display_name(resolved_locale)}: {status_text}{punctuation}"
            return self._result(
                status="ok",
                locale=resolved_locale,
                response_markdown=bulletize([line]),
                data={"item": mentioned_profile.canonical_name},
            )

        filtered = [
            item
            for item in inventory
            if target_category is None or item.item_group in target_category or item.category in target_category
        ]
        lines = [
            t(
                resolved_locale,
                "inventory.item_line",
                name=self._name(item, resolved_locale),
                quantity=stock_label(
                    resolved_locale,
                    item.uncertain,
                    item.total_quantity,
                    item.unit,
                ),
            )
            for item in filtered
        ] or [t(resolved_locale, "inventory.no_match")]
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(lines),
            data={"items": [self._summary_to_payload(item, resolved_locale) for item in filtered]},
        )

    def consume_inventory(
        self,
        item_name: str,
        quantity: float,
        unit: Optional[str] = None,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        if quantity <= 0:
            raise ValueError("quantity must be greater than 0")

        normalized_unit = normalize_unit(unit)
        profile = lookup_profile(item_name, normalized_unit)
        all_batches = self._filtered_batches(
            household_id=household_id,
            only_available=True,
            canonical_name=profile.canonical_name,
        )

        if not all_batches:
            return self._result(
                status="needs_user_input",
                locale=resolved_locale,
                response_markdown=bulletize(
                    [t(resolved_locale, "inventory.consume_no_match", name=profile.display_name(resolved_locale))]
                ),
                data={
                    "item": profile.canonical_name,
                    "requested_quantity": quantity,
                    "unit": normalized_unit,
                    "consumed_from_batches": [],
                    "updated_batches": [],
                    "deleted_batch_ids": [],
                    "uncertain_batches": [],
                },
            )

        if normalized_unit is None:
            known_units = {
                batch.unit
                for batch in all_batches
                if batch.quantity is not None and not batch.uncertain
            }
            if len(known_units) > 1:
                raise ValueError("unit is required when the item exists in multiple units")
            match_unit = next(iter(known_units), None) if known_units else None
        else:
            match_unit = normalized_unit
            if normalized_unit == "piece":
                explicit_piece_batches = [
                    batch
                    for batch in all_batches
                    if not batch.uncertain and batch.quantity is not None and batch.unit == normalized_unit
                ]
                unitless_count_batches = [
                    batch
                    for batch in all_batches
                    if not batch.uncertain and batch.quantity is not None and batch.unit is None
                ]
                if not explicit_piece_batches and unitless_count_batches:
                    match_unit = None

        uncertain_batches = [
            batch
            for batch in all_batches
            if batch.uncertain or batch.quantity is None or batch.unit != match_unit
        ]
        candidates = [
            batch
            for batch in all_batches
            if not batch.uncertain and batch.quantity is not None and batch.unit == match_unit
        ]
        candidates.sort(key=lambda batch: (batch.relevant_date or date.max, batch.checked_in_at, batch.batch_id))

        confirmed_available = sum(batch.quantity or 0 for batch in candidates)
        if confirmed_available < quantity:
            lines = [
                t(
                    resolved_locale,
                    "inventory.consume_insufficient",
                    name=profile.display_name(resolved_locale),
                    quantity=format_quantity(confirmed_available, normalized_unit),
                )
            ]
            if uncertain_batches:
                lines.append(
                    t(
                        resolved_locale,
                        "inventory.consume_unknown_batches",
                        name=profile.display_name(resolved_locale),
                    )
                )
            return self._result(
                status="needs_user_input",
                locale=resolved_locale,
                response_markdown=bulletize(lines),
                data={
                    "item": profile.canonical_name,
                    "requested_quantity": quantity,
                    "unit": normalized_unit,
                    "confirmed_available": confirmed_available,
                    "consumed_from_batches": [],
                    "updated_batches": [],
                    "deleted_batch_ids": [],
                    "uncertain_batches": [
                        self._serialize_batch(batch, resolved_locale) for batch in uncertain_batches
                    ],
                },
            )

        remaining = quantity
        consumed_from_batches: list[dict[str, object]] = []
        updated_batches: list[dict[str, object]] = []
        deleted_batch_ids: list[int] = []
        for batch in candidates:
            if remaining <= 0:
                break
            consume_amount = min(batch.quantity or 0, remaining)
            consumed_from_batches.append(
                {
                    "batch_id": batch.batch_id,
                    "quantity": consume_amount,
                    "unit": batch.unit,
                }
            )
            if consume_amount >= (batch.quantity or 0):
                self.db.delete_batch(batch.batch_id, household_id)
                deleted_batch_ids.append(batch.batch_id)
            else:
                updated_batch = InventoryBatch(
                    batch_id=batch.batch_id,
                    household_id=batch.household_id,
                    canonical_name=batch.canonical_name,
                    display_name_en=batch.display_name_en,
                    display_name_zh=batch.display_name_zh,
                    quantity=(batch.quantity or 0) - consume_amount,
                    unit=batch.unit,
                    category=batch.category,
                    item_group=batch.item_group,
                    freshness_type=batch.freshness_type,
                    checked_in_at=batch.checked_in_at,
                    expiration_date=batch.expiration_date,
                    recommended_use_by=batch.recommended_use_by,
                    uncertain=batch.uncertain,
                    source_text=batch.source_text,
                )
                self.db.update_batch(updated_batch)
                updated_batches.append(self._serialize_batch(updated_batch, resolved_locale))
            remaining -= consume_amount

        self.db.record_event(
            household_id,
            "consume",
            profile.canonical_name,
            {
                "item_name": item_name,
                "quantity": quantity,
                "unit": normalized_unit,
                "consumed_from_batches": consumed_from_batches,
                "deleted_batch_ids": deleted_batch_ids,
            },
        )

        remaining_item = next(
            (
                item
                for item in self._batches_to_summary(household_id, resolved_locale)
                if item.canonical_name == profile.canonical_name
            ),
            None,
        )
        lines = [
            t(
                resolved_locale,
                "inventory.consume_line",
                name=profile.display_name(resolved_locale),
                quantity=format_quantity(quantity, normalized_unit),
            )
        ]
        if remaining_item:
            lines.append(
                t(
                    resolved_locale,
                    "inventory.item_line",
                    name=self._name(remaining_item, resolved_locale),
                    quantity=stock_label(
                        resolved_locale,
                        remaining_item.uncertain,
                        remaining_item.total_quantity,
                        remaining_item.unit,
                    ),
                )
            )

        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(lines),
            data={
                "item": profile.canonical_name,
                "requested_quantity": quantity,
                "unit": normalized_unit,
                "consumed_from_batches": consumed_from_batches,
                "updated_batches": updated_batches,
                "deleted_batch_ids": deleted_batch_ids,
                "remaining_item": (
                    self._summary_to_payload(remaining_item, resolved_locale)
                    if remaining_item
                    else None
                ),
                "uncertain_batches": [
                    self._serialize_batch(batch, resolved_locale) for batch in uncertain_batches
                ],
            },
        )

    def update_inventory_batch(
        self,
        batch_id: int,
        batch_patch: dict[str, object],
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        if not batch_patch:
            raise ValueError("at least one batch field must be provided")

        resolved_locale = self._resolve_locale(locale, language)
        batch = self._get_batch_or_raise(batch_id, household_id)

        raw_name = str(batch_patch["name"]).strip() if "name" in batch_patch else batch.canonical_name
        if not raw_name:
            raise ValueError("name cannot be blank")

        quantity = batch.quantity
        uncertain = batch.uncertain
        if "quantity" in batch_patch:
            raw_quantity = batch_patch["quantity"]
            if raw_quantity is None or float(raw_quantity) <= 0:
                raise ValueError("quantity must be greater than 0")
            quantity = float(raw_quantity)
            uncertain = False

        unit = batch.unit
        if "unit" in batch_patch:
            unit = normalize_unit(batch_patch["unit"])

        checked_in_at = batch.checked_in_at
        if "checked_in_at" in batch_patch and batch_patch["checked_in_at"] is not None:
            checked_in_at = batch_patch["checked_in_at"]  # type: ignore[assignment]

        expiration_date = batch.expiration_date
        if "expiration_date" in batch_patch:
            expiration_date = batch_patch["expiration_date"]  # type: ignore[assignment]

        source_text = batch.source_text
        if "source_text" in batch_patch and batch_patch["source_text"] is not None:
            source_text = str(batch_patch["source_text"])

        profile = lookup_profile(raw_name, unit)
        if profile.freshness_type == "packaged" and expiration_date is None:
            raise ValueError("packaged items require an expiration_date")

        recommended_use_by = None
        if profile.freshness_type == "fresh" and expiration_date is None:
            recommended_use_by = self._compute_recommended_use_by(
                profile.canonical_name,
                profile.freshness_type,
                checked_in_at,
            )

        updated_batch = InventoryBatch(
            batch_id=batch.batch_id,
            household_id=batch.household_id,
            canonical_name=profile.canonical_name,
            display_name_en=profile.display_name_en,
            display_name_zh=profile.display_name_zh,
            quantity=quantity,
            unit=unit,
            category=profile.category,
            item_group=profile.item_group,
            freshness_type=profile.freshness_type,
            checked_in_at=checked_in_at,
            expiration_date=expiration_date,
            recommended_use_by=recommended_use_by,
            uncertain=uncertain,
            source_text=source_text,
        )
        self.db.update_batch(updated_batch)
        self.db.record_event(
            household_id,
            "update_batch",
            updated_batch.canonical_name,
            {
                "batch_id": batch_id,
                "fields": sorted(batch_patch.keys()),
            },
        )

        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(
                [
                    t(
                        resolved_locale,
                        "inventory.batch_updated",
                        batch_id=batch_id,
                        name=self._name(updated_batch, resolved_locale),
                    )
                ]
            ),
            data={"batch": self._serialize_batch(updated_batch, resolved_locale)},
        )

    def delete_inventory_batch(
        self,
        batch_id: int,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        batch = self._get_batch_or_raise(batch_id, household_id)
        self.db.delete_batch(batch_id, household_id)
        self.db.record_event(
            household_id,
            "delete_batch",
            batch.canonical_name,
            {"batch_id": batch_id},
        )
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(
                [
                    t(
                        resolved_locale,
                        "inventory.batch_deleted",
                        batch_id=batch_id,
                        name=self._name(batch, resolved_locale),
                    )
                ]
            ),
            data={"deleted_batch": self._serialize_batch(batch, resolved_locale)},
        )

    def plan_day(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        suggestions, _, ranked = self._rank_recipes(
            household_id=household_id,
            locale=resolved_locale,
            limit=2,
        )
        warnings = [
            asdict(warning)
            for warning in self.recipe_repository.warnings_for_locale(resolved_locale)
        ]

        if not ranked or ranked[0][1] < 0.6:
            fallback = asdict(
                self._fallback_request(
                    household_id=household_id,
                    locale=resolved_locale,
                    reason=t(resolved_locale, "plan.day.no_local_match"),
                )
            )
            return self._result(
                status="needs_web_search",
                locale=resolved_locale,
                response_markdown=bulletize([t(resolved_locale, "plan.day.no_local_match")]),
                data={
                    "suggestions": [],
                    "fallback_request": fallback,
                    "localization_warnings": warnings,
                },
            )

        grocery_items = self._grocery_items(suggestions)
        snack_suggestions = self._snack_suggestions(suggestions, resolved_locale)
        lines: list[str] = []
        for suggestion in suggestions:
            lines.append(
                t(
                    resolved_locale,
                    "plan.day.recipe_line",
                    title=suggestion.title,
                    protein=macro_label(resolved_locale, suggestion.macro_summary["protein"]),
                    fiber=macro_label(resolved_locale, suggestion.macro_summary["fiber"]),
                    fats=macro_label(resolved_locale, suggestion.macro_summary["fats"]),
                )
            )
            if suggestion.missing_condiments:
                lines.append(
                    t(
                        resolved_locale,
                        "plan.day.missing_condiments",
                        items=join_display_list(resolved_locale, suggestion.missing_condiments),
                    )
                )
        lines.append(
            t(
                resolved_locale,
                "plan.day.snacks",
                items=join_display_list(resolved_locale, snack_suggestions),
            )
        )
        if grocery_items:
            lines.append(
                t(
                    resolved_locale,
                    "plan.day.grocery",
                    items=join_display_list(resolved_locale, grocery_items),
                )
            )

        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(lines),
            data={
                "suggestions": [asdict(item) for item in suggestions],
                "snack_suggestions": snack_suggestions,
                "grocery_items": grocery_items,
                "localization_warnings": warnings,
            },
        )

    def plan_weekend(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        suggestions, inventory, _ = self._rank_recipes(
            household_id=household_id,
            locale=resolved_locale,
            limit=2,
        )
        warnings = [
            asdict(warning)
            for warning in self.recipe_repository.warnings_for_locale(resolved_locale)
        ]
        expiring_focus = [self._name(item, resolved_locale) for item in inventory if item.expiring_soon][:4]
        grocery_items = self._grocery_items(suggestions)
        restock_items = [
            alert["canonical_name"]
            for alert in self.restock_alerts(locale=resolved_locale, household_id=household_id).data["alerts"]
        ]
        grocery_items.extend([lookup_profile(name).display_name(resolved_locale) for name in restock_items])

        deduped_grocery: list[str] = []
        seen: set[str] = set()
        for item in grocery_items:
            if item not in seen:
                deduped_grocery.append(item)
                seen.add(item)

        lines = [
            t(resolved_locale, "weekend.use_first", items=join_display_list(resolved_locale, expiring_focus))
            if expiring_focus
            else t(resolved_locale, "weekend.regular_rotation"),
            t(
                resolved_locale,
                "weekend.prep_ideas",
                items=join_display_list(resolved_locale, [suggestion.title for suggestion in suggestions]),
            )
            if suggestions
            else t(resolved_locale, "weekend.no_prep_match"),
            t(
                resolved_locale,
                "weekend.next_week_groceries",
                items=join_display_list(resolved_locale, deduped_grocery),
            )
            if deduped_grocery
            else t(resolved_locale, "weekend.no_extra_groceries"),
        ]
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(lines),
            data={
                "prep_recipes": [asdict(item) for item in suggestions],
                "expiring_focus": expiring_focus,
                "grocery_items": deduped_grocery,
                "localization_warnings": warnings,
            },
        )

    def expiry_alerts(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
        days_threshold: int = 2,
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        today = self._today()
        alerts: list[AlertItem] = []
        for item in self._batches_to_summary(
            household_id=household_id,
            locale=resolved_locale,
            expiring_within_days=days_threshold,
        ):
            if not item.expires_on or item.expires_on > today + timedelta(days=days_threshold):
                continue
            severity = "expired" if item.expires_on < today else "soon"
            alerts.append(
                AlertItem(
                    canonical_name=item.canonical_name,
                    display_name_en=item.display_name_en,
                    display_name_zh=item.display_name_zh,
                    due_date=item.expires_on,
                    severity=severity,
                    reason=t(
                        resolved_locale,
                        "alerts.expiry_reason",
                        date=format_date(item.expires_on),
                    ),
                )
            )

        lines = [f"{self._name(alert, resolved_locale)}: {alert.reason}" for alert in alerts]
        if not lines:
            lines = [t(resolved_locale, "alerts.no_expiry")]
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(lines),
            data={"alerts": [asdict(alert) for alert in alerts]},
        )

    def restock_alerts(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        inventory_map = {
            item.canonical_name: item
            for item in self._batches_to_summary(household_id, resolved_locale)
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
            alerts.append(
                AlertItem(
                    canonical_name=threshold.canonical_name,
                    display_name_en=threshold.display_name_en,
                    display_name_zh=threshold.display_name_zh,
                    due_date=None,
                    severity="low",
                    reason=t(
                        resolved_locale,
                        "alerts.restock_reason",
                        threshold=format_quantity(threshold.threshold_quantity, threshold.unit),
                    ),
                )
            )
        lines = [f"{self._name(alert, resolved_locale)}: {alert.reason}" for alert in alerts]
        if not lines:
            lines = [t(resolved_locale, "alerts.no_restock")]
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(lines),
            data={"alerts": [asdict(alert) for alert in alerts]},
        )

    def fallback_search_request(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        household_id: str = "default",
        preferred_ingredients: Optional[list[str]] = None,
        reason: Optional[str] = None,
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        request = asdict(
            self._fallback_request(
                household_id=household_id,
                locale=resolved_locale,
                reason=reason or t(resolved_locale, "fallback.default_reason"),
                preferred_ingredients=preferred_ingredients,
            )
        )
        return self._result(
            status="needs_web_search",
            locale=resolved_locale,
            response_markdown=bulletize([t(resolved_locale, "fallback.line")]),
            data={"search_request": request},
        )

    def list_recipes(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
        tag: Optional[str] = None,
        category: Optional[str] = None,
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        recipe_tag = tag or category
        recipes = self.recipe_repository.list_recipes(
            locale=resolved_locale,
            tag=recipe_tag,
        )
        serialized_recipes = [
            self._serialize_recipe(recipe, resolved_locale) for recipe in recipes
        ]
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(
                [
                    t(
                        resolved_locale,
                        "recipes.list_line_with_tags",
                        title=item["title"],
                        tags=join_display_list(resolved_locale, item["tags"]),
                    )
                    if item["tags"]
                    else t(resolved_locale, "recipes.list_line", title=item["title"])
                    for item in serialized_recipes
                ]
                or [t(resolved_locale, "recipes.none")]
            ),
            data={
                "recipes": serialized_recipes,
                "filter_tag": normalize_recipe_tag(recipe_tag) if recipe_tag else None,
                "localization_warnings": [
                    asdict(warning)
                    for warning in self.recipe_repository.warnings_for_locale(resolved_locale)
                ],
            },
        )

    def create_recipe(
        self,
        recipe_payload: dict[str, object],
        locale: Optional[str] = None,
        language: Optional[str] = "en",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        recipe = self.recipe_repository.create_recipe(recipe_payload)
        self._refresh_recipe_index()
        serialized = self._serialize_recipe(recipe, resolved_locale)
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(
                [
                    t(
                        resolved_locale,
                        "recipes.created",
                        title=serialized["title"],
                    ),
                    t(
                        resolved_locale,
                        "recipes.list_line_with_tags",
                        title=serialized["title"],
                        tags=join_display_list(resolved_locale, serialized["tags"]),
                    )
                    if serialized["tags"]
                    else t(resolved_locale, "recipes.list_line", title=serialized["title"])
                ]
            ),
            data={"recipe": serialized},
        )

    def reload_recipes(
        self,
        locale: Optional[str] = None,
        language: Optional[str] = "en",
    ) -> ServiceResult:
        resolved_locale = self._resolve_locale(locale, language)
        recipes = self.recipe_repository.reload()
        self._refresh_recipe_index()
        recipe_count = len(recipes)
        warning_count = len(self.recipe_repository.warnings_for_locale(resolved_locale))
        return self._result(
            status="ok",
            locale=resolved_locale,
            response_markdown=bulletize(
                [
                    t(
                        resolved_locale,
                        "recipes.reload",
                        count=recipe_count,
                        warnings=warning_count,
                    )
                ]
            ),
            data={
                "recipe_count": recipe_count,
                "localization_warnings": [
                    asdict(warning)
                    for warning in self.recipe_repository.warnings_for_locale(resolved_locale)
                ],
            },
        )
