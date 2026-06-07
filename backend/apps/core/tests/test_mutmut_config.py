"""Guard: every path mutmut is told to mutate or test must exist on disk.

The nightly mutation gate silently no-ops the *entire* run if `setup.cfg`'s
`[mutmut]` test-selection points at a path that no longer exists: pytest exits
with code 4 (usage error) on a missing collection path and bails *before*
running the valid paths, mutmut crashes on that exit, and
`.github/workflows/mutation.yml`'s `|| true` swallows the crash into a green
check. This exact regression happened when the 27->15 app consolidation moved
`apps/triggers` -> `apps/observer/triggers` without updating `setup.cfg`, so the
money-path mutation gate (ai/cost, ai/catalog, market/returns, thesis/postmortem)
went dead and unreported. This guard turns a stale path into a loud per-commit
failure in the normal suite instead of a silent nightly no-op.
"""

import configparser
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[3]
_SETUP_CFG = _BACKEND / "setup.cfg"


def _mutmut_values(key: str) -> list[str]:
    parser = configparser.ConfigParser()
    parser.read(_SETUP_CFG)
    return [tok.strip() for tok in parser["mutmut"][key].split() if tok.strip()]


@pytest.mark.parametrize("rel", _mutmut_values("paths_to_mutate"))
def test_mutmut_paths_to_mutate_exist(rel: str) -> None:
    assert (_BACKEND / rel).exists(), (
        f"setup.cfg [mutmut] paths_to_mutate references a missing path: {rel!r}. "
        "A stale mutate-target silently drops it from the nightly mutation gate."
    )


@pytest.mark.parametrize("rel", _mutmut_values("pytest_add_cli_args_test_selection"))
def test_mutmut_test_selection_dirs_exist(rel: str) -> None:
    assert (_BACKEND / rel).is_dir(), (
        f"setup.cfg [mutmut] pytest_add_cli_args_test_selection references a "
        f"missing dir: {rel!r}. pytest exits 4 on a missing collection path and "
        "bails before the valid paths, silently no-op-ing the whole mutation run."
    )
