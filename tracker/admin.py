from django.contrib import admin
from .models import Profile, Job, Application, ApplicationEvent

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("owner", "yoe_min", "yoe_max")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "source", "stage", "score", "first_seen_at")
    list_filter = ("stage", "source")
    search_fields = ("title", "company")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "status", "method", "applied_at")
    list_filter = ("status", "method")


@admin.register(ApplicationEvent)
class ApplicationEventAdmin(admin.ModelAdmin):
    list_display = ("application", "status", "source", "occurred_at")
    list_filter = ("status", "source")