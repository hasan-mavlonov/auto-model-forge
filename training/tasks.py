"""Lightweight background orchestration for LoRA training jobs."""
from __future__ import annotations

import threading
from typing import Callable

from django.db import transaction

from .models import LoRATrainingJob, TrainingJob
from .runpod_client import RunPodCapacityError, RunPodClient, RunPodError
from .training_runner import LoRATrainingRunner


def _process_job(
    job: LoRATrainingJob, runner_factory: Callable[[], LoRATrainingRunner] | None = None
) -> LoRATrainingJob:
    """Run a single LoRA training job and persist status transitions."""

    runner_factory = runner_factory or (lambda: LoRATrainingRunner(RunPodClient()))
    runner = runner_factory()

    # Reserve the job so concurrent workers do not pick it up twice.
    if job.status == LoRATrainingJob.Status.PENDING:
        job.status = LoRATrainingJob.Status.PROVISIONING
        job.save(update_fields=["status", "updated_at"])

    job.training_job.status = TrainingJob.Status.PROCESSING
    job.training_job.save(update_fields=["status"])

    try:
        runner.run(job)
    except RunPodCapacityError as err:
        job.append_log(f"RunPod capacity unavailable: {err}")
        raise
    except RunPodError as err:
        job.append_log(f"RunPod error: {err}")
        raise
    except Exception as exc:  # noqa: BLE001
        job.append_log(f"Unexpected failure: {exc}")
        raise

    return job


def start_lora_job_async(job: LoRATrainingJob) -> None:
    """Kick off a background thread to process a pending LoRA job."""

    def _worker(job_id: int) -> None:
        with transaction.atomic():
            job_for_update = (
                LoRATrainingJob.objects.select_for_update(skip_locked=True)
                .select_related("training_job")
                .get(id=job_id)
            )
        try:
            _process_job(job_for_update)
        except RunPodCapacityError:
            # Leave the job pending for a later retry.
            return
        except Exception:
            return

    if job.status not in {LoRATrainingJob.Status.PENDING, LoRATrainingJob.Status.PROVISIONING}:
        return

    thread = threading.Thread(target=_worker, args=(job.id,), daemon=True)
    thread.start()
