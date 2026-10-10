from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, UserStats


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile_and_stats(sender, instance, created, raw=False, **kwargs):
    """Every new user automatically gets a Profile and a UserStats row."""
    if created and not raw:
        Profile.objects.get_or_create(user=instance)
        UserStats.objects.get_or_create(user=instance)
