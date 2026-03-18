# Chef Claw 🍳🦞

<p align="center">
  <img src="assets/chefclaw_avatar.jpg" alt="Chef Claw avatar" width="280">
</p>

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

Helper scripts:

```bash
./scripts/start-local.sh
./scripts/healthcheck-local.sh
```

## Optional: run as a user service

To keep Chef Claw running under your user account via systemd:

```bash
./scripts/install-user-service.sh
```

Then manage it with:

```bash
systemctl --user status chef-claw
systemctl --user restart chef-claw
systemctl --user stop chef-claw
```

## API Overview

- `GET /health`
- `POST /checkin`
- `GET /inventory`
- `GET /inventory/query`
- `POST /inventory/consume`
- `PATCH /inventory/batches/{id}`
- `DELETE /inventory/batches/{id}`
- `POST /plan/day`
- `POST /plan/weekend`
- `POST /alerts/expiry`
- `POST /alerts/restock`
- `GET /recipes`
- `POST /recipes`
- `POST /recipes/reload`
- `POST /recipes/fallback-search-request`

## API Notes

- Responses include both `locale` and backward-compatible `language`.
- `locale` is the preferred request field. `language` remains supported for compatibility.
- `GET /inventory` returns both aggregated `data.items` and batch-level `data.batches`. Use the `batch_id` values in `data.batches` or `data.items[*].batch_ids` when calling batch mutation APIs.
- `POST /inventory/consume` consumes confirmed stock only. It will not partially consume if the confirmed quantity is insufficient, and it surfaces uncertain batches in the response for OpenClaw follow-up.
- `PATCH /inventory/batches/{id}` corrects an existing batch in place. If the updated item is packaged, `expiration_date` is required.
- `DELETE /inventory/batches/{id}` removes a single inventory batch.
- `GET /recipes` supports either `tag` or `category` as a filter. Values like `meal prep`, `meal-prep`, and `meal_prep` are normalized to `meal-prep`.
- `POST /recipes` writes a new `recipes/*.json` file and refreshes the in-memory recipe index.
- `POST /recipes/reload` rescans the recipe directory and returns any localization warnings for the selected locale.
- Recipe listing, planning, and reload responses may include `localization_warnings` when a recipe is incomplete for a locale.

## Inventory Mutation Payloads

Consume confirmed stock:

```json
{
  "locale": "en",
  "household_id": "default",
  "item_name": "egg",
  "quantity": 2,
  "unit": "piece"
}
```

Patch a batch:

```json
{
  "locale": "en",
  "household_id": "default",
  "quantity": 8,
  "expiration_date": "2026-03-30"
}
```

Delete a batch:

```bash
curl -X DELETE 'http://127.0.0.1:8000/inventory/batches/12?locale=en&household_id=default'
```

## Recipe Create Payload

`POST /recipes` expects curated bilingual content. English and Simplified Chinese titles and every step translation are required.

Example:

```json
{
  "locale": "en",
  "recipe_id": "lemon-chicken-prep",
  "title_translations": {
    "en": "Lemon Chicken Prep",
    "zh": "柠檬鸡肉备餐"
  },
  "tags": ["meal prep", "personal"],
  "proficiency": "established",
  "source_type": "personal",
  "ingredients": [
    {"name": "chicken breast", "quantity": 1, "unit": "piece"},
    {"name": "broccoli", "quantity": 1, "unit": "piece"}
  ],
  "condiments": ["soy sauce", "salt"],
  "steps": [
    {"en": "Season and sear the chicken.", "zh": "调味后煎鸡肉。"},
    {"en": "Cook broccoli and portion for the week.", "zh": "炒西兰花并分装。"}
  ],
  "macro_summary": {
    "protein": "high",
    "fiber": "medium",
    "fats": "low"
  },
  "search_hints": ["meal prep"]
}
```

Validation rules:

- `title_translations.en` and `title_translations.zh`/`zh-Hans` are required.
- At least one ingredient is required.
- At least one step is required.
- Every step must include both English and Simplified Chinese text.
- `macro_summary` is required.
- If `recipe_id` is omitted, it is generated from the English title.

## Local Data

- SQLite database: `data/chef_claw.db`
- Recipe files: `recipes/*.json`
- Pantry thresholds: `data/pantry_thresholds.json`

## Notes

- Responses are concise and mobile-oriented.
- Language is mirrored from the `language` field supplied by OpenClaw.
- Web search is not performed in-process. The service returns structured search requests when local recipes are insufficient.
- Recipe familiarity is represented by `source_type: "personal"` and `proficiency: "established"`.
- `meal-prep` is supported as a tag/category filter for listing, but planning does not yet filter or rank recipes by tag.

## License

MIT. See `LICENSE`.
