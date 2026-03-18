from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    recipes_dir: Path
    pantry_thresholds_path: Path
    host: str = "127.0.0.1"
    port: int = 8000


def get_settings() -> Settings:
    return Settings(
        database_path=Path(
            os.getenv("CHEF_CLAW_DB", ROOT_DIR / "data" / "chef_claw.db")
        ),
        recipes_dir=Path(
            os.getenv("CHEF_CLAW_RECIPES_DIR", ROOT_DIR / "recipes")
        ),
        pantry_thresholds_path=Path(
            os.getenv(
                "CHEF_CLAW_THRESHOLDS",
                ROOT_DIR / "data" / "pantry_thresholds.json",
            )
        ),
        host=os.getenv("CHEF_CLAW_HOST", "127.0.0.1"),
        port=int(os.getenv("CHEF_CLAW_PORT", "8000")),
    )
