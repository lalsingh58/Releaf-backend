import uuid
from pathlib import Path

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


# --------------------------------------------------------------------------- #
# Custom user: email is the login identifier
# --------------------------------------------------------------------------- #
class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, email):
        # Case-insensitive login ("Bob@Example.com" == "bob@example.com").
        return self.get(email__iexact=email)

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email address", unique=True)
    full_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
def profile_picture_path(instance, filename):
    extension = Path(filename).suffix.lower() or ".jpg"
    return f"profiles/{instance.user_id}/{uuid.uuid4().hex}{extension}"


class Profile(models.Model):
    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="profile")
    profile_picture = models.ImageField(upload_to=profile_picture_path, null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    city = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.email}"


# --------------------------------------------------------------------------- #
# Gamification stats (points, level, streaks)
# --------------------------------------------------------------------------- #
class UserStats(models.Model):
    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="stats")
    points = models.PositiveIntegerField(default=0)
    level = models.PositiveSmallIntegerField(default=1)
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)
    total_actions = models.PositiveIntegerField(default=0)
    last_action_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user stats"
        verbose_name_plural = "user stats"
        indexes = [models.Index(fields=["-points"], name="userstats_points_idx")]

    def __str__(self):
        return f"{self.user.email}: {self.points} pts (L{self.level})"

    def get_rank(self) -> int:
        """Leaderboard rank (1 = best). Users with equal points share a rank."""
        return (
            UserStats.objects.filter(points__gt=self.points, user__is_active=True).count() + 1
        )
