# payments/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from django.utils import timezone

from training.models import TrainingJob


class PaymentSuccessView(LoginRequiredMixin, View):
    """
    Страница, куда попадает пользователь ПОСЛЕ успешной оплаты.
    Для MVP мы просто помечаем job как paid и редиректим на страницу статуса.
    Позже сюда привяжем Stripe session_id / вебхук.
    """

    def get(self, request, public_id):
        job = get_object_or_404(
            TrainingJob,
            public_id=public_id,
            user=request.user,
        )

        # Если ещё не оплачено — считаем, что сейчас оплата прошла успешно
        if job.status == TrainingJob.Status.AWAITING_PAYMENT:
            job.mark_as_paid()

        return redirect(job.get_absolute_url())
