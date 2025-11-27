# AutoModel_Forge/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from training.views import StaffJobListView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("train/", include("training.urls")),
    path("payments/", include("payments.urls")),
    path("admin-jobs/", StaffJobListView.as_view(), name="staff_job_list"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

