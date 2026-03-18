# Chef Claw

Local kitchen assistant service for OpenClaw. The service manages household inventory, recipe selection, alert generation, and grocery planning while OpenClaw owns messaging, scheduling, and online search.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Run

```bash
chef-claw
```

Or directly:

```bash
uvicorn chef_claw.api:create_app --factory --reload
```

## API Overview

- `POST /checkin`
- `GET /inventory`
- `GET /inventory/query`
- `POST /plan/day`
- `POST /plan/weekend`
- `POST /alerts/expiry`
- `POST /alerts/restock`
- `GET /recipes`
- `POST /recipes`
- `POST /recipes/reload`
- `POST /recipes/fallback-search-request`

## Local Data

- SQLite database: `data/chef_claw.db`
- Recipe files: `recipes/*.json`
- Pantry thresholds: `data/pantry_thresholds.json`

## Notes

- Responses are concise and mobile-oriented.
- Language is mirrored from the `language` field supplied by OpenClaw.
- `locale` is the preferred request field; `language` remains supported for compatibility.
- Web search is not performed in-process. The service returns structured search requests when local recipes are insufficient.
- Recipe creation is file-backed. `POST /recipes` writes a new `recipes/*.json` file and refreshes the in-memory index.
- Recipe listing supports `tag` or `category` filters; values like `meal prep` are normalized to `meal-prep`.
