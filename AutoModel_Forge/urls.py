# AutoModel_Forge/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),           # лендинг, home
    path("accounts/", include("accounts.urls")),
    path("train/", include("training.urls")),  # создание/статус заказов
    path("payments/", include("payments.urls")),
]
