from django.contrib import admin

from .models import AIRun, Message, Thread


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("role", "status", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "title", "profile", "created_at")
    list_filter = ("kind",)
    inlines = [MessageInline]


@admin.register(AIRun)
class AIRunAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "model", "status", "cost_usd", "created_at")
    list_filter = ("provider", "status")
