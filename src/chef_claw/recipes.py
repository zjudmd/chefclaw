from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .i18n import resolve_locale
from .types import LocalizationWarning, MacroSummary, Recipe, RecipeIngredient


REQUIRED_RECIPE_LOCALES = ("en", "zh-Hans")
RECIPE_ID_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_recipe_tag(value: str) -> str:
    cleaned = value.strip().lower().replace("_", " ").replace("-", " ")
    return "-".join(part for part in cleaned.split() if part)


def slugify_recipe_id(value: str) -> str:
    normalized = RECIPE_ID_PATTERN.sub("-", value.strip().lower()).strip("-")
    return normalized


class RecipeRepository:
    def __init__(self, recipes_dir: Path):
        self.recipes_dir = recipes_dir
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        self._warnings: list[LocalizationWarning] = []
        self._recipes: list[Recipe] = []
        self.reload()

    def reload(self) -> list[Recipe]:
        self._warnings = []
        self._recipes = self._load_recipes()
        return self.recipes

    def _normalize_text_map(self, raw_map: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in raw_map.items():
            locale = resolve_locale(key)
            normalized[locale] = value.strip()
        return normalized

    def _normalize_recipe_payload(self, payload: dict[str, object]) -> dict[str, object]:
        title_translations = self._normalize_text_map(
            dict(payload.get("title_translations", {}))
        )
        steps = [
            self._normalize_text_map(step)
            for step in payload.get("steps", [])
        ]
        return {
            **payload,
            "title": str(payload.get("title", title_translations.get("en", ""))).strip(),
            "title_translations": title_translations,
            "tags": [
                normalize_recipe_tag(tag)
                for tag in payload.get("tags", [])
                if normalize_recipe_tag(tag)
            ],
            "steps": steps,
        }

    def _recipe_warnings(
        self,
        recipe_id: str,
        path: Path,
        title_translations: dict[str, str],
        steps: list[dict[str, str]],
    ) -> list[LocalizationWarning]:
        warnings: list[LocalizationWarning] = []
        for locale in REQUIRED_RECIPE_LOCALES:
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
                elif not step[locale].strip():
                    warnings.append(
                        LocalizationWarning(
                            code="blank_recipe_step_translation",
                            message=f"Recipe step {index} is blank for locale {locale}.",
                            locale=locale,
                            recipe_id=recipe_id,
                            path=str(path),
                        )
                    )
        return warnings

    def _load_recipe(self, path: Path) -> Recipe:
        payload = self._normalize_recipe_payload(
            json.loads(path.read_text(encoding="utf-8"))
        )
        warnings = self._recipe_warnings(
            recipe_id=payload["recipe_id"],
            path=path,
            title_translations=payload["title_translations"],
            steps=payload["steps"],
        )
        self._warnings.extend(warnings)
        return Recipe(
            recipe_id=payload["recipe_id"],
            path=path,
            title=payload["title"],
            title_translations=payload["title_translations"],
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
            steps=payload.get("steps", []),
            macro_summary=MacroSummary(**payload.get("macro_summary", {})),
            search_hints=payload.get("search_hints", []),
            localization_warnings=warnings,
        )

    def _load_recipes(self) -> list[Recipe]:
        recipes: list[Recipe] = []
        for path in sorted(self.recipes_dir.glob("*.json")):
            recipes.append(self._load_recipe(path))
        return recipes

    def _validate_recipe_payload(self, payload: dict[str, object]) -> dict[str, object]:
        normalized = self._normalize_recipe_payload(payload)
        title_translations = normalized["title_translations"]
        steps = normalized["steps"]
        for locale in REQUIRED_RECIPE_LOCALES:
            if not title_translations.get(locale):
                raise ValueError(f"Recipe title translation is required for {locale}.")
        if not steps:
            raise ValueError("Recipe must include at least one step.")
        for index, step in enumerate(steps, start=1):
            for locale in REQUIRED_RECIPE_LOCALES:
                text = step.get(locale, "").strip()
                if not text:
                    raise ValueError(
                        f"Recipe step {index} translation is required for {locale}."
                    )
        if not normalized.get("ingredients"):
            raise ValueError("Recipe must include at least one ingredient.")
        if not normalized.get("macro_summary"):
            raise ValueError("Recipe must include a macro summary.")
        recipe_id = normalized.get("recipe_id") or slugify_recipe_id(
            title_translations["en"]
        )
        if not recipe_id:
            raise ValueError("Recipe id could not be generated. Provide recipe_id explicitly.")
        normalized["recipe_id"] = recipe_id
        normalized["title"] = title_translations["en"]
        normalized["language"] = normalized.get("language", "en")
        normalized["source_type"] = normalized.get("source_type", "personal")
        normalized["proficiency"] = normalized.get("proficiency", "established")
        return normalized

    def create_recipe(self, payload: dict[str, object]) -> Recipe:
        normalized = self._validate_recipe_payload(payload)
        path = self.recipes_dir / f"{normalized['recipe_id']}.json"
        if path.exists():
            raise ValueError(f"Recipe '{normalized['recipe_id']}' already exists.")

        serialized = {
            "recipe_id": normalized["recipe_id"],
            "title": normalized["title"],
            "title_translations": normalized["title_translations"],
            "language": normalized["language"],
            "tags": normalized.get("tags", []),
            "proficiency": normalized["proficiency"],
            "source_type": normalized["source_type"],
            "ingredients": normalized["ingredients"],
            "condiments": normalized.get("condiments", []),
            "steps": normalized["steps"],
            "macro_summary": normalized["macro_summary"],
            "search_hints": normalized.get("search_hints", []),
        }
        path.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.reload()
        return next(recipe for recipe in self._recipes if recipe.recipe_id == normalized["recipe_id"])

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

    def list_recipes(
        self,
        locale: str,
        tag: Optional[str] = None,
    ) -> list[Recipe]:
        normalized_tag = normalize_recipe_tag(tag) if tag else None
        recipes = self.recipes_for_locale(locale)
        if normalized_tag:
            recipes = [
                recipe
                for recipe in recipes
                if normalized_tag in {normalize_recipe_tag(item) for item in recipe.tags}
            ]
        return recipes
