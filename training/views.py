# training/views.py
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import FormView, DetailView
from django.utils import timezone
from .forms import TrainingJobCreateForm
from .models import TrainingJob, TrainingImage
from .services import calculate_job_price


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
        job.status = TrainingJob.Status.AWAITING_PAYMENT
        job.save()

        # 4. Редирект на страницу статуса заказа
        return redirect("training:job_detail", public_id=job.public_id)


class TrainingJobDetailView(LoginRequiredMixin, DetailView):
    model = TrainingJob
    template_name = "training/job_detail.html"
    context_object_name = "job"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    def get_queryset(self):
        qs = super().get_queryset()
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

        ctx["countdown_seconds"] = countdown_seconds
        return ctx
