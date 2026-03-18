from __future__ import annotations

import sys

from .config import get_settings


def main() -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "uvicorn is not installed. Run `pip install -e .[dev]` first."
        ) from exc

    settings = get_settings()
    uvicorn.run(
        "chef_claw.api:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
