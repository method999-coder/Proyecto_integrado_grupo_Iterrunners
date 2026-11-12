# INICIO - Consultar el estado de la integración
from django.conf import settings
# FIN - Consultar el estado de la integración
from django.core.management.base import BaseCommand

from users.models import Perfil
from users.views import _auto_mark_cumplimiento_from_strava, _strava_sync_latest_activities


class Command(BaseCommand):
    help = "Sincroniza Strava y auto-marca cumplimiento para corredores con cuenta conectada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lookback-days",
            type=int,
            default=3,
            help="Dias hacia atras para buscar actividades y marcar cumplimiento (default: 3).",
        )
        parser.add_argument(
            "--per-page",
            type=int,
            default=30,
            help="Cantidad de actividades a pedir a Strava por corredor (default: 30).",
        )

    def handle(self, *args, **options):
        # INICIO - Omitir sincronización y escrituras cuando Strava está desactivado
        if not settings.STRAVA_ENABLED:
            self.stdout.write("Strava está desactivado. Se omitió el auto-cumplimiento.")
            return
        # FIN - Omitir sincronización y escrituras cuando Strava está desactivado

        lookback_days = max(0, int(options["lookback_days"]))
        per_page = max(1, int(options["per_page"]))

        perfiles = list(
            Perfil.objects
            .filter(
                rol="corredor",
                strava_access_token__isnull=False,
            )
            .exclude(strava_access_token="")
            .select_related("usuario", "grupo")
        )

        total = len(perfiles)
        synced_ok = 0
        synced_error = 0
        sync_exceptions = 0
        auto_marked_total = 0

        for perfil in perfiles:
            try:
                ok = _strava_sync_latest_activities(perfil, per_page=per_page)
                if ok:
                    synced_ok += 1
                else:
                    synced_error += 1

                auto_marked_total += _auto_mark_cumplimiento_from_strava(
                    perfil,
                    lookback_days=lookback_days,
                )
            except Exception as exc:
                sync_exceptions += 1
                synced_error += 1
                self.stderr.write(
                    f"[ERROR] Perfil {perfil.id} ({perfil.usuario.username}): {type(exc).__name__}: {exc}"
                )
                continue

        self.stdout.write(self.style.SUCCESS("Auto-cumplimiento Strava finalizado"))
        self.stdout.write(f"Corredores evaluados: {total}")
        self.stdout.write(f"Sync exitoso: {synced_ok}")
        self.stdout.write(f"Sync con error: {synced_error}")
        self.stdout.write(f"Errores por excepción: {sync_exceptions}")
        self.stdout.write(f"Cumplimientos auto-marcados: {auto_marked_total}")
