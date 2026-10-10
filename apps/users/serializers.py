from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.actions.models import ProofStatus
from apps.actions.serializers import ActionSerializer
from apps.core.utils import describe_level
from apps.core.validators import ImageFileValidator

from .models import UserStats

User = get_user_model()


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
class UserStatsSerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()

    class Meta:
        model = UserStats
        fields = (
            "points",
            "level",
            "current_streak",
            "longest_streak",
            "total_actions",
            "last_action_date",
            "rank",
        )
        read_only_fields = fields

    def get_rank(self, stats) -> int:
        return stats.get_rank()

    def to_representation(self, stats):
        data = super().to_representation(stats)
        # level_title, points_to_next_level, level_progress_percent
        data.update(describe_level(stats.points))
        return data


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class UserSerializer(serializers.ModelSerializer):
    """Basic account data (used by register, login and /auth/me/)."""

    stats = UserStatsSerializer(read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "date_joined", "stats")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )

    class Meta:
        model = User
        fields = ("full_name", "email", "password")

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Full name cannot be blank.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs.get("email"), full_name=attrs.get("full_name"))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login with ``email`` + ``password``; responds with tokens and the user."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["full_name"] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)  # {"refresh": ..., "access": ...}
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
class PublicProfileSerializer(serializers.ModelSerializer):
    """What other users can see about someone (no email)."""

    bio = serializers.CharField(source="profile.bio", read_only=True)
    city = serializers.CharField(source="profile.city", read_only=True)
    profile_picture = serializers.ImageField(source="profile.profile_picture", read_only=True)
    stats = UserStatsSerializer(read_only=True)
    recent_actions = serializers.SerializerMethodField()

    recent_actions_limit = 5
    only_approved_actions = True  # public view hides pending/rejected proofs

    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "bio",
            "city",
            "profile_picture",
            "date_joined",
            "stats",
            "recent_actions",
        )
        read_only_fields = fields

    def get_recent_actions(self, user):
        actions = user.actions.select_related("proof")
        if self.only_approved_actions:
            actions = actions.filter(proof__status=ProofStatus.APPROVED)
        return ActionSerializer(
            actions[: self.recent_actions_limit], many=True, context=self.context
        ).data


class MyProfileSerializer(PublicProfileSerializer):
    """The signed-in user's own profile: adds email and shows all proof statuses."""

    only_approved_actions = False

    class Meta(PublicProfileSerializer.Meta):
        fields = PublicProfileSerializer.Meta.fields + ("email",)
        read_only_fields = fields


class ProfileUpdateSerializer(serializers.Serializer):
    """
    Input for PUT/PATCH /api/profile/me/ (JSON or multipart).
    Every field is optional, so PUT and PATCH behave the same.
    """

    full_name = serializers.CharField(max_length=150, required=False)
    bio = serializers.CharField(max_length=500, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    profile_picture = serializers.ImageField(
        required=False,
        validators=[ImageFileValidator("PROFILE_PICTURE_MAX_SIZE_MB")],
    )
    remove_profile_picture = serializers.BooleanField(required=False, default=False)

    def update(self, user, validated_data):
        profile = user.profile

        if "full_name" in validated_data:
            user.full_name = validated_data["full_name"].strip()
            user.save(update_fields=["full_name"])

        for field in ("bio", "city"):
            if field in validated_data:
                setattr(profile, field, validated_data[field].strip())

        old_picture_name = profile.profile_picture.name if profile.profile_picture else None
        new_picture = validated_data.get("profile_picture")
        picture_changed = False
        if new_picture is not None:
            profile.profile_picture = new_picture
            picture_changed = True
        elif validated_data.get("remove_profile_picture") and old_picture_name:
            profile.profile_picture = None
            picture_changed = True

        profile.save()

        # Clean up the replaced/removed file so storage does not fill with orphans.
        if picture_changed and old_picture_name:
            profile.profile_picture.storage.delete(old_picture_name)
        return user
