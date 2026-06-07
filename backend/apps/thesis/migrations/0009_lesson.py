"""Move Lesson from the removed apps.lessons into apps.thesis, preserving the table
(and its M2M through table). State: CreateModel(thesis.Lesson, db_table="lessons_lesson").
Database: a following RunPython that creates lessons_lesson (+ the lessons_lesson_evidence
M2M table) only if missing — a fresh DB builds them with Django's DDL; an existing DB
keeps them untouched. The M2M targets thesis.PostMortem (same app, guaranteed present).
"""

from django.db import migrations, models


def _create_table_if_missing(apps, schema_editor):
    if "lessons_lesson" in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(apps.get_model("thesis", "Lesson"))


def _drop_table(apps, schema_editor):
    schema_editor.delete_model(apps.get_model("thesis", "Lesson"))


class Migration(migrations.Migration):

    dependencies = [
        ("thesis", "0008_position"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Lesson",
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
                        ("text", models.TextField(help_text="Representative bullet of the cluster.")),
                        ("embedding", models.JSONField(blank=True, null=True)),
                        ("tags", models.JSONField(default=dict)),
                        (
                            "support_n",
                            models.PositiveIntegerField(
                                default=0,
                                help_text="Number of post-mortems supporting this lesson.",
                            ),
                        ),
                        (
                            "muted",
                            models.BooleanField(
                                default=False, help_text="Hidden from the coach when True."
                            ),
                        ),
                        ("last_seen", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "evidence",
                            models.ManyToManyField(
                                blank=True, related_name="lessons", to="thesis.postmortem"
                            ),
                        ),
                    ],
                    options={
                        "db_table": "lessons_lesson",
                        "ordering": ["-support_n", "-last_seen"],
                        "indexes": [
                            models.Index(
                                fields=["muted", "-support_n"], name="lessons_les_muted_44468c_idx"
                            )
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(_create_table_if_missing, _drop_table),
    ]
