# training/views.py
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, FormView, ListView

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
                "payment_submitted": job.status == TrainingJob.Status.PAYMENT_SUBMITTED,
                "show_submit_payment": job.status
                in {
                    TrainingJob.Status.AWAITING_PAYMENT,
                    TrainingJob.Status.CREATED,
                },
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


class SubmitPaymentView(LoginRequiredMixin, View):
    def post(self, request, public_id):
        job = get_object_or_404(
            TrainingJob, public_id=public_id, user=request.user
        )

        if job.status not in {
            TrainingJob.Status.AWAITING_PAYMENT,
            TrainingJob.Status.CREATED,
        }:
            messages.info(
                request,
                "This job is already submitted or processed."
            )
            return redirect(job)

        job.submit_payment()
        messages.success(
            request,
            "We received your payment submission. We will verify it and start training soon.",
        )
        return redirect(job)


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
            TrainingJob.objects.select_related("user", "model_type", "base_model")
            .annotate(image_count=models.F("num_images"))
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        status_groups = {
            "Awaiting payment": [
                TrainingJob.Status.CREATED,
                TrainingJob.Status.AWAITING_PAYMENT,
            ],
            "Payment submitted": [TrainingJob.Status.PAYMENT_SUBMITTED],
            "Paid / processing": [
                TrainingJob.Status.PAID,
                TrainingJob.Status.PROCESSING,
            ],
            "Completed / other": [
                TrainingJob.Status.COMPLETED,
                TrainingJob.Status.REFUNDED,
                TrainingJob.Status.FAILED,
                TrainingJob.Status.EXPIRED,
            ],
        }

        group_counts = {
            label: sum(1 for job in ctx["jobs"] if job.status in statuses)
            for label, statuses in status_groups.items()
        }

        ctx.update({"status_groups": status_groups, "group_counts": group_counts})
        return ctx
