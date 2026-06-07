"""Manual offline AI evaluation harness.

Replays a candidate (system prompt, model) against the frozen source snapshots
of past theses whose outcome is known, and scores the model's directional call
against the objective verdict (directional hit-rate + Brier).

This calls the REAL model once per labeled row → real $$. It is therefore a
MANUAL command (never a beat task / never auto-run): respects the provider's
configured daily + monthly cost caps via a pre-flight check (aborts with
CommandError if already over) and supports ``--limit`` for cheap smoke runs.
In MOCK_EXTERNAL mode / under test the model call is mocked, so it is free.

    manage.py aieval --model claude-opus-4-8 --system-file prompt.txt
    manage.py aieval --model claude-sonnet-4-6 --system-file - --horizon 30 --limit 5
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand, CommandError

from apps.ai.cost import CostCapExceededError
from apps.analytics.services.aieval import (
    DEFAULT_EVAL_SYSTEM,
    evaluate,
    persist_eval_run,
    preflight_cost_cap,
)


class Command(BaseCommand):
    help = "Replay a candidate (system prompt, model) against labeled past theses and score it."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--model", required=True, help="Model id to evaluate, e.g. claude-opus-4-8"
        )
        parser.add_argument(
            "--system-file",
            default=None,
            help="Path to a file holding the system prompt, or '-' to read stdin. "
            "Omit for a built-in default prompt.",
        )
        parser.add_argument(
            "--horizon", type=int, default=None, help="Post-mortem horizon (7/30/90)."
        )
        parser.add_argument(
            "--limit", type=int, default=None, help="Cap how many labeled rows to replay."
        )
        parser.add_argument(
            "--label", default="baseline", help="Label for this variant in the results."
        )

    def _read_system(self, system_file: str | None) -> str:
        if not system_file:
            return DEFAULT_EVAL_SYSTEM
        if system_file == "-":
            return sys.stdin.read().strip() or DEFAULT_EVAL_SYSTEM
        try:
            with open(system_file, encoding="utf-8") as fh:
                return fh.read().strip() or DEFAULT_EVAL_SYSTEM
        except OSError as exc:
            raise CommandError(f"could not read --system-file {system_file!r}: {exc}") from exc

    def handle(self, *args, **options) -> None:
        system = self._read_system(options["system_file"])

        try:
            preflight_cost_cap("claude")
        except CostCapExceededError as exc:
            raise CommandError(str(exc)) from exc

        res = evaluate(
            system=system,
            model=options["model"],
            label=options["label"],
            horizon=options["horizon"],
            limit=options["limit"],
        )

        if res["n"] == 0:
            self.stdout.write(
                self.style.WARNING(
                    "no labeled data yet — need theses with a frozen snapshot AND a "
                    "decisive post-mortem (verdict correct/incorrect, forward return known)."
                )
            )
            return

        persist_eval_run(res, source="manual")

        self.stdout.write(
            self.style.SUCCESS(
                f"variant={res['label']} model={res['model']} "
                f"n={res['n']} scored={res['scored']} skipped={res['skipped']} "
                f"hit_rate={res['hit_rate']} brier={res['brier']} "
                f"avg_confidence={res['avg_confidence']}"
            )
        )
        for r in res["examples"]:
            self.stdout.write(
                f"  predicted={r['predicted_direction']} "
                f"outcome={r['outcome_direction']} "
                f"verdict={r['actual_verdict']} "
                f"confidence={r['confidence']} hit={r['hit']}"
            )

        # Calibration reliability table
        non_empty = [b for b in res.get("calibration", []) if b["n"] > 0]
        if non_empty:
            self.stdout.write("\ncalibration reliability curve:")
            for b in non_empty:
                self.stdout.write(
                    f"  conf [{b['bin_low']:.2f},{b['bin_high']:.2f}): "
                    f"n={b['n']} observed={b['observed_hit_rate']} stated={b['mean_confidence']}"
                )
            if res.get("calibration_error") is not None:
                self.stdout.write(
                    f"calibration_error (mean|observed-stated|)={res['calibration_error']}"
                )
