# training/services.py
from decimal import Decimal
from django.conf import settings

from .models import LoRATrainingJob, ModelType, TrainingJob

PER_IMAGE_PRICE = Decimal("0.10")
MIN_IMAGES_CHARGED = 10


def calculate_job_price(model_type: ModelType, num_images: int) -> Decimal:
    """Base price + per-image pricing with minimum image charge."""
    charged_images = max(num_images, MIN_IMAGES_CHARGED)
    per_image_total = PER_IMAGE_PRICE * charged_images
    return model_type.base_price + per_image_total


def queue_lora_job(
    training_job: TrainingJob,
    *,
    trigger_token: str,
    repeat: int = 5,
    steps: int | None = None,
    learning_rate: Decimal | None = None,
    train_text_encoder: bool | None = None,
) -> LoRATrainingJob:
    """Create or update a LoRA training workflow entry for a paid job."""

    defaults = {
        "trigger_token": trigger_token,
        "repeat": repeat,
        "image_count": training_job.num_images,
        "gpu_type": settings.RUNPOD_DEFAULT_GPU,
        "steps": steps or settings.LORA_DEFAULT_STEPS,
        "learning_rate": learning_rate or Decimal(settings.LORA_DEFAULT_LEARNING_RATE),
        "train_text_encoder": (
            settings.LORA_TRAIN_TEXT_ENCODER if train_text_encoder is None else train_text_encoder
        ),
    }
    lora_job, _ = LoRATrainingJob.objects.update_or_create(
        training_job=training_job,
        defaults=defaults,
    )
    return lora_job
