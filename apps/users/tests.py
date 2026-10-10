from django.contrib.auth import get_user_model

from apps.core.testing import BaseAPITestCase, make_upload

from .models import Profile, UserStats

User = get_user_model()


class RegistrationAndLoginTests(BaseAPITestCase):
    def register(self, **overrides):
        payload = {
            "full_name": "Asha Verma",
            "email": "Asha@Example.com",
            "password": self.password,
        }
        payload.update(overrides)
        return self.client.post("/api/auth/register/", payload, format="json")

    def test_register_creates_user_profile_stats_and_returns_tokens(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "asha@example.com")  # normalised

        user = User.objects.get(email="asha@example.com")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertTrue(UserStats.objects.filter(user=user, points=0, level=1).exists())
        self.assertNotIn("password", response.data["user"])

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.register()
        response = self.register(email="ASHA@example.com")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data["error"]["details"])

    def test_weak_password_is_rejected(self):
        response = self.register(password="12345678")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data["error"]["details"])

    def test_missing_fields(self):
        response = self.client.post("/api/auth/register/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        details = response.data["error"]["details"]
        self.assertTrue({"full_name", "email", "password"} <= set(details))

    def test_login_returns_tokens_and_user_and_is_case_insensitive(self):
        self.create_user(email="login@example.com")
        response = self.client.post(
            "/api/auth/login/",
            {"email": "LOGIN@example.com", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "login@example.com")

    def test_login_with_wrong_password(self):
        self.create_user(email="login@example.com")
        response = self.client.post(
            "/api/auth/login/", {"email": "login@example.com", "password": "nope"}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_me_requires_a_valid_token_and_returns_user(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

        self.register()
        login = self.client.post(
            "/api/auth/login/",
            {"email": "asha@example.com", "password": self.password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["full_name"], "Asha Verma")
        self.assertEqual(response.data["stats"]["points"], 0)

    def test_refresh_and_logout_blacklists_refresh_token(self):
        self.create_user(email="tok@example.com")
        login = self.client.post(
            "/api/auth/login/", {"email": "tok@example.com", "password": self.password}, format="json"
        )
        refresh = login.data["refresh"]

        refreshed = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(refreshed.status_code, 200)
        new_refresh = refreshed.data["refresh"]  # rotated

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        logout = self.client.post("/api/auth/logout/", {"refresh": new_refresh}, format="json")
        self.assertEqual(logout.status_code, 200)

        self.client.credentials()
        reused = self.client.post("/api/auth/token/refresh/", {"refresh": new_refresh}, format="json")
        self.assertEqual(reused.status_code, 401)

    def test_register_endpoint_is_throttled(self):
        statuses = [
            self.register(email=f"user{i}@example.com").status_code for i in range(12)
        ]
        self.assertIn(429, statuses)


class ProfileTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(email="me@example.com", full_name="Me Myself")
        self.login_as(self.user)

    def test_get_my_profile(self):
        response = self.client.get("/api/profile/me/")
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data["email"], "me@example.com")
        self.assertEqual(data["full_name"], "Me Myself")
        self.assertIsNone(data["profile_picture"])
        self.assertEqual(data["stats"]["points"], 0)
        self.assertEqual(data["stats"]["rank"], 1)
        self.assertEqual(data["recent_actions"], [])

    def test_put_updates_name_bio_city_and_picture(self):
        response = self.client.put(
            "/api/profile/me/",
            {
                "full_name": "Meera Singh",
                "bio": "Planting one tree at a time.",
                "city": "Hathras",
                "profile_picture": make_upload("me.png", fmt="PNG", content_type="image/png", size=(120, 120)),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["full_name"], "Meera Singh")
        self.assertEqual(response.data["bio"], "Planting one tree at a time.")
        self.assertEqual(response.data["city"], "Hathras")
        self.assertIn("/media/profiles/", response.data["profile_picture"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Meera Singh")

    def test_patch_partial_update_keeps_other_fields(self):
        self.client.put("/api/profile/me/", {"bio": "hello", "city": "Agra"}, format="json")
        response = self.client.patch("/api/profile/me/", {"city": "Delhi"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["city"], "Delhi")
        self.assertEqual(response.data["bio"], "hello")

    def test_replacing_and_removing_picture_deletes_old_file(self):
        self.client.put(
            "/api/profile/me/", {"profile_picture": make_upload("a.jpg", size=(100, 100))}, format="multipart"
        )
        first = Profile.objects.get(user=self.user).profile_picture
        first_name = first.name
        self.assertTrue(first.storage.exists(first_name))

        self.client.put(
            "/api/profile/me/",
            {"profile_picture": make_upload("b.jpg", color=(200, 10, 10), size=(100, 100))},
            format="multipart",
        )
        profile = Profile.objects.get(user=self.user)
        self.assertNotEqual(profile.profile_picture.name, first_name)
        self.assertFalse(profile.profile_picture.storage.exists(first_name))

        self.client.put("/api/profile/me/", {"remove_profile_picture": "true"}, format="multipart")
        profile.refresh_from_db()
        self.assertFalse(profile.profile_picture)

    def test_invalid_profile_picture_is_rejected(self):
        response = self.client.put(
            "/api/profile/me/",
            {"profile_picture": make_upload("a.gif", fmt="GIF", content_type="image/gif")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("profile_picture", response.data["error"]["details"])

    def test_blank_full_name_is_rejected(self):
        response = self.client.put("/api/profile/me/", {"full_name": "  "}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_public_profile_hides_email_and_non_approved_actions(self):
        other = self.create_user(email="other@example.com", full_name="Other Person")
        response = self.client.get(f"/api/profile/{other.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["full_name"], "Other Person")
        self.assertNotIn("email", response.data)

    def test_public_profile_404_for_unknown_or_inactive_user(self):
        self.assertEqual(self.client.get("/api/profile/999999/").status_code, 404)
        inactive = self.create_user(email="gone@example.com", is_active=False)
        self.assertEqual(self.client.get(f"/api/profile/{inactive.id}/").status_code, 404)

    def test_profile_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/profile/me/").status_code, 401)
        self.assertEqual(self.client.get(f"/api/profile/{self.user.id}/").status_code, 401)
        self.assertEqual(self.client.get("/api/profile/me/actions/").status_code, 401)
