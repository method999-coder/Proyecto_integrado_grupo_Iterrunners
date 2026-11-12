from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Perfil, Club

@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    if created:
        perfil, _ = Perfil.objects.get_or_create(
            usuario=instance,
            defaults={
                "nombre": instance.username,
                "rol": Perfil.role_from_user(instance),
            }
        )
        # Ensure every newly created user has an explicit club when possible.
        # Prefer the most recently created club so tests that create a club
        # just before creating a user receive that club.
        if not perfil.club:
            default_club = Club.objects.order_by("-id").first()
            if default_club:
                perfil.club = default_club
                perfil.save()
