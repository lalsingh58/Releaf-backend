from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views import defaults
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.actions.models import Action, ActionType, ProofStatus
from apps.users.models import User

from .aqi import AQIServiceError, fetch_current_aqi
from .exceptions import AQIDataNotAvailable, UpstreamServiceError
from .serializers import CoordinatesSerializer


class AQIView(APIView):
    """
    GET /api/aqi/?latitude=28.61&longitude=77.20

    Live AQI for a location (public; throttled and cached).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        serializer = CoordinatesSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            data = fetch_current_aqi(**serializer.validated_data)
        except AQIServiceError as exc:
            if exc.no_data:
                raise AQIDataNotAvailable(exc.message) from exc
            raise UpstreamServiceError(exc.message) from exc
        return Response(data)


class ImpactView(APIView):
    """
    GET /api/impact/

    Community-wide impact statistics (approved actions only). Cached briefly
    because the numbers are aggregates over the whole table.
    """

    permission_classes = [AllowAny]

    CACHE_KEY = "community_impact"

    def get(self, request):
        data = cache.get(self.CACHE_KEY)
        if data is None:
            data = self._compute()
            cache.set(self.CACHE_KEY, data, settings.IMPACT_CACHE_SECONDS)
        return Response(data)

    @staticmethod
    def _compute():
        approved = Action.objects.filter(proof__status=ProofStatus.APPROVED)
        totals = approved.aggregate(
            total_actions=Count("id"),
            trees_planted=Count("id", filter=Q(action_type=ActionType.PLANT)),
            plants_watered=Count("id", filter=Q(action_type=ActionType.WATER)),
            total_points=Sum("points"),
        )
        week_ago = timezone.now() - timedelta(days=7)
        trees = totals["trees_planted"]
        return {
            "total_users": User.objects.filter(is_active=True).count(),
            "active_contributors": approved.values("user").distinct().count(),
            "total_actions": totals["total_actions"],
            "trees_planted": trees,
            "plants_watered": totals["plants_watered"],
            "total_points": totals["total_points"] or 0,
            "actions_last_7_days": approved.filter(created_at__gte=week_ago).count(),
            "estimated_co2_absorbed_kg_per_year": round(trees * settings.CO2_KG_PER_TREE_PER_YEAR, 1),
            "note": "CO2 figure is a rough estimate based on an average mature tree.",
            "generated_at": timezone.now(),
        }


class HealthView(APIView):
    """GET /api/health/ - liveness probe for load balancers."""

    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        return Response({"status": "ok"})


# --------------------------------------------------------------------------- #
# JSON 404 / 500 for API paths (HTML pages are kept for everything else).
# --------------------------------------------------------------------------- #
def _json_error(status_code, code, message):
    return JsonResponse(
        {"error": {"status_code": status_code, "code": code, "message": message, "details": None}},
        status=status_code,
    )


def api_not_found(request, exception=None):
    if request.path.startswith("/api/"):
        return _json_error(404, "not_found", "The requested resource was not found.")
    return defaults.page_not_found(request, exception)


def api_server_error(request):
    if request.path.startswith("/api/"):
        return _json_error(500, "server_error", "An unexpected error occurred.")
    return defaults.server_error(request)
