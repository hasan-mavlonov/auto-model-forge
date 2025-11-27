# accounts/views.py
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.generic import FormView, TemplateView, View

from django.core.mail import send_mail
from django.conf import settings

from .forms import UserRegistrationForm

User = get_user_model()


def send_activation_email(user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    activation_url = request.build_absolute_uri(
        reverse("accounts:activate", kwargs={"uidb64": uid, "token": token})
    )

    subject = "Activate your Auto Model Forge account"
    message = (
        f"Hi!\n\n"
        f"To finish your registration at Auto Model Forge, please click the link below:\n\n"
        f"{activation_url}\n\n"
        f"If you didn't sign up, you can ignore this email."
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    send_mail(subject, message, from_email, [user.email])


class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("accounts:activation_sent")

    def form_valid(self, form):
        user = form.save()
        try:
            send_activation_email(user, self.request)
        except Exception as exc:  # pragma: no cover - depends on email backend
            user.delete()
            form.add_error(
                None,
                "We could not send the activation email. Please check your email address or contact support.",
            )
            return self.form_invalid(form)

        messages.success(
            self.request,
            "Activation link has been sent. Please check your inbox to finish signup.",
        )
        return super().form_valid(form)


class ActivationSentView(TemplateView):
    template_name = "accounts/activation_sent.html"


class ActivateAccountView(View):
    def get(self, request, uidb64, token):
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.is_active = True
            user.save()
            messages.success(request, "Your account has been activated. You can now log in.")
            return redirect("accounts:login")

        return render(request, "accounts/activation_invalid.html")
