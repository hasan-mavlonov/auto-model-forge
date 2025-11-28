# accounts/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views

from .forms import EmailAuthenticationForm
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("activation-sent/", views.ActivationSentView.as_view(), name="activation_sent"),
    path("activate/<uidb64>/<token>/", views.ActivateAccountView.as_view(), name="activate"),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=EmailAuthenticationForm,
        ),
        name="login",
    ),
    path(
        "logout/",
        views.LogoutView.as_view(),
        name="logout",
    ),
]
