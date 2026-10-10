from datetime import date

from django.test import SimpleTestCase, override_settings

from apps.core.testing import BaseAPITestCase, make_upload
from apps.users.models import UserStats

from .models import Action, Proof, ProofStatus
from .services import apply_streak, approve_proof, calculate_action_points, reject_proof


class PointsAndStreakUnitTests(SimpleTestCase):
    def test_points_without_aqi(self):
        self.assertEqual(calculate_action_points("plant"), 50)
        self.assertEqual(calculate_action_points("water"), 20)

    def test_aqi_bonus_tiers(self):
        self.assertEqual(calculate_action_points("plant", aqi=50), 50)
        self.assertEqual(calculate_action_points("plant", aqi=100), 60)
        self.assertEqual(calculate_action_points("plant", aqi=160), 65)
        self.assertEqual(calculate_action_points("plant", aqi=250), 70)
        self.assertEqual(calculate_action_points("plant", aqi=400), 80)

    def test_streak_rules(self):
        stats = UserStats()  # unsaved; apply_streak only mutates it

        apply_streak(stats, date(2026, 10, 1))
        self.assertEqual((stats.current_streak, stats.longest_streak), (1, 1))

        apply_streak(stats, date(2026, 10, 1))  # same day: unchanged
        self.assertEqual(stats.current_streak, 1)

        apply_streak(stats, date(2026, 10, 2))  # next day: +1
        apply_streak(stats, date(2026, 10, 3))
        self.assertEqual((stats.current_streak, stats.longest_streak), (3, 3))

        apply_streak(stats, date(2026, 10, 6))  # gap: restart, longest kept
        self.assertEqual((stats.current_streak, stats.longest_streak), (1, 3))

        apply_streak(stats, date(2026, 10, 4))  # older date (late approval): ignored
        self.assertEqual(stats.current_streak, 1)
        self.assertEqual(stats.last_action_date, date(2026, 10, 6))


class SubmitActionTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = self.login_as(self.create_user())

    def test_successful_submission_awards_points_streak_and_level(self):
        response = self.submit(aqi=160)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["points_awarded"], 65)  # 50 base + 15 AQI bonus
        self.assertFalse(response.data["leveled_up"])
        self.assertEqual(response.data["action"]["proof"]["status"], "approved")
        self.assertEqual(response.data["stats"]["points"], 65)
        self.assertEqual(response.data["stats"]["current_streak"], 1)
        self.assertEqual(response.data["stats"]["total_actions"], 1)

        # Second action the same day: streak unchanged, level up at 100+ points.
        response = self.submit(color=(200, 50, 50), action_type="plant", aqi=160)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["leveled_up"])
        self.assertEqual(response.data["stats"]["points"], 130)
        self.assertEqual(response.data["stats"]["level"], 2)
        self.assertEqual(response.data["stats"]["current_streak"], 1)
        self.assertEqual(response.data["stats"]["longest_streak"], 1)
        self.assertEqual(response.data["stats"]["total_actions"], 2)

    def test_water_action_points(self):
        response = self.submit(action_type="water")
        self.assertEqual(response.data["points_awarded"], 20)

    def test_invalid_action_type_and_coordinates(self):
        response = self.submit(action_type="dance", latitude=200)
        self.assertEqual(response.status_code, 400)
        details = response.data["error"]["details"]
        self.assertIn("action_type", details)
        self.assertIn("latitude", details)

    def test_image_is_required(self):
        response = self.client.post(
            "/api/actions/submit/",
            {"action_type": "plant", "latitude": 1, "longitude": 1},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data["error"]["details"])

    def test_non_image_file_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile("proof.jpg", b"definitely not an image", content_type="image/jpeg")
        response = self.submit(image=fake)
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data["error"]["details"])

    def test_unsupported_image_format_is_rejected(self):
        gif = make_upload("proof.gif", fmt="GIF", content_type="image/gif")
        response = self.submit(image=gif)
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data["error"]["details"])

    @override_settings(PROOF_MAX_SIZE_MB=0.0001)
    def test_oversized_image_is_rejected(self):
        response = self.submit()
        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", str(response.data["error"]["details"]["image"]))

    def test_tiny_image_is_rejected(self):
        response = self.submit(image=make_upload(size=(40, 40)))
        self.assertEqual(response.status_code, 400)
        self.assertIn("too small", str(response.data["error"]["details"]["image"]))

    def test_duplicate_photo_is_rejected(self):
        self.assertEqual(self.submit(color=(1, 2, 3)).status_code, 201)
        response = self.submit(color=(1, 2, 3))
        self.assertEqual(response.status_code, 400)
        self.assertIn("already been submitted", str(response.data["error"]["details"]["image"]))
        self.assertEqual(Action.objects.count(), 1)  # nothing leaked from the failed attempt

    @override_settings(MAX_ACTIONS_PER_DAY=2)
    def test_daily_limit(self):
        self.assertEqual(self.submit(color=(10, 0, 0)).status_code, 201)
        self.assertEqual(self.submit(color=(20, 0, 0)).status_code, 201)
        response = self.submit(color=(30, 0, 0))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["error"]["code"], "daily_limit_reached")

    def test_submit_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.submit().status_code, 401)


class ManualReviewTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = self.login_as(self.create_user())

    @override_settings(PROOF_AUTO_APPROVE=False)
    def test_pending_proof_gives_no_points_until_approved(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["points_awarded"], 0)
        self.assertEqual(response.data["action"]["proof"]["status"], "pending")
        self.user.stats.refresh_from_db()
        self.assertEqual(self.user.stats.points, 0)

        proof = Proof.objects.get()
        approve_proof(proof, note="Looks good")
        approve_proof(proof)  # idempotent: must not double-award
        self.user.stats.refresh_from_db()
        self.assertEqual(self.user.stats.points, 50)
        self.assertEqual(self.user.stats.total_actions, 1)
        self.assertEqual(self.user.stats.current_streak, 1)

        proof.refresh_from_db()
        self.assertEqual(proof.status, ProofStatus.APPROVED)
        self.assertIsNotNone(proof.reviewed_at)

    @override_settings(PROOF_AUTO_APPROVE=True)
    def test_rejecting_an_approved_proof_revokes_points(self):
        self.submit()
        self.user.stats.refresh_from_db()
        self.assertEqual(self.user.stats.points, 50)

        reject_proof(Proof.objects.get(), note="Not a plant")
        self.user.stats.refresh_from_db()
        self.assertEqual(self.user.stats.points, 0)
        self.assertEqual(self.user.stats.total_actions, 0)
        self.assertEqual(self.user.stats.level, 1)
        self.assertFalse(Action.objects.get().points_awarded)

    def test_rejected_photo_can_be_resubmitted_and_does_not_count_to_daily_limit(self):
        self.submit(color=(5, 5, 5))
        reject_proof(Proof.objects.get(), note="Blurry")
        response = self.submit(color=(5, 5, 5))  # same bytes, previous one was rejected
        self.assertEqual(response.status_code, 201)

    @override_settings(PROOF_VERIFIER="apps.actions.tests.always_reject_verifier")
    def test_custom_verifier_can_reject(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["points_awarded"], 0)
        self.assertEqual(response.data["action"]["proof"]["status"], "rejected")
        self.assertIn("could not be verified", response.data["message"])


def always_reject_verifier(proof):
    from .verification import VerificationResult

    return VerificationResult(ProofStatus.REJECTED, "No plant detected", 0.1)


class ListingAndStatsTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = self.login_as(self.create_user(email="me@example.com", full_name="Me"))

    def test_my_actions_lists_newest_first_with_proofs_and_filters(self):
        self.submit(color=(11, 0, 0), action_type="plant")
        self.submit(color=(22, 0, 0), action_type="water")

        response = self.client.get("/api/actions/my/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["action_type"], "water")
        self.assertEqual(response.data["results"][0]["proof"]["status"], "approved")

        only_plants = self.client.get("/api/actions/my/", {"action_type": "plant"})
        self.assertEqual(only_plants.data["count"], 1)
        pending = self.client.get("/api/actions/my/", {"status": "pending"})
        self.assertEqual(pending.data["count"], 0)

        alias = self.client.get("/api/profile/me/actions/")
        self.assertEqual(alias.data["count"], 2)

    def test_my_actions_only_shows_own_actions(self):
        other = self.create_user(email="other@example.com")
        self.client.force_authenticate(user=other)
        self.submit(color=(99, 0, 0))
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get("/api/actions/my/").data["count"], 0)

    def test_stats_me(self):
        self.submit(aqi=210)  # 50 + 20
        response = self.client.get("/api/stats/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["points"], 70)
        self.assertEqual(response.data["level"], 1)
        self.assertEqual(response.data["level_title"], "Seedling")
        self.assertEqual(response.data["points_to_next_level"], 30)
        self.assertEqual(response.data["current_streak"], 1)
        self.assertEqual(response.data["rank"], 1)

    def test_profile_shows_recent_actions_and_public_profile_only_approved(self):
        self.submit()
        mine = self.client.get("/api/profile/me/")
        self.assertEqual(len(mine.data["recent_actions"]), 1)
        self.assertEqual(mine.data["stats"]["points"], 50)

        viewer = self.create_user(email="viewer@example.com")
        self.client.force_authenticate(user=viewer)
        public = self.client.get(f"/api/profile/{self.user.id}/")
        self.assertEqual(len(public.data["recent_actions"]), 1)

        reject_proof(Proof.objects.get(), note="nope")
        public = self.client.get(f"/api/profile/{self.user.id}/")
        self.assertEqual(public.data["recent_actions"], [])

    def test_leaderboard_ranks_with_ties_and_me(self):
        users = {
            "top": self.create_user(email="top@example.com", full_name="Top"),
            "tie_a": self.create_user(email="a@example.com", full_name="Tie A"),
            "tie_b": self.create_user(email="b@example.com", full_name="Tie B"),
            "zero": self.create_user(email="zero@example.com", full_name="Zero"),
        }
        for key, points in {"top": 300, "tie_a": 100, "tie_b": 100}.items():
            UserStats.objects.filter(user=users[key]).update(points=points)

        self.client.force_authenticate(user=users["tie_b"])
        response = self.client.get("/api/leaderboard/")
        self.assertEqual(response.status_code, 200)

        rows = response.data["results"]
        self.assertEqual(rows[0]["full_name"], "Top")
        # 5 users in total (incl. the one from setUp): 300, 100, 100, 0, 0 points.
        self.assertEqual([r["rank"] for r in rows], [1, 2, 2, 4, 4])
        self.assertEqual(response.data["me"]["rank"], 2)
        self.assertTrue(response.data["me"]["is_me"])
        self.assertEqual(sum(1 for r in rows if r["is_me"]), 1)

    def test_leaderboard_is_paginated(self):
        for i in range(5):
            self.create_user(email=f"p{i}@example.com")
        response = self.client.get("/api/leaderboard/", {"page_size": 2})
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["count"], 6)
        self.assertIsNotNone(response.data["next"])

    def test_impact_counts_only_approved_actions(self):
        self.submit(color=(1, 0, 0), action_type="plant")
        self.submit(color=(2, 0, 0), action_type="plant")
        self.submit(color=(3, 0, 0), action_type="water")
        reject_proof(Proof.objects.filter(action__action_type="water").get(), note="x")

        self.client.force_authenticate(user=None)  # impact is public
        response = self.client.get("/api/impact/")
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data["trees_planted"], 2)
        self.assertEqual(data["plants_watered"], 0)
        self.assertEqual(data["total_actions"], 2)
        self.assertEqual(data["total_points"], 100)
        self.assertEqual(data["active_contributors"], 1)
        self.assertEqual(data["total_users"], 1)
        self.assertEqual(data["estimated_co2_absorbed_kg_per_year"], 43.6)


class AdminSmokeTests(BaseAPITestCase):
    """Make sure every admin page renders (catches broken admin configuration)."""

    def test_admin_pages_render(self):
        from django.contrib.auth import get_user_model

        admin_user = get_user_model().objects.create_superuser(
            email="admin@example.com", password=self.password, full_name="Admin"
        )

        member = self.create_user(email="member@example.com")
        self.client.force_authenticate(user=member)
        self.submit()
        proof = Proof.objects.get()

        # force_authenticate(None) would also log the session out, so switch to a
        # session login (what the admin uses) only now.
        self.client.force_authenticate(user=None)
        self.client.force_login(admin_user)

        pages = [
            "/admin/users/user/",
            "/admin/users/user/add/",
            f"/admin/users/user/{member.id}/change/",
            "/admin/users/profile/",
            "/admin/users/userstats/",
            "/admin/actions/action/",
            f"/admin/actions/action/{proof.action_id}/change/",
            "/admin/actions/proof/",
            f"/admin/actions/proof/{proof.id}/change/",
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_admin_actions_approve_and_reject(self):
        admin_user = self.create_user(email="admin2@example.com", is_staff=True, is_superuser=True)
        member = self.create_user(email="m2@example.com")
        self.client.force_authenticate(user=member)
        with override_settings(PROOF_AUTO_APPROVE=False):
            self.submit()
        proof = Proof.objects.get()

        self.client.force_authenticate(user=None)
        self.client.force_login(admin_user)
        self.client.post(
            "/admin/actions/proof/",
            {"action": "approve_selected", "_selected_action": [proof.pk]},
            follow=True,
        )
        member.stats.refresh_from_db()
        self.assertEqual(member.stats.points, 50)

        self.client.post(
            "/admin/actions/proof/",
            {"action": "reject_selected", "_selected_action": [proof.pk]},
            follow=True,
        )
        member.stats.refresh_from_db()
        self.assertEqual(member.stats.points, 0)
