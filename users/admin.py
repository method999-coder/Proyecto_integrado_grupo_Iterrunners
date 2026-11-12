from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from .models import CumplimientoEntrenamiento, EntrenamientoDiario, Grupo, Perfil, Ritmo, Club, RankingEntry, RankingAudit


class NeverLoggedInFilter(admin.SimpleListFilter):
    title = _("nunca inició sesión")
    parameter_name = "never_logged_in"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Sí")),
            ("no", _("No")),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "yes":
            return queryset.filter(last_login__isnull=True)
        if value == "no":
            return queryset.filter(last_login__isnull=False)
        return queryset


class PerfilInline(admin.StackedInline):
    model = Perfil
    can_delete = False
    verbose_name_plural = "Perfil"
    fk_name = "usuario"
    fields = ("nombre", "apellido", "rol", "club", "grupo", "must_change_password")
    extra = 0


class CustomUserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ("last_login",)
    list_filter = DjangoUserAdmin.list_filter + (NeverLoggedInFilter,)
    inlines = (PerfilInline,)


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

admin.site.register(User, CustomUserAdmin)


@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion", "club")
    search_fields = ("nombre",)
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            user_club = request.user.perfil.club
        except Exception:
            return qs.none()
        if not user_club:
            return qs.none()
        return qs.filter(club=user_club)


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion", "creado_en")
    search_fields = ("nombre",)


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("nombre", "usuario", "rol", "club", "grupo", "must_change_password")
    list_filter = ("rol", "club", "grupo", "must_change_password")
    search_fields = ("nombre", "usuario__username", "usuario__first_name", "usuario__last_name")
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            user_club = request.user.perfil.club
        except Exception:
            return qs.none()
        if not user_club:
            return qs.none()
        return qs.filter(club=user_club)


@admin.register(Ritmo)
class RitmoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "fecha")
    list_filter = ("fecha",)
    search_fields = ("usuario__username",)


@admin.register(EntrenamientoDiario)
class EntrenamientoDiarioAdmin(admin.ModelAdmin):
    list_display = ("grupo", "fecha", "tipo", "titulo")
    list_filter = ("grupo", "tipo", "fecha")
    search_fields = ("grupo__nombre", "titulo", "descripcion")
    ordering = ("fecha",)


@admin.register(CumplimientoEntrenamiento)
class CumplimientoEntrenamientoAdmin(admin.ModelAdmin):
    list_display = ("perfil", "entrenamiento", "fecha", "realizada", "realizada_at", "comentario")
    list_filter = ("realizada", "fecha", "entrenamiento__grupo")
    search_fields = ("perfil__nombre", "perfil__usuario__username", "entrenamiento__titulo", "comentario")
    ordering = ("-fecha", "-updated_at")


# Admin action: delete selected RankingEntry rows but record an audit for each
def delete_ranking_entries_with_audit(modeladmin, request, queryset):
    if not request.user.is_staff:
        messages.error(request, "No permission.")
        return
    with transaction.atomic():
        for entry in queryset:
            RankingAudit.objects.create(
                perfil=entry.perfil,
                club=getattr(entry.perfil, "club", None),
                action="manual_delete",
                origin="admin",
                snapshot={"ranking_distancia": entry.ranking_distancia, "time_seconds": entry.time_seconds},
                accepted=True,
                comment=f"Deleted by {request.user.username}"
            )
        count = queryset.count()
        queryset.delete()
    messages.success(request, f"Deleted {count} ranking entries and created audits.")

delete_ranking_entries_with_audit.short_description = "Delete selected ranking entries (create audit entry)"


@admin.register(RankingEntry)
class RankingEntryAdmin(admin.ModelAdmin):
    verbose_name_plural = "Ranking"
    list_display = ("perfil", "ranking_distancia", "time_seconds")
    list_filter = ("ranking_distancia", "perfil__club")
    search_fields = ("perfil__nombre", "perfil__usuario__username")
    ordering = ("ranking_distancia", "time_seconds")
    actions = [delete_ranking_entries_with_audit]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser and not request.user.has_perm("users.delete_rankingentry"):
            actions.pop("delete_ranking_entries_with_audit", None)
        return actions


@admin.register(RankingAudit)
class RankingAuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "perfil", "action", "origin", "suggested_ranking", "accepted", "published_ranking")
    list_filter = ("action", "origin", "accepted", "published_ranking", "suggested_ranking")
    search_fields = ("perfil__nombre", "perfil__usuario__username", "comment")
    ordering = ("-created_at",)
