from django.core.management.base import BaseCommand

from apps.recall.services.index import index_one, pending


class Command(BaseCommand):
    help = "Backfill RecallDocument index for all unindexed sources."

    def handle(self, *args, **options):
        items = pending(cap=10**9)
        total = len(items)
        self.stdout.write(f"Backfilling {total} documents...")
        for i, (kind, object_id) in enumerate(items, 1):
            index_one(kind, object_id)
            if i % 50 == 0 or i == total:
                self.stdout.write(f"  {i}/{total}")
        self.stdout.write(self.style.SUCCESS(f"Done. Indexed {total} documents."))
