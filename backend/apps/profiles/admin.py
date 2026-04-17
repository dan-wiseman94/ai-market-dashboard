from django.contrib import admin

from .models import Watchlist, WatchlistSymbol


class WatchlistSymbolInline(admin.TabularInline):
    model = WatchlistSymbol
    extra = 1


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    inlines = [WatchlistSymbolInline]
