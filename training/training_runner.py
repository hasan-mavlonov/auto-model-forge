"""LoRA training orchestration for SDXL inside a RunPod pod."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.base import File
from django.utils import timezone

from .models import LoRATrainingJob, ModelArtifact, TrainingJob
from .runpod_client import RunPodCapacityError, RunPodClient, RunPodError

DATA_ROOT = "/workspace/data"
OUTPUT_ROOT = "/workspace/output"
KOHYA_PATH = "/workspace/kohya_ss"


class LoRATrainingRunner:
    def __init__(self, client: RunPodClient) -> None:
        self.client = client

    def _build_dataset(self, job: LoRATrainingJob) -> Path:
        """Create a temp folder with images arranged per spec."""
        temp_dir = Path(tempfile.mkdtemp())
        target = temp_dir / f"{job.repeat}_{job.trigger_token}"
        target.mkdir(parents=True, exist_ok=True)

        count = 0
        for idx, image in enumerate(job.training_job.images.all().order_by("id"), start=1):
            filename = f"image_{idx:04d}{Path(image.image.name).suffix or '.png'}"
            with image.image.open("rb") as src:
                (target / filename).write_bytes(src.read())
            count = idx
        job.append_log(f"Prepared dataset with {count} images")
        return temp_dir

    def _upload_dataset(self, pod_id: str, job: LoRATrainingJob, dataset_root: Path) -> str:
        remote_root = f"{DATA_ROOT}/{job.job_id}"
        # ensure parent folder exists and upload
        folder = dataset_root / f"{job.repeat}_{job.trigger_token}"
        files = sorted(folder.iterdir())
        self.client.upload_files(pod_id, files, remote_dir=f"{remote_root}/{folder.name}")
        return f"{remote_root}/{folder.name}"

    def _run_captioning(self, pod_id: str, dataset_dir: str, job: LoRATrainingJob) -> None:
        command = (
            f"python {KOHYA_PATH}/finetune/make_captions.py "
            f"--batch_size 1 --max_length 75 --caption_extension .txt "
            f"--device cuda --num_workers 2 --model blip --input_dir {dataset_dir} --overwrite"
        )
        output = self.client.execute_command(pod_id, command)
        job.append_log(f"Captioning output:\n{output}")

    def _run_training(self, pod_id: str, dataset_dir: str, job: LoRATrainingJob) -> str:
        out_dir = f"{OUTPUT_ROOT}/{job.job_id}"
        output_name = f"{job.job_id}"
        base_model = job.training_job.base_model.identifier
        extra_text_encoder_flag = "--train_text_encoder" if job.train_text_encoder else ""
        command = (
            f"python {KOHYA_PATH}/sdxl_train_network.py "
            f"--pretrained_model_name_or_path={base_model} "
            f"--train_data_dir={dataset_dir} "
            f"--output_dir={out_dir} "
            f"--logging_dir={out_dir}/logs "
            f"--output_name={output_name} "
            f"--caption_extension=.txt --shuffle_caption --save_precision=bf16 "
            f"--network_module=networks.lora --network_dim=16 --network_alpha=1 "
            f"--max_train_steps={job.steps} --learning_rate={job.learning_rate} "
            f"--resolution=1024,1024 --train_batch_size=1 --mixed_precision=bf16 "
            f"--network_train_unet_only --cache_latents=False --optimizer_type=adamw8bit "
            f"{extra_text_encoder_flag}"
        ).strip()
        output = self.client.execute_command(pod_id, command)
        job.append_log(f"Training output:\n{output}")
        return f"{out_dir}/{output_name}.safetensors"

    def _collect_artifact(self, pod_id: str, remote_path: str, job: LoRATrainingJob) -> Path:
        local_dir = Path(settings.MEDIA_ROOT) / "trained_models" / timezone.now().strftime("%Y/%m/%d")
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / Path(remote_path).name
        self.client.download_file(pod_id, remote_path, local_path)
        job.output_path = str(local_path)
        job.save(update_fields=["output_path", "updated_at"])
        return local_path

    def run(self, job: LoRATrainingJob) -> None:
        pod_id = job.runpod_pod_id
        dataset_root: Path | None = None
        try:
            try:
                # Provision
                job.status = LoRATrainingJob.Status.PROVISIONING
                job.save(update_fields=["status", "updated_at"])
                if not pod_id:
                    pod_id = self.client.create_pod(gpu_type=job.gpu_type)
                    job.runpod_pod_id = pod_id
                    job.append_log(f"Provisioned pod {pod_id}")
                    job.save(update_fields=["runpod_pod_id", "logs", "updated_at"])
                self.client.wait_for_pod_ready(pod_id)
            except RunPodCapacityError:
                job.status = LoRATrainingJob.Status.PENDING
                job.save(update_fields=["status", "updated_at"])
                job.append_log(
                    "RunPod does not currently have capacity for this GPU type. "
                    "Job will retry shortly.",
                )
                return

            # Upload
            job.status = LoRATrainingJob.Status.UPLOADING
            job.save(update_fields=["status", "updated_at"])
            dataset_root = self._build_dataset(job)
            dataset_dir = self._upload_dataset(pod_id, job, dataset_root)

            # Caption
            job.status = LoRATrainingJob.Status.CAPTIONING
            job.save(update_fields=["status", "updated_at"])
            self._run_captioning(pod_id, dataset_dir, job)

            # Train
            job.status = LoRATrainingJob.Status.TRAINING
            job.save(update_fields=["status", "updated_at"])
            remote_output = self._run_training(pod_id, dataset_dir, job)

            # Collect
            job.status = LoRATrainingJob.Status.COLLECTING
            job.save(update_fields=["status", "updated_at"])
            local_artifact = self._collect_artifact(pod_id, remote_output, job)

            artifact, _ = ModelArtifact.objects.get_or_create(job=job.training_job)
            relative_name = local_artifact.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
            with local_artifact.open("rb") as f:
                artifact.file.save(relative_name, File(f), save=False)
            artifact.download_url = ""
            artifact.size_mb = round(local_artifact.stat().st_size / (1024 * 1024), 2)
            artifact.save()

            job.status = LoRATrainingJob.Status.COMPLETED
            job.training_job.status = TrainingJob.Status.COMPLETED
            job.training_job.completed_at = timezone.now()
            job.training_job.save(update_fields=["status", "completed_at"])
            job.save(update_fields=["status", "updated_at", "output_path"])
        except Exception as exc:  # noqa: BLE001
            job.mark_failed(str(exc))
            job.training_job.status = TrainingJob.Status.FAILED
            job.training_job.save(update_fields=["status"])
            raise
        finally:
            if pod_id:
                try:
                    self.client.terminate_pod(pod_id)
                    job.append_log(f"Terminated pod {pod_id}")
                    job.save(update_fields=["logs", "updated_at"])
                except RunPodError as err:
                    job.append_log(f"Pod termination failed: {err}")
            if dataset_root:
                shutil.rmtree(dataset_root, ignore_errors=True)
