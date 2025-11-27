# training/services.py
from decimal import Decimal
from .models import ModelType

PER_IMAGE_PRICE = Decimal("0.10")
MIN_IMAGES_CHARGED = 10


def calculate_job_price(model_type: ModelType, num_images: int) -> Decimal:
    """Base price + per-image pricing with minimum image charge."""
    charged_images = max(num_images, MIN_IMAGES_CHARGED)
    per_image_total = PER_IMAGE_PRICE * charged_images
    return model_type.base_price + per_image_total
