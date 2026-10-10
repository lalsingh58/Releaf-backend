"""Project-level URL configuration for ReLeaf."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "ReLeaf"
admin.site.site_title = "ReLeaf Admin"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    # Authentication: register / login / refresh / logout / me
    path("api/auth/", include("apps.users.auth_urls")),
    # Profiles: /api/profile/me/, /api/profile/<id>/ ...
    path("api/profile/", include("apps.users.urls")),
    # Actions, leaderboard, stats
    path("api/", include("apps.actions.urls")),
    # AQI, community impact, health check
    path("api/", include("apps.core.urls")),
]

# Serve uploaded media only in development. In production use object storage
# (S3/GCS) or let nginx serve MEDIA_ROOT.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "apps.core.views.api_not_found"
handler500 = "apps.core.views.api_server_error"
