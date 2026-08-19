"""Guard: every [tool.vulture] path must be COPY'd into the backend image.

`make vulture` runs inside the web container (`exec -w /app web uv run
vulture`), so vulture can only scan what backend/Dockerfile copies into /app.
A pyproject path the image never receives makes vulture error out before
scanning anything, and the advisory target reports success anyway — silently
no-op-ing the whole dead-code sweep (this happened with
tools/vulture_whitelist.py). This guard turns that drift into a loud
per-commit failure in the normal suite.
"""

import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOCKERFILE = _REPO_ROOT / "backend" / "Dockerfile"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _vulture_paths() -> list[str]:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["tool"]["vulture"]["paths"]


def _dockerfile_copy_sources() -> set[str]:
    sources: set[str] = set()
    for raw in _DOCKERFILE.read_text().splitlines():
        line = raw.strip()
        if not line.upper().startswith("COPY ") or "--from=" in line:
            continue
        tokens = [tok for tok in line.split()[1:] if not tok.startswith("--")]
        sources.update(tokens[:-1])
    return sources


@pytest.mark.parametrize("rel", _vulture_paths())
def test_vulture_paths_are_copied_into_image(rel: str) -> None:
    sources = _dockerfile_copy_sources()
    top = rel.split("/", 1)[0]
    assert rel in sources or top in sources, (
        f"pyproject.toml [tool.vulture] paths references {rel!r}, but "
        "backend/Dockerfile never COPYs it into the image — `make vulture` "
        "errors before scanning anything, and the advisory target hides that."
    )
