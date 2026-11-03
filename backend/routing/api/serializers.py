from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True, default="")
    lon = serializers.FloatField(min_value=-180, max_value=180)
    lat = serializers.FloatField(min_value=-90, max_value=90)


def validate_departure(value):
    now = timezone.now()
    if value < now - timedelta(hours=1) or value > now + timedelta(days=7):
        raise serializers.ValidationError(
            "departure must be between 1 hour ago and 7 days from now"
        )
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=80_000)
    interval_mi = serializers.IntegerField()

    def validate_departure(self, value):
        return validate_departure(value)

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if abs(o["lat"] - d["lat"]) < 0.01 and abs(o["lon"] - d["lon"]) < 0.01:  # ~1 km
            raise serializers.ValidationError(
                {"destination": "Origin and destination are the same place; pick two different locations."}
            )
        return attrs

    def validate_interval_mi(self, value):
        if value not in (10, 25, 50):
            raise serializers.ValidationError("interval_mi must be one of 10, 25, 50")
        return value


class LineStringSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["LineString"])
    coordinates = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=3),
        min_length=2,
        max_length=50_000,
    )


class HeatmapRequestSerializer(serializers.Serializer):
    departure = serializers.DateTimeField()
    route_geometries = serializers.ListField(
        child=LineStringSerializer(), min_length=1, max_length=5
    )

    def validate_departure(self, value):
        return validate_departure(value)


def first_error(errors) -> tuple[str, str]:
    """Flatten DRF's nested error dict to (message, dotted field path)."""
    if isinstance(errors, dict):
        for key, val in errors.items():
            msg, sub = first_error(val)
            return msg, f"{key}.{sub}" if sub else str(key)
    if isinstance(errors, list):
        for idx, val in enumerate(errors):
            if isinstance(val, (dict, list)):
                if not val:
                    continue
                msg, sub = first_error(val)
                return msg, f"{idx}.{sub}" if sub else str(idx)
            return str(val), ""
    return str(errors), ""
