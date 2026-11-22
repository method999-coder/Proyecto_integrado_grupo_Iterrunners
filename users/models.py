

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone


class Club(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=300, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Grupo(models.Model):
    nombre = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=200, blank=True)
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name="grupos")

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        Perfil.objects.filter(grupo=self).exclude(club=self.club).update(club=self.club)


class Perfil(models.Model):
    ROL_CHOICES = [
        ("corredor", "Corredor"),
        ("profesor", "Profesor"),
        ("admin", "Administrador"),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100, blank=True, default="")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    rol = models.CharField(max_length=20, choices=ROL_CHOICES)

    grupo = models.ForeignKey(Grupo, on_delete=models.SET_NULL, null=True, blank=True)
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name="perfiles")

    meta_actual = models.CharField(max_length=200, blank=True)
    mejor_marca = models.CharField(max_length=200, blank=True)

    must_change_password = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    MODALIDAD_RITMO_CHOICES = [
        ("runners", "Runners"),
        ("trail", "Trail"),
    ]
    modalidad_ritmo = models.CharField(max_length=20, choices=MODALIDAD_RITMO_CHOICES, default="runners")

    @staticmethod
    def role_from_user(user):
        if not user:
            return "corredor"
        if user.is_superuser or user.groups.filter(name="Admin").exists():
            return "admin"
        if user.groups.filter(name="Profesor").exists():
            return "profesor"
        return "corredor"

    def save(self, *args, **kwargs):
        if self.grupo_id and self.grupo and self.grupo.club_id:
            self.club = self.grupo.club
        if not self.rol:
            self.rol = self.role_from_user(self.usuario)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre
    
    # --- Strava ---
    strava_athlete_id = models.BigIntegerField(null=True, blank=True)
    strava_access_token = models.CharField(max_length=255, null=True, blank=True)
    strava_refresh_token = models.CharField(max_length=255, null=True, blank=True)
    strava_expires_at = models.BigIntegerField(null=True, blank=True)



class Ritmo(models.Model):
    TIPO_CHOICES = [
        ("runners", "Runners"),
        ("trail", "Trail"),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ritmos"
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="runners")
    fecha = models.DateField()

    distancia_test_m = models.PositiveIntegerField(default=3000)
    tiempo_test = models.CharField(max_length=10, blank=True)
    paso_vo2max = models.CharField(max_length=10, blank=True)
    vo2max = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    fc_maxima_ppm = models.PositiveIntegerField(null=True, blank=True)

    reg_min = models.CharField(max_length=10, blank=True)
    reg_max = models.CharField(max_length=10, blank=True)

    r1_min = models.CharField(max_length=10, blank=True)
    r1_max = models.CharField(max_length=10, blank=True)

    r2_min = models.CharField(max_length=10, blank=True)
    r2_max = models.CharField(max_length=10, blank=True)

    r3_min = models.CharField(max_length=10, blank=True)
    r3_max = models.CharField(max_length=10, blank=True)

    ul_min = models.CharField(max_length=10, blank=True)
    ul_max = models.CharField(max_length=10, blank=True)

    ca_min = models.CharField(max_length=10, blank=True)
    ca_max = models.CharField(max_length=10, blank=True)

    can_min = models.CharField(max_length=10, blank=True)
    can_max = models.CharField(max_length=10, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-creado_en"]

    def __str__(self):
        return f"Ritmos {self.usuario.username} ({self.fecha})"


class EntrenamientoDiario(models.Model):
    MODALIDAD_CHOICES = [
        ("runners", "Runners"),
        ("trail", "Trail"),
    ]

    TIPO_CHOICES = [
        ("entreno", "Entrenamiento"),
        ("descanso", "Descanso"),
        ("core", "Core / Fuerza"),
        ("carrera", "Carrera"),
        ("control", "Control"),
    ]

    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE, related_name="entrenamientos")
    fecha = models.DateField()
    modalidad = models.CharField(max_length=20, choices=MODALIDAD_CHOICES, default="runners")

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="entreno")
    titulo = models.CharField(max_length=80, blank=True)
    descripcion = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("grupo", "fecha")
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.grupo.nombre} - {self.fecha}"


class EntrenamientoRecurso(models.Model):
    TIPO_CHOICES = [
        ("video", "Video"),
        ("documento", "Documento"),
        ("otro", "Otro"),
    ]

    entrenamiento = models.ForeignKey(
        "EntrenamientoDiario",
        on_delete=models.CASCADE,
        related_name="recursos",
    )
    titulo = models.CharField(max_length=120)
    url = models.URLField(max_length=500)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="video")
    orden = models.PositiveSmallIntegerField(default=1)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return f"{self.entrenamiento} - {self.titulo}"

