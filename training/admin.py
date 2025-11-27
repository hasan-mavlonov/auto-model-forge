# training/admin.py
from django.contrib import admin
from .models import ModelType, BaseModel, TrainingJob, TrainingImage, ModelArtifact


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


@admin.register(ModelArtifact)
class ModelArtifactAdmin(admin.ModelAdmin):
    list_display = ("job", "download_url", "size_mb", "created_at")
    search_fields = ("job__project_name", "job__public_id")
