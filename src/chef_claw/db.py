from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from .types import InventoryBatch, PantryThreshold, ParsedIngredient, Recipe


SCHEMA = """
CREATE TABLE IF NOT EXISTS ingredient_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    display_name_en TEXT NOT NULL,
    display_name_zh TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    category TEXT NOT NULL,
    item_group TEXT NOT NULL,
    freshness_type TEXT NOT NULL,
    checked_in_at TEXT NOT NULL,
    expiration_date TEXT,
    recommended_use_by TEXT,
    uncertain INTEGER NOT NULL DEFAULT 0,
    source_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pantry_thresholds (
    canonical_name TEXT PRIMARY KEY,
    display_name_en TEXT NOT NULL,
    display_name_zh TEXT NOT NULL,
    threshold_quantity REAL,
    unit TEXT,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_index_cache (
    recipe_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    title TEXT NOT NULL,
    language TEXT NOT NULL,
    proficiency TEXT NOT NULL,
    source_type TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    ingredients_json TEXT NOT NULL,
    condiments_json TEXT NOT NULL,
    macro_json TEXT NOT NULL,
    search_hints_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _serialize_date(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def insert_batch(self, item: ParsedIngredient, household_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ingredient_batches (
                    household_id,
                    canonical_name,
                    display_name_en,
                    display_name_zh,
                    quantity,
                    unit,
                    category,
                    item_group,
                    freshness_type,
                    checked_in_at,
                    expiration_date,
                    recommended_use_by,
                    uncertain,
                    source_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    household_id,
                    item.canonical_name,
                    item.display_name_en,
                    item.display_name_zh,
                    item.quantity,
                    item.unit,
                    item.category,
                    item.item_group,
                    item.freshness_type,
                    item.checked_in_at.isoformat(),
                    _serialize_date(item.expiration_date),
                    _serialize_date(item.recommended_use_by),
                    1 if item.uncertain else 0,
                    item.source_text,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def record_event(
        self,
        household_id: str,
        event_type: str,
        canonical_name: str,
        payload: dict[str, object],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO inventory_events (
                    household_id,
                    event_type,
                    canonical_name,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    household_id,
                    event_type,
                    canonical_name,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.utcnow().isoformat(),
                ),
            )
            connection.commit()

    def list_batches(self, household_id: str) -> list[InventoryBatch]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM ingredient_batches
                WHERE household_id = ?
                ORDER BY checked_in_at DESC, id DESC
                """,
                (household_id,),
            ).fetchall()
        return [
            InventoryBatch(
                batch_id=int(row["id"]),
                household_id=row["household_id"],
                canonical_name=row["canonical_name"],
                display_name_en=row["display_name_en"],
                display_name_zh=row["display_name_zh"],
                quantity=row["quantity"],
                unit=row["unit"],
                category=row["category"],
                item_group=row["item_group"],
                freshness_type=row["freshness_type"],
                checked_in_at=_parse_datetime(row["checked_in_at"]),
                expiration_date=_parse_date(row["expiration_date"]),
                recommended_use_by=_parse_date(row["recommended_use_by"]),
                uncertain=bool(row["uncertain"]),
                source_text=row["source_text"],
            )
            for row in rows
        ]

    def replace_thresholds(self, thresholds: Iterable[PantryThreshold]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM pantry_thresholds")
            connection.executemany(
                """
                INSERT INTO pantry_thresholds (
                    canonical_name,
                    display_name_en,
                    display_name_zh,
                    threshold_quantity,
                    unit,
                    category
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        threshold.canonical_name,
                        threshold.display_name_en,
                        threshold.display_name_zh,
                        threshold.threshold_quantity,
                        threshold.unit,
                        threshold.category,
                    )
                    for threshold in thresholds
                ],
            )
            connection.commit()

    def list_thresholds(self) -> list[PantryThreshold]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pantry_thresholds ORDER BY canonical_name"
            ).fetchall()
        return [
            PantryThreshold(
                canonical_name=row["canonical_name"],
                display_name_en=row["display_name_en"],
                display_name_zh=row["display_name_zh"],
                threshold_quantity=row["threshold_quantity"],
                unit=row["unit"],
                category=row["category"],
            )
            for row in rows
        ]

    def replace_recipe_cache(self, recipes: Iterable[Recipe]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM recipe_index_cache")
            connection.executemany(
                """
                INSERT INTO recipe_index_cache (
                    recipe_id,
                    file_path,
                    title,
                    language,
                    proficiency,
                    source_type,
                    tags_json,
                    ingredients_json,
                    condiments_json,
                    macro_json,
                    search_hints_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        recipe.recipe_id,
                        str(recipe.path),
                        recipe.title,
                        recipe.language,
                        recipe.proficiency,
                        recipe.source_type,
                        json.dumps(recipe.tags, ensure_ascii=False),
                        json.dumps(
                            [asdict(ingredient) for ingredient in recipe.ingredients],
                            ensure_ascii=False,
                        ),
                        json.dumps(recipe.condiments, ensure_ascii=False),
                        json.dumps(asdict(recipe.macro_summary), ensure_ascii=False),
                        json.dumps(recipe.search_hints, ensure_ascii=False),
                        datetime.utcnow().isoformat(),
                    )
                    for recipe in recipes
                ],
            )
            connection.commit()
