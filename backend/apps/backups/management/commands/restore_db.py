"""``manage.py restore_db <file>`` — restore the DB from a backup archive.

Lives in Python (not the Makefile) so the restore connects with the same
``POSTGRES_*`` credential mapping the backup writer uses — the container only
sets ``POSTGRES_*``, never the ``PG*`` names libpq reads, so a Makefile-built
``pg_restore -h $PGHOST ...`` expands to empty and never connects.
"""

from __future__ import annotations

import subprocess

from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import perform_restore


class Command(BaseCommand):
    help = "Restore the database from a pg_dump archive in /data/backups/."

    def add_arguments(self, parser) -> None:
        parser.add_argument("filename", help="Backup file name inside /data/backups/")

    def handle(self, *args, **opts) -> None:
        filename = opts["filename"]
        try:
            path = perform_restore(filename)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"pg_restore failed (exit {exc.returncode})") from exc
        self.stdout.write(self.style.SUCCESS(f"restored database from {path}"))
