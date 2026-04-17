from typing import ClassVar

from django.contrib import admin

from .models import Snapshot, SnapshotSection


class SnapshotSectionInline(admin.TabularInline):
    model = SnapshotSection
    extra = 0


@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "status", "source", "captured_at")
    list_filter = ("status", "source")
    inlines: ClassVar = [SnapshotSectionInline]
