from rest_framework import serializers


class CoordinatesSerializer(serializers.Serializer):
    """Validates ``?latitude=..&longitude=..`` query parameters."""

    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
