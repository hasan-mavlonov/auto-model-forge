# training/models.py
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class ModelType(models.Model):
    """Character / Face / Object with base prices."""
    slug = models.SlugField(unique=True)  # "character", "face", "object"
    name = models.CharField(max_length=100)
    base_price = models.DecimalField(max_digits=6, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.name} (${self.base_price})"


class BaseModel(models.Model):
    """Base SDXL / SD1.5 model that we fine-tune against."""
    name = models.CharField(max_length=100)        # "SDXL 1.0"
    identifier = models.CharField(
        max_length=255,
        help_text="Internal or HF identifier, e.g. stabilityai/stable-diffusion-xl-base-1.0",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class TrainingJob(models.Model):
    """A single fine-tuning job requested & paid by user."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
        EXPIRED = "expired", "Expired"

    # неудобно светить автоинкрементные id,
    # лучше иметь внешний UUID для URL’ов
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="training_jobs",
    )

    project_name = models.CharField(max_length=100)

    model_type = models.ForeignKey(ModelType, on_delete=models.PROTECT)
    base_model = models.ForeignKey(BaseModel, on_delete=models.PROTECT)

    num_images = models.PositiveIntegerField(default=0)

    total_price = models.DecimalField(max_digits=7, decimal_places=2)
    currency = models.CharField(max_length=10, default="usd")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )

    stripe_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe Checkout Session ID",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.project_name} ({self.public_id})"

    @property
    def is_refundable(self) -> bool:
        """Потом сюда можно положить бизнес-логику по дедлайну."""
        return (
            self.status in {self.Status.PAID, self.Status.PROCESSING}
            and self.deadline_at is not None
        )


class TrainingImage(models.Model):
    job = models.ForeignKey(
        TrainingJob,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="training_images/%Y/%m/%d/")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Image for job {self.job.public_id}"


class ModelArtifact(models.Model):
    """Final trained model / LoRA checkpoint."""
    job = models.OneToOneField(
        TrainingJob,
        on_delete=models.CASCADE,
        related_name="artifact",
    )
    # На MVP можно использовать только URL, если будешь кидать на HF / GDrive
    file = models.FileField(
        upload_to="trained_models/%Y/%m/%d/",
        blank=True,
    )
    download_url = models.URLField(blank=True)
    size_mb = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Artifact for job {self.job.public_id}"