class StravaActividad(models.Model):
    perfil = models.ForeignKey("Perfil", on_delete=models.CASCADE, related_name="strava_actividades")

    # Id único de Strava para esa actividad
    strava_id = models.BigIntegerField(unique=True)

    # Datos base para mostrar en UI
    name = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=50, blank=True)  # Run, Ride, etc.
    sport_type = models.CharField(max_length=50, blank=True)  # TrailRun, Ride, EBikeRide, etc.
    start_date = models.DateTimeField(null=True, blank=True)

    distance_m = models.FloatField(null=True, blank=True)
    moving_time_s = models.IntegerField(null=True, blank=True)
    elapsed_time_s = models.IntegerField(null=True, blank=True)

    total_elevation_gain_m = models.FloatField(null=True, blank=True)
    average_heartrate = models.FloatField(null=True, blank=True)
    max_heartrate = models.FloatField(null=True, blank=True)

    start_lat = models.FloatField(null=True, blank=True)
    start_lng = models.FloatField(null=True, blank=True)

    # Para geocoding (lo llenaremos después con Nominatim)
    comuna = models.CharField(max_length=120, blank=True, null=True)
    region = models.CharField(max_length=120, blank=True, null=True)
    pais = models.CharField(max_length=120, blank=True, null=True)

    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name or 'Actividad'} ({self.strava_id})"

    @property
    def distance_km(self):
        """Distancia en km"""
        if self.distance_m:
            return round(self.distance_m / 1000, 2)
        return 0

    @property
    def moving_hms(self):
        """Tiempo en formato HH:MM:SS"""
        if not self.moving_time_s:
            return "-"
        seconds = int(self.moving_time_s)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

    @property
    def pace(self):
        """Ritmo en MM:SS /km"""
        if not self.moving_time_s or not self.distance_m or self.distance_m == 0:
            return "-"
        km = self.distance_m / 1000
        pace = self.moving_time_s / km
        m = int(pace // 60)
        s = int(round(pace % 60))
        if s == 60:
            m += 1
            s = 0
        return f"{m}:{s:02d} /km"

    @property
    def activity_kind(self):
        """Tipo deportivo detallado de Strava cuando exista."""
        return (self.sport_type or self.type or "").strip()

    @property
    def is_trail(self):
        return self.activity_kind in {"TrailRun"}

    @property
    def is_ride(self):
        return self.activity_kind in {"Ride", "VirtualRide", "EBikeRide", "MountainBikeRide", "GravelRide", "Handcycle"}

    @property
    def speed_kmh(self):
        if not self.moving_time_s or not self.distance_m or self.moving_time_s <= 0:
            return "-"
        kmh = (float(self.distance_m) / float(self.moving_time_s)) * 3.6
        return f"{kmh:.1f} km/h"

    @property
    def elev_gain_text(self):
        if self.total_elevation_gain_m is None:
            return "-"
        return f"{int(round(self.total_elevation_gain_m))} m"

    @property
    def avg_hr_text(self):
        if self.average_heartrate is None:
            return "-"
        return f"{int(round(self.average_heartrate))} ppm"

    @property
    def date_short(self):
        """Fecha en formato '16 de febrero'"""
        if not self.start_date:
            return ""
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        return f"{self.start_date.day} de {meses[self.start_date.month - 1]}"

    @property
    def location(self):
        """Ubicación: muestra la comuna + Carrera"""
        if self.comuna:
            return f"{self.comuna} Carrera"
        return ""
        return ""


class CumplimientoEntrenamiento(models.Model):

    perfil = models.ForeignKey("Perfil", on_delete=models.CASCADE, related_name="cumplimientos")
    entrenamiento = models.ForeignKey(
        "EntrenamientoDiario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cumplimientos",
    )
    fecha = models.DateField()

    realizada = models.BooleanField(default=False)
    realizada_at = models.DateTimeField(null=True, blank=True)
    comentario = models.TextField(blank=True, default="")

    # Auditoría y snapshot: guarda un pequeño JSON con datos relevantes
    audit_meta = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("perfil", "entrenamiento", "fecha")
        ordering = ["-fecha", "-updated_at"]

    def save(self, *args, **kwargs):
        if self.entrenamiento_id:
            self.fecha = self.entrenamiento.fecha
        if self.realizada and not self.realizada_at:
            self.realizada_at = timezone.now()
        if not self.realizada:
            self.realizada_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        estado = "✅" if self.realizada else "⏳"
        return f"{self.perfil} - {self.fecha} {estado}"


# --- Historial manual de carreras ---
# (Definir SIEMPRE después de todas las importaciones y modelos)
class CarreraManual(models.Model):
    DISTANCIA_CHOICES = [
        (3000, "3000m"),
        (5000, "5K"),
        (10000, "10K"),
        (21000, "21K"),
        (42000, "42K"),
    ]

    perfil = models.ForeignKey("Perfil", on_delete=models.CASCADE, related_name="carreras_manuales")
    fecha = models.DateField()
    distancia_m = models.PositiveIntegerField(choices=DISTANCIA_CHOICES)
    tiempo = models.CharField(max_length=10, help_text="Formato mm:ss o hh:mm:ss")

    class Meta:
        ordering = ["-fecha", "distancia_m"]

    def __str__(self):
        return f"{self.get_distancia_m_display()} - {self.fecha} - {self.tiempo}"
