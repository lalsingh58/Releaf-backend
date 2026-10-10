"""
Consistent JSON error responses.

Every error returned by the API has the shape::

    {
      "error": {
        "status_code": 400,
        "code": "validation_error",
        "message": "Invalid input.",
        "details": {"email": ["A user with this email already exists."]}
      }
    }
"""
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class UpstreamServiceError(APIException):
    """A third-party service (e.g. Open-Meteo) failed."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "An upstream service is currently unavailable. Please try again later."
    default_code = "upstream_error"


class AQIDataNotAvailable(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "No air quality data is available for this location."
    default_code = "aqi_not_available"


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled exception: let Django log it and render the JSON 500 page.
        return None

    data = response.data
    if isinstance(exc, ValidationError):
        code, message, details = "validation_error", "Invalid input.", data
    else:
        detail = data.get("detail") if isinstance(data, dict) else None
        code = getattr(exc, "default_code", "error")
        message = str(detail) if detail else "Request failed."
        details = None

    response.data = {
        "error": {
            "status_code": response.status_code,
            "code": code,
            "message": message,
            "details": details,
        }
    }
    return response
