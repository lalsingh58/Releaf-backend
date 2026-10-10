"""Mounted at /api/"""
from django.urls import path

from .views import ActionSubmitView, LeaderboardView, MyActionsView, MyStatsView

urlpatterns = [
    path("actions/submit/", ActionSubmitView.as_view(), name="action-submit"),
    path("actions/my/", MyActionsView.as_view(), name="action-my"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("stats/me/", MyStatsView.as_view(), name="stats-me"),
]
