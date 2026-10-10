from django.urls import path

from .views import AQIView, HealthView, ImpactView

urlpatterns = [
    path("aqi/", AQIView.as_view(), name="aqi"),
    path("impact/", ImpactView.as_view(), name="impact"),
    path("health/", HealthView.as_view(), name="health"),
]
