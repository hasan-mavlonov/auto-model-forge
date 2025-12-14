from __future__ import annotations

import time
from django.core.management.base import BaseCommand
from django.db import transaction

from training.models import LoRATrainingJob, TrainingJob
from training.runpod_client import RunPodClient, RunPodError
from training.training_runner import LoRATrainingRunner


class Command(BaseCommand):
    help = "Process queued LoRA training jobs via RunPod"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sleep",
            type=int,
            default=30,
            help="Seconds to sleep between polling cycles when not running once.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process one batch and exit.",
        )

    def handle(self, *args, **options):
        client = RunPodClient()
        runner = LoRATrainingRunner(client)
        sleep_seconds: int = options["sleep"]
        run_once: bool = options["once"]

        while True:
            jobs_processed = 0
            for job in self._next_jobs():
                jobs_processed += 1
                self.stdout.write(self.style.NOTICE(f"Starting LoRA job {job.job_id}"))
                job.training_job.status = TrainingJob.Status.PROCESSING
                job.training_job.save(update_fields=["status"])
                try:
                    runner.run(job)
                    self.stdout.write(self.style.SUCCESS(f"Completed LoRA job {job.job_id}"))
                except RunPodError as err:
                    self.stderr.write(self.style.ERROR(f"RunPod failure for {job.job_id}: {err}"))
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(self.style.ERROR(f"Unexpected failure for {job.job_id}: {exc}"))
            if run_once:
                break
            if jobs_processed == 0:
                time.sleep(sleep_seconds)

    def _next_jobs(self):
        """Fetch jobs atomically so only one worker picks them up."""
        with transaction.atomic():
            jobs = (
                LoRATrainingJob.objects.select_for_update(skip_locked=True)
                .filter(
                    status=LoRATrainingJob.Status.PENDING,
                    training_job__status__in=[
                        TrainingJob.Status.PAID,
                        TrainingJob.Status.PROCESSING,
                        TrainingJob.Status.CREATED,
                    ],
                )
                .order_by("created_at")
            )
            for job in jobs:
                job.status = LoRATrainingJob.Status.PROVISIONING
                job.save(update_fields=["status", "updated_at"])
                yield job
