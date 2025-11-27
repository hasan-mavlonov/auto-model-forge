# training/admin.py
from django.contrib import admin, messages

from .models import BaseModel, ModelType, ModelArtifact, TrainingImage, TrainingJob


@admin.register(ModelType)
class ModelTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "base_price", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BaseModel)
class BaseModelAdmin(admin.ModelAdmin):
    list_display = ("name", "identifier", "is_active")
    list_filter = ("is_active",)


class TrainingImageInline(admin.TabularInline):
    model = TrainingImage
    extra = 0

def mark_as_paid(modeladmin, request, queryset):
    updated = 0
    skipped = 0

    for job in queryset:
        if job.status in {
            TrainingJob.Status.CREATED,
            TrainingJob.Status.AWAITING_PAYMENT,
            TrainingJob.Status.PAYMENT_SUBMITTED,
        }:
            job.mark_as_paid()
            updated += 1
        else:
            skipped += 1

    if updated:
        modeladmin.message_user(
            request,
            f"Marked {updated} job(s) as paid and started their deadlines.",
            level=messages.SUCCESS,
        )

    if skipped:
        modeladmin.message_user(
            request,
            f"Skipped {skipped} job(s) already paid or in later states.",
            level=messages.WARNING,
        )
mark_as_paid.short_description = "Mark selected jobs as PAID and start 24h deadline"

@admin.register(TrainingJob)
class TrainingJobAdmin(admin.ModelAdmin):
    list_display = (
        "project_name",
        "user",
        "model_type",
        "base_model",
        "num_images",
        "total_price",
        "status",
        "created_at",
        "paid_at",
        "deadline_at",
        "completed_at",
    )
    list_filter = ("status", "model_type", "base_model", "created_at")
    search_fields = ("project_name", "user__username", "public_id")
    readonly_fields = ("public_id", "created_at", "paid_at", "deadline_at", "completed_at")
    inlines = [TrainingImageInline]
    actions = [mark_as_paid]


@admin.register(ModelArtifact)
class ModelArtifactAdmin(admin.ModelAdmin):
    list_display = ("job", "download_url", "size_mb", "created_at")
    search_fields = ("job__project_name", "job__public_id")

