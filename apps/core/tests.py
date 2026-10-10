from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from .testing import BaseAPITestCase
from .utils import calculate_level, describe_level, points_required_for_level


class LevelTests(SimpleTestCase):
    def test_level_thresholds(self):
        self.assertEqual(calculate_level(0), 1)
        self.assertEqual(calculate_level(99), 1)
        self.assertEqual(calculate_level(100), 2)
        self.assertEqual(calculate_level(399), 2)
        self.assertEqual(calculate_level(400), 3)
        self.assertEqual(calculate_level(900), 4)

    def test_points_required_for_level_matches_calculate_level(self):
        for level in range(1, 12):
            self.assertEqual(calculate_level(points_required_for_level(level)), level)

    def test_describe_level(self):
        info = describe_level(150)
        self.assertEqual(info["level_title"], "Sprout")
        self.assertEqual(info["points_to_next_level"], 250)
        self.assertAlmostEqual(info["level_progress_percent"], 16.7)


def fake_open_meteo_response(us_aqi=162):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "latitude": 28.6,
        "longitude": 77.2,
        "current_units": {"pm2_5": "μg/m³", "pm10": "μg/m³"},
        "current": {
            "time": "2026-10-10T11:00",
            "us_aqi": us_aqi,
            "european_aqi": 120,
            "pm2_5": 71.2,
            "pm10": 110.5,
            "carbon_monoxide": 540.0,
            "nitrogen_dioxide": 40.1,
            "sulphur_dioxide": 12.3,
            "ozone": 33.0,
        },
    }
    return response


class AQIEndpointTests(BaseAPITestCase):
    url = "/api/aqi/"

    @mock.patch("apps.core.aqi.requests.get")
    def test_returns_aqi_and_triggers_challenge(self, mock_get):
        mock_get.return_value = fake_open_meteo_response(162)
        response = self.client.get(self.url, {"latitude": 28.61, "longitude": 77.20})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["us_aqi"], 162)
        self.assertEqual(response.data["category"], "Unhealthy")
        self.assertTrue(response.data["challenge"]["triggered"])
        self.assertEqual(response.data["pollutants"]["pm2_5"]["value"], 71.2)

    @mock.patch("apps.core.aqi.requests.get")
    def test_good_air_does_not_trigger_challenge(self, mock_get):
        mock_get.return_value = fake_open_meteo_response(35)
        response = self.client.get(self.url, {"latitude": 10, "longitude": 20})
        self.assertEqual(response.data["category"], "Good")
        self.assertFalse(response.data["challenge"]["triggered"])

    @mock.patch("apps.core.aqi.requests.get")
    def test_second_request_is_served_from_cache(self, mock_get):
        mock_get.return_value = fake_open_meteo_response()
        params = {"latitude": 28.61, "longitude": 77.20}
        self.client.get(self.url, params)
        self.client.get(self.url, params)
        self.assertEqual(mock_get.call_count, 1)

    @override_settings(AQI_CHALLENGE_THRESHOLD=200)
    @mock.patch("apps.core.aqi.requests.get")
    def test_threshold_is_configurable(self, mock_get):
        mock_get.return_value = fake_open_meteo_response(162)
        response = self.client.get(self.url, {"latitude": 1, "longitude": 1})
        self.assertFalse(response.data["challenge"]["triggered"])

    def test_missing_or_invalid_coordinates(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")

        response = self.client.get(self.url, {"latitude": 123, "longitude": 10})
        self.assertEqual(response.status_code, 400)
        self.assertIn("latitude", response.data["error"]["details"])

    @mock.patch("apps.core.aqi.requests.get", side_effect=requests.ConnectionError("boom"))
    def test_upstream_failure_returns_502(self, _mock_get):
        response = self.client.get(self.url, {"latitude": 28.6, "longitude": 77.2})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"]["code"], "upstream_error")

    @mock.patch("apps.core.aqi.requests.get")
    def test_no_data_for_location_returns_404(self, mock_get):
        response = fake_open_meteo_response()
        response.json.return_value["current"]["us_aqi"] = None
        mock_get.return_value = response
        result = self.client.get(self.url, {"latitude": 0, "longitude": 0})
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.data["error"]["code"], "aqi_not_available")


class MiscEndpointTests(BaseAPITestCase):
    def test_health(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "ok"})

    def test_unknown_api_path_returns_json_404(self):
        response = self.client.get("/api/does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_unauthenticated_request_uses_error_envelope(self):
        response = self.client.get("/api/stats/me/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["status_code"], 401)
