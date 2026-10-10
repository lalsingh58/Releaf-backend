"""Mounted at /api/profile/"""
from django.urls import path

from apps.actions.views import MyActionsView

from .views import MyProfileView, PublicProfileView

urlpatterns = [
    path("me/", MyProfileView.as_view(), name="profile-me"),
    path("me/actions/", MyActionsView.as_view(), name="profile-my-actions"),
    path("<int:user_id>/", PublicProfileView.as_view(), name="profile-public"),
]
