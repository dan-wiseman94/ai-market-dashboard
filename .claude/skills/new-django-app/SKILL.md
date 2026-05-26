---
name: new-django-app
description: >-
  Scaffold a new Django app in this repo (backend/apps/<name>/) with the exact layout and wiring
  this project uses — AppConfig with label, urls.py, INSTALLED_APPS entry, and the config/urls.py
  include placed BEFORE the generic /api/ include. Use when adding a new backend app.
---

# Add a Django app

This repo uses a fixed, order-sensitive recipe for new apps (CLAUDE.md → "Adding a Django app").
Follow it exactly — the URL include ordering is a documented footgun.

## Steps

1. **Scaffold the files.** Run the bundled script with a lowercase snake_case app name:
   ```bash
   bash "$CLAUDE_PROJECT_DIR/.claude/skills/new-django-app/scaffold.sh" <name>
   ```
   It creates `backend/apps/<name>/` with `__init__.py`, `apps.py` (AppConfig with
   `name = "apps.<name>"` + `label`), `models.py`, `views.py`, `urls.py`, and `migrations/` +
   `tests/` packages. It refuses to overwrite an existing app.

2. **Register the app.** Add `"apps.<name>"` to `INSTALLED_APPS` in
   `backend/config/settings/base.py`.

3. **Wire the URLs — ORDER MATTERS.** In `backend/config/urls.py` add:
   ```python
   path("api/<name>/", include("apps.<name>.urls")),
   ```
   Place it among the SPECIFIC `/api/<name>/` includes, **before** any generic `/api/` include.
   Putting it after a generic include silently routes requests to the wrong app (documented
   regression).

4. **WebSocket consumers (only if needed).** Add `consumers.py` and register the route in
   `backend/config/routing.py`. Join the group in `connect()`, leave it in `disconnect()`.

5. **Celery tasks (only if needed).** If you add a `tasks.py`, also add its module to the
   explicit list in `backend/config/celery.py` — tasks are NOT autodiscovered and will silently
   never run otherwise.

6. **Migrate** (only if you added models): `make makemigrations && make migrate`.

7. **Verify:** `make lint`, then a quick test pass for the new app.

After wiring, consider running the `conventions-reviewer` subagent on the diff.
