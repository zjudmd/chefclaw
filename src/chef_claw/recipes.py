from __future__ import annotations

import json
from pathlib import Path

from .i18n import resolve_locale
from .types import LocalizationWarning, MacroSummary, Recipe, RecipeIngredient


class RecipeRepository:
    def __init__(self, recipes_dir: Path):
        self.recipes_dir = recipes_dir
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        self._warnings: list[LocalizationWarning] = []
        self._recipes = self._load_recipes()

    def _normalize_text_map(self, raw_map: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in raw_map.items():
            locale = resolve_locale(key)
            normalized[locale] = value
        return normalized

    def _recipe_warnings(
        self,
        recipe_id: str,
        path: Path,
        title_translations: dict[str, str],
        steps: list[dict[str, str]],
    ) -> list[LocalizationWarning]:
        warnings: list[LocalizationWarning] = []
        for locale in ("en", "zh-Hans"):
            if not title_translations.get(locale):
                warnings.append(
                    LocalizationWarning(
                        code="missing_recipe_title_translation",
                        message=f"Recipe title is missing for locale {locale}.",
                        locale=locale,
                        recipe_id=recipe_id,
                        path=str(path),
                    )
                )
            for index, step in enumerate(steps, start=1):
                if not step.get(locale):
                    warnings.append(
                        LocalizationWarning(
                            code="missing_recipe_step_translation",
                            message=f"Recipe step {index} is missing for locale {locale}.",
                            locale=locale,
                            recipe_id=recipe_id,
                            path=str(path),
                        )
                    )
        return warnings

    def _load_recipes(self) -> list[Recipe]:
        recipes: list[Recipe] = []
        for path in sorted(self.recipes_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            title_translations = self._normalize_text_map(
                payload.get("title_translations", {})
            )
            steps = [
                self._normalize_text_map(step)
                for step in payload.get("steps", [])
            ]
            warnings = self._recipe_warnings(
                recipe_id=payload["recipe_id"],
                path=path,
                title_translations=title_translations,
                steps=steps,
            )
            self._warnings.extend(warnings)
            recipes.append(
                Recipe(
                    recipe_id=payload["recipe_id"],
                    path=path,
                    title=payload["title"],
                    title_translations=title_translations,
                    language=payload.get("language", "en"),
                    tags=payload.get("tags", []),
                    proficiency=payload.get("proficiency", "established"),
                    source_type=payload.get("source_type", "personal"),
                    ingredients=[
                        RecipeIngredient(
                            name=item["name"],
                            quantity=item.get("quantity"),
                            unit=item.get("unit"),
                            optional=item.get("optional", False),
                        )
                        for item in payload.get("ingredients", [])
                    ],
                    condiments=payload.get("condiments", []),
                    steps=steps,
                    macro_summary=MacroSummary(**payload.get("macro_summary", {})),
                    search_hints=payload.get("search_hints", []),
                    localization_warnings=warnings,
                )
            )
        return recipes

    @property
    def recipes(self) -> list[Recipe]:
        return list(self._recipes)

    @property
    def warnings(self) -> list[LocalizationWarning]:
        return list(self._warnings)

    def warnings_for_locale(self, locale: str) -> list[LocalizationWarning]:
        return [
            warning
            for warning in self._warnings
            if warning.locale in (None, locale)
        ]

    def recipes_for_locale(self, locale: str) -> list[Recipe]:
        return [recipe for recipe in self._recipes if recipe.supports_locale(locale)]
