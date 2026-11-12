from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import PasswordResetConfirmView
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import HttpResponseForbidden
from django.http import HttpResponse
from django.http import JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string

from .forms import CrearCorredorForm, EditarCorredorForm, EntrenamientoDiarioForm, EntrenamientoRecursoForm, GrupoForm, RitmoForm, CarreraManualForm, LactatoManualForm
from .models import CumplimientoEntrenamiento, EntrenamientoDiario, EntrenamientoRecurso, FeedComentario, FeedLike, Grupo, Perfil, Ritmo, StravaActividad, CarreraManual, LactatoManual, Club, RankingEntry, RankingAudit
from django.db.models import Count, Max, Q
import urllib.parse
import requests
from django.conf import settings
from django.utils import timezone
import math
from django.utils.dateparse import parse_datetime
from geopy.geocoders import Nominatim
import time
from django.db.models import Sum
from django.db.models.functions import Coalesce


_GEOCODER = Nominatim(user_agent="iterrunners_app")
logger = logging.getLogger(__name__)


class IterPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "users/password_reset_confirm.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        Perfil.objects.filter(usuario=form.user).update(must_change_password=False)
        return response


def _pick_first(mapping: dict, keys: list[str]):
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def _clean_admin_name(value):
    if not value:
        return None

    clean = str(value).strip()
    prefixes = (
        "Provincia de ",
        "Región de ",
        "Region de ",
        "Comuna de ",
        "Municipalidad de ",
    )
    for prefix in prefixes:
        if clean.startswith(prefix):
            clean = clean.replace(prefix, "", 1).strip()

    return clean or None

# ---------------------------------------------------------------------
# Helpers (permiso/roles)
# ---------------------------------------------------------------------

def _is_in_group(user, name: str) -> bool:
    return user.groups.filter(name=name).exists()


def _is_staffish(user) -> bool:
    # “Profesor” o “Admin” funcional o superuser
    return user.is_superuser or _is_in_group(user, "Profesor") or _is_in_group(user, "Admin")


def _normalize_ritmo_tipo(value):
    value = (value or "").strip().lower()
    return value if value in {"runners", "trail"} else "runners"


def _build_ritmos_resumen(ritmo_actual, tipo_ritmo):
    if not ritmo_actual:
        return []

    if tipo_ritmo == "trail":
        etiquetas = ["Z0", "Z1", "Z2", "Z3", "Z4", "Z5"]
    else:
        etiquetas = ["REG", "R1", "R2", "R3", "UL", "CA", "CAN"]

    valores = [
        (ritmo_actual.reg_min, ritmo_actual.reg_max),
        (ritmo_actual.r1_min, ritmo_actual.r1_max),
        (ritmo_actual.r2_min, ritmo_actual.r2_max),
        (ritmo_actual.r3_min, ritmo_actual.r3_max),
        (ritmo_actual.ul_min, ritmo_actual.ul_max),
        (ritmo_actual.ca_min, ritmo_actual.ca_max),
        (ritmo_actual.can_min, ritmo_actual.can_max),
    ]
    if tipo_ritmo == "trail":
        valores = valores[:6]

    return [(etiquetas[i], pair[0], pair[1]) for i, pair in enumerate(valores)]


def _forbidden(msg: str = "No tienes permiso para ver esta página."):
    return HttpResponseForbidden(msg)


def _resolve_user_club(user):
    perfil = (
        Perfil.objects
        .select_related("club", "grupo__club")
        .filter(usuario=user)
        .first()
    )
    if perfil:
        if perfil.club:
            return perfil.club
        if perfil.grupo and perfil.grupo.club:
            return perfil.grupo.club

    if user.is_superuser:
        return Club.objects.filter(nombre__iexact="kinerrunners").first() or Club.objects.order_by("id").first()

    return None


def _perfil_belongs_to_club(perfil, club):
    if not perfil or not club:
        return False
    if getattr(perfil, "club_id", None) == club.id:
        return True
    if getattr(perfil, "grupo_id", None) and perfil.grupo and perfil.grupo.club_id == club.id:
        return True
    return False


def _grupo_belongs_to_club(grupo, club):
    if not grupo or not club:
        return False
    return getattr(grupo, "club_id", None) == club.id


def _strava_refresh_token(perfil):
    """
    Refresca el access_token usando refresh_token si existe.
    Guarda nuevos tokens en el Perfil y retorna True si pudo refrescar.
    """

    # INICIO - Bloqueo de Strava en desarrollo
    if not settings.STRAVA_ENABLED:
        logger.info("Strava desactivado en Iterrunners-Dev")
        return False
    # FIN - Bloqueo de Strava en desarrollo

    if not perfil.strava_refresh_token:
        return False

    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": perfil.strava_refresh_token,
        },
        timeout=15,
    )

    data = resp.json()

    # Si Strava responde error, no refrescamos
    if resp.status_code != 200 or "access_token" not in data:
        logger.warning("Strava refresh token falló", extra={"status_code": resp.status_code})
        return False

    perfil.strava_access_token = data.get("access_token")
    perfil.strava_refresh_token = data.get("refresh_token")
    perfil.strava_expires_at = data.get("expires_at")

    athlete = data.get("athlete") or {}
    if athlete.get("id"):
        perfil.strava_athlete_id = athlete.get("id")

    perfil.save()
    logger.info("Strava refresh token exitoso")
    return True


def _strava_sync_latest_activities(perfil, per_page=30):
    """
    Sincroniza ultimas actividades de Strava hacia BD local.
    Retorna True si la llamada principal fue exitosa.
    """
    # INICIO - Bloqueo de Strava en desarrollo
    if not settings.STRAVA_ENABLED:
        logger.info("Sincronización de Strava desactivada")
        return False
    # FIN - Bloqueo de Strava en desarrollo
    if not perfil or not perfil.strava_access_token:
        return False

    now_ts = int(timezone.now().timestamp())
    if perfil.strava_expires_at and perfil.strava_expires_at <= now_ts:
        if not _strava_refresh_token(perfil):
            return False

    headers = {"Authorization": f"Bearer {perfil.strava_access_token}"}
    try:
        resp = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers=headers,
            params={"per_page": per_page, "page": 1},
            timeout=15,
        )
    except Exception:
        logger.exception("Error consultando actividades en Strava")
        return False

    if resp.status_code != 200:
        logger.warning("Strava activities fallo", extra={"status_code": resp.status_code})
        return False

    actividades = resp.json() or []
    with transaction.atomic():
        for a in actividades:
            strava_id = a.get("id")
            if not strava_id:
                continue

            start_date = parse_datetime(a.get("start_date"))

            StravaActividad.objects.update_or_create(
                strava_id=strava_id,
                defaults={
                    "perfil": perfil,
                    "name": a.get("name") or "",
                    "type": a.get("type") or "",
                    "sport_type": a.get("sport_type") or "",
                    "start_date": start_date,
                    "distance_m": a.get("distance"),
                    "moving_time_s": a.get("moving_time"),
                    "elapsed_time_s": a.get("elapsed_time"),
                    "total_elevation_gain_m": a.get("total_elevation_gain"),
                    "average_heartrate": a.get("average_heartrate"),
                    "max_heartrate": a.get("max_heartrate"),
                    "publicar_en_feed": True,
                    "start_lat": None,
                    "start_lng": None,
                    "comuna": None,
                    "region": None,
                    "pais": None,
                },
            )

    return True


def _auto_mark_cumplimiento_from_strava(perfil, lookback_days=3, min_distance_m=1):
    """
    Marca cumplimiento automatico usando actividades Strava recientes.
    No modifica la vista de profesor: solo completa datos en backend.
    """
    if not perfil or not getattr(perfil, "grupo_id", None):
        return 0

    today = timezone.localdate()
    start_date = today - timedelta(days=max(0, int(lookback_days)))

    actividades = list(
        StravaActividad.objects
        .filter(
            perfil=perfil,
            start_date__date__range=(start_date, today),
            distance_m__gte=min_distance_m,
        )
        .order_by("-start_date")
    )
    if not actividades:
        return 0

    actividades_por_fecha = {}
    for actividad in actividades:
        if not actividad.start_date:
            continue

        fecha_local = timezone.localtime(actividad.start_date).date()
        if fecha_local < start_date or fecha_local > today:
            continue

        actividad_kind = (actividad.sport_type or actividad.type or "").strip()
        if actividad_kind not in {"Run", "TrailRun"}:
            continue

        current = actividades_por_fecha.get(fecha_local)
        if not current:
            actividades_por_fecha[fecha_local] = actividad
            continue

        current_dist = current.distance_m or 0
        new_dist = actividad.distance_m or 0
        if new_dist > current_dist:
            actividades_por_fecha[fecha_local] = actividad

    if not actividades_por_fecha:
        return 0

    fechas = sorted(actividades_por_fecha.keys())
    entrenos = list(
        EntrenamientoDiario.objects
        .filter(
            grupo=perfil.grupo,
            fecha__in=fechas,
        )
        .order_by("fecha")
    )
    if not entrenos:
        return 0

    cumplimientos = {
        c.entrenamiento_id: c
        for c in CumplimientoEntrenamiento.objects.filter(
            perfil=perfil,
            entrenamiento_id__in=[e.id for e in entrenos],
        )
    }

    def _is_kind_compatible(entreno_item, actividad_item):
        modalidad = _normalize_ritmo_tipo(getattr(entreno_item, "modalidad", "runners"))
        kind = (actividad_item.sport_type or actividad_item.type or "").strip()
        if modalidad == "trail":
            return kind in {"TrailRun", "Run"}
        return kind in {"Run", "TrailRun"}

    marcados = 0
    with transaction.atomic():
        for entreno in entrenos:
            actividad = actividades_por_fecha.get(entreno.fecha)
            if not actividad or not _is_kind_compatible(entreno, actividad):
                continue

            cumplimiento = cumplimientos.get(entreno.id)
            if cumplimiento and cumplimiento.realizada:
                continue

            if cumplimiento and not cumplimiento.realizada:
                # Respetar pendientes con comentario/ranking cargado manualmente.
                if (cumplimiento.comentario or "").strip() or cumplimiento.publicar_ranking or cumplimiento.ranking_distancia:
                    continue
                cumplimiento.realizada = True
                cumplimiento.realizada_at = timezone.now()
                cumplimiento.save(update_fields=["realizada", "realizada_at", "updated_at"])
                marcados += 1
                continue

            CumplimientoEntrenamiento.objects.create(
                perfil=perfil,
                entrenamiento=entreno,
                fecha=entreno.fecha,
                realizada=True,
                realizada_at=timezone.now(),
            )
            marcados += 1

    return marcados


def _geocode_location(lat, lng):
    """
    Obtiene la ubicación (comuna, provincia, país) a partir de coordenadas.
    Usa Nominatim (OpenStreetMap) - gratis pero requiere respetar rate limit.
    Retorna (comuna, provincia, pais) o (None, None, None) si falla.
    """
    if lat is None or lng is None:
        return None, None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, None, None
    
    try:
        # Nominatim requiere rate limiting (max 1 request/segundo)
        time.sleep(1.1)  # Esperar 1.1 segundos entre requests

        location = _GEOCODER.reverse(
            f"{lat}, {lng}",
            language="es",
            timeout=10,
            exactly_one=True,
            zoom=14,
            addressdetails=True,
        )

        if not location or not location.raw:
            location = _GEOCODER.reverse(
                f"{lat}, {lng}",
                language="es",
                timeout=10,
                exactly_one=True,
                addressdetails=True,
            )
        
        if not location or not location.raw:
            return None, None, None
        
        address = location.raw.get("address", {})
        
        country_code = (address.get("country_code") or "").lower()
        pais = _clean_admin_name(address.get("country"))

        if country_code == "cl":
            comuna = _pick_first(address, [
                "municipality",
                "city_district",
                "suburb",
                "quarter",
                "borough",
                "town",
                "village",
                "city",
            ])
            region = _pick_first(address, [
                "state",
                "region",
                "state_district",
                "county",
            ])
        else:
            comuna = _pick_first(address, [
                "city",
                "town",
                "village",
                "municipality",
                "suburb",
                "city_district",
            ])
            region = _pick_first(address, [
                "state",
                "region",
                "state_district",
                "county",
            ])

        comuna = _clean_admin_name(comuna)
        region = _clean_admin_name(region)

        return comuna, region, pais
    
    except Exception:
        logger.exception("Error geocodificando ubicación")
        return None, None, None


# ---------------------------------------------------------------------
# PÚBLICO / HOME
# ---------------------------------------------------------------------

