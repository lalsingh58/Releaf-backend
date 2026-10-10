from rest_framework import serializers

from apps.core.validators import ImageFileValidator
from apps.users.models import UserStats

from .models import Action, ActionType, Proof
from .services import submit_action


class ProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proof
        fields = ("id", "image", "status", "verification_note", "uploaded_at", "reviewed_at")
        read_only_fields = fields


class ActionSerializer(serializers.ModelSerializer):
    action_type_display = serializers.CharField(source="get_action_type_display", read_only=True)
    proof = ProofSerializer(read_only=True)

    class Meta:
        model = Action
        fields = (
            "id",
            "action_type",
            "action_type_display",
            "description",
            "latitude",
            "longitude",
            "aqi_at_action",
            "points",
            "points_awarded",
            "created_at",
            "proof",
        )
        read_only_fields = fields


class ActionSubmitSerializer(serializers.Serializer):
    """Input for POST /api/actions/submit/ (multipart/form-data)."""

    action_type = serializers.ChoiceField(choices=ActionType.choices)
    description = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    aqi = serializers.IntegerField(
        required=False, min_value=0, max_value=1000, help_text="AQI the app displayed (optional)."
    )
    image = serializers.ImageField(
        validators=[ImageFileValidator("PROOF_MAX_SIZE_MB", "PROOF_MIN_DIMENSION")]
    )

    def create(self, validated_data):
        return submit_action(user=self.context["request"].user, **validated_data)


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    """One leaderboard row. ``rank`` is annotated by the view."""

    rank = serializers.IntegerField(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    city = serializers.CharField(source="user.profile.city", read_only=True)
    profile_picture = serializers.ImageField(source="user.profile.profile_picture", read_only=True)
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = UserStats
        fields = (
            "rank",
            "user_id",
            "full_name",
            "city",
            "profile_picture",
            "points",
            "level",
            "current_streak",
            "total_actions",
            "is_me",
        )
        read_only_fields = fields

    def get_is_me(self, stats) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and stats.user_id == request.user.id)
