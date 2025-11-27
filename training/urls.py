# training/urls.py
from django.urls import path
from . import views

app_name = "training"

urlpatterns = [
    path("new/", views.TrainingJobCreateView.as_view(), name="job_create"),
    path("<uuid:public_id>/", views.TrainingJobDetailView.as_view(), name="job_detail"),
    # позже можем добавить список:
    # path("", views.TrainingJobListView.as_view(), name="job_list"),
]