def home_public(request):
    return render(request, "users/home_public.html")


def healthcheck(request):
    return HttpResponse("ok", content_type="text/plain")


def privacy_policy(request):
    return render(request, "users/privacy.html")


def logout_view(request):
    auth_logout(request)
    return redirect("login")


@login_required
def home(request):
    es_profesor = _is_in_group(request.user, "Profesor")
    es_admin = _is_in_group(request.user, "Admin")
    es_corredor = _is_in_group(request.user, "Corredor")

    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )

    # Si es corredor y debe cambiar contraseña -> forzar
    if perfil and perfil.must_change_password and es_corredor:
        return redirect("cambiar_password")

    entreno_hoy = None
    grupo = None
    fecha_hoy = timezone.localdate()

    if perfil and perfil.grupo:
        grupo = perfil.grupo

        entreno_hoy = EntrenamientoDiario.objects.filter(
            grupo=grupo,
            fecha=fecha_hoy
        ).prefetch_related("recursos").first()
        
    # INICIO - Omitir sincronización y auto-cumplimiento con Strava desactivado
    strava_conectado = bool(settings.STRAVA_ENABLED and perfil and perfil.strava_access_token)
    if strava_conectado:

        # Sincronizacion liviana para reflejar rapido nuevos kms semanales sin recarga manual.
        last_sync = (
            StravaActividad.objects
            .filter(perfil=perfil)
            .aggregate(last=Max("updated_at"))
            .get("last")
        )
        sync_threshold = timezone.now() - timedelta(minutes=3)
        should_sync = (last_sync is None) or (last_sync < sync_threshold)
        if should_sync:
            _strava_sync_latest_activities(perfil, per_page=30)

        # Auto cumplimiento por Strava (no cambia UX de cumplimiento para profesor).
        _auto_mark_cumplimiento_from_strava(perfil, lookback_days=3)
    # FIN - Omitir sincronización y auto-cumplimiento con Strava desactivado

    tipo_ritmo = _normalize_ritmo_tipo(
        getattr(entreno_hoy, "modalidad", None)
        or getattr(perfil, "modalidad_ritmo", "runners")
    )
    ritmo_actual = Ritmo.objects.filter(usuario=request.user, tipo=tipo_ritmo).first()
    ritmos_resumen = _build_ritmos_resumen(ritmo_actual, tipo_ritmo)

    km_semana = None
    if perfil:
        inicio_semana = fecha_hoy - timedelta(days=fecha_hoy.weekday())
        fin_semana = inicio_semana + timedelta(days=6)

        agg_semana = StravaActividad.objects.filter(
            perfil=perfil,
            start_date__date__range=(inicio_semana, fin_semana),
        ).aggregate(
            dist_m=Coalesce(Sum("distance_m"), 0.0),
        )

        km_semana = (agg_semana.get("dist_m") or 0.0) / 1000.0

    # Cumpleaños hoy (por club)
    cumpleanos_hoy = []
    if perfil and perfil.club:
        hoy = fecha_hoy
        cumple_qs = Perfil.objects.filter(
            club=perfil.club,
            fecha_nacimiento__isnull=False,
            fecha_nacimiento__month=hoy.month,
            fecha_nacimiento__day=hoy.day,
        ).select_related("usuario")
        cumpleanos_hoy = list(cumple_qs)


    return render(request, "users/home.html", {
        "perfil": perfil,
        "grupo": grupo,
        "entreno_hoy": entreno_hoy,
        "fecha_hoy": fecha_hoy,
        "es_profesor": es_profesor,
        "es_admin": es_admin,
        "es_corredor": es_corredor,
        # INICIO - Controlar acciones de Strava en el inicio
        "strava_enabled": settings.STRAVA_ENABLED,
        "strava_conectado": strava_conectado,
        # FIN - Controlar acciones de Strava en el inicio
        "ritmos_resumen": ritmos_resumen,
        "tipo_ritmo_actual": tipo_ritmo,
        "km_semana": km_semana,
        "cumpleanos_hoy": cumpleanos_hoy,
    })


@login_required
def ranking(request):
    distancias = [
        (3, "3000m"),
        (5, "5K"),
        (10, "10K"),
        (21, "21K"),
        (42, "42K"),
    ]
    distancia_valores = {valor for valor, _ in distancias}
    distancias_por_valor = {valor: texto for valor, texto in distancias}
    distancia_raw = (request.GET.get("distancia") or "10").strip()
    distancia_actual = int(distancia_raw) if distancia_raw.isdigit() and int(distancia_raw) in distancia_valores else 10
    distancia_actual_label = distancias_por_valor.get(distancia_actual, "10K")

    es_corredor = _is_in_group(request.user, "Corredor")
    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )
    scope_label = "Global"
    def _format_seconds(value):
        if value is None:
            return None
        total = int(value)
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _format_pace(value_seconds, distance_km):
        if not value_seconds or not distance_km:
            return "-"
        pace_seconds = int(round(value_seconds / float(distance_km)))
        minutes = pace_seconds // 60
        seconds = pace_seconds % 60
        return f"{minutes}:{seconds:02d} /km"

    ranking_entries = (
        RankingEntry.objects
        .filter(ranking_distancia=distancia_actual)
        .select_related("perfil", "perfil__usuario", "cumplimiento")
    )

    filas_ranking = []
    for entry in ranking_entries:
        perfil_entry = entry.perfil
        if not perfil_entry:
            continue

        nombre = (perfil_entry.nombre or "").strip()
        apellido = (perfil_entry.apellido or "").strip()
        username = perfil_entry.usuario.username if perfil_entry.usuario else ""
        nombre_mostrar = f"{nombre} {apellido}".strip() or username

        time_seconds = entry.time_seconds
        if time_seconds is None and entry.cumplimiento and entry.cumplimiento.audit_meta:
            audit_meta = entry.cumplimiento.audit_meta if isinstance(entry.cumplimiento.audit_meta, dict) else None
            if audit_meta:
                stored_time = audit_meta.get("time_seconds")
                if isinstance(stored_time, (int, float)):
                    time_seconds = int(stored_time)

        if time_seconds is None:
            continue

        if entry.cumplimiento and entry.cumplimiento.fecha:
            ultima_marca = entry.cumplimiento.fecha
        else:
            ultima_marca = entry.created_at.date()

        filas_ranking.append({
            "perfil_id": perfil_entry.id,
            "nombre": nombre_mostrar,
            "marca_tiempo": _format_seconds(time_seconds),
            "marca_distancia_km": f"{distancia_actual:.0f}",
            "marca_ritmo": _format_pace(time_seconds, distancia_actual),
            "ultima_marca": ultima_marca,
            "_orden_time": time_seconds,
        })

    filas_ranking.sort(key=lambda row: (row["_orden_time"], row["ultima_marca"]))
    for posicion, fila in enumerate(filas_ranking, start=1):
        fila["posicion"] = posicion
        fila.pop("_orden_time", None)

    return render(request, "users/ranking.html", {
        "perfil": perfil,
        "distancias": distancias,
        "distancia_actual": distancia_actual,
        "distancia_actual_label": distancia_actual_label,
        "filas_ranking": filas_ranking,
        "scope_label": scope_label,
        "es_corredor": es_corredor,
    })


@login_required
def feed(request):
    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )

    feed_posts = list(
        StravaActividad.objects
        .filter(perfil__rol="corredor", publicar_en_feed=True)
        .select_related(
            "perfil",
            "perfil__usuario",
            "perfil__grupo",
        )
        .prefetch_related("feed_comentarios", "feed_comentarios__usuario")
        .annotate(
            likes_total=Count("feed_likes", distinct=True),
            comentarios_total=Count("feed_comentarios", distinct=True),
        )
        .order_by("-start_date", "-updated_at")[:60]
    )

    liked_ids = set(
        FeedLike.objects
        .filter(usuario=request.user, actividad_id__in=[post.id for post in feed_posts])
        .values_list("actividad_id", flat=True)
    )

    for post in feed_posts:
        post.user_liked = post.id in liked_ids

    return render(request, "users/feed.html", {
        "perfil": perfil,
        "feed_posts": feed_posts,
    })


@login_required
def feed_like_toggle(request, actividad_id):
    if request.method != "POST":
        return _forbidden("Método no permitido.")

    actividad = get_object_or_404(
        StravaActividad.objects.filter(
            perfil__rol="corredor",
            publicar_en_feed=True,
        ),
        id=actividad_id,
    )

    like = FeedLike.objects.filter(actividad=actividad, usuario=request.user).first()
    if like:
        like.delete()
    else:
        FeedLike.objects.create(actividad=actividad, usuario=request.user)

    return redirect(f"{reverse('feed')}#post-{actividad_id}")


@login_required
def feed_comentar(request, actividad_id):
    if request.method != "POST":
        return _forbidden("Método no permitido.")

    actividad = get_object_or_404(
        StravaActividad.objects.filter(
            perfil__rol="corredor",
            publicar_en_feed=True,
        ),
        id=actividad_id,
    )

    texto = (request.POST.get("texto") or "").strip()
    if not texto:
        return redirect(f"{reverse('feed')}#post-{actividad_id}")

    if len(texto) > 300:
        messages.error(request, "El comentario no puede superar 300 caracteres.")
        return redirect(f"{reverse('feed')}#post-{actividad_id}")

    FeedComentario.objects.create(
        actividad=actividad,
        usuario=request.user,
        texto=texto,
    )
    return redirect(f"{reverse('feed')}#post-{actividad_id}")


def _sugerencia_ranking_desde_strava(perfil, fecha_obj):
    if not perfil:
        return None

    if perfil.strava_athlete_id:
        perfiles_mismo_athlete = Perfil.objects.filter(
            strava_athlete_id=perfil.strava_athlete_id
        ).values_list("id", flat=True)
        actividades_qs = StravaActividad.objects.filter(perfil_id__in=perfiles_mismo_athlete)
    else:
        actividades_qs = StravaActividad.objects.filter(perfil=perfil)

    actividad = (
        actividades_qs
        .filter(start_date__date=fecha_obj)
        .order_by("-distance_m", "-start_date")
        .first()
    )

    if not actividad or not actividad.distance_m:
        return None

    distancia_km = float(actividad.distance_m) / 1000.0
    opciones = [
        (3, "3000m (Control)", 3.0, 0.35),
        (5, "5K", 5.0, 0.60),
        (10, "10K", 10.0, 1.00),
        (21, "21K", 21.0, 1.50),
        (42, "42K", 42.0, 3.00),
    ]

    mejor_opcion = None
    for valor, etiqueta, referencia_km, tolerancia_km in opciones:
        diferencia = abs(distancia_km - referencia_km)
        if diferencia <= tolerancia_km:
            if mejor_opcion is None or diferencia < mejor_opcion["diferencia"]:
                mejor_opcion = {
                    "valor": valor,
                    "etiqueta": etiqueta,
                    "diferencia": diferencia,
                }

    return {
        "actividad_nombre": actividad.name or "Actividad",
        "actividad_km": round(distancia_km, 2),
        "sugerencia_valor": mejor_opcion["valor"] if mejor_opcion else None,
        "sugerencia_etiqueta": mejor_opcion["etiqueta"] if mejor_opcion else None,
    }


def _parse_tiempo_a_segundos(value):
    if not value:
        return None

    parts = str(value).strip().split(":")
    try:
        numbers = [int(part) for part in parts]
    except Exception:
        return None

    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
        return hours * 3600 + minutes * 60 + seconds
    return None


def _obtener_tiempo_segundos_para_ranking(cumplimiento, fallback_time_s=None):
    if cumplimiento and cumplimiento.audit_meta:
        audit_meta = cumplimiento.audit_meta if isinstance(cumplimiento.audit_meta, dict) else None
        if audit_meta:
            stored_time = audit_meta.get("time_seconds")
            if isinstance(stored_time, (int, float)):
                return int(stored_time)

    if fallback_time_s is not None:
        try:
            return int(fallback_time_s)
        except Exception:
            return None

    return None


