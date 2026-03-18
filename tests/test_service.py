from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chef_claw.config import Settings
from chef_claw.parser import parse_checkin_text
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
        recorded = result.data["recorded_items"][0]
        self.assertEqual(recorded["recommended_use_by"], "2026-03-22")

    def test_packaged_item_without_expiry_needs_follow_up(self) -> None:
        result = self.service.checkin(text="milk 1 carton")
        self.assertEqual(result.status, "needs_user_input")
        self.assertEqual(len(result.data["recorded_items"]), 0)
        self.assertIn("expiration date", result.data["follow_up_questions"][0]["question"])

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

    def test_day_plan_prefers_local_recipe_and_includes_snacks(self) -> None:
        self.service.checkin(text="2 tomatoes")
        self.service.checkin(
            text="egg 6 piece expires 2026-03-30",
            checked_in_at=datetime(2026, 3, 18, 9, 0, 0),
        )
        self.service.checkin(
            text="cooking oil 1 bottle expires 2026-08-01, salt 1 pack expires 2027-01-01",
            checked_in_at=datetime(2026, 3, 18, 9, 0, 0),
        )
        result = self.service.plan_day()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["suggestions"][0]["recipe_id"], "tomato-egg-stir-fry")
        self.assertTrue(result.data["snack_suggestions"])

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
        result = self.service.fallback_search_request(preferred_ingredients=["spinach", "tofu"])
        self.assertEqual(result.status, "needs_web_search")
        request = result.data["search_request"]
        self.assertTrue(request["require_video"])
        self.assertIn("video_url", request["expected_fields"])

    def test_weekend_plan_builds_grocery_list(self) -> None:
        self.service.checkin(text="spinach 1 bag")
        result = self.service.plan_weekend()
        self.assertEqual(result.status, "ok")
        self.assertIn("grocery_items", result.data)


if __name__ == "__main__":
    unittest.main()
