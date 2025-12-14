from django.core.management.base import BaseCommand
from training.models import LoRATrainingJob
from training.runpod_client import RunPodClient
from training.training_runner import LoRATrainingRunner


class Command(BaseCommand):
    help = "Run pending LoRA training jobs"

    def handle(self, *args, **options):
        client = RunPodClient()
        runner = LoRATrainingRunner(client)

        jobs = LoRATrainingJob.objects.filter(
            status=LoRATrainingJob.Status.PENDING
        )

        for job in jobs:
            self.stdout.write(f"Running LoRA job {job.job_id}")
            runner.run(job)
