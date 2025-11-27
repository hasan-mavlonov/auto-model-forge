# payments/urls.py
from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("success/<uuid:public_id>/", views.PaymentSuccessView.as_view(), name="success"),
]