def _registrar_ranking_manual(*, perfil, cumplimiento, entrenamiento, ranking_distancia, tiempo_segundos, actor):
    snapshot = {
        "cumplimiento_id": cumplimiento.id if cumplimiento else None,
        "entrenamiento_id": entrenamiento.id if entrenamiento else None,
        "perfil_id": perfil.id if perfil else None,
        "ranking_distancia": ranking_distancia,
        "time_seconds": tiempo_segundos,
    }

    with transaction.atomic():
        existing = (
            RankingEntry.objects
            .select_for_update()
            .filter(perfil=perfil, ranking_distancia=ranking_distancia)
            .first()
        )

        accepted = False
        replaced = False
        previous_time = existing.time_seconds if existing else None

        if existing is None:
            RankingEntry.objects.create(
                perfil=perfil,
                ranking_distancia=ranking_distancia,
                cumplimiento=cumplimiento,
                time_seconds=tiempo_segundos,
            )
            accepted = True
        else:
            current_time = existing.time_seconds
            if current_time is None or (tiempo_segundos is not None and tiempo_segundos < current_time):
                existing.cumplimiento = cumplimiento
                existing.time_seconds = tiempo_segundos
                existing.save(update_fields=["cumplimiento", "time_seconds"])
                accepted = True
                replaced = True

        RankingAudit.objects.create(
            perfil=perfil,
            club=getattr(perfil, "club", None),
            cumplimiento=cumplimiento,
            entrenamiento=entrenamiento,
            actor=actor,
            action="subir_al_ranking",
            origin="manual",
            suggested_ranking=ranking_distancia,
            accepted=accepted,
            published_ranking=accepted,
            snapshot={
                **snapshot,
                "accepted": accepted,
                "replaced": replaced,
                "previous_time_seconds": previous_time,
            },
            comment="Subida manual al ranking",
        )

        return accepted, replaced, previous_time


def _sugerir_ranking_desde_distancia(distance_m):
    if not distance_m:
        return None

    distancia_km = float(distance_m) / 1000.0
    opciones = [
        (3, 3.0, 0.35),
        (5, 5.0, 0.60),
        (10, 10.0, 1.00),
        (21, 21.0, 1.50),
        (42, 42.0, 3.00),
    ]

    mejor_opcion = None
    for valor, referencia_km, tolerancia_km in opciones:
        diferencia = abs(distancia_km - referencia_km)
        if diferencia <= tolerancia_km:
            if mejor_opcion is None or diferencia < mejor_opcion["diferencia"]:
                mejor_opcion = {
                    "valor": valor,
                    "etiqueta": f"{valor}K" if valor != 3 else "3000m",
                    "diferencia": diferencia,
                }

    return {
        "actividad_km": round(distancia_km, 2),
        "sugerencia_valor": mejor_opcion["valor"] if mejor_opcion else None,
        "sugerencia_etiqueta": mejor_opcion["etiqueta"] if mejor_opcion else None,
    }


@login_required
@transaction.atomic
def registro_actividad(request):
    ranking_distancias = [
        (3, "3000m (Control)"),
        (5, "5K"),
        (10, "10K"),
        (21, "21K"),
        (42, "42K"),
    ]
    ranking_distancias_validas = {str(valor) for valor, _ in ranking_distancias}

    es_corredor = _is_in_group(request.user, "Corredor")
    es_admin = request.user.is_superuser or _is_in_group(request.user, "Admin")
    puede_registrar = es_corredor or es_admin

    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )

    if not perfil or not puede_registrar:
        return _forbidden("Solo corredores y administradores pueden marcar cumplimiento.")

    # Si el corredor no tiene grupo, redirigir a su historial de carreras manuales
    # para que pueda agregar una marca manual (no restauramos grupos anteriores).
    if not perfil.grupo:
        messages.info(request, "No tienes un grupo asignado. Puedes agregar una marca manual en tu historial.")
        return redirect("historial_carreras_manual", perfil_id=perfil.id)

    fecha_hoy = timezone.localdate()
    fecha_raw = request.POST.get("fecha") if request.method == "POST" else request.GET.get("fecha")

    if not fecha_raw:
        fecha_obj = fecha_hoy
    else:
        try:
            fecha_obj = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
        except Exception:
            fecha_obj = fecha_hoy

    entreno_registro = EntrenamientoDiario.objects.filter(grupo=perfil.grupo, fecha=fecha_obj).first()
    cumplimiento_registro = None

    if entreno_registro:
        cumplimiento_registro = (
            CumplimientoEntrenamiento.objects
            .filter(perfil=perfil, entrenamiento=entreno_registro, fecha=fecha_obj)
            .first()
        )

    strava_sugerencia = _sugerencia_ranking_desde_strava(perfil, fecha_obj)
    ranking_distancia_sugerida = None
    if strava_sugerencia and strava_sugerencia.get("sugerencia_valor"):
        if not (cumplimiento_registro and cumplimiento_registro.ranking_distancia):
            ranking_distancia_sugerida = strava_sugerencia.get("sugerencia_valor")

    current_month = fecha_obj.replace(day=1)
    last_day_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    entrenos_mes = EntrenamientoDiario.objects.filter(
        grupo=perfil.grupo,
        fecha__range=(current_month, last_day_month),
    )
    entrenos_mes_set = set(entrenos_mes.values_list("fecha", flat=True))

    cumplimientos_mes = CumplimientoEntrenamiento.objects.filter(
        perfil=perfil,
        entrenamiento__grupo=perfil.grupo,
        fecha__range=(current_month, last_day_month),
    ).values("fecha", "realizada")
    cumplimiento_realizado_fechas = {
        item["fecha"] for item in cumplimientos_mes if bool(item["realizada"])
    }

    cal = calendar.Calendar(firstweekday=0)  # lunes
    month_days = list(cal.itermonthdates(current_month.year, current_month.month))
    weeks_month = []
    for i in range(0, len(month_days), 7):
        row = []
        for d in month_days[i:i + 7]:
            in_month = d.month == current_month.month
            status = "empty"
            if in_month and d in entrenos_mes_set:
                status = "done" if d in cumplimiento_realizado_fechas else "pending"

            row.append({
                "date": d,
                "in_month": in_month,
                "status": status,
                "selected": d == fecha_obj,
                "today": d == fecha_hoy,
            })
        weeks_month.append(row)

    prev_month_ref = (current_month - timedelta(days=1)).replace(day=1)
    next_month_ref = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)

    if request.method != "POST":
        ranking_habilitado = bool(entreno_registro and entreno_registro.tipo in {"carrera", "control"})
        return render(request, "users/registro_actividad.html", {
            "perfil": perfil,
            "fecha_hoy": fecha_hoy,
            "fecha_consulta": fecha_obj,
            "entreno_registro": entreno_registro,
            "cumplimiento_registro": cumplimiento_registro,
            "ranking_habilitado": ranking_habilitado,
            "ranking_distancias": ranking_distancias,
            "strava_sugerencia": strava_sugerencia,
            "ranking_distancia_sugerida": ranking_distancia_sugerida,
            "month_current": current_month,
            "month_prev_ref": prev_month_ref,
            "month_next_ref": next_month_ref,
            "month_weeks": weeks_month,
        })

    try:
        fecha_obj = datetime.strptime(request.POST.get("fecha"), "%Y-%m-%d").date()
    except Exception:
        messages.error(request, "La fecha seleccionada no es válida.")
        return redirect(reverse("registro_actividad"))

    entreno_hoy = EntrenamientoDiario.objects.filter(grupo=perfil.grupo, fecha=fecha_obj).first()

    if not entreno_hoy:
        messages.warning(request, "No tienes entrenamiento asignado en la fecha seleccionada.")
        return redirect(f"{reverse('registro_actividad')}?fecha={fecha_obj.strftime('%Y-%m-%d')}")

    realizada = request.POST.get("realizada") == "on"
    comentario = (request.POST.get("comentario") or "").strip()
    ranking_habilitado = entreno_hoy.tipo in {"carrera", "control"}
    publicar_ranking = request.POST.get("publicar_ranking") == "on"
    ranking_distancia_raw = (request.POST.get("ranking_distancia") or "").strip()

    if publicar_ranking and not ranking_distancia_raw:
        sugerencia_post = _sugerencia_ranking_desde_strava(perfil, fecha_obj)
        if sugerencia_post and sugerencia_post.get("sugerencia_valor"):
            ranking_distancia_raw = str(sugerencia_post.get("sugerencia_valor"))

    if not ranking_habilitado:
        publicar_ranking = False
        ranking_distancia_raw = ""

    if not realizada:
        publicar_ranking = False
        ranking_distancia_raw = ""

    if publicar_ranking and ranking_distancia_raw not in ranking_distancias_validas:
        messages.error(request, "Debes seleccionar una distancia válida para publicar en ranking.")
        return redirect(f"{reverse('registro_actividad')}?fecha={fecha_obj.strftime('%Y-%m-%d')}")

    ranking_distancia = int(ranking_distancia_raw) if publicar_ranking and ranking_distancia_raw else None

    cumplimiento, created = CumplimientoEntrenamiento.objects.get_or_create(
        perfil=perfil,
        entrenamiento=entreno_hoy,
        fecha=fecha_obj,
    )

    if not realizada and not comentario:
        if not created:
            cumplimiento.delete()
            messages.info(request, "Registro eliminado. Queda como pendiente.")
        else:
            messages.info(request, "Sin cambios: queda como pendiente.")
        return redirect(f"{reverse('registro_actividad')}?fecha={fecha_obj.strftime('%Y-%m-%d')}")

    cumplimiento.realizada = realizada
    cumplimiento.comentario = comentario
    cumplimiento.realizada_at = timezone.now() if cumplimiento.realizada else None
    cumplimiento.publicar_ranking = publicar_ranking
    cumplimiento.ranking_distancia = ranking_distancia
    cumplimiento.save(update_fields=[
        "fecha",
        "realizada",
        "realizada_at",
        "comentario",
        "publicar_ranking",
        "ranking_distancia",
        "updated_at",
    ])

    if cumplimiento.realizada:
        messages.success(request, "Actividad registrada como realizada ✅")
    else:
        messages.success(request, "Registro guardado como pendiente.")

    return redirect(f"{reverse('registro_actividad')}?fecha={fecha_obj.strftime('%Y-%m-%d')}")


# ---------------------------------------------------------------------
# CORREDOR
# ---------------------------------------------------------------------

@login_required
def calendario(request):
    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )

    today = timezone.localdate()

    if not perfil or not perfil.grupo:
        return render(request, "users/calendario.html", {
            "perfil": perfil,
            "grupo": getattr(perfil, "grupo", None),
            "weeks": [],
            "current": None,
            "prev_month": None,
            "next_month": None,
            "today": today,
            "selected": None,
            "selected_item": None,
        })

    grupo = perfil.grupo

    # mes actual
    ym = request.GET.get("m")  # "YYYY-MM"
    if ym:
        try:
            year, month = [int(x) for x in ym.split("-")]
            current = today.replace(year=year, month=month, day=1)
        except Exception:
            current = today.replace(day=1)
    else:
        current = today.replace(day=1)

    first_day = current
    last_day = (current.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    entrenos = EntrenamientoDiario.objects.filter(
        grupo=grupo,
        fecha__range=(first_day, last_day)
    ).prefetch_related("recursos").order_by("fecha")

    entrenos_by_date = {e.fecha: e for e in entrenos}

    cal = calendar.Calendar(firstweekday=0)  # lunes
    month_days = list(cal.itermonthdates(current.year, current.month))

    weeks = []
    for i in range(0, len(month_days), 7):
        row = []
        for d in month_days[i:i + 7]:
            if d.month != current.month:
                row.append({"date": d, "in_month": False, "item": None})
            else:
                row.append({"date": d, "in_month": True, "item": entrenos_by_date.get(d)})
        weeks.append(row)

    # día seleccionado
    selected = None
    selected_item = None
    qdate = request.GET.get("date")  # "YYYY-MM-DD"
    if qdate:
        try:
            selected = datetime.strptime(qdate, "%Y-%m-%d").date()
            if selected.month == current.month and selected.year == current.year:
                selected_item = entrenos_by_date.get(selected)
        except Exception:
            selected = None
            selected_item = None

    prev_month = (current.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

    return render(request, "users/calendario.html", {
        "perfil": perfil,
        "grupo": grupo,
        "weeks": weeks,
        "current": current,
        "prev_month": prev_month,
        "next_month": next_month,
        "today": today,
        "selected": selected,
        "selected_item": selected_item,
    })


@login_required
def perfil_view(request):
    perfil = Perfil.objects.filter(usuario=request.user).select_related("grupo").first()
    ritmos_runners_qs = Ritmo.objects.filter(usuario=request.user, tipo="runners").order_by("-fecha", "-creado_en")
    ritmos_trail_qs = Ritmo.objects.filter(usuario=request.user, tipo="trail").order_by("-fecha", "-creado_en")

    ritmo_runners = ritmos_runners_qs.first()
    ritmo_trail = ritmos_trail_qs.first()

    ritmos_runners_prev = list(ritmos_runners_qs[1:])
    ritmos_trail_prev = list(ritmos_trail_qs[1:])

    return render(request, "users/perfil.html", {
        "perfil_obj": perfil,
        "ritmo_runners": ritmo_runners,
        "ritmo_trail": ritmo_trail,
        "ritmos_runners_prev": ritmos_runners_prev,
        "ritmos_trail_prev": ritmos_trail_prev,
    })


@login_required
def cambiar_password(request):
    perfil = get_object_or_404(Perfil, usuario=request.user)

    if not perfil.must_change_password:
        return redirect("home")

    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)

            perfil.must_change_password = False
            perfil.save()

            return redirect("home")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "users/cambiar_password.html", {"form": form})


