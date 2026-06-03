"""Invariant guards for Celery task registration and the beat schedule.

CLAUDE.md landmine: task modules are listed **explicitly** in config/celery.py
because a past startup-ordering bug made bare autodiscovery untrustworthy.  That
makes the list a thing a human must remember to update — exactly the kind of
silent failure these guards turn into a red test.  Failure modes covered:

  * a new ``apps/<x>/tasks.py`` wired into ``beat_schedule`` but never added to
    the autodiscover list  ->  task silently unregistered  ->  beat fires a
    ``NotRegistered`` task into the void;
  * a renamed/typo'd entry in the autodiscover list  ->  Celery swallows the
    ImportError and skips it silently;
  * a typo'd ``task`` name in a beat entry  ->  schedules a task that never runs.
"""

import importlib.util

import pytest

from config.celery import TASK_PACKAGES, app


@pytest.fixture(scope="module", autouse=True)
def _finalize_celery():
    """Run the same task discovery the worker/beat do at boot, so ``app.tasks``
    is fully populated regardless of test import order."""
    app.loader.import_default_modules()
    app.finalize()


def test_every_autodiscover_package_has_importable_tasks_module():
    """A typo'd / renamed entry in TASK_PACKAGES is otherwise silent — autodiscover
    catches the ImportError and skips the module, dropping all its tasks.

    ``find_spec`` locates the module without executing it (and raises if the parent
    package path itself is bogus), so a missing/misspelled entry fails loudly here."""
    for pkg in TASK_PACKAGES:
        spec = importlib.util.find_spec(f"{pkg}.tasks")
        assert spec is not None, (
            f"{pkg!r} is listed in config.celery.TASK_PACKAGES but has no importable 'tasks' module"
        )


def test_every_beat_task_is_registered():
    """Every scheduled task name must resolve to a registered Celery task."""
    registered = set(app.tasks.keys())
    unregistered = {
        entry["task"]
        for entry in app.conf.beat_schedule.values()
        if entry["task"] not in registered
    }
    assert not unregistered, (
        f"beat_schedule references unregistered task(s): {sorted(unregistered)} — "
        "either the task name is misspelled or its app is missing from "
        "config.celery.TASK_PACKAGES"
    )


def test_every_beat_task_app_is_in_autodiscover_list():
    """Structural guard (independent of registration timing): the app that owns
    each beat task — the prefix of its dotted name — must appear in TASK_PACKAGES."""
    covered = {pkg.split(".")[-1] for pkg in TASK_PACKAGES}  # {"market", "observer", ...}
    for name, entry in app.conf.beat_schedule.items():
        owner = entry["task"].split(".")[0]
        assert owner in covered, (
            f"beat entry {name!r} schedules {entry['task']!r}, owned by app "
            f"{owner!r}, which is not in config.celery.TASK_PACKAGES"
        )
