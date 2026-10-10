"""
Live AQI via the Open-Meteo Air Quality API (https://open-meteo.com/en/docs/air-quality-api).

Results are cached per ~1 km grid cell so that many users in the same area
do not each trigger an upstream request.
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# (upper bound inclusive, label) following the US EPA AQI breakpoints.
AQI_CATEGORIES = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (float("inf"), "Hazardous"),
]

CURRENT_FIELDS = (
    "us_aqi",
    "european_aqi",
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
)


class AQIServiceError(Exception):
    """Raised when AQI data cannot be fetched or parsed."""

    def __init__(self, message: str, *, no_data: bool = False):
        super().__init__(message)
        self.message = message
        self.no_data = no_data


def get_aqi_category(us_aqi: float) -> dict:
    for level, (upper_bound, label) in enumerate(AQI_CATEGORIES):
        if us_aqi <= upper_bound:
            return {"category": label, "category_level": level}
    raise AssertionError("unreachable")  # pragma: no cover


def build_challenge(us_aqi: float) -> dict:
    """Decide whether the app should prompt the user for a green action."""
    threshold = settings.AQI_CHALLENGE_THRESHOLD
    triggered = us_aqi >= threshold
    if triggered:
        message = (
            f"Air quality is poor (AQI {round(us_aqi)}). "
            "Plant a tree or water a plant to take green action!"
        )
    else:
        message = "Air quality is acceptable right now. You can still plant or water for bonus karma!"
    return {
        "triggered": triggered,
        "threshold": threshold,
        "message": message,
        "suggested_actions": [
            {"type": action_type, "base_points": points}
            for action_type, points in settings.POINTS_PER_ACTION.items()
        ],
    }


def _fetch_from_open_meteo(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(CURRENT_FIELDS),
        "timezone": "auto",
    }
    try:
        response = requests.get(
            settings.OPEN_METEO_AIR_QUALITY_URL,
            params=params,
            timeout=settings.OPEN_METEO_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        raise AQIServiceError("The air quality provider is unavailable. Please try again later.") from exc
    except ValueError as exc:  # invalid JSON
        logger.warning("Open-Meteo returned invalid JSON: %s", exc)
        raise AQIServiceError("The air quality provider returned an invalid response.") from exc

    current = payload.get("current") or {}
    us_aqi = current.get("us_aqi")
    if us_aqi is None:
        raise AQIServiceError("No air quality data is available for this location.", no_data=True)

    units = payload.get("current_units") or {}
    return {
        "location": {
            "latitude": payload.get("latitude", latitude),
            "longitude": payload.get("longitude", longitude),
        },
        "measured_at": current.get("time"),
        "us_aqi": us_aqi,
        "european_aqi": current.get("european_aqi"),
        **get_aqi_category(us_aqi),
        "pollutants": {
            name: {"value": current.get(name), "unit": units.get(name)}
            for name in CURRENT_FIELDS
            if name not in ("us_aqi", "european_aqi")
        },
        "source": "Open-Meteo",
    }


def fetch_current_aqi(latitude: float, longitude: float) -> dict:
    """
    Return current air quality (plus the challenge decision) for a location.

    Raises ``AQIServiceError`` if the upstream service fails or has no data.
    """
    # Round to 2 decimals (~1.1 km): finer than the model grid, great for caching.
    latitude, longitude = round(latitude, 2), round(longitude, 2)
    cache_key = f"aqi:{latitude:.2f}:{longitude:.2f}"

    data = cache.get(cache_key)
    if data is None:
        data = _fetch_from_open_meteo(latitude, longitude)
        cache.set(cache_key, data, settings.AQI_CACHE_SECONDS)

    # The challenge is derived on every call so threshold changes apply immediately.
    return {**data, "challenge": build_challenge(data["us_aqi"])}