# ---------------------------------------------------------------------
# ADMIN / PROFESOR
# ---------------------------------------------------------------------

@login_required
def administracion(request):
    if not _is_staffish(request.user):
        return _forbidden()
    return render(
        request,
        "users/administracion.html",
        {
            "show_activity_users": request.user.is_superuser,
        },
    )


@login_required
def actividad_usuarios(request):
    is_super = request.user.is_superuser
    is_admin_funcional = request.user.groups.filter(name="Admin").exists()
    if not (is_super or is_admin_funcional):
        return _forbidden()

    grupos = Grupo.objects.all().order_by("nombre")

    # if not superuser, scope lists to the user's club
    user_club = None
    if not is_super:
        perfil_self = Perfil.objects.filter(usuario=request.user).select_related("club", "grupo__club").first()
        if perfil_self:
            user_club = perfil_self.club or (perfil_self.grupo.club if perfil_self.grupo else None)
        if user_club:
            grupos = grupos.filter(club=user_club)
        else:
            grupos = Grupo.objects.none()
    grupo_id = (request.GET.get("grupo") or "").strip()
    estado = (request.GET.get("estado") or "todos").strip().lower()
    if estado not in {"todos", "activos", "inactivos", "strava", "nunca"}:
        estado = "todos"

    perfiles_qs = Perfil.objects.select_related("usuario", "grupo", "club").order_by("nombre", "apellido")
    if grupo_id:
        perfiles_qs = perfiles_qs.filter(grupo_id=grupo_id)
    if not is_super and user_club:
        perfiles_qs = perfiles_qs.filter(club=user_club)
    elif not is_super and not user_club:
        perfiles_qs = perfiles_qs.none()

    now = timezone.now()
    active_window_days = 7
    threshold = now - timedelta(days=active_window_days)

    all_rows = []
    for perfil in perfiles_qs:
        user = perfil.usuario
        last_login = user.last_login
        last_seen = perfil.last_seen
        if last_seen and last_login:
            last_access = max(last_seen, last_login)
        else:
            last_access = last_seen or last_login

        is_recently_active = bool(last_access and last_access >= threshold)
        strava_connected = bool(perfil.strava_access_token)

        item = {
            "perfil": perfil,
            "grupo_nombre": perfil.grupo.nombre if perfil.grupo else "Sin grupo",
            "last_login": last_login,
            "last_seen": last_seen,
            "last_access": last_access,
            "is_recently_active": is_recently_active,
            "strava_connected": strava_connected,
            "is_account_enabled": user.is_active,
        }
        all_rows.append(item)

    stats_total = len(all_rows)
    stats_active = sum(1 for item in all_rows if item["is_recently_active"])
    stats_inactive = stats_total - stats_active
    stats_strava = sum(1 for item in all_rows if item["strava_connected"])
    stats_never = sum(1 for item in all_rows if item["last_login"] is None)
    never_login_usernames = sorted(
        [item["perfil"].usuario.username for item in all_rows if item["last_login"] is None],
        key=lambda username: username.lower(),
    )

    rows = []
    for item in all_rows:
        if estado == "activos" and not item["is_recently_active"]:
            continue
        if estado == "inactivos" and item["is_recently_active"]:
            continue
        if estado == "strava" and not item["strava_connected"]:
            continue
        if estado == "nunca" and item["last_login"] is not None:
            continue
        rows.append(item)

    rows.sort(
        key=lambda item: (
            item["last_login"] is None,
            -(item["last_login"].timestamp()) if item["last_login"] else 0,
            (item["perfil"].nombre or "").lower(),
        )
    )

    context = {
        "grupos": grupos,
        "grupo_id": grupo_id,
        "estado": estado,
        "rows": rows,
        "active_window_days": active_window_days,
        "total": len(rows),
        "stats_total": stats_total,
        "stats_active": stats_active,
        "stats_inactive": stats_inactive,
        "stats_strava": stats_strava,
        "stats_never": stats_never,
        "never_login_usernames": never_login_usernames,
    }
    return render(request, "users/actividad_usuarios.html", context)


