from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Perfil


class UpdateLastSeenMiddleware:
    """Update Perfil.last_seen for authenticated users with a small write throttle."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return response

        now = timezone.now()
        cutoff = now - timedelta(minutes=5)

        Perfil.objects.filter(usuario_id=user.id).filter(
            Q(last_seen__isnull=True) | Q(last_seen__lt=cutoff)
        ).update(last_seen=now)

        return response
