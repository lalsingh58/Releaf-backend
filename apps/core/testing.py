"""Shared helpers for the test suites."""
import atexit
import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="releaf_test_media_")
atexit.register(shutil.rmtree, TEST_MEDIA_ROOT, ignore_errors=True)

User = get_user_model()


def make_image_bytes(color=(34, 139, 34), size=(300, 300), fmt="JPEG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def make_upload(name="proof.jpg", color=(34, 139, 34), size=(300, 300), fmt="JPEG", content_type="image/jpeg"):
    return SimpleUploadedFile(name, make_image_bytes(color, size, fmt), content_type=content_type)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class BaseAPITestCase(APITestCase):
    password = "Str0ng-Passw0rd!"

    def setUp(self):
        super().setUp()
        cache.clear()  # reset throttling counters, AQI and impact caches

    def create_user(self, email="user@example.com", full_name="Test User", **extra):
        return User.objects.create_user(
            email=email, password=self.password, full_name=full_name, **extra
        )

    def login_as(self, user):
        self.client.force_authenticate(user=user)
        return user

    def submit(self, color=(10, 120, 10), **overrides):
        data = {
            "action_type": "plant",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "description": "Planted a neem sapling",
            "image": make_upload(color=color),
        }
        data.update(overrides)
        return self.client.post("/api/actions/submit/", data, format="multipart")
