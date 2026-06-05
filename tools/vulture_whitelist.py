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
