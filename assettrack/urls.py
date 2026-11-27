from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic import RedirectView

from .admin_site import assettrack_admin

urlpatterns = [
    path("admin/", assettrack_admin.urls),
    path("accounts/", include("accounts.urls")),
    path("assets/", include("assets.urls")),
    path("", RedirectView.as_view(pattern_name="accounts:login", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
