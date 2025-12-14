from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0003_trainingjob_payment_reference"),
    ]

    operations = [
        migrations.CreateModel(
            name="LoRATrainingJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending"),
                    ("provisioning", "Provisioning GPU"),
                    ("uploading", "Uploading dataset"),
                    ("captioning", "Generating captions"),
                    ("training", "Training"),
                    ("collecting", "Collecting artifacts"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ], default="pending", max_length=20)),
                ("trigger_token", models.CharField(max_length=100)),
                ("repeat", models.PositiveIntegerField(default=5)),
                ("image_count", models.PositiveIntegerField(default=0)),
                ("gpu_type", models.CharField(default="NVIDIA_L4", max_length=100)),
                ("runpod_pod_id", models.CharField(blank=True, max_length=255)),
                ("logs", models.TextField(blank=True)),
                ("output_path", models.CharField(blank=True, max_length=500)),
                ("error", models.TextField(blank=True)),
                ("learning_rate", models.DecimalField(decimal_places=6, default=Decimal("0.000100"), max_digits=8)),
                ("steps", models.PositiveIntegerField(default=2000)),
                ("train_text_encoder", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "training_job",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="lora_job", to="training.trainingjob"),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
