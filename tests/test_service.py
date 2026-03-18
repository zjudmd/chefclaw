from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chef_claw.config import Settings
from chef_claw.i18n import MESSAGES, message_placeholders, resolve_locale
from chef_claw.parser import parse_checkin_text
from chef_claw.recipes import RecipeRepository
from chef_claw.service import KitchenService


class KitchenServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = Settings(
            database_path=Path(self.temp_dir.name) / "chef_claw.db",
            recipes_dir=ROOT / "recipes",
            pantry_thresholds_path=ROOT / "data" / "pantry_thresholds.json",
        )
        self.service = KitchenService(self.settings)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_day_plan_inventory(self) -> None:
        self.service.checkin(text="2 tomatoes")
        self.service.checkin(
            text="egg 6 piece expires 2026-03-30",
            checked_in_at=datetime(2026, 3, 18, 9, 0, 0),
        )
        self.service.checkin(
            text="cooking oil 1 bottle expires 2026-08-01, salt 1 pack expires 2027-01-01",
            checked_in_at=datetime(2026, 3, 18, 9, 0, 0),
        )

    def _make_recipe_service(self) -> KitchenService:
        recipe_dir = Path(self.temp_dir.name) / "recipes"
        recipe_dir.mkdir(parents=True, exist_ok=True)
        return KitchenService(
            Settings(
                database_path=Path(self.temp_dir.name) / f"recipes-{len(list(recipe_dir.glob('*.json')))}.db",
                recipes_dir=recipe_dir,
                pantry_thresholds_path=ROOT / "data" / "pantry_thresholds.json",
            )
        )

    def test_locale_resolution(self) -> None:
        self.assertEqual(resolve_locale("en"), "en")
        self.assertEqual(resolve_locale("en-US"), "en")
        self.assertEqual(resolve_locale("zh"), "zh-Hans")
        self.assertEqual(resolve_locale("zh-CN"), "zh-Hans")
        self.assertEqual(resolve_locale("zh-Hans"), "zh-Hans")

    def test_message_catalog_parity(self) -> None:
        self.assertEqual(set(MESSAGES["en"]), set(MESSAGES["zh-Hans"]))
        for key in MESSAGES["en"]:
            self.assertEqual(
                message_placeholders("en", key),
                message_placeholders("zh-Hans", key),
            )

    def test_parse_english_checkin(self) -> None:
        items = parse_checkin_text("2 tomatoes, spinach 1 bag", datetime(2026, 3, 18, 9, 0, 0))
        self.assertEqual(items[0].canonical_name, "tomato")
        self.assertEqual(items[0].quantity, 2)
        self.assertEqual(items[1].canonical_name, "spinach")
        self.assertEqual(items[1].unit, "bag")

    def test_parse_chinese_checkin(self) -> None:
        items = parse_checkin_text("西红柿2个，菠菜1把", datetime(2026, 3, 18, 9, 0, 0))
        self.assertEqual(items[0].canonical_name, "tomato")
        self.assertEqual(items[0].unit, "piece")
        self.assertEqual(items[1].canonical_name, "spinach")
        self.assertEqual(items[1].unit, "bunch")

    def test_fresh_item_gets_auto_recommended_use_by(self) -> None:
        result = self.service.checkin(
            text="spinach 1 bag",
            checked_in_at=datetime(2026, 3, 18, 9, 0, 0),
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.locale, "en")
        recorded = result.data["recorded_items"][0]
        self.assertEqual(recorded["recommended_use_by"], "2026-03-22")

    def test_packaged_item_without_expiry_needs_follow_up(self) -> None:
        result = self.service.checkin(text="milk 1 carton", locale="en-US")
        self.assertEqual(result.status, "needs_user_input")
        self.assertEqual(len(result.data["recorded_items"]), 0)
        self.assertIn("expiration date", result.data["follow_up_questions"][0]["question"])
        self.assertEqual(result.locale, "en")

    def test_packaged_item_follow_up_is_localized_in_chinese(self) -> None:
        result = self.service.checkin(text="牛奶 1 盒", language="zh")
        self.assertEqual(result.status, "needs_user_input")
        self.assertEqual(result.locale, "zh-Hans")
        self.assertEqual(result.language, "zh")
        self.assertIn("请提供", result.data["follow_up_questions"][0]["question"])

    def test_quantity_updates_are_aggregated(self) -> None:
        self.service.checkin(
            text="2 tomatoes",
            checked_in_at=datetime(2026, 3, 18, 9, 0, 0),
        )
        self.service.checkin(
            text="tomatoes 1",
            checked_in_at=datetime(2026, 3, 18, 10, 0, 0),
        )
        inventory = self.service.get_inventory()
        tomato = next(item for item in inventory.data["items"] if item["canonical_name"] == "tomato")
        self.assertEqual(tomato["quantity"], 3)

    def test_query_vegetables_left(self) -> None:
        self.service.checkin(text="spinach 1 bag, tomato 2")
        result = self.service.query_inventory("What vegetables do we have left?")
        self.assertIn("Spinach", result.response_markdown)
        self.assertIn("Tomato", result.response_markdown)

    def test_chinese_inventory_query_matches_same_semantics(self) -> None:
        self.service.checkin(text="spinach 1 bag, tomato 2")
        result = self.service.query_inventory("还有什么蔬菜？", locale="zh-CN")
        self.assertEqual(result.locale, "zh-Hans")
        self.assertIn("菠菜", result.response_markdown)
        self.assertIn("西红柿", result.response_markdown)

    def test_day_plan_prefers_local_recipe_and_includes_snacks(self) -> None:
        self._seed_day_plan_inventory()
        result = self.service.plan_day()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["suggestions"][0]["recipe_id"], "tomato-egg-stir-fry")
        self.assertTrue(result.data["snack_suggestions"])
        self.assertEqual(result.data["localization_warnings"], [])

    def test_day_plan_is_fully_localized_in_chinese(self) -> None:
        self._seed_day_plan_inventory()
        result = self.service.plan_day(language="zh")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.locale, "zh-Hans")
        self.assertIn("番茄炒蛋", result.response_markdown)
        self.assertIn("加餐建议", result.response_markdown)
        self.assertNotIn("protein", result.response_markdown)
        self.assertNotIn("Snack ideas", result.response_markdown)

    def test_uncertain_inventory_is_not_treated_as_available(self) -> None:
        self.service.checkin(text="spinach")
        result = self.service.plan_day()
        self.assertEqual(result.status, "needs_web_search")

    def test_expiry_and_restock_alerts_are_idempotent(self) -> None:
        self.service.checkin(
            text="spinach 1 bag",
            checked_in_at=datetime(2026, 3, 18, 9, 0, 0),
        )
        first = self.service.expiry_alerts(days_threshold=10)
        second = self.service.expiry_alerts(days_threshold=10)
        self.assertEqual(first.data, second.data)

        restock_one = self.service.restock_alerts()
        restock_two = self.service.restock_alerts()
        self.assertEqual(restock_one.data, restock_two.data)

    def test_fallback_search_request_contract(self) -> None:
        result = self.service.fallback_search_request(
            preferred_ingredients=["spinach", "tofu"],
            locale="zh-Hans",
        )
        self.assertEqual(result.status, "needs_web_search")
        request = result.data["search_request"]
        self.assertEqual(request["locale"], "zh-Hans")
        self.assertEqual(request["language"], "zh")
        self.assertTrue(request["require_video"])
        self.assertIn("video_url", request["expected_fields"])

    def test_weekend_plan_builds_grocery_list(self) -> None:
        self.service.checkin(text="spinach 1 bag")
        result = self.service.plan_weekend()
        self.assertEqual(result.status, "ok")
        self.assertIn("grocery_items", result.data)

    def test_recipe_loader_accepts_zh_alias_and_flags_incomplete_locale(self) -> None:
        with tempfile.TemporaryDirectory() as recipe_dir_name:
            recipe_dir = Path(recipe_dir_name)
            (recipe_dir / "good.json").write_text(
                json.dumps(
                    {
                        "recipe_id": "good",
                        "title": "Good Recipe",
                        "title_translations": {"en": "Good Recipe", "zh": "好菜"},
                        "language": "en",
                        "ingredients": [{"name": "tomato", "quantity": 1, "unit": "piece"}],
                        "condiments": [],
                        "steps": [{"en": "Cook it.", "zh": "做就行。"}],
                        "macro_summary": {"protein": "low", "fiber": "low", "fats": "low"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (recipe_dir / "bad.json").write_text(
                json.dumps(
                    {
                        "recipe_id": "bad",
                        "title": "Bad Recipe",
                        "title_translations": {"en": "Bad Recipe"},
                        "language": "en",
                        "ingredients": [{"name": "spinach", "quantity": 1, "unit": "bag"}],
                        "condiments": [],
                        "steps": [{"en": "Cook it."}],
                        "macro_summary": {"protein": "low", "fiber": "low", "fats": "low"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            repository = RecipeRepository(recipe_dir)
            zh_recipes = repository.recipes_for_locale("zh-Hans")
            warnings = repository.warnings_for_locale("zh-Hans")

            self.assertEqual([recipe.recipe_id for recipe in zh_recipes], ["good"])
            self.assertTrue(any(warning.recipe_id == "bad" for warning in warnings))

    def test_backward_compat_language_argument(self) -> None:
        self.service.checkin(text="spinach 1 bag")
        result = self.service.get_inventory(language="zh")
        self.assertEqual(result.locale, "zh-Hans")
        self.assertEqual(result.language, "zh")
        self.assertIn("当前库存", result.response_markdown)

    def test_create_recipe_and_list_by_meal_prep_tag(self) -> None:
        service = self._make_recipe_service()
        create_result = service.create_recipe(
            recipe_payload={
                "title_translations": {
                    "en": "Lemon Chicken Prep",
                    "zh": "柠檬鸡肉备餐",
                },
                "tags": ["meal prep", "personal"],
                "proficiency": "established",
                "source_type": "personal",
                "ingredients": [
                    {"name": "chicken breast", "quantity": 1, "unit": "piece"},
                    {"name": "broccoli", "quantity": 1, "unit": "piece"},
                ],
                "condiments": ["soy sauce", "salt"],
                "steps": [
                    {"en": "Season and sear the chicken.", "zh": "调味后煎鸡肉。"},
                    {"en": "Cook broccoli and portion for the week.", "zh": "炒西兰花并分装。"},
                ],
                "macro_summary": {
                    "protein": "high",
                    "fiber": "medium",
                    "fats": "low",
                },
                "search_hints": ["meal prep"],
            },
            language="en",
        )
        self.assertEqual(create_result.status, "ok")
        recipe = create_result.data["recipe"]
        self.assertEqual(recipe["recipe_id"], "lemon-chicken-prep")
        self.assertIn("meal-prep", recipe["tags"])
        self.assertTrue((service.settings.recipes_dir / "lemon-chicken-prep.json").exists())

        list_result = service.list_recipes(tag="meal prep", language="zh")
        self.assertEqual(list_result.data["filter_tag"], "meal-prep")
        self.assertEqual(len(list_result.data["recipes"]), 1)
        self.assertEqual(list_result.data["recipes"][0]["title"], "柠檬鸡肉备餐")

        category_result = service.list_recipes(category="meal-prep")
        self.assertEqual(len(category_result.data["recipes"]), 1)

    def test_reload_recipes_picks_up_new_file(self) -> None:
        service = self._make_recipe_service()
        before = service.list_recipes()
        self.assertEqual(before.data["recipes"], [])

        (service.settings.recipes_dir / "manual-prep.json").write_text(
            json.dumps(
                {
                    "recipe_id": "manual-prep",
                    "title": "Manual Prep",
                    "title_translations": {
                        "en": "Manual Prep",
                        "zh": "手动备餐",
                    },
                    "language": "en",
                    "tags": ["meal prep"],
                    "proficiency": "established",
                    "source_type": "personal",
                    "ingredients": [{"name": "rice", "quantity": 1, "unit": "kg"}],
                    "condiments": ["salt"],
                    "steps": [{"en": "Cook and portion.", "zh": "煮好后分装。"}],
                    "macro_summary": {
                        "protein": "low",
                        "fiber": "low",
                        "fats": "low",
                    },
                    "search_hints": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        reload_result = service.reload_recipes(language="en")
        self.assertEqual(reload_result.status, "ok")
        self.assertEqual(reload_result.data["recipe_count"], 1)

        after = service.list_recipes(tag="meal prep")
        self.assertEqual(len(after.data["recipes"]), 1)
        self.assertEqual(after.data["recipes"][0]["recipe_id"], "manual-prep")

    def test_create_recipe_requires_bilingual_content(self) -> None:
        service = self._make_recipe_service()
        with self.assertRaises(ValueError):
            service.create_recipe(
                recipe_payload={
                    "title_translations": {"en": "Broken Recipe"},
                    "tags": ["meal prep"],
                    "ingredients": [{"name": "rice", "quantity": 1, "unit": "kg"}],
                    "condiments": [],
                    "steps": [{"en": "Cook rice."}],
                    "macro_summary": {
                        "protein": "low",
                        "fiber": "low",
                        "fats": "low",
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
