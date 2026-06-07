"""Move UserFile from the removed apps.files into apps.threads, preserving the table.

State: CreateModel(threads.UserFile, db_table="files_userfile").
Database: a RunPython that creates the table ONLY when missing —
  - fresh DB (CI/new install): apps.files no longer exists to run its 0001, so this
    creates files_userfile with Django's own DDL;
  - existing DB: the table is already there (the old apps.files.0001 created it), so
    we skip and only move the ORM state.
This makes the app removal clean (no tombstone) and safe on both DB shapes.
"""

from django.db import migrations, models


def _create_table_if_missing(apps, schema_editor):
    if "files_userfile" in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(apps.get_model("threads", "UserFile"))


def _drop_table(apps, schema_editor):
    schema_editor.delete_model(apps.get_model("threads", "UserFile"))


class Migration(migrations.Migration):
    dependencies = [
        ("threads", "0008_alter_airun_message"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="UserFile",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("anthropic_id", models.CharField(max_length=64, unique=True)),
                        (
                            "kind",
                            models.CharField(
                                choices=[
                                    ("filing", "SEC filing"),
                                    ("transcript", "Earnings transcript"),
                                    ("ohlc_csv", "Historical OHLC CSV"),
                                    ("research", "Research PDF"),
                                    ("other", "Other"),
                                ],
                                default="other",
                                max_length=16,
                            ),
                        ),
                        (
                            "ticker",
                            models.CharField(blank=True, db_index=True, default="", max_length=16),
                        ),
                        ("mime", models.CharField(default="application/octet-stream", max_length=64)),
                        ("size", models.BigIntegerField(default=0)),
                        ("filename", models.CharField(blank=True, default="", max_length=200)),
                        ("uploaded_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                    ],
                    options={"db_table": "files_userfile", "ordering": ["-uploaded_at"]},
                ),
            ],
            database_operations=[],
        ),
        # Separate op (NOT nested in database_operations above) so the RunPython
        # sees UserFile in the migration state that the SeparateDatabaseAndState
        # just added — and uses that state model, so it stays correct if a later
        # migration alters UserFile on a fresh build.
        migrations.RunPython(_create_table_if_missing, _drop_table),
    ]
