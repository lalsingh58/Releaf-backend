from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    MyProfileSerializer,
    ProfileUpdateSerializer,
    PublicProfileSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class RegisterView(generics.GenericAPIView):
    """POST /api/auth/register/  {full_name, email, password}"""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        refresh["email"] = user.email
        refresh["full_name"] = user.full_name
        return Response(
            {
                "user": UserSerializer(user, context={"request": request}).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/  {email, password} -> {access, refresh, user}"""

    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class LogoutView(APIView):
    """POST /api/auth/logout/  {refresh}: blacklists the refresh token."""

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response(
                {"error": {"status_code": 400, "code": "invalid_token",
                           "message": "Token is invalid or already expired.", "details": None}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Logged out."})


def _load_user_with_relations(user):
    """Fresh copy of the user with profile + stats fetched in a single query."""
    return User.objects.select_related("profile", "stats").get(pk=user.pk)


class MeView(APIView):
    """GET /api/auth/me/  -> the authenticated user (with stats)."""

    def get(self, request):
        user = _load_user_with_relations(request.user)
        return Response(UserSerializer(user, context={"request": request}).data)


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
class MyProfileView(APIView):
    """
    GET   /api/profile/me/   -> my full profile
    PUT   /api/profile/me/   -> update full_name, bio, city, profile_picture
    PATCH /api/profile/me/   -> same as PUT (all fields optional)

    Use multipart/form-data when uploading a picture. Send
    ``remove_profile_picture=true`` to delete the current one.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        user = _load_user_with_relations(request.user)
        return Response(MyProfileSerializer(user, context={"request": request}).data)

    def put(self, request):
        serializer = ProfileUpdateSerializer(instance=request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = _load_user_with_relations(request.user)
        return Response(MyProfileSerializer(user, context={"request": request}).data)

    patch = put


class PublicProfileView(generics.RetrieveAPIView):
    """GET /api/profile/<user_id>/  -> public profile of any active user."""

    serializer_class = PublicProfileSerializer
    queryset = User.objects.filter(is_active=True).select_related("profile", "stats")
    lookup_url_kwarg = "user_id"
    lookup_field = "pk"
