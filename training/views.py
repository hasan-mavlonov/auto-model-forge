# training/views.py
import os
import tempfile
import zipfile
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from .forms import ModelArtifactForm, TrainingJobCreateForm
from .models import TrainingJob, TrainingImage
from .services import calculate_job_price, queue_lora_job
from .tasks import start_lora_job_async


class TrainingJobCreateView(LoginRequiredMixin, FormView):
    template_name = "training/job_create.html"
    form_class = TrainingJobCreateForm

    def form_valid(self, form):
        user = self.request.user
        model_type = form.cleaned_data["model_type"]
        base_model = form.cleaned_data["base_model"]
        project_name = form.cleaned_data["project_name"]
        images = form.cleaned_data["images"]  # это список файлов из clean_images

        # 1. Создаём job с базовыми полями
        job = TrainingJob.objects.create(
            user=user,
            project_name=project_name,
            model_type=model_type,
            base_model=base_model,
            num_images=len(images),  # временно, перепроверим позже
            total_price=0,
            currency="usd",
            status=TrainingJob.Status.CREATED,
        )

        # 2. Сохраняем изображения
        for f in images:
            TrainingImage.objects.create(
                job=job,
                image=f,
                original_filename=f.name,
            )

        # 3. Пересчитываем num_images (на всякий случай) и цену
        job.num_images = job.images.count()
        job.total_price = calculate_job_price(model_type, job.num_images)
        job.save(update_fields=["num_images", "total_price"])

        # 3a. Immediately start the training window and queue the run
        job.start_processing()
        trigger_slug = slugify(project_name) or "model"
        trigger_token = f"{trigger_slug[:40]}-{str(job.public_id)[:8]}"
        lora_job = queue_lora_job(job, trigger_token=trigger_token)
        start_lora_job_async(lora_job)

        # 4. Редирект на страницу статуса заказа
        return redirect("training:job_detail", public_id=job.public_id)


class TrainingJobDetailView(LoginRequiredMixin, DetailView):
    model = TrainingJob
    template_name = "training/job_detail.html"
    context_object_name = "job"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if not request.user.is_staff:
            messages.error(request, "You do not have permission to update this job.")
            return redirect(self.object)

        artifact_instance = getattr(self.object, "artifact", None)
        form = ModelArtifactForm(
            request.POST,
            request.FILES,
            instance=artifact_instance,
        )

        if form.is_valid():
            artifact = form.save(commit=False)
            artifact.job = self.object
            artifact.save()

            if self.object.status != TrainingJob.Status.COMPLETED:
                now = timezone.now()
                self.object.status = TrainingJob.Status.COMPLETED
                self.object.completed_at = now
                self.object.save(update_fields=["status", "completed_at"])

            messages.success(
                request,
                "Model artifact uploaded. The job is marked as completed for the user to download.",
            )
            return redirect(self.object)

        ctx = self.get_context_data(artifact_form=form)
        return self.render_to_response(ctx)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        job: TrainingJob = self.object

        countdown_seconds = None
        if job.deadline_at and job.status in {
            TrainingJob.Status.PAID,
            TrainingJob.Status.PROCESSING,
        }:
            remaining = job.deadline_at - timezone.now()
            countdown_seconds = max(int(remaining.total_seconds()), 0)

        price_usd = job.total_price
        rate = Decimal(str(settings.USD_TO_CNY_RATE))
        price_cny = (price_usd * rate).quantize(Decimal("0.01"))

        ctx.update(
            {
                "countdown_seconds": countdown_seconds,
                "price_usd": price_usd,
                "price_cny": price_cny,
                "artifact_form": kwargs.get(
                    "artifact_form",
                    ModelArtifactForm(instance=getattr(job, "artifact", None))
                    if self.request.user.is_staff
                    else None,
                ),
            }
        )
        return ctx


class TrainingJobListView(LoginRequiredMixin, ListView):
    model = TrainingJob
    template_name = "training/job_list.html"
    context_object_name = "jobs"
    paginate_by = 50

    def get_queryset(self):
        return (
            TrainingJob.objects.filter(user=self.request.user)
            .select_related("model_type", "base_model")
            .order_by("-created_at")
        )
class JobImagesDownloadView(LoginRequiredMixin, View):
    """Allow job owners and staff to download training images as a ZIP archive."""

    def get(self, request, public_id):
        job = get_object_or_404(TrainingJob, public_id=public_id)

        if not (request.user.is_staff or job.user_id == request.user.id):
            raise Http404()

        images = list(job.images.all().order_by("uploaded_at"))
        if not images:
            messages.warning(request, "No training images available to download for this job.")
            return redirect(job)

        archive = tempfile.SpooledTemporaryFile(max_size=1024 * 1024 * 100)

        with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for idx, image in enumerate(images, start=1):
                filename = image.original_filename or os.path.basename(image.image.name)
                if not filename:
                    filename = f"image-{idx}.jpg"

                safe_name = f"{idx:03d}-{filename}"
                zip_file.write(image.image.path, arcname=safe_name)

        archive.seek(0)
        filename = f"{job.project_name}_images.zip"
        return FileResponse(archive, as_attachment=True, filename=filename)


@method_decorator(staff_member_required, name="dispatch")
class StaffJobListView(ListView):
    model = TrainingJob
    template_name = "training/admin_job_list.html"
    context_object_name = "jobs"

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        job_id = request.POST.get("job_id")
        job = get_object_or_404(TrainingJob, id=job_id)

        if action == "mark_paid":
            if job.status in {
                TrainingJob.Status.CREATED,
                TrainingJob.Status.AWAITING_PAYMENT,
                TrainingJob.Status.PAYMENT_SUBMITTED,
            }:
                job.mark_as_paid()
                messages.success(request, f"Job {job.project_name} marked as paid.")
            else:
                messages.warning(request, "Job is already paid or past this step.")
        elif action == "mark_completed":
            now = timezone.now()
            job.status = TrainingJob.Status.COMPLETED
            job.completed_at = now
            job.save(update_fields=["status", "completed_at"])
            messages.success(request, f"Job {job.project_name} marked as completed.")
        else:
            messages.warning(request, "Unknown action.")

        return redirect("staff_job_list")

    def get_queryset(self):
        return (
            TrainingJob.objects.select_related(
                "user", "model_type", "base_model", "lora_job"
            )
            .annotate(image_count=models.F("num_images"))
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        status_groups = {
            "Queued / processing": [
                TrainingJob.Status.CREATED,
                TrainingJob.Status.PROCESSING,
                TrainingJob.Status.PAID,
            ],
            "Completed": [TrainingJob.Status.COMPLETED],
            "Issues / other": [
                TrainingJob.Status.PAYMENT_SUBMITTED,
                TrainingJob.Status.AWAITING_PAYMENT,
                TrainingJob.Status.REFUNDED,
                TrainingJob.Status.FAILED,
                TrainingJob.Status.EXPIRED,
            ],
        }

        grouped_jobs = [
            {
                "label": label,
                "statuses": statuses,
                "jobs": [job for job in ctx["jobs"] if job.status in statuses],
            }
            for label, statuses in status_groups.items()
        ]

        ctx.update({"grouped_jobs": grouped_jobs})
        return ctx
