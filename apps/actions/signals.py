from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Proof


@receiver(post_delete, sender=Proof)
def delete_proof_image_file(sender, instance, **kwargs):
    """Remove the image from storage when a Proof row is deleted."""
    if instance.image:
        instance.image.delete(save=False)
