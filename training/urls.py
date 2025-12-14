# training/urls.py
from django.urls import path
from . import views

app_name = "training"

urlpatterns = [
    path("new/", views.TrainingJobCreateView.as_view(), name="job_create"),
    path("jobs/", views.TrainingJobListView.as_view(), name="job_list"),
    path(
        "<uuid:public_id>/download-images/",
        views.JobImagesDownloadView.as_view(),
        name="job_images_download",
    ),
    path("<uuid:public_id>/", views.TrainingJobDetailView.as_view(), name="job_detail"),
]
