"""Reusable upload validators."""
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")  # what Pillow reports for the real content


class ImageFileValidator:
    """
    Validates an uploaded image: extension, size, real image content
    (via Pillow, so renamed non-images are rejected), allowed format and
    minimum dimensions.

    Limits are read from Django settings *at call time*, which keeps them
    configurable per environment (and easy to override in tests).
    """

    def __init__(self, size_setting: str, min_dimension_setting: str | None = None):
        self.size_setting = size_setting
        self.min_dimension_setting = min_dimension_setting

    def __call__(self, file):
        extension = Path(file.name).suffix.lower().lstrip(".")
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file type '.{extension}'. Allowed types: JPG, JPEG, PNG, WEBP.",
                code="invalid_extension",
            )

        max_mb = getattr(settings, self.size_setting)
        if file.size > max_mb * 1024 * 1024:
            raise ValidationError(
                f"Image is too large ({file.size / 1024 / 1024:.1f} MB). "
                f"Maximum allowed size is {max_mb:g} MB.",
                code="file_too_large",
            )

        try:
            file.seek(0)
            with Image.open(file) as image:
                image_format = image.format
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
            raise ValidationError("The uploaded file is not a valid image.", code="invalid_image") from exc
        finally:
            file.seek(0)

        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError(
                f"Unsupported image format '{image_format}'. Allowed formats: JPEG, PNG, WEBP.",
                code="invalid_format",
            )

        if self.min_dimension_setting:
            min_dimension = getattr(settings, self.min_dimension_setting)
            if min(width, height) < min_dimension:
                raise ValidationError(
                    f"Image is too small ({width}x{height}px). "
                    f"The shortest side must be at least {min_dimension}px.",
                    code="image_too_small",
                )
