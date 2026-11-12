from django.urls import path

from . import views

urlpatterns = [
    path("_health/", views.healthcheck, name="healthcheck"),
    path("", views.home, name="home"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("administracion/", views.administracion, name="administracion"),

    # Corredor
    path("perfil/", views.perfil_view, name="perfil"),
    path("calendario/", views.calendario, name="calendario"),
    path("cambiar-password/", views.cambiar_password, name="cambiar_password"),
    path("registro-actividad/", views.registro_actividad, name="registro_actividad"),
    path("ranking/", views.ranking, name="ranking"),
    path("feed/", views.feed, name="feed"),
    path("feed/<int:actividad_id>/like/", views.feed_like_toggle, name="feed_like_toggle"),
    path("feed/<int:actividad_id>/comentar/", views.feed_comentar, name="feed_comentar"),

    # Admin: Corredores
    path("gestion/corredores/", views.gestion_corredores, name="gestion_corredores"),
    path("gestion/corredores/nuevo/", views.crear_corredor, name="crear_corredor"),
    path("gestion/corredores/<int:perfil_id>/editar/", views.editar_corredor, name="editar_corredor"),
    path("gestion/corredores/<int:perfil_id>/eliminar/", views.eliminar_corredor, name="eliminar_corredor"),
    path("gestion/corredores/<int:perfil_id>/ritmos/crear/", views.crear_ritmo, name="crear_ritmo"),
    path("gestion/corredores/<int:perfil_id>/ritmos/<int:ritmo_id>/editar/", views.editar_ritmo, name="editar_ritmo"),
    path("gestion/corredores/<int:perfil_id>/ritmos/<int:ritmo_id>/eliminar/", views.eliminar_ritmo, name="eliminar_ritmo"),
    path("gestion/corredores/<int:perfil_id>/historial-carreras/", views.historial_carreras_manual, name="historial_carreras_manual"),
    path("gestion/corredores/<int:perfil_id>/historial-lactato/", views.historial_lactato_manual, name="historial_lactato_manual"),
    path("gestion/corredores/<int:perfil_id>/asignar-grupo/", views.asignar_grupo, name="asignar_grupo"),
    path("gestion/corredores/<int:perfil_id>/restablecer-password/", views.restablecer_password_corredor, name="restablecer_password_corredor"),

    # Admin: Grupos
    path("gestion/grupos/", views.gestion_grupos, name="gestion_grupos"),
    path("gestion/grupos/crear/", views.crear_grupo, name="crear_grupo"),
    path("gestion/grupos/<int:grupo_id>/editar/", views.editar_grupo, name="editar_grupo"),
    path("gestion/grupos/<int:grupo_id>/eliminar/", views.eliminar_grupo, name="eliminar_grupo"),

    # Admin: Calendarios
    path("gestion/calendarios/", views.gestion_calendarios, name="gestion_calendarios"),
    path("gestion/actividad-usuarios/", views.actividad_usuarios, name="actividad_usuarios"),
    path("gestion/cumplimiento-hoy/", views.cumplimiento_hoy, name="cumplimiento_hoy"),
    path("gestion/cumplimiento-hoy/cumplidos/todos/", views.cumplimiento_cumplidos_todos, name="cumplimiento_cumplidos_todos"),
    path("gestion/cumplimiento-hoy/<int:grupo_id>/cumplidos/", views.cumplimiento_cumplidos, name="cumplimiento_cumplidos"),
    path("gestion/calendarios/copiar-mes/", views.copiar_mes, name="copiar_mes"),
    path("gestion/calendarios/borrar-mes/", views.borrar_mes_calendario, name="borrar_mes_calendario"),
    path("gestion/calendarios/<int:grupo_id>/<str:fecha>/editar/", views.editar_entrenamiento_dia, name="editar_entrenamiento_dia"),
    path("gestion/calendarios/recurso/<int:recurso_id>/eliminar/", views.eliminar_entrenamiento_recurso, name="eliminar_entrenamiento_recurso"),
    path("mi-grupo/", views.mi_grupo, name="mi_grupo"),
    path("strava/login/", views.strava_login, name="strava_login"),
    path("strava/disconnect/", views.strava_disconnect, name="strava_disconnect"),
    path("strava/delete-data/", views.strava_delete_data, name="strava_delete_data"),
    path("strava/feed/<int:actividad_id>/ranking/", views.strava_publish_ranking, name="strava_publish_ranking"),
    path("strava/callback/", views.strava_callback, name="strava_callback"),
    path("strava/activities/", views.strava_activities, name="strava_activities"),
    path("strava/activities/corredor/<int:perfil_id>/", views.strava_activities_runner_detail, name="strava_activities_runner_detail"),
    path("actividad/", views.actividad, name="actividad"),
    path("estadisticas/", views.estadisticas, name="estadisticas"),



]
