# training/models.py
import secrets
import uuid
from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


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
    name = models.CharField(max_length=100)  # "SDXL 1.0"
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
        PAYMENT_SUBMITTED = "payment_submitted", "Payment submitted"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
        EXPIRED = "expired", "Expired"

    DEADLINE_HOURS = 24

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="training_jobs",
    )

    project_name = models.CharField(max_length=100)

    model_type = models.ForeignKey("ModelType", on_delete=models.PROTECT)
    base_model = models.ForeignKey("BaseModel", on_delete=models.PROTECT)

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

    payment_reference = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
        help_text="Short code used to match incoming payments",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_submitted_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.project_name} ({self.public_id})"

    def get_absolute_url(self):
        return reverse("training:job_detail", kwargs={"public_id": self.public_id})

    @property
    def is_refundable(self) -> bool:
        return (
                self.status in {self.Status.PAID, self.Status.PROCESSING}
                and self.deadline_at is not None
        )

    def mark_as_paid(self, when: timezone.datetime | None = None):
        """
        Вызывается после успешной оплаты.
        Ставит paid_at, deadline_at и статус PAID.
        """
        if when is None:
            when = timezone.now()
        self.paid_at = when
        self.deadline_at = when + timedelta(hours=self.DEADLINE_HOURS)
        self.status = self.Status.PAID
        self.save(update_fields=["paid_at", "deadline_at", "status"])

    def submit_payment(self, when: timezone.datetime | None = None):
        """Отмечает, что пользователь отправил оплату на проверку."""
        if when is None:
            when = timezone.now()
        self.payment_submitted_at = when
        self.status = self.Status.PAYMENT_SUBMITTED
        self.save(update_fields=["payment_submitted_at", "status"])

    @classmethod
    def generate_payment_reference(cls) -> str:
        """Generate a short, unique payment code that fits payment memo limits."""

        def _candidates() -> Iterable[str]:
            prefix = "AMF-"
            while True:
                yield f"{prefix}{secrets.token_hex(4).upper()}"

        for candidate in _candidates():
            if not cls.objects.filter(payment_reference=candidate).exists():
                return candidate

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")

        if not self.payment_reference:
            self.payment_reference = self.generate_payment_reference()
            if update_fields is not None and "payment_reference" not in update_fields:
                kwargs["update_fields"] = list(update_fields) + ["payment_reference"]

        super().save(*args, **kwargs)


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


class LoRATrainingJob(models.Model):
    """Tracks the full lifecycle of a LoRA fine-tuning run on RunPod."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROVISIONING = "provisioning", "Provisioning GPU"
        UPLOADING = "uploading", "Uploading dataset"
        CAPTIONING = "captioning", "Generating captions"
        TRAINING = "training", "Training"
        COLLECTING = "collecting", "Collecting artifacts"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    training_job = models.OneToOneField(
        TrainingJob,
        on_delete=models.CASCADE,
        related_name="lora_job",
    )
    job_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    trigger_token = models.CharField(max_length=100)
    repeat = models.PositiveIntegerField(default=5)
    image_count = models.PositiveIntegerField(default=0)
    gpu_type = models.CharField(max_length=100, default="NVIDIA_L4")
    runpod_pod_id = models.CharField(max_length=255, blank=True)
    logs = models.TextField(blank=True)
    output_path = models.CharField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    learning_rate = models.DecimalField(max_digits=8, decimal_places=6, default=Decimal("0.000100"))
    steps = models.PositiveIntegerField(default=2000)
    train_text_encoder = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"LoRA job {self.job_id} ({self.training_job.project_name})"

    def append_log(self, message: str, *, persist: bool = True) -> None:
        timestamp = timezone.now().isoformat()
        entry = f"[{timestamp}] {message}\n"
        self.logs += entry
        if persist:
            self.save(update_fields=["logs", "updated_at"])

    def mark_failed(self, error: str) -> None:
        self.error = error
        self.status = self.Status.FAILED
        self.append_log(f"FAILED: {error}", persist=False)
        self.save(update_fields=["status", "error", "logs", "updated_at"])
