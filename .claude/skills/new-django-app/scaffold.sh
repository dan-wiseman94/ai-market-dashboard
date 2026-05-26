#!/usr/bin/env bash
# Scaffold a new Django app in backend/apps/<name>/ using this repo's layout.
# Usage: bash .claude/skills/new-django-app/scaffold.sh <name>
set -euo pipefail

name="${1:-}"
if [ -z "$name" ] || ! printf '%s' "$name" | grep -Eq '^[a-z][a-z0-9_]*$'; then
  echo "usage: scaffold.sh <app_name>   (lowercase; [a-z0-9_]; must start with a letter)" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
app_dir="$repo_root/backend/apps/$name"

if [ -e "$app_dir" ]; then
  echo "✗ $app_dir already exists — aborting" >&2
  exit 1
fi

# CamelCase class name: second_brain -> SecondBrain
camel="$(printf '%s' "$name" | sed -E 's/(^|_)([a-z0-9])/\U\2/g')"

mkdir -p "$app_dir/migrations" "$app_dir/tests"
: > "$app_dir/__init__.py"
: > "$app_dir/migrations/__init__.py"
: > "$app_dir/tests/__init__.py"

cat > "$app_dir/apps.py" <<EOF
from django.apps import AppConfig


class ${camel}Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.$name"
    label = "$name"
EOF

cat > "$app_dir/models.py" <<'EOF'
from django.db import models  # noqa: F401

# Define models here.
EOF

cat > "$app_dir/views.py" <<'EOF'
# DRF views for this app.
EOF

cat > "$app_dir/urls.py" <<'EOF'
from django.urls import path

urlpatterns: list = []
EOF

echo "✓ created $app_dir"
echo
echo "Next — wiring (ORDER MATTERS):"
echo "  1. backend/config/settings/base.py  →  add \"apps.$name\" to INSTALLED_APPS"
echo "  2. backend/config/urls.py           →  path(\"api/$name/\", include(\"apps.$name.urls\")),"
echo "     Place it with the SPECIFIC /api/<name>/ includes, BEFORE any generic /api/ include."
echo "  3. (WS?)  add consumers.py + register the route in backend/config/routing.py"
echo "  4. (tasks?) add the task module to the explicit list in backend/config/celery.py"
echo "  5. (models?) make makemigrations && make migrate"
