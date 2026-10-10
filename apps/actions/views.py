from django.db.models import F, Window
from django.db.models.functions import Rank
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.users.models import UserStats
from apps.users.serializers import UserStatsSerializer

from .models import Action, ActionType, ProofStatus
from .serializers import (
    ActionSerializer,
    ActionSubmitSerializer,
    LeaderboardEntrySerializer,
)


class ActionSubmitView(APIView):
    """
    POST /api/actions/submit/   (multipart/form-data)

    Fields: action_type (plant|water), latitude, longitude, image,
    description (optional), aqi (optional).
    """

    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "submit"

    def post(self, request):
        serializer = ActionSubmitSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        context = {"request": request}
        proof = result.action.proof
        if proof.status == ProofStatus.APPROVED:
            message = f"Great work! You earned {result.points_awarded} points."
            if result.leveled_up:
                message += f" Level up! You are now level {result.stats.level}."
        elif proof.status == ProofStatus.REJECTED:
            message = f"Your photo could not be verified: {proof.verification_note}"
        else:
            message = "Photo received! Points will be added once your proof has been reviewed."

        return Response(
            {
                "message": message,
                "points_awarded": result.points_awarded,
                "leveled_up": result.leveled_up,
                "action": ActionSerializer(result.action, context=context).data,
                "stats": UserStatsSerializer(result.stats, context=context).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MyActionsView(generics.ListAPIView):
    """
    GET /api/actions/my/   (also served at /api/profile/me/actions/)

    Optional filters: ?status=pending|approved|rejected  &  ?action_type=plant|water
    Paginated: ?page=1&page_size=20
    """

    serializer_class = ActionSerializer

    def get_queryset(self):
        queryset = Action.objects.filter(user=self.request.user).select_related("proof")
        status_filter = self.request.query_params.get("status")
        if status_filter in ProofStatus.values:
            queryset = queryset.filter(proof__status=status_filter)
        type_filter = self.request.query_params.get("action_type")
        if type_filter in ActionType.values:
            queryset = queryset.filter(action_type=type_filter)
        return queryset


class MyStatsView(APIView):
    """GET /api/stats/me/  -> points, level, streaks, total actions, rank."""

    def get(self, request):
        stats = UserStats.objects.get(user=request.user)
        return Response(UserStatsSerializer(stats, context={"request": request}).data)


class LeaderboardView(generics.ListAPIView):
    """
    GET /api/leaderboard/   (paginated, 20 per page by default)

    Ranked by points; users with equal points share a rank. The response
    also contains ``me``: the caller's own entry, wherever they are ranked.
    """

    serializer_class = LeaderboardEntrySerializer

    def get_queryset(self):
        return (
            UserStats.objects.filter(user__is_active=True)
            .select_related("user", "user__profile")
            .annotate(rank=Window(expression=Rank(), order_by=F("points").desc()))
            .order_by("-points", "-longest_streak", "user_id")
        )

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        my_stats = UserStats.objects.select_related("user", "user__profile").get(user=request.user)
        my_stats.rank = my_stats.get_rank()
        response.data["me"] = LeaderboardEntrySerializer(
            my_stats, context=self.get_serializer_context()
        ).data
        return response