@login_required
def gestion_calendarios(request):
    if not _is_staffish(request.user):
        return _forbidden()

    user_club = None if request.user.is_superuser else _resolve_user_club(request.user)
    grupos = Grupo.objects.select_related("club").order_by("nombre")
    if not request.user.is_superuser:
        grupos = grupos.filter(club=user_club) if user_club else grupos.none()

    grupo = None
    grupo_id = request.GET.get("grupo")
    if grupo_id:
        grupo = grupos.filter(id=grupo_id).first()

    today = timezone.localdate()

    month_param = request.GET.get("month")
    year_param = request.GET.get("year")
    
    if month_param and year_param:
        try:
            month = int(month_param)
            year = int(year_param)
            current = today.replace(year=year, month=month, day=1)
        except Exception:
            current = today.replace(day=1)
    else:
        current = today.replace(day=1)

    weeks = []
    entrenos_by_date = {}
    selected = None
    selected_item = None

    if grupo:
        first_day = current
        last_day = (current.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        entrenos = EntrenamientoDiario.objects.filter(
            grupo=grupo,
            fecha__range=(first_day, last_day)
        ).prefetch_related("recursos").order_by("fecha")

        entrenos_by_date = {e.fecha: e for e in entrenos}

        cal = calendar.Calendar(firstweekday=0)
        month_days = list(cal.itermonthdates(current.year, current.month))

        for i in range(0, len(month_days), 7):
            row = []
            for d in month_days[i:i + 7]:
                if d.month != current.month:
                    row.append({"date": d, "in_month": False, "item": None})
                else:
                    row.append({"date": d, "in_month": True, "item": entrenos_by_date.get(d)})
            weeks.append(row)

        qdate = request.GET.get("date")  # "YYYY-MM-DD"
        if qdate:
            try:
                selected = datetime.strptime(qdate, "%Y-%m-%d").date()
                if selected.month == current.month and selected.year == current.year:
                    selected_item = entrenos_by_date.get(selected)
            except Exception:
                selected = None
                selected_item = None

    prev_month = (current.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

    return render(request, "users/gestion_calendarios.html", {
        "grupos": grupos,
        "grupo": grupo,
        "weeks": weeks,
        "current": current,
        "prev_month": prev_month,
        "next_month": next_month,
        "today": today,
        "selected": selected,
        "selected_item": selected_item,
    })


@login_required
def cumplimiento_hoy(request):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ver el cumplimiento.")

    fecha_param = request.GET.get("fecha")
    today = timezone.localdate()
    if fecha_param:
        try:
            today = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            pass
    grupo_id = request.GET.get("grupo")
    user_club = None if request.user.is_superuser else _resolve_user_club(request.user)
    grupos = Grupo.objects.select_related("club").order_by("nombre")
    if not request.user.is_superuser:
        grupos = grupos.filter(club=user_club) if user_club else grupos.none()
    grupo_seleccionado = grupos.filter(id=grupo_id).first() if grupo_id else None

    entrenamientos_hoy = EntrenamientoDiario.objects.filter(fecha=today).select_related("grupo").order_by("grupo__nombre")
    if not request.user.is_superuser:
        entrenamientos_hoy = entrenamientos_hoy.filter(grupo__club=user_club) if user_club else entrenamientos_hoy.none()
    if grupo_id:
        entrenamientos_hoy = entrenamientos_hoy.filter(grupo_id=grupo_id)

    grupos_data = []
    for entreno in entrenamientos_hoy:
        corredores = (
            Perfil.objects
            .filter(grupo=entreno.grupo)
            .filter(
                Q(rol__iexact="corredor")
                | Q(usuario__groups__name="Corredor")
                | Q(cumplimientos__entrenamiento=entreno, cumplimientos__fecha=today)
            )
            .distinct()
            .select_related("usuario")
            .order_by("nombre", "apellido", "usuario__username")
        )

        cumplimientos = (
            CumplimientoEntrenamiento.objects
            .filter(entrenamiento=entreno, fecha=today, perfil__in=corredores)
            .select_related("perfil")
        )
        cumplimientos_map = {item.perfil_id: item for item in cumplimientos}

        filas = []
        total_realizadas = 0

        for corredor in corredores:
            cumplimiento = cumplimientos_map.get(corredor.id)
            realizada = bool(cumplimiento and cumplimiento.realizada)
            if realizada:
                total_realizadas += 1

            nombre = (
                f"{corredor.usuario.first_name} {corredor.usuario.last_name}".strip()
                or corredor.nombre
                or corredor.usuario.username
            )

            filas.append({
                "perfil": corredor,
                "nombre": nombre,
                "realizada": realizada,
                "realizada_at": getattr(cumplimiento, "realizada_at", None),
                "comentario": (cumplimiento.comentario if cumplimiento else ""),
            })

        grupos_data.append({
            "grupo": entreno.grupo,
            "entreno": entreno,
            "filas": filas,
            "total_corredores": len(filas),
            "total_realizadas": total_realizadas,
            "estado": "con_plan_con_corredores" if filas else "con_plan_sin_corredores",
        })

    fecha_hoy_real = timezone.localdate()
    total_corredores = sum(item.get("total_corredores", 0) for item in grupos_data)
    total_realizadas = sum(item.get("total_realizadas", 0) for item in grupos_data)

    return render(request, "users/cumplimiento_hoy.html", {
        "today": today,
        "grupos": grupos,
        "grupo_seleccionado": grupo_seleccionado,
        "grupo_id": str(grupo_id) if grupo_id else "",
        "fecha": today,
        "es_hoy": (today == fecha_hoy_real),
        "grupos_data": grupos_data,
        "totales_cumplimiento": {
            "total_corredores": total_corredores,
            "total_realizadas": total_realizadas,
        },
    })


def _build_cumplidos_filas(cumplimientos, fecha):
    def _format_seconds(total_seconds):
        if not total_seconds:
            return "-"
        seconds = int(total_seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

    def _format_pace(total_seconds, total_distance_m):
        if not total_seconds or not total_distance_m or float(total_distance_m) <= 0:
            return "-"
        pace_seconds = float(total_seconds) / (float(total_distance_m) / 1000.0)
        mins = int(pace_seconds // 60)
        secs = int(round(pace_seconds % 60))
        if secs == 60:
            mins += 1
            secs = 0
        return f"{mins}:{secs:02d} /km"

    filas = []
    for item in cumplimientos:
        perfil = item.perfil
        usuario = perfil.usuario
        first_source = (usuario.first_name or perfil.nombre or "").strip()
        last_source = (usuario.last_name or perfil.apellido or "").strip()

        first_tokens = [token for token in first_source.split() if token]
        last_tokens = [token for token in last_source.split() if token]

        nombre_corto = ""
        if first_tokens:
            nombre_corto = first_tokens[0]
            if last_tokens:
                nombre_corto = f"{nombre_corto} {' '.join(last_tokens[:2])}".strip()

        nombre = nombre_corto or (
            f"{usuario.first_name} {usuario.last_name}".strip()
            or perfil.nombre
            or usuario.username
        )

        comentario = (item.comentario or "").strip()

        if perfil.strava_athlete_id:
            perfiles_relacionados = list(
                Perfil.objects
                .filter(strava_athlete_id=perfil.strava_athlete_id)
                .values_list("id", flat=True)
            )
        else:
            perfiles_relacionados = [perfil.id]

        actividades_dia_qs = (
            StravaActividad.objects
            .filter(
                perfil_id__in=perfiles_relacionados,
                start_date__date=fecha,
                distance_m__isnull=False,
                moving_time_s__isnull=False,
            )
            .filter(
                Q(type__in=["Run", "TrailRun"]) | Q(sport_type__in=["Run", "TrailRun"])
            )
            .order_by("start_date", "id")
        )

        actividad_agg = (
            actividades_dia_qs
            .aggregate(
                total_km_m=Coalesce(Sum("distance_m"), 0.0),
                total_time_s=Coalesce(Sum("moving_time_s"), 0),
                total_actividades=Count("id"),
            )
        )

        total_km_m = float(actividad_agg.get("total_km_m") or 0.0)
        total_time_s = int(actividad_agg.get("total_time_s") or 0)
        total_actividades = int(actividad_agg.get("total_actividades") or 0)
        tiene_resumen = total_actividades > 0 and total_km_m > 0 and total_time_s > 0

        actividades_dia = []
        for actividad in actividades_dia_qs:
            actividades_dia.append({
                "nombre": actividad.name or actividad.activity_kind or "Actividad",
                "km": round((actividad.distance_m or 0) / 1000.0, 2),
                "tiempo": _format_seconds(actividad.moving_time_s),
                "ritmo": actividad.pace,
            })

        filas.append({
            "nombre": nombre,
            "grupo_nombre": getattr(getattr(item, "entrenamiento", None), "grupo", None).nombre if getattr(getattr(item, "entrenamiento", None), "grupo", None) else "",
            "realizada_at": item.realizada_at,
            "comentario": comentario,
            "actividad_tiene_resumen": tiene_resumen,
            "actividad_total": total_actividades,
            "actividad_km": round(total_km_m / 1000.0, 2),
            "actividad_tiempo": _format_seconds(total_time_s),
            "actividad_ritmo": _format_pace(total_time_s, total_km_m),
            "actividades_dia": actividades_dia,
        })

    return filas


@login_required
def cumplimiento_cumplidos(request, grupo_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ver los cumplidos.")

    grupo_qs = Grupo.objects.select_related("club")
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        grupo_qs = grupo_qs.filter(club=user_club) if user_club else grupo_qs.none()
    grupo = get_object_or_404(grupo_qs, id=grupo_id)

    fecha_param = request.GET.get("fecha")
    fecha = timezone.localdate()
    if fecha_param:
        try:
            fecha = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            pass

    entreno = EntrenamientoDiario.objects.filter(grupo=grupo, fecha=fecha).first()

    if not entreno:
        messages.info(request, "No hay entrenamiento para ese grupo en la fecha seleccionada.")
        return redirect(f"{reverse('cumplimiento_hoy')}?fecha={fecha.strftime('%Y-%m-%d')}&grupo={grupo.id}")

    cumplimientos = (
        CumplimientoEntrenamiento.objects
        .filter(entrenamiento=entreno, fecha=fecha, realizada=True)
        .select_related("perfil", "perfil__usuario", "entrenamiento", "entrenamiento__grupo")
        .order_by("perfil__nombre", "perfil__apellido", "perfil__usuario__username")
    )
    filas = _build_cumplidos_filas(cumplimientos, fecha)

    return render(request, "users/cumplimiento_cumplidos.html", {
        "grupo": grupo,
        "titulo_grupo": grupo.nombre,
        "fecha": fecha,
        "filas": filas,
    })


@login_required
def cumplimiento_cumplidos_todos(request):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ver los cumplidos.")

    fecha_param = request.GET.get("fecha")
    fecha = timezone.localdate()
    if fecha_param:
        try:
            fecha = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            pass

    grupo_id = request.GET.get("grupo")
    entrenos = EntrenamientoDiario.objects.filter(fecha=fecha)
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        entrenos = entrenos.filter(grupo__club=user_club) if user_club else entrenos.none()
    if grupo_id:
        entrenos = entrenos.filter(grupo_id=grupo_id)

    if not entrenos.exists():
        messages.info(request, "No hay entrenamientos para la fecha seleccionada.")
        suffix = f"&grupo={grupo_id}" if grupo_id else ""
        return redirect(f"{reverse('cumplimiento_hoy')}?fecha={fecha.strftime('%Y-%m-%d')}{suffix}")

    cumplimientos = (
        CumplimientoEntrenamiento.objects
        .filter(entrenamiento__in=entrenos, fecha=fecha, realizada=True)
        .select_related("perfil", "perfil__usuario", "entrenamiento", "entrenamiento__grupo")
        .order_by("entrenamiento__grupo__nombre", "perfil__nombre", "perfil__apellido", "perfil__usuario__username")
    )

    filas = _build_cumplidos_filas(cumplimientos, fecha)

    return render(request, "users/cumplimiento_cumplidos.html", {
        "grupo": None,
        "titulo_grupo": "TODOS",
        "fecha": fecha,
        "filas": filas,
        "mostrar_grupo_en_fila": True,
    })


@login_required
def editar_entrenamiento_dia(request, grupo_id, fecha):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para editar calendarios.")

    grupo_qs = Grupo.objects.select_related("club")
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        grupo_qs = grupo_qs.filter(club=user_club) if user_club else grupo_qs.none()
    grupo = get_object_or_404(grupo_qs, id=grupo_id)

    try:
        fecha_date = datetime.strptime(fecha, "%Y-%m-%d").date()
    except Exception:
        return _forbidden("Fecha inválida.")

    obj, _ = EntrenamientoDiario.objects.get_or_create(
        grupo=grupo,
        fecha=fecha_date,
        defaults={"tipo": "entreno", "titulo": "", "descripcion": ""}
    )

    recurso_formset_class = inlineformset_factory(
        EntrenamientoDiario,
        EntrenamientoRecurso,
        form=EntrenamientoRecursoForm,
        extra=1,
        can_delete=True,
    )

    if request.method == "POST":
        form = EntrenamientoDiarioForm(request.POST, instance=obj)
        recurso_formset = recurso_formset_class(request.POST, instance=obj)
        if form.is_valid() and recurso_formset.is_valid():
            form.save()
            recurso_formset.save()
            return redirect(
                f"/gestion/calendarios/?grupo={grupo.id}&month={fecha_date.month}&year={fecha_date.year}&date={fecha_date.strftime('%Y-%m-%d')}"
            )
    else:
        form = EntrenamientoDiarioForm(instance=obj)
        recurso_formset = recurso_formset_class(instance=obj)

    return render(request, "users/entrenamiento_dia_form.html", {
        "grupo": grupo,
        "fecha": fecha_date,
        "form": form,
        "recurso_formset": recurso_formset,
    })


@login_required
def eliminar_entrenamiento_recurso(request, recurso_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para eliminar recursos.")

    if request.method != "POST":
        return _forbidden("Método no permitido.")

    recurso_qs = EntrenamientoRecurso.objects.select_related("entrenamiento__grupo__club")
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        recurso_qs = recurso_qs.filter(entrenamiento__grupo__club=user_club) if user_club else recurso_qs.none()
    recurso = get_object_or_404(recurso_qs, id=recurso_id)
    recurso.delete()
    return JsonResponse({"ok": True})


@login_required
def gestion_corredores(request):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ver corredores.")

    user_club = None if request.user.is_superuser else _resolve_user_club(request.user)
    corredores_qs = Perfil.objects.select_related("usuario", "grupo", "club").order_by("usuario__username")
    if not request.user.is_superuser:
        if user_club:
            corredores_qs = corredores_qs.filter(Q(club=user_club) | Q(grupo__club=user_club))
        else:
            corredores_qs = corredores_qs.none()

    corredores = list(corredores_qs)
    usuarios_ids = [corredor.usuario_id for corredor in corredores]
    usuarios_con_ritmo = set(
        Ritmo.objects.filter(usuario_id__in=usuarios_ids)
        .values_list("usuario_id", flat=True)
        .distinct()
    )

    for corredor in corredores:
        corredor.tiene_ritmo = corredor.usuario_id in usuarios_con_ritmo

    return render(request, "users/gestion_corredores.html", {"corredores": corredores})


@login_required
@transaction.atomic
def crear_corredor(request):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para crear corredores.")

    user_club = _resolve_user_club(request.user)

    if request.method == "POST":
        form = CrearCorredorForm(request.POST, user=request.user, user_club=user_club)
        if form.is_valid():
            username = form.cleaned_data["username"]
            nombre = form.cleaned_data["first_name"]
            apellido = form.cleaned_data["last_name"]
            fecha_nacimiento = form.cleaned_data.get("fecha_nacimiento")
            email = form.cleaned_data["email"]
            grupo = form.cleaned_data["grupo"]
            meta_actual = form.cleaned_data["meta_actual"]
            mejor_marca = form.cleaned_data["mejor_marca"]
            modalidad_ritmo = _normalize_ritmo_tipo(form.cleaned_data.get("modalidad_ritmo"))
            club = grupo.club if grupo and grupo.club else user_club

            temp_password = get_random_string(14)
            user = User.objects.create(username=username, email=email)
            user.set_password(temp_password)
            user.first_name = nombre
            user.last_name = apellido
            user.save()

            corredor_group, _ = Group.objects.get_or_create(name="Corredor")
            user.groups.add(corredor_group)

            perfil, _ = Perfil.objects.get_or_create(usuario=user)
            perfil.nombre = nombre or user.username
            perfil.rol = "corredor"

            # Si tu Perfil NO tiene apellido/correo, borra estas 2 líneas:
            perfil.apellido = apellido
            perfil.correo = email
            perfil.club = club

            # fecha de nacimiento (opcional)
            perfil.fecha_nacimiento = fecha_nacimiento

            if grupo:
                perfil.grupo = grupo

            perfil.meta_actual = meta_actual
            perfil.mejor_marca = mejor_marca
            perfil.modalidad_ritmo = modalidad_ritmo

            perfil.must_change_password = True
            perfil.save()

            return render(request, "users/crear_corredor_ok.html", {
                "username": user.username,
                "temp_password": temp_password
            })
    else:
        form = CrearCorredorForm(user=request.user, user_club=user_club)

    return render(request, "users/crear_corredor.html", {"form": form})


@login_required
@transaction.atomic
def restablecer_password_corredor(request, perfil_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para restablecer contraseña.")

    if request.method != "POST":
        return _forbidden("Método no permitido.")

    perfil = get_object_or_404(
        Perfil.objects.select_related("usuario", "grupo", "club"),
        id=perfil_id,
    )
    if not request.user.is_superuser and not _perfil_belongs_to_club(perfil, _resolve_user_club(request.user)):
        return _forbidden("No tienes permiso para restablecer la contraseña de este corredor.")
    usuario = perfil.usuario

    temp_password = get_random_string(14)
    usuario.set_password(temp_password)
    usuario.save(update_fields=["password"])

    perfil.must_change_password = True
    perfil.save(update_fields=["must_change_password"])

    return render(request, "users/restablecer_password_ok.html", {
        "username": usuario.username,
        "temp_password": temp_password,
    })


@login_required
def editar_corredor(request, perfil_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para editar corredores.")

    perfil = get_object_or_404(Perfil.objects.select_related("grupo", "club"), id=perfil_id)
    user_club = _resolve_user_club(request.user)
    if not request.user.is_superuser and not _perfil_belongs_to_club(perfil, user_club):
        return _forbidden("No tienes permiso para editar este corredor.")
    usuario = perfil.usuario

    if request.method == "POST":
        form = EditarCorredorForm(request.POST, user=request.user, user_club=user_club)
        if form.is_valid():
            nombre = form.cleaned_data["first_name"]
            apellido = form.cleaned_data["last_name"]
            fecha_nacimiento = form.cleaned_data.get("fecha_nacimiento")
            email = form.cleaned_data["email"]
            grupo = form.cleaned_data["grupo"]
            meta_actual = form.cleaned_data["meta_actual"]
            mejor_marca = form.cleaned_data["mejor_marca"]
            modalidad_ritmo = _normalize_ritmo_tipo(form.cleaned_data.get("modalidad_ritmo"))
            club = grupo.club if grupo and grupo.club else (perfil.club or user_club)

            usuario.email = email
            usuario.first_name = nombre
            usuario.last_name = apellido
            usuario.save()

            perfil.nombre = nombre or usuario.username
            perfil.apellido = apellido
            perfil.fecha_nacimiento = fecha_nacimiento
            perfil.correo = email
            perfil.rol = "corredor"
            perfil.grupo = grupo
            perfil.club = club
            perfil.meta_actual = meta_actual
            perfil.mejor_marca = mejor_marca
            perfil.modalidad_ritmo = modalidad_ritmo
            perfil.save()

            messages.success(request, "Corredor actualizado exitosamente.")
            return redirect("gestion_corredores")
    else:
        form = EditarCorredorForm(initial={
            "first_name": usuario.first_name,
            "last_name": usuario.last_name,
            "fecha_nacimiento": perfil.fecha_nacimiento,
            "email": usuario.email,
            "grupo": perfil.grupo,
            "meta_actual": perfil.meta_actual,
            "mejor_marca": perfil.mejor_marca,
            "modalidad_ritmo": _normalize_ritmo_tipo(getattr(perfil, "modalidad_ritmo", "runners")),
        }, user=request.user, user_club=user_club)

    return render(request, "users/editar_corredor.html", {"form": form, "perfil": perfil})



@login_required
@transaction.atomic
def eliminar_corredor(request, perfil_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para eliminar corredores.")

    perfil = get_object_or_404(Perfil.objects.select_related("grupo", "club"), id=perfil_id)
    if not request.user.is_superuser and not _perfil_belongs_to_club(perfil, _resolve_user_club(request.user)):
        return _forbidden("No tienes permiso para eliminar este corredor.")

    if request.method == "POST":
        usuario = perfil.usuario
        perfil.delete()
        usuario.delete()
        return redirect("gestion_corredores")

    return render(request, "users/corredor_confirm_delete.html", {"perfil": perfil})


@login_required
def asignar_grupo(request, perfil_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para asignar grupos.")

    perfil = get_object_or_404(Perfil.objects.select_related("grupo", "club"), id=perfil_id)
    if not request.user.is_superuser and not _perfil_belongs_to_club(perfil, _resolve_user_club(request.user)):
        return _forbidden("No tienes permiso para asignar grupos a este corredor.")

    grupos = Grupo.objects.select_related("club").order_by("nombre")
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        if user_club:
            grupos = grupos.filter(club=user_club)
        else:
            grupos = grupos.none()

    if request.method == "POST":
        grupo_id = request.POST.get("grupo")
        if grupo_id:
            try:
                grupo = grupos.get(id=grupo_id)
                perfil.grupo = grupo
                perfil.club = grupo.club or perfil.club or _resolve_user_club(request.user)
                perfil.save()
                messages.success(request, f"Grupo '{grupo.nombre}' asignado a {perfil.nombre}")
                return redirect("gestion_corredores")
            except Grupo.DoesNotExist:
                messages.error(request, "El grupo seleccionado no existe.")
        else:
            messages.error(request, "Debes seleccionar un grupo.")

    return render(request, "users/asignar_grupo.html", {
        "perfil": perfil,
        "grupos": grupos,
    })


@login_required
def crear_ritmo(request, perfil_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ingresar ritmos.")

    perfil = get_object_or_404(Perfil.objects.select_related("grupo", "club"), id=perfil_id)
    if not request.user.is_superuser and not _perfil_belongs_to_club(perfil, _resolve_user_club(request.user)):
        return _forbidden("No tienes permiso para ingresar ritmos a este corredor.")

    tipo_ritmo = _normalize_ritmo_tipo(
        request.GET.get("tipo")
        or request.POST.get("tipo")
        or getattr(perfil, "modalidad_ritmo", "runners")
    )

    ritmos_qs = Ritmo.objects.filter(usuario=perfil.usuario, tipo=tipo_ritmo).order_by("-fecha", "-creado_en")
    ritmo_actual = ritmos_qs.first()
    ritmos_historico = list(ritmos_qs)
    ritmos_anteriores = ritmos_historico[1:] if len(ritmos_historico) > 1 else []

    if request.method == "POST":
        form = RitmoForm(request.POST)
        if form.is_valid():
            ritmo = form.save(commit=False)
            ritmo.usuario = perfil.usuario
            ritmo.tipo = tipo_ritmo
            ritmo.save()
            if getattr(perfil, "modalidad_ritmo", "runners") != tipo_ritmo:
                perfil.modalidad_ritmo = tipo_ritmo
                perfil.save(update_fields=["modalidad_ritmo"])
            messages.success(request, "Control de ritmos agregado correctamente.")
            return redirect(f"{reverse('crear_ritmo', kwargs={'perfil_id': perfil.id})}?tipo={tipo_ritmo}")
    else:
        initial_data = {"fecha": timezone.localdate().strftime("%Y-%m-%d")}
        form = RitmoForm(initial=initial_data)

    return render(request, "users/ritmo_form.html", {
        "form": form,
        "perfil": perfil,
        "ritmo_actual": ritmo_actual,
        "ritmos_anteriores": ritmos_anteriores,
        "tiene_historial": bool(ritmos_historico),
        "es_staffish": _is_staffish(request.user),
        "tipo_ritmo": tipo_ritmo,
    })


@login_required
def editar_ritmo(request, perfil_id, ritmo_id):
    # Allow professors/admins to edit a ritmo
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para editar controles.")

    perfil = get_object_or_404(Perfil.objects.select_related("grupo", "club"), id=perfil_id)
    if not request.user.is_superuser and not _perfil_belongs_to_club(perfil, _resolve_user_club(request.user)):
        return _forbidden("No tienes permiso para editar controles de este corredor.")

    ritmo = get_object_or_404(Ritmo.objects.filter(usuario=perfil.usuario), id=ritmo_id)

    if request.method == "POST":
        form = RitmoForm(request.POST, instance=ritmo)
        if form.is_valid():
            form.save()
            messages.success(request, "Control editado correctamente.")
            return redirect(f"{reverse('crear_ritmo', kwargs={'perfil_id': perfil.id})}?tipo={ritmo.tipo}")
    else:
        form = RitmoForm(instance=ritmo)

    return render(request, "users/ritmo_form.html", {
        "form": form,
        "perfil": perfil,
        "ritmo_actual": ritmo,
        "ritmos_anteriores": [],
        "tiene_historial": True,
        "es_staffish": _is_staffish(request.user),
        "tipo_ritmo": ritmo.tipo,
        "editando": True,
    })


@login_required
def eliminar_ritmo(request, perfil_id, ritmo_id):
    if request.method != "POST":
        return _forbidden("Método no permitido.")

    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para eliminar controles.")

    perfil = get_object_or_404(Perfil.objects.select_related("grupo", "club"), id=perfil_id)
    if not request.user.is_superuser and not _perfil_belongs_to_club(perfil, _resolve_user_club(request.user)):
        return _forbidden("No tienes permiso para eliminar controles de este corredor.")

    ritmo = get_object_or_404(Ritmo.objects.filter(usuario=perfil.usuario), id=ritmo_id)

    ritmo_tipo = ritmo.tipo
    ritmo.delete()
    messages.success(request, "Control eliminado correctamente.")
    return redirect(f"{reverse('crear_ritmo', kwargs={'perfil_id': perfil.id})}?tipo={ritmo_tipo}")


@login_required
def gestion_grupos(request):
    es_profesor = request.user.groups.filter(name="Profesor").exists()
    es_admin_funcional = request.user.groups.filter(name="Admin").exists()

    if not (es_profesor or es_admin_funcional or request.user.is_superuser):
        return HttpResponseForbidden("No tienes permiso para ver esta página.")

    grupos = (
        Grupo.objects.select_related("club")
        .annotate(
            corredores_count=Count(
                "perfil",
                filter=Q(perfil__usuario__groups__name="Corredor"),
                distinct=True,
            )
        )
        .order_by("nombre")
    )

    # scope grupos by club for non-superusers
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        grupos = grupos.filter(club=user_club) if user_club else grupos.none()

    return render(request, "users/gestion_grupos.html", {"grupos": grupos})

@login_required
def crear_grupo(request):
    if not _is_staffish(request.user):
        return _forbidden()

    if request.method == "POST":
        form = GrupoForm(request.POST)
        if form.is_valid():
            grupo = form.save(commit=False)
            grupo.club = _resolve_user_club(request.user)
            grupo.save()
            return redirect("gestion_grupos")
    else:
        form = GrupoForm()

    return render(request, "users/crear_grupo.html", {"form": form})


@login_required
def editar_grupo(request, grupo_id):
    if not _is_staffish(request.user):
        return _forbidden()

    grupo = get_object_or_404(Grupo.objects.select_related("club"), id=grupo_id)
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        if not _grupo_belongs_to_club(grupo, user_club):
            return _forbidden()

    if request.method == "POST":
        form = GrupoForm(request.POST, instance=grupo)
        if form.is_valid():
            grupo_editado = form.save(commit=False)
            grupo_editado.club = grupo.club or _resolve_user_club(request.user)
            grupo_editado.save()
            return redirect("gestion_grupos")
    else:
        form = GrupoForm(instance=grupo)

    return render(request, "users/crear_grupo.html", {
        "form": form,
        "editando": True,
        "grupo": grupo
    })


@login_required
def eliminar_grupo(request, grupo_id):
    if not _is_staffish(request.user):
        return _forbidden()

    grupo = get_object_or_404(Grupo.objects.select_related("club"), id=grupo_id)
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        if not _grupo_belongs_to_club(grupo, user_club):
            return _forbidden()

    tiene_corredores = Perfil.objects.filter(grupo=grupo).exists()
    if tiene_corredores:
        messages.error(request, "No puedes eliminar este grupo porque tiene corredores asociados.")
        return redirect("gestion_grupos")

    if request.method == "POST":
        grupo.delete()
        messages.success(request, "Grupo eliminado correctamente.")
        return redirect("gestion_grupos")

    return render(request, "users/grupo_confirm_delete.html", {"grupo": grupo})


@login_required
def copiar_mes(request):
    if not _is_staffish(request.user):
        return _forbidden()

    grupo_id = request.GET.get("grupo")
    month_param = request.GET.get("month")
    year_param = request.GET.get("year")

    if not grupo_id or not month_param or not year_param:
        messages.error(request, "Faltan parámetros.")
        return redirect("gestion_calendarios")

    grupo_qs = Grupo.objects.select_related("club")
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        grupo_qs = grupo_qs.filter(club=user_club) if user_club else grupo_qs.none()
    grupo = get_object_or_404(grupo_qs, id=grupo_id)
    mes_destino = int(month_param)
    anio_destino = int(year_param)

    if request.method == "POST":
        try:
            grupo_origen_id = int(request.POST.get("grupo_origen"))
            mes_origen = int(request.POST.get("mes_origen"))
            anio_origen = int(request.POST.get("anio_origen"))
        except (TypeError, ValueError):
            messages.error(request, "Debes seleccionar grupo y mes de origen válidos.")
            return redirect(
                f"{reverse('copiar_mes')}?grupo={grupo_id}&month={mes_destino}&year={anio_destino}"
            )

        grupo_origen_qs = Grupo.objects.select_related("club")
        if not request.user.is_superuser:
            user_club = _resolve_user_club(request.user)
            grupo_origen_qs = grupo_origen_qs.filter(club=user_club) if user_club else grupo_origen_qs.none()
        grupo_origen = grupo_origen_qs.filter(id=grupo_origen_id).first()
        if not grupo_origen:
            messages.error(request, "El grupo de origen no existe.")
            return redirect(
                f"{reverse('copiar_mes')}?grupo={grupo_id}&month={mes_destino}&year={anio_destino}"
            )

        # Obtener entrenamientos del mes origen
        fecha_inicio_origen = datetime(anio_origen, mes_origen, 1).date()
        fecha_fin_origen = (fecha_inicio_origen.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        entrenamientos_origen = EntrenamientoDiario.objects.filter(
            grupo=grupo_origen,
            fecha__range=(fecha_inicio_origen, fecha_fin_origen)
        ).order_by("fecha")

        copiados = 0
        for entreno in entrenamientos_origen:
            dia = entreno.fecha.day
            try:
                nueva_fecha = datetime(anio_destino, mes_destino, dia).date()
                
                # Solo copiar si no existe ya un entrenamiento en esa fecha
                if not EntrenamientoDiario.objects.filter(grupo=grupo, fecha=nueva_fecha).exists():
                    EntrenamientoDiario.objects.create(
                        grupo=grupo,
                        fecha=nueva_fecha,
                        modalidad=getattr(entreno, "modalidad", "runners"),
                        tipo=entreno.tipo,
                        titulo=entreno.titulo,
                        descripcion=entreno.descripcion
                    )
                    copiados += 1
            except ValueError:
                # El día no existe en el mes destino (ej: 31 de febrero)
                continue

        if copiados > 0:
            messages.success(
                request,
                f"Se copiaron {copiados} entrenamientos desde {grupo_origen.nombre} hacia {grupo.nombre}."
            )
        else:
            messages.warning(request, "No se copiaron entrenamientos (ya existían o no había entrenamientos para copiar).")

        return redirect(f"/gestion/calendarios/?grupo={grupo_id}&month={mes_destino}&year={anio_destino}")

    # GET: Obtener meses disponibles por grupo origen
    grupos_disponibles_qs = Grupo.objects.select_related("club").order_by("nombre")
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        grupos_disponibles_qs = grupos_disponibles_qs.filter(club=user_club) if user_club else grupos_disponibles_qs.none()
    grupos_disponibles = list(grupos_disponibles_qs)

    meses_por_grupo = {}
    for g in grupos_disponibles:
        entrenamientos = (
            EntrenamientoDiario.objects
            .filter(grupo=g)
            .values_list("fecha", flat=True)
            .distinct()
        )

        meses_disponibles = set()
        for fecha in entrenamientos:
            if g.id == grupo.id and fecha.year == anio_destino and fecha.month == mes_destino:
                continue
            meses_disponibles.add((fecha.year, fecha.month))

        meses_ordenados = sorted(meses_disponibles, reverse=True)
        if meses_ordenados:
            meses_por_grupo[g.id] = meses_ordenados

    # Formatear para el template
    meses_opciones = []
    meses_nombres = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                     "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    for g in grupos_disponibles:
        for anio, mes in meses_por_grupo.get(g.id, []):
            meses_opciones.append({
                "grupo_id": g.id,
                "grupo_nombre": g.nombre,
                "mes": mes,
                "anio": anio,
                "nombre": f"{meses_nombres[mes]} {anio}",
            })

    return render(request, "users/copiar_mes.html", {
        "grupo": grupo,
        "mes_destino": mes_destino,
        "anio_destino": anio_destino,
        "grupos_disponibles": grupos_disponibles,
        "meses_opciones": meses_opciones,
        "meses_nombres": meses_nombres,
    })


@login_required
def borrar_mes_calendario(request):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para borrar calendarios.")

    if request.method != "POST":
        return _forbidden("Método no permitido.")

    grupo_id = request.POST.get("grupo")
    month_raw = request.POST.get("month")
    year_raw = request.POST.get("year")

    if not (grupo_id and month_raw and year_raw):
        messages.error(request, "Faltan datos para borrar el mes.")
        return redirect("gestion_calendarios")

    try:
        month = int(month_raw)
        year = int(year_raw)
        if month < 1 or month > 12:
            raise ValueError
    except ValueError:
        messages.error(request, "Mes o año inválido.")
        return redirect("gestion_calendarios")

    grupo_qs = Grupo.objects.select_related("club")
    if not request.user.is_superuser:
        user_club = _resolve_user_club(request.user)
        grupo_qs = grupo_qs.filter(club=user_club) if user_club else grupo_qs.none()
    grupo = grupo_qs.filter(id=grupo_id).first()
    if not grupo:
        messages.error(request, "Grupo no encontrado.")
        return redirect("gestion_calendarios")

    first_day = datetime(year, month, 1).date()
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    queryset = EntrenamientoDiario.objects.filter(
        grupo=grupo,
        fecha__range=(first_day, last_day),
    )
    total = queryset.count()
    queryset.delete()

    if total:
        messages.success(request, f"Se borraron {total} entrenamientos de {grupo.nombre} ({month:02d}/{year}).")
    else:
        messages.info(request, f"No habia entrenamientos para borrar en {grupo.nombre} ({month:02d}/{year}).")

    return redirect(f"{reverse('gestion_calendarios')}?grupo={grupo.id}&month={month}&year={year}")


@login_required
def mi_grupo(request):
    # perfil del usuario actual
    try:
        perfil = Perfil.objects.select_related("grupo", "usuario").get(usuario=request.user)
    except Perfil.DoesNotExist:
        return render(request, "users/mi_grupo.html", {
            "perfil": None,
            "grupo": None,
            "companeros": [],
        })

    grupo = perfil.grupo

    if not grupo:
        return render(request, "users/mi_grupo.html", {
            "perfil": perfil,
            "grupo": None,
            "companeros": [],
        })

    companeros = (
        Perfil.objects
        .filter(grupo=grupo)
        .exclude(usuario=request.user)
        .select_related("usuario", "grupo")
        .order_by("nombre")
    )

    return render(request, "users/mi_grupo.html", {
        "perfil": perfil,
        "grupo": grupo,
        "companeros": companeros,
    })
    
    
def _format_seconds_to_hms(total_seconds: int) -> str:
    total_seconds = int(total_seconds or 0)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def _format_pace_seconds_per_km(pace_s_per_km):
    if not pace_s_per_km or pace_s_per_km <= 0:
        return "—"
    pace_s = int(round(pace_s_per_km))
    mm = pace_s // 60
    ss = pace_s % 60
    return f"{mm}:{ss:02d} /km"


def _pct(realizadas: int, planificadas: int) -> int:
    if planificadas <= 0:
        return 0
    return int(round((realizadas / planificadas) * 100))


@login_required
def estadisticas(request):
    es_corredor = _is_in_group(request.user, "Corredor")
    es_admin = request.user.is_superuser or _is_in_group(request.user, "Admin")
    puede_ver_estadisticas = es_corredor or es_admin

    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )

    # Si no tiene rol habilitado, o no hay perfil/grupo, mostramos template con mensaje
    if not perfil or not puede_ver_estadisticas:
        return render(request, "users/estadisticas.html", {
            "perfil": perfil,
            "grupo": getattr(perfil, "grupo", None) if perfil else None,
            "error": "Esta sección está disponible para corredores y administradores.",
        })

    if not perfil.grupo:
        return render(request, "users/estadisticas.html", {
            "perfil": perfil,
            "grupo": None,
            "error": "Tu perfil no tiene un grupo asignado.",
        })

    grupo = perfil.grupo
    hoy = timezone.localdate()

    # Rangos navegables (semana y mes), sin adelantar navegación al futuro
    current_week_start = hoy - timedelta(days=hoy.weekday())
    current_month_start = hoy.replace(day=1)

    week_start_param = request.GET.get("week_start")
    if week_start_param:
        try:
            parsed_week = datetime.strptime(week_start_param, "%Y-%m-%d").date()
            inicio_semana = parsed_week - timedelta(days=parsed_week.weekday())
            if inicio_semana > current_week_start:
                inicio_semana = current_week_start
        except Exception:
            inicio_semana = current_week_start
    else:
        inicio_semana = current_week_start

    fin_semana = inicio_semana + timedelta(days=6)

    month_param = request.GET.get("month")  # YYYY-MM
    if month_param:
        try:
            year, month = [int(x) for x in month_param.split("-")]
            inicio_mes = hoy.replace(year=year, month=month, day=1)
            if inicio_mes > current_month_start:
                inicio_mes = current_month_start
        except Exception:
            inicio_mes = current_month_start
    else:
        inicio_mes = current_month_start

    fin_mes = (inicio_mes.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    prev_week_start = inicio_semana - timedelta(days=7)
    next_week_start_candidate = inicio_semana + timedelta(days=7)
    next_week_start = None if next_week_start_candidate > current_week_start else next_week_start_candidate

    prev_month_start = (inicio_mes - timedelta(days=1)).replace(day=1)
    next_month_start_candidate = (inicio_mes.replace(day=28) + timedelta(days=4)).replace(day=1)
    next_month_start = None if next_month_start_candidate > current_month_start else next_month_start_candidate

    # -------------------------
    # CUMPLIMIENTO (planificadas vs realizadas)
    # -------------------------
    plan_semana = EntrenamientoDiario.objects.filter(
        grupo=grupo,
        fecha__range=(inicio_semana, fin_semana)
    ).count()

    real_semana = CumplimientoEntrenamiento.objects.filter(
        perfil=perfil,
        realizada=True,
        fecha__range=(inicio_semana, fin_semana)
    ).count()

    plan_mes = EntrenamientoDiario.objects.filter(
        grupo=grupo,
        fecha__range=(inicio_mes, fin_mes)
    ).count()

    real_mes = CumplimientoEntrenamiento.objects.filter(
        perfil=perfil,
        realizada=True,
        fecha__range=(inicio_mes, fin_mes)
    ).count()

    pct_semana = _pct(real_semana, plan_semana)
    pct_mes = _pct(real_mes, plan_mes)

    # -------------------------
    # VOLUMEN (StravaActividad) desde BD local
    # Si existen varios perfiles con el mismo athlete_id, agregamos en conjunto
    # para evitar vacíos de datos por asociación de perfil.
    # -------------------------
    if perfil.strava_athlete_id:
        perfiles_mismo_athlete = Perfil.objects.filter(
            strava_athlete_id=perfil.strava_athlete_id
        ).values_list("id", flat=True)
        volumen_base_qs = StravaActividad.objects.filter(perfil_id__in=perfiles_mismo_athlete)
    else:
        volumen_base_qs = StravaActividad.objects.filter(perfil=perfil)

    qs_semana = volumen_base_qs.filter(
        start_date__date__range=(inicio_semana, fin_semana)
    )
    agg_semana = qs_semana.aggregate(
        dist_m=Coalesce(Sum("distance_m"), 0.0),
        time_s=Coalesce(Sum("moving_time_s"), 0),
        elev_m=Coalesce(Sum("total_elevation_gain_m"), 0.0),
    )

    qs_mes = volumen_base_qs.filter(
        start_date__date__range=(inicio_mes, fin_mes)
    )
    agg_mes = qs_mes.aggregate(
        dist_m=Coalesce(Sum("distance_m"), 0.0),
        time_s=Coalesce(Sum("moving_time_s"), 0),
        elev_m=Coalesce(Sum("total_elevation_gain_m"), 0.0),
    )

    def to_km(meters: float) -> float:
        return float(meters or 0.0) / 1000.0

    sem_km = to_km(agg_semana["dist_m"])
    mes_km = to_km(agg_mes["dist_m"])

    sem_time_s = int(agg_semana["time_s"] or 0)
    mes_time_s = int(agg_mes["time_s"] or 0)

    sem_elev_m = float(agg_semana["elev_m"] or 0.0)
    mes_elev_m = float(agg_mes["elev_m"] or 0.0)

    sem_pace = (sem_time_s / sem_km) if sem_km > 0 else None
    mes_pace = (mes_time_s / mes_km) if mes_km > 0 else None

    return render(request, "users/estadisticas.html", {
        "perfil": perfil,
        "grupo": grupo,
        "hoy": hoy,

        "inicio_semana": inicio_semana,
        "fin_semana": fin_semana,
        "inicio_mes": inicio_mes,
        "fin_mes": fin_mes,
        "prev_week_start": prev_week_start,
        "next_week_start": next_week_start,
        "prev_month_start": prev_month_start,
        "next_month_start": next_month_start,

        "plan_semana": plan_semana,
        "real_semana": real_semana,
        "pct_semana": pct_semana,

        "plan_mes": plan_mes,
        "real_mes": real_mes,
        "pct_mes": pct_mes,

        "sem_km": round(sem_km, 1),
        "mes_km": round(mes_km, 1),

        "sem_time": _format_seconds_to_hms(sem_time_s),
        "mes_time": _format_seconds_to_hms(mes_time_s),

        "sem_elev": int(round(sem_elev_m)),
        "mes_elev": int(round(mes_elev_m)),

        "sem_pace": _format_pace_seconds_per_km(sem_pace),
        "mes_pace": _format_pace_seconds_per_km(mes_pace),

        "error": "",
    })    
    
    
    
    
@login_required
def strava_login(request):

    # INICIO - Bloqueo de Strava en desarrollo
    if not settings.STRAVA_ENABLED:
        logger.info("Intento de vinculación con Strava bloqueado")
        return redirect("home")
    # FIN - Bloqueo de Strava en desarrollo

    oauth_state = get_random_string(32)
    request.session["strava_oauth_state"] = oauth_state

    params = {
        "client_id": settings.STRAVA_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.STRAVA_REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
        "state": oauth_state,
    }

    url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode(params)
    return redirect(url)


@login_required
def strava_disconnect(request):
    if request.method != "POST":
        return _forbidden("Método no permitido.")

    # INICIO - Evitar revocaciones y cambios locales con Strava desactivado
    if not settings.STRAVA_ENABLED:
        messages.warning(request, "La integración con Strava está desactivada.")
        return redirect("home")
    # FIN - Evitar revocaciones y cambios locales con Strava desactivado

    perfil = Perfil.objects.filter(usuario=request.user).first()
    if not perfil:
        messages.error(request, "No se encontró perfil de usuario.")
        return redirect("home")

    access_token = perfil.strava_access_token
    if access_token:
        try:
            requests.post(
                "https://www.strava.com/oauth/deauthorize",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
        except Exception:
            logger.exception("Error al revocar token en Strava")

    perfil.strava_access_token = None
    perfil.strava_refresh_token = None
    perfil.strava_expires_at = None
    perfil.strava_athlete_id = None
    perfil.save(update_fields=[
        "strava_access_token",
        "strava_refresh_token",
        "strava_expires_at",
        "strava_athlete_id",
    ])

    messages.success(request, "Strava desconectado correctamente.")
    return redirect("home")


@login_required
def strava_delete_data(request):
        # INICIO - Bloqueo de eliminación de datos Strava en desarrollo
    if not settings.STRAVA_ENABLED:
        logger.info("Eliminación de datos Strava desactivada en desarrollo")
        messages.warning(request, "La integración con Strava está desactivada.")
        return redirect("home")
    # FIN - Bloqueo de eliminación de datos Strava en desarrollo
    if request.method != "POST":
        return _forbidden("Método no permitido.")

    perfil = Perfil.objects.filter(usuario=request.user).first()
    if not perfil:
        messages.error(request, "No se encontró perfil de usuario.")
        return redirect("home")

    access_token = perfil.strava_access_token
    if access_token:
        try:
            requests.post(
                "https://www.strava.com/oauth/deauthorize",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
        except Exception:
            logger.exception("Error al revocar token al eliminar datos de Strava")

    StravaActividad.objects.filter(perfil=perfil).delete()

    perfil.strava_access_token = None
    perfil.strava_refresh_token = None
    perfil.strava_expires_at = None
    perfil.strava_athlete_id = None
    perfil.save(update_fields=[
        "strava_access_token",
        "strava_refresh_token",
        "strava_expires_at",
        "strava_athlete_id",
    ])

    messages.success(request, "Se eliminaron tus datos de Strava y se desconectó tu cuenta.")
    return redirect("home")

@login_required
def strava_callback(request):

    # INICIO - Bloqueo de Strava en desarrollo
    if not settings.STRAVA_ENABLED:
        logger.info("Callback de Strava bloqueado en desarrollo")
        return redirect("home")
    # FIN - Bloqueo de Strava en desarrollo

    code = request.GET.get("code")
    error = request.GET.get("error")
    state = request.GET.get("state")
    expected_state = request.session.pop("strava_oauth_state", None)

    if not expected_state or state != expected_state:
        logger.warning("Callback Strava con state inválido o ausente")
        return redirect("home")

    if error or not code:
        return redirect("home")

    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )

    data = resp.json()
    if resp.status_code != 200 or "access_token" not in data:
        logger.warning("Intercambio de código por token en Strava falló", extra={"status_code": resp.status_code})
        return redirect("home")

    # ✅ Guardar en Perfil
    perfil = Perfil.objects.get(usuario=request.user)
    perfil.strava_access_token = data.get("access_token")
    perfil.strava_refresh_token = data.get("refresh_token")
    perfil.strava_expires_at = data.get("expires_at")

    athlete = data.get("athlete") or {}
    perfil.strava_athlete_id = athlete.get("id")

    perfil.save()

    return redirect("home")


@login_required
def strava_activities(request):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ver esta sección.")

    user_club = _resolve_user_club(request.user)
    corredores = Perfil.objects.none()
    if user_club:
        corredores = (
            Perfil.objects
            .select_related("usuario", "grupo", "club")
            .filter(rol="corredor")
            .filter(Q(club=user_club) | Q(grupo__club=user_club))
            .distinct()
            .order_by("nombre", "apellido")
        )

    return render(
        request,
        "users/strava_activities.html",
        {
            "corredores": corredores,
            "club": user_club,
        },
    )


@login_required
def strava_activities_runner_detail(request, perfil_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ver esta sección.")

    user_club = _resolve_user_club(request.user)
    if not user_club:
        return _forbidden("No tienes un club asignado.")

    corredores_qs = (
        Perfil.objects
        .select_related("usuario", "grupo", "club")
        .filter(rol="corredor")
        .filter(Q(club=user_club) | Q(grupo__club=user_club))
        .distinct()
    )
    corredor = get_object_or_404(corredores_qs, id=perfil_id)

    # Reutilizar lógica de actividad: obtener actividades Strava del corredor desde BD
    actividades_qs = StravaActividad.objects.filter(perfil=corredor).order_by("-start_date")
    actividades = list(actividades_qs[:30])

    return render(
        request,
        "users/strava_activities_runner_detail.html",
        {
            "corredor": corredor,
            "club": user_club,
            "actividades": actividades,
        },
    )


@login_required
def strava_publish_ranking(request, actividad_id):
    if request.method != "POST":
        return _forbidden("Método no permitido.")

    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )
    if not perfil:
        return _forbidden("No tienes perfil asociado.")

    actividad = get_object_or_404(StravaActividad, id=actividad_id, perfil=perfil)
    sugerencia = _sugerir_ranking_desde_distancia(actividad.distance_m)
    if not sugerencia or not sugerencia.get("sugerencia_valor"):
        messages.info(request, "Esta actividad no está dentro del rango para ranking.")
        return redirect("actividad")

    ranking_distancia = int(sugerencia["sugerencia_valor"])
    tiempo_segundos = int(actividad.moving_time_s or 0)
    if tiempo_segundos <= 0:
        messages.error(request, "No se pudo publicar porque la actividad no tiene tiempo válido.")
        return redirect("actividad")

    accepted, replaced, previous_time = _registrar_ranking_manual(
        perfil=perfil,
        cumplimiento=None,
        entrenamiento=None,
        ranking_distancia=ranking_distancia,
        tiempo_segundos=tiempo_segundos,
        actor=request.user,
    )

    if accepted and replaced:
        messages.success(request, f"Ranking actualizado: esta actividad mejora la marca anterior ({previous_time}s).")
    elif accepted:
        messages.success(request, "Actividad subida al ranking correctamente.")
    else:
        messages.info(request, "No se publicó: la actividad no mejora el ranking actual.")

    return redirect("actividad")

@login_required
def actividad(request):
    # INICIO - Bloqueo de Strava en desarrollo
    if not settings.STRAVA_ENABLED:
        logger.info("Consulta de actividades de Strava desactivada")
        return redirect("home")
    # FIN - Bloqueo de Strava en desarrollo
    perfil = (
        Perfil.objects
        .filter(usuario=request.user)
        .select_related("grupo")
        .first()
    )

    if not perfil or not perfil.strava_access_token:
        return redirect("strava_login")

    # 1) Refrescar token si expiró
    now_ts = int(timezone.now().timestamp())
    if perfil.strava_expires_at and perfil.strava_expires_at <= now_ts:
        ok = _strava_refresh_token(perfil)
        if not ok:
            return redirect("strava_login")

    # 2) Pedir a Strava
    headers = {"Authorization": f"Bearer {perfil.strava_access_token}"}
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=headers,
        params={"per_page": 30, "page": 1},
        timeout=15,
    )

    if resp.status_code != 200:
        # si Strava falla, al menos mostramos lo que tengamos guardado
        actividades_db = StravaActividad.objects.filter(perfil=perfil)[:30]
        return render(request, "users/actividad.html", {
            "perfil": perfil,
            "actividades": actividades_db,
            "nombre_completo": f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
        })

    actividades = resp.json()  # lista de dicts

    # 3) Guardar/Actualizar en BD PRIMERO (rápido, sin geocoding)
    with transaction.atomic():
        for a in actividades:
            strava_id = a.get("id")
            if not strava_id:
                continue

            # Fechas (Strava manda ISO con Z)
            start_date = parse_datetime(a.get("start_date"))  # UTC

            StravaActividad.objects.update_or_create(
                strava_id=strava_id,
                defaults={
                    "perfil": perfil,
                    "name": a.get("name") or "",
                    "type": a.get("type") or "",
                    "sport_type": a.get("sport_type") or "",
                    "start_date": start_date,
                    "distance_m": a.get("distance"),
                    "moving_time_s": a.get("moving_time"),
                    "elapsed_time_s": a.get("elapsed_time"),
                    "total_elevation_gain_m": a.get("total_elevation_gain"),
                    "average_heartrate": a.get("average_heartrate"),
                    "max_heartrate": a.get("max_heartrate"),
                    "start_lat": None,
                    "start_lng": None,
                    "comuna": None,
                    "region": None,
                    "pais": None,
                }
            )

    _auto_mark_cumplimiento_from_strava(perfil, lookback_days=3)

    # 5) Leer desde BD (ya limpio) y mostrar
    actividades_qs = StravaActividad.objects.filter(perfil=perfil).order_by("-start_date")

    # Para atletas en modalidad Trail, priorizamos mostrar actividades trail.
    if _normalize_ritmo_tipo(getattr(perfil, "modalidad_ritmo", "runners")) == "trail":
        trail_qs = actividades_qs.filter(sport_type="TrailRun")
        actividades_db = list(trail_qs[:30]) if trail_qs.exists() else list(actividades_qs[:30])
    else:
        actividades_db = list(actividades_qs[:30])

    return render(request, "users/actividad.html", {
        "perfil": perfil,
        "actividades": actividades_db,
        "nombre_completo": f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
    })


@login_required
def historial_carreras_manual(request, perfil_id):
    perfil = get_object_or_404(Perfil, id=perfil_id)
    # Permitir al propio corredor ver/añadir sus marcas manuales, o profesores/admin
    if not (_is_staffish(request.user) or perfil.usuario == request.user):
        return _forbidden("No tienes permiso para ver el historial de carreras.")

    def tiempo_a_segundos(tiempo_str):
        try:
            partes = [int(x) for x in str(tiempo_str).split(":")]
        except (TypeError, ValueError):
            return None

        if len(partes) == 3:
            return partes[0] * 3600 + partes[1] * 60 + partes[2]
        if len(partes) == 2:
            return partes[0] * 60 + partes[1]
        return None

    def ritmo_por_km(tiempo_str, distancia_m):
        total_seg = tiempo_a_segundos(tiempo_str)
        if not total_seg or not distancia_m:
            return "-"

        seg_km = total_seg / (distancia_m / 1000)
        mm = int(seg_km // 60)
        ss = int(round(seg_km % 60))
        if ss == 60:
            mm += 1
            ss = 0
        return f"{mm}:{ss:02d} /km"

    if request.method == "POST" and request.POST.get("eliminar_id"):
        carrera = CarreraManual.objects.filter(
            id=request.POST.get("eliminar_id"),
            perfil=perfil,
        ).first()
        if carrera:
            carrera.delete()
            messages.success(request, "Marca eliminada correctamente.")
        else:
            messages.error(request, "No se encontró la marca para eliminar.")
        return redirect("historial_carreras_manual", perfil_id=perfil.id)

    form = CarreraManualForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        nueva = form.save(commit=False)
        nueva.perfil = perfil
        nueva.save()
        messages.success(request, "Marca agregada correctamente.")
        return redirect("historial_carreras_manual", perfil_id=perfil.id)

    carreras = CarreraManual.objects.filter(perfil=perfil).order_by("distancia_m", "-fecha")

    # Agrupar por distancia
    distancias = [3000, 5000, 10000, 21000, 42000]
    carreras_por_distancia = {}
    for d in distancias:
        carreras_por_distancia[d] = list(carreras.filter(distancia_m=d))
        for c in carreras_por_distancia[d]:
            c.ritmo = ritmo_por_km(c.tiempo, c.distancia_m)

        # Mejor marca (menor tiempo en segundos)
        if carreras_por_distancia[d]:
            mejor = min(
                carreras_por_distancia[d],
                key=lambda c: tiempo_a_segundos(c.tiempo) or 999999,
            )
            for c in carreras_por_distancia[d]:
                c.es_mejor = (c.id == mejor.id)

    return render(request, "users/historial_carreras_modal.html", {
        "perfil": perfil,
        "carreras_por_distancia": carreras_por_distancia,
        "form": form,
    })


@login_required
def historial_lactato_manual(request, perfil_id):
    if not _is_staffish(request.user):
        return _forbidden("No tienes permiso para ver el historial de lactato.")

    perfil = get_object_or_404(Perfil, id=perfil_id)

    if request.method == "POST" and request.POST.get("eliminar_id"):
        registro = LactatoManual.objects.filter(
            id=request.POST.get("eliminar_id"),
            perfil=perfil,
        ).first()
        if registro:
            registro.delete()
            messages.success(request, "Registro de lactato eliminado correctamente.")
        else:
            messages.error(request, "No se encontró el registro para eliminar.")
        return redirect("historial_lactato_manual", perfil_id=perfil.id)

    form = LactatoManualForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        nuevo = form.save(commit=False)
        nuevo.perfil = perfil
        nuevo.save()
        messages.success(request, "Registro de lactato agregado correctamente.")
        return redirect("historial_lactato_manual", perfil_id=perfil.id)

    registros = LactatoManual.objects.filter(perfil=perfil).order_by("-fecha", "-id")

    return render(request, "users/historial_lactato.html", {
        "perfil": perfil,
        "registros": registros,
        "form": form,
    })
