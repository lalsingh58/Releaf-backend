import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class ActionType(models.TextChoices):
    PLANT = "plant", "Plant a tree"
    WATER = "water", "Water a plant"


class ProofStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Action(models.Model):
    """A green action a user claims to have done (plant / water)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="actions"
    )
    action_type = models.CharField(max_length=10, choices=ActionType.choices, db_index=True)
    description = models.TextField(max_length=500, blank=True)
    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    # AQI reported by the client when the action was taken (optional, used for bonus points).
    aqi_at_action = models.PositiveSmallIntegerField(null=True, blank=True)
    # Points this action is worth; they are only credited to the user once the proof is approved.
    points = models.PositiveIntegerField(default=0)
    points_awarded = models.BooleanField(default=False, help_text="True once the points were credited.")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "-created_at"], name="action_user_created_idx")]

    def __str__(self):
        return f"{self.get_action_type_display()} by {self.user_id} at {self.created_at:%Y-%m-%d %H:%M}"


def proof_image_path(instance, filename):
    extension = Path(filename).suffix.lower() or ".jpg"
    return f"proofs/{instance.action.user_id}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"


class Proof(models.Model):
    """Photo evidence for an Action, plus its verification state."""

    action = models.OneToOneField(Action, on_delete=models.CASCADE, related_name="proof")
    image = models.ImageField(upload_to=proof_image_path)
    # SHA-256 of the file: used to block re-submitting the same photo.
    image_hash = models.CharField(max_length=64, db_index=True, blank=True)
    status = models.CharField(
        max_length=10, choices=ProofStatus.choices, default=ProofStatus.PENDING, db_index=True
    )
    verification_note = models.CharField(max_length=255, blank=True)
    ai_confidence = models.FloatField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Proof #{self.pk} ({self.status})"
