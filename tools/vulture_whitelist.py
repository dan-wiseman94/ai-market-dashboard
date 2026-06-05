# Vulture whitelist — names that are framework-required but read as "unused" to static
# analysis (Django ORM/Field signatures, DRF hooks, attributes set for side effects).
# Vulture scans this file too; referencing a name here suppresses its "unused" report.
# Keep each entry commented with WHY it's required so the list stays honest.
#
# Add entries as:  _ = SomeClass.some_attr   (or)   SomeClass().method
# Run `make vulture` to see current findings, then triage: real dead code → delete it;
# framework-required → add here with a reason.

expression  # Django Field.from_db_value(self, value, expression, connection) — positional
            # framework signature; required by the ORM even though unused (apps/secrets/fields.py)

vix_percentile  # KNOWN GAP (not dead code): regime services/compute.py PASSES this into
                # classify_volatility() and services/inputs.py COMPUTES it (real percentile-of-
                # history math), yet classify_volatility() ignores it — it only thresholds the
                # absolute vix_last. Percentile-aware volatility classification was stubbed in the
                # signature but never implemented. Kept as a reserved param (removing it would drop
                # the wired-in percentile) pending a modeling decision. Flagged in the PR.
