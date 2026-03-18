from __future__ import annotations

import json
from pathlib import Path

from .types import MacroSummary, Recipe, RecipeIngredient


class RecipeRepository:
    def __init__(self, recipes_dir: Path):
        self.recipes_dir = recipes_dir
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        self._recipes = self._load_recipes()

    def _load_recipes(self) -> list[Recipe]:
        recipes: list[Recipe] = []
        for path in sorted(self.recipes_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            recipes.append(
                Recipe(
                    recipe_id=payload["recipe_id"],
                    path=path,
                    title=payload["title"],
                    title_translations=payload.get("title_translations", {}),
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
                )
            )
        return recipes

    @property
    def recipes(self) -> list[Recipe]:
        return list(self._recipes)
