"""
Business logic for green actions: scoring, streaks, levels and proof review.

Views and the admin call into this module so the rules live in one place.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from apps.core.utils import calculate_level, compute_sha256
from apps.users.models import UserStats

from .models import Action, Proof, ProofStatus


class DailyActionLimitReached(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "You have reached the daily limit of green actions. Come back tomorrow!"
    default_code = "daily_limit_reached"


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def calculate_action_points(action_type: str, aqi: Optional[int] = None) -> int:
    """Base points for the action type, plus a bonus when the air was bad."""
    points = settings.POINTS_PER_ACTION[action_type]
    if aqi is not None:
        for minimum_aqi, bonus in settings.AQI_BONUS_POINTS:
            if aqi >= minimum_aqi:
                points += bonus
                break
    return points


def apply_streak(stats: UserStats, action_date: date) -> None:
    """
    Update current/longest streak for an action performed on ``action_date``.

    - first ever action          -> streak = 1
    - same day as the last one   -> unchanged
    - the day after the last one -> streak + 1
    - a gap of 2+ days           -> streak restarts at 1
    - older than the last action -> ignored (late approval of an old action)
    """
    last = stats.last_action_date
    if last is None:
        stats.current_streak = 1
    elif action_date == last:
        return
    elif action_date == last + timedelta(days=1):
        stats.current_streak += 1
    elif action_date > last:
        stats.current_streak = 1
    else:
        return

    stats.last_action_date = action_date
    stats.longest_streak = max(stats.longest_streak, stats.current_streak)


# --------------------------------------------------------------------------- #
# Awarding / revoking points
# --------------------------------------------------------------------------- #
def _award_points(action: Action) -> UserStats:
    stats = UserStats.objects.select_for_update().get(user_id=action.user_id)
    stats.points += action.points
    stats.total_actions += 1
    stats.level = calculate_level(stats.points)
    apply_streak(stats, timezone.localdate(action.created_at))
    stats.save()

    action.points_awarded = True
    action.save(update_fields=["points_awarded"])
    return stats


def _revoke_points(action: Action) -> UserStats:
    """Take back points of a previously approved action (streaks are left as they are)."""
    stats = UserStats.objects.select_for_update().get(user_id=action.user_id)
    stats.points = max(stats.points - action.points, 0)
    stats.total_actions = max(stats.total_actions - 1, 0)
    stats.level = calculate_level(stats.points)
    stats.save()

    action.points_awarded = False
    action.save(update_fields=["points_awarded"])
    return stats


# --------------------------------------------------------------------------- #
# Proof review (used by verification, admin and any future moderation API)
# --------------------------------------------------------------------------- #
def _lock_proof_and_action(proof: Proof):
    proof = Proof.objects.select_for_update().get(pk=proof.pk)
    action = Action.objects.select_for_update().get(pk=proof.action_id)
    return proof, action


@transaction.atomic
def approve_proof(proof: Proof, *, note: str = "", confidence: Optional[float] = None) -> Proof:
    """Mark a proof approved and credit points once (idempotent)."""
    proof, action = _lock_proof_and_action(proof)

    proof.status = ProofStatus.APPROVED
    proof.verification_note = note[:255]
    proof.ai_confidence = confidence
    proof.reviewed_at = timezone.now()
    proof.save(update_fields=["status", "verification_note", "ai_confidence", "reviewed_at"])

    if not action.points_awarded:
        _award_points(action)
    return proof


@transaction.atomic
def reject_proof(proof: Proof, *, note: str = "", confidence: Optional[float] = None) -> Proof:
    """Mark a proof rejected; takes points back if they had already been credited."""
    proof, action = _lock_proof_and_action(proof)

    proof.status = ProofStatus.REJECTED
    proof.verification_note = note[:255]
    proof.ai_confidence = confidence
    proof.reviewed_at = timezone.now()
    proof.save(update_fields=["status", "verification_note", "ai_confidence", "reviewed_at"])

    if action.points_awarded:
        _revoke_points(action)
    return proof


# --------------------------------------------------------------------------- #
# Submission
# --------------------------------------------------------------------------- #
@dataclass
class SubmissionResult:
    action: Action
    stats: UserStats
    points_awarded: int
    leveled_up: bool
    previous_level: int


@transaction.atomic
def submit_action(
    *,
    user,
    action_type: str,
    latitude: float,
    longitude: float,
    image,
    description: str = "",
    aqi: Optional[int] = None,
) -> SubmissionResult:
    """
    Create an Action + Proof, run verification and (if approved) award points,
    update the streak and recompute the level. All in one transaction.
    """
    # Locking the stats row serialises a user's submissions, so two parallel
    # requests cannot both slip under the daily limit.
    stats = UserStats.objects.select_for_update().get(user=user)
    previous_level = stats.level

    today = timezone.localdate()
    actions_today = (
        Action.objects.filter(user=user, created_at__date=today)
        .exclude(proof__status=ProofStatus.REJECTED)
        .count()
    )
    if actions_today >= settings.MAX_ACTIONS_PER_DAY:
        raise DailyActionLimitReached()

    image_hash = compute_sha256(image)
    if (
        Proof.objects.filter(image_hash=image_hash)
        .exclude(status=ProofStatus.REJECTED)
        .exists()
    ):
        raise ValidationError({"image": ["This photo has already been submitted."]})

    action = Action.objects.create(
        user=user,
        action_type=action_type,
        description=description,
        latitude=latitude,
        longitude=longitude,
        aqi_at_action=aqi,
        points=calculate_action_points(action_type, aqi),
    )
    proof = Proof.objects.create(action=action, image=image, image_hash=image_hash)

    verifier = import_string(settings.PROOF_VERIFIER)
    result = verifier(proof)

    if result.status == ProofStatus.APPROVED:
        approve_proof(proof, note=result.note, confidence=result.confidence)
    elif result.status == ProofStatus.REJECTED:
        reject_proof(proof, note=result.note, confidence=result.confidence)
    else:  # pending: keep for manual review
        proof.verification_note = result.note[:255]
        proof.ai_confidence = result.confidence
        proof.save(update_fields=["verification_note", "ai_confidence"])

    action.refresh_from_db()
    proof.refresh_from_db()
    action.proof = proof
    stats.refresh_from_db()

    return SubmissionResult(
        action=action,
        stats=stats,
        points_awarded=action.points if action.points_awarded else 0,
        leveled_up=stats.level > previous_level,
        previous_level=previous_level,
    )
