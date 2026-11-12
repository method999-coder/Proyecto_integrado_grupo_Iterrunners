# Iter Runners - Contexto del Proyecto

## Descripción

Iter Runners es una aplicación Django para la administración de clubes de running.

La plataforma permite gestionar clubes, grupos, corredores, calendarios de entrenamiento, cumplimiento diario, rankings, estadísticas y actividades sincronizadas desde Strava.

El sistema está orientado a tres perfiles principales: administradores, profesores y corredores. Además, mantiene separación por club para que profesores y administradores funcionales vean solo la información correspondiente a su organización, salvo usuarios superuser.

La aplicación está diseñada como plataforma web responsiva y cuenta con soporte básico tipo PWA mediante manifest, service worker e íconos.

## Tecnologías

- Python
- Django 6
- SQLite para desarrollo local
- PostgreSQL mediante `DATABASE_URL` para producción, compatible con Supabase
- Render para despliegue
- Gunicorn como servidor WSGI
- WhiteNoise para archivos estáticos en producción
- Strava API para OAuth y actividades
- Geopy/Nominatim preparado para geocoding
- HTML templates de Django
- CSS propio en `users/static/css/style.css`

## Estructura General

- `iterrunners/`: configuración principal del proyecto Django.
- `users/`: aplicación principal del sistema.
- `users/models.py`: modelos de negocio.
- `users/views.py`: vistas, permisos, integración Strava, ranking, feed y paneles.
- `users/urls.py`: rutas funcionales de la app.
- `users/forms.py`: formularios para corredores, grupos, ritmos, entrenamientos y registros manuales.
- `users/admin.py`: personalización del Django Admin.
- `users/templates/users/`: templates principales de la interfaz.
- `users/static/`: CSS, imágenes, manifest e íconos.
- `users/management/commands/`: comandos operativos, incluyendo sincronización automática con Strava.
- `tools/`: scripts auxiliares de análisis, reconstrucción y respaldo.
- `render-build.sh`: instalación, migraciones y collectstatic para Render.
- `Procfile`: arranque con Gunicorn.
- `.github/workflows/deploy-render.yml`: workflow que dispara deploy en Render al hacer push a `main`.

## Modelos Principales

### Club

Representa una organización o club de running.

Campos principales:

- `nombre`
- `descripcion`
- `creado_en`

Los clubes agrupan corredores, profesores y grupos. Muchas vistas limitan los datos visibles según el club del usuario.

### Grupo

Representa un grupo de entrenamiento dentro de un club.

Campos principales:

- `nombre`
- `descripcion`
- `club`

Cuando un grupo cambia de club, los perfiles asociados se actualizan para mantener consistencia con el club del grupo.

### Perfil

Extiende al usuario Django con información funcional del dominio.

Campos principales:

- `usuario`
- `nombre`
- `apellido`
- `fecha_nacimiento`
- `rol`
- `grupo`
- `club`
- `meta_actual`
- `mejor_marca`
- `must_change_password`
- `last_seen`
- `modalidad_ritmo`
- credenciales y metadatos Strava

Roles soportados:

- `admin`
- `profesor`
- `corredor`

El rol se calcula también desde grupos Django: `Admin`, `Profesor` y `Corredor`.

### Ritmo

Guarda zonas o ritmos de entrenamiento por usuario.

Soporta modalidad:

- `runners`
- `trail`

Incluye datos de test, VO2max, frecuencia cardíaca máxima y rangos de ritmo como REG, R1, R2, R3, UL, CA y CAN. Para trail se reutilizan como zonas Z0 a Z5 en la vista.

### EntrenamientoDiario

Representa un entrenamiento planificado para un grupo en una fecha.

Campos principales:

- `grupo`
- `fecha`
- `modalidad`
- `tipo`
- `titulo`
- `descripcion`

Tipos detectados:

- entrenamiento
- descanso
- core/fuerza
- carrera
- control

Existe restricción única por `grupo` y `fecha`.

### EntrenamientoRecurso

Recursos asociados a un entrenamiento diario.

Campos principales:

- `entrenamiento`
- `titulo`
- `url`
- `tipo`
- `orden`

Tipos:

- video
- documento
- otro

### StravaActividad

Representa una actividad sincronizada desde Strava.

Campos principales:

- `perfil`
- `strava_id`
- `name`
- `type`
- `sport_type`
- `start_date`
- `distance_m`
- `moving_time_s`
- `elapsed_time_s`
- `total_elevation_gain_m`
- `average_heartrate`
- `max_heartrate`
- `comuna`
- `region`
- `pais`
- `publicar_en_feed`

Incluye propiedades para mostrar distancia, tiempo, ritmo, velocidad, desnivel, frecuencia cardíaca y ubicación.

### CumplimientoEntrenamiento

Registra si un corredor realizó un entrenamiento planificado.

Campos principales:

- `perfil`
- `entrenamiento`
- `fecha`
- `realizada`
- `realizada_at`
- `comentario`
- `publicar_ranking`
- `ranking_distancia`
- `audit_meta`

Puede alimentar el ranking si corresponde.

### RankingEntry

Fuente canónica del ranking por corredor y distancia.

Campos principales:

- `perfil`
- `ranking_distancia`
- `cumplimiento`
- `time_seconds`

Tiene restricción única por `perfil` y `ranking_distancia`.

### RankingAudit

Historial de acciones relacionadas con ranking.

Registra actor, origen, distancia, snapshot, aceptación y publicación. Está pensado como auditoría inmutable.

### FeedLike y FeedComentario

Permiten interacción social sobre actividades Strava publicadas en el feed.

### CarreraManual

Historial manual de carreras por corredor.

Distancias soportadas:

- 3000m
- 5K
- 10K
- 21K
- 42K

### LactatoManual

Historial manual de mediciones de lactato para corredores.

## Roles y Permisos

### Administrador

Puede acceder a paneles de gestión y, si es superuser, ver información global.

Capacidades detectadas:

- Gestión de corredores.
- Gestión de grupos.
- Gestión de calendarios.
- Visualización de cumplimiento.
- Visualización de actividad de usuarios.
- Acceso al Django Admin.
- Acceso a información global si es superuser.

### Profesor

Puede operar sobre corredores, grupos y calendarios dentro de su club.

Capacidades detectadas:

- Ver y gestionar corredores de su club.
- Crear corredores asociados a su club.
- Editar corredores de su club.
- Gestionar grupos de su club.
- Gestionar calendarios de entrenamiento.
- Ver cumplimiento de entrenamientos.
- Ver actividades Strava de corredores de su club.
- Ver registros manuales asociados a corredores.

### Corredor

Usuario final de la plataforma.

Capacidades detectadas:

- Ver home personalizada.
- Ver entrenamiento del día.
- Ver calendario de su grupo.
- Registrar cumplimiento de actividad.
- Conectar/desconectar Strava.
- Ver actividades Strava propias.
- Publicar actividad al ranking cuando aplica.
- Ver estadísticas.
- Ver ranking.
- Ver feed.
- Ver compañeros de grupo.
- Ver perfil y ritmos.
- Agregar historial manual de carreras propias en ciertos casos.

## Permisos por Club

El proyecto implementa scoping por club en varias vistas.

Patrones detectados:

- Superuser puede ver datos globales.
- Usuarios no superuser se limitan al club resuelto desde `Perfil.club` o `Perfil.grupo.club`.
- Profesores no pueden editar corredores de otros clubes.
- Listados de grupos, corredores, actividades Strava y cumplimiento se filtran por club.
- El Django Admin también filtra `Grupo` y `Perfil` según club para usuarios no superuser.

Helper principal:

- `_resolve_user_club(user)`

## Criterios de Autorización

- Todo acceso de Profesor o Admin funcional a datos de corredores, grupos, entrenamientos, cumplimiento, actividades Strava, ranking o historiales debe validar pertenencia al mismo club.
- Los usuarios superuser pueden acceder a información global cuando la vista lo permita explícitamente.
- Los corredores solo deben acceder a información propia o a información compartida de su grupo/club según la funcionalidad.
- Antes de agregar una vista nueva, revisar si existe lógica reutilizable de autorización por club.
- Si una acción modifica datos, debe usar `POST` y validar permisos antes de escribir en base de datos.
- Las vistas administrativas nuevas deben considerar permisos por rol y scoping por club desde el inicio.

## Funcionalidades Existentes

### Home

La vista principal muestra información personalizada según perfil.

Incluye:

- Entrenamiento del día.
- Estado de conexión con Strava.
- Sincronización liviana de Strava cada cierto intervalo.
- Auto-marcado de cumplimiento desde Strava.
- Ritmos de entrenamiento.
- Kilómetros semanales.
- Cumpleaños del día por club.
- Accesos según rol.

### Calendario

Permite al corredor ver el calendario mensual de entrenamientos de su grupo.

Incluye navegación mensual, selección de día y visualización del entrenamiento planificado.

### Gestión de Calendarios

Panel para profesores/admins.

Permite:

- Seleccionar grupo.
- Ver calendario mensual.
- Crear o editar entrenamiento de un día.
- Asociar recursos al entrenamiento.
- Copiar entrenamientos entre meses.
- Borrar un mes de calendario.

### Gestión de Corredores

Panel para profesores/admins.

Permite:

- Listar corredores.
- Crear corredor.
- Editar corredor.
- Eliminar corredor.
- Asignar grupo.
- Crear, editar y eliminar ritmos.
- Restablecer contraseña temporal.
- Ver historial manual de carreras.
- Ver historial de lactato.

### Gestión de Grupos

Permite listar, crear, editar y eliminar grupos.

Incluye conteo de corredores por grupo y filtro por club para usuarios no superuser.

### Registro de Actividad

Permite a corredores y administradores marcar cumplimiento.

Características detectadas:

- Usa el entrenamiento del día o fecha seleccionada.
- Permite comentario.
- Puede publicar marca en ranking.
- Sugiere distancia de ranking según actividad Strava del día.
- Solo permite ranking para entrenamientos de tipo carrera o control.
- Si el corredor no tiene grupo, redirige al historial de carreras manuales.

### Cumplimiento

Panel para profesores/admins que muestra cumplimiento por grupo y fecha.

Incluye:

- Total de corredores.
- Total de cumplidos.
- Estado por corredor.
- Comentarios.
- Vistas de cumplidos por grupo o todos los grupos.

### Estadísticas

Vista para corredores y administradores.

Incluye:

- Cumplimiento semanal y mensual.
- Volumen de entrenamientos.
- Navegación por semana y mes.
- Protección para no navegar hacia periodos futuros.

### Ranking

Ranking por distancia:

- 3000m
- 5K
- 10K
- 21K
- 42K

Características:

- Usa `RankingEntry` como fuente canónica.
- Ordena por menor tiempo.
- Calcula ritmo.
- Para corredores, filtra o contextualiza por grupo.
- Registra acciones en `RankingAudit`.

### Feed

Feed social basado en actividades Strava publicadas.

Incluye:

- Actividades publicadas desde Strava.
- Likes.
- Comentarios.
- Conteo de interacciones.
- Orden por fecha de actividad.

### Mi Grupo

Permite al corredor ver su grupo y compañeros.

### Perfil

Muestra información personal, grupo, objetivos, marcas y ritmos de entrenamiento.

### Actividad de Usuarios

Vista administrativa para superuser o admin funcional.

Incluye:

- Último login.
- Última actividad detectada por middleware.
- Estado activo/inactivo.
- Estado de conexión Strava.
- Filtro por grupo y estado.

## Integración con Strava

La integración con Strava está centralizada en `users/views.py` y el modelo `Perfil`.

### Configuración

Variables usadas:

- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REDIRECT_URI`

En producción:

- `STRAVA_CLIENT_ID` es obligatorio.
- `STRAVA_CLIENT_SECRET` es obligatorio.
- `STRAVA_REDIRECT_URI` debe usar HTTPS.

### OAuth

Flujo detectado:

1. `strava_login` genera `state` aleatorio.
2. Redirige a Strava con scope `read,activity:read_all`.
3. `strava_callback` valida `state`.
4. Intercambia `code` por tokens.
5. Guarda tokens y `athlete_id` en `Perfil`.

### Refresh Token

`_strava_refresh_token(perfil)` refresca tokens cuando el access token expira.

### Sincronización

`_strava_sync_latest_activities(perfil, per_page=30)` consulta:

`https://www.strava.com/api/v3/athlete/activities`

Luego guarda o actualiza `StravaActividad` usando `strava_id`.

### Actividades

La vista `actividad`:

- Redirige a conectar Strava si no hay token.
- Refresca token si expiró.
- Pide actividades recientes a Strava.
- Guarda actividades localmente.
- Auto-marca cumplimiento.
- Muestra actividades desde base de datos.

### Auto-cumplimiento

`_auto_mark_cumplimiento_from_strava` marca entrenamientos como realizados cuando encuentra actividades recientes compatibles.

Reglas detectadas:

- Requiere perfil con grupo.
- Evalúa un rango configurable de días hacia atrás.
- Considera actividades `Run` y `TrailRun`.
- Prioriza la actividad de mayor distancia por fecha.
- No sobrescribe cumplimientos ya realizados.
- No sobrescribe pendientes con comentario o ranking manual.

### Desconexión y Eliminación de Datos

- `strava_disconnect` revoca token en Strava y limpia credenciales locales.
- `strava_delete_data` revoca token, borra actividades locales y limpia credenciales.
- Ambas acciones requieren POST.

### Panel Strava para Profesores/Admins

Permite ver corredores del club y revisar sus actividades Strava guardadas en la base de datos.

## Panel de Administración

Existen dos paneles:

### Panel Interno de la Aplicación

Ruta principal:

- `/administracion/`

Accesible para profesores, admins funcionales y superusers.

Incluye accesos a:

- Gestión de corredores.
- Gestión de calendarios.
- Gestión de grupos.
- Actividades Strava.
- Cumplimiento.
- Actividad de usuarios, visible para superuser según template.

### Django Admin

Ruta:

- `/admin/`

Personalizaciones detectadas:

- `UserAdmin` personalizado con inline de `Perfil`.
- Filtro para usuarios que nunca iniciaron sesión.
- Admin de `Grupo` filtrado por club para no superusers.
- Admin de `Perfil` filtrado por club para no superusers.
- Admin de `Ritmo`, `EntrenamientoDiario`, `CumplimientoEntrenamiento`.
- Admin de `RankingEntry` con acción auditada para eliminar entradas.
- Admin de `RankingAudit`.

## Templates Principales

Templates detectados:

- `base.html`: layout base, meta viewport, PWA, mensajes y scripts móviles.
- `home.html`: home autenticada.
- `administracion.html`: panel interno.
- `gestion_corredores.html`: gestión de corredores.
- `gestion_grupos.html`: gestión de grupos.
- `gestion_calendarios.html`: calendario administrativo.
- `calendario.html`: calendario del corredor.
- `registro_actividad.html`: registro de cumplimiento.
- `actividad.html`: actividades Strava propias.
- `strava_activities.html`: listado de corredores para revisión Strava.
- `strava_activities_runner_detail.html`: actividades Strava de un corredor.
- `feed.html`: feed social.
- `ranking.html`: ranking por distancia.
- `estadisticas.html`: métricas de cumplimiento y volumen.
- `perfil.html`: perfil y ritmos.
- `mi_grupo.html`: compañeros de grupo.
- `actividad_usuarios.html`: actividad de usuarios.
- `cumplimiento_hoy.html`: cumplimiento por día.

## Responsividad y PWA

El proyecto incluye:

- Meta viewport en `base.html`.
- CSS con múltiples media queries.
- Diseño con clases responsivas propias.
- Manifest web en `users/static/manifest.webmanifest`.
- Service worker servido desde `/service-worker.js`.
- Íconos para instalación móvil.
- Ajustes de navegación móvil en JavaScript dentro de `base.html`.

Todo cambio visual debe mantener compatibilidad con computador, tablet y celular.

## Configuración y Despliegue

### Desarrollo Local

Si `DATABASE_URL` está vacío, Django usa SQLite local:

- `db.sqlite3`

### Producción

Si `DATABASE_URL` existe y usa esquema `postgres` o `postgresql`, Django configura PostgreSQL.

Esto es compatible con Supabase si se usa una URL PostgreSQL válida con SSL cuando corresponda.

### Render

Archivos relacionados:

- `Procfile`
- `render-build.sh`
- `.github/workflows/deploy-render.yml`

`render-build.sh` ejecuta:

- instalar dependencias
- migraciones
- collectstatic

El workflow de GitHub dispara deploy en Render al hacer push a `main`.

Datos actuales de producción:

- URL de producción: [https://iter-runners.onrender.com](https://iter-runners.onrender.com/)
- Proveedor de despliegue: Render
- Servicio: `Iter-runners`
- Tipo: Web Service
- Plan: Starter
- Runtime: Python 3
- Repositorio conectado: `Catalina995/Iter-runners`
- Rama de despliegue: `main`

Flujo de despliegue recomendado:

1. Crear rama feature.
2. Desarrollar y probar localmente.
3. Realizar commit.
4. Fusionar cambios en `main`.
5. Render detecta cambios en `main`.
6. Se ejecuta despliegue automático.
7. Validar funcionamiento en producción.

### Supabase

Base de datos de producción:

- Proveedor: Supabase PostgreSQL
- Proyecto: `Iter runners`
- URL del proyecto: [https://qdmikxvodsvjwedrjywy.supabase.co](https://qdmikxvodsvjwedrjywy.supabase.co/)
- Entorno: Producción
- Región: West US (Oregon)
- Código de región: `us-west-2`
- Proveedor de infraestructura: AWS
- Instancia: `t4g.nano`
- Plan: Nano
- Backups: actualmente no configurados
- Repositorio Git: no conectado directamente a Supabase

El despliegue se realiza mediante Render. Supabase solo provee la base de datos PostgreSQL y la conexión desde Django se realiza mediante `DATABASE_URL`.

### Arquitectura por Entorno

Desarrollo:

- SQLite local
- Django local mediante `runserver`

Producción:

- Django desplegado en Render
- PostgreSQL administrado por Supabase
- Conexión mediante `DATABASE_URL`

## Middleware y Señales

### Middleware

`UpdateLastSeenMiddleware` actualiza `Perfil.last_seen` para usuarios autenticados con throttling de 5 minutos.

### Señales

Al crear un `User`, se crea automáticamente un `Perfil`.

Si existe un club, se asigna como club por defecto el club más recientemente creado.

## Formularios

Formularios detectados:

- `CrearCorredorForm`
- `EditarCorredorForm`
- `RitmoForm`
- `GrupoForm`
- `EntrenamientoDiarioForm`
- `EntrenamientoRecursoForm`
- `CarreraManualForm`
- `LactatoManualForm`

Los formularios de corredor filtran grupos por club cuando el usuario no es superuser.

## Pruebas Existentes

El proyecto incluye pruebas en `users/tests.py`.

Coberturas detectadas:

- Restablecimiento de contraseña temporal.
- Cumplimiento diario.
- Copia de mes de calendario.
- Estadísticas sin navegación futura.
- Restricciones de ranking por tipo de entrenamiento.
- Scoping por club para profesores.
- Señal de creación de perfil.
- Creación de corredor con club del profesor.
- Ranking por distancia y grupo.
- Sugerencia de ranking desde Strava.
- Feed, likes y comentarios.
- Eliminación de datos Strava.
- Seguridad de OAuth state en Strava.

## Principios del Proyecto

- Reutilizar lógica existente antes de crear código nuevo.
- No duplicar integración con Strava.
- Mantener separación por club.
- Mantener compatibilidad con Render y Supabase.
- Mantener diseño responsivo.
- No romper vista móvil.
- Trabajar por cambios pequeños y verificables.
- Evitar migraciones salvo autorización explícita.
- No modificar modelos sin explicar impacto.
- No tocar producción directamente.
- No hacer commit ni push sin autorización explícita.

## Responsables

- Dueño funcional: Catalina Manríquez
- Responsable técnico: Catalina Manríquez

## Reglas de Negocio

- Un corredor pertenece a un grupo.
- Un grupo pertenece a un club.
- Los profesores solo pueden gestionar corredores de su propio club.
- Los profesores y administradores pueden restablecer contraseñas temporales solo para corredores de su propio club.
- Los corredores pueden recuperar su contraseña de forma autónoma mediante correo electrónico si tienen un email registrado.
- Después de una recuperación autónoma exitosa, el corredor no debe quedar obligado a cambiar nuevamente la contraseña.
- Las actividades Strava no deben duplicarse.
- Los rankings utilizan únicamente actividades válidas definidas por la aplicación.
- Los cumpleaños se muestran únicamente a usuarios del mismo club.
- Los planes de entrenamiento son gestionados por profesores o administradores.
- Los corredores pueden visualizar sus entrenamientos y actividades sincronizadas.

## Recuperación de Contraseña

Iter Runners mantiene dos caminos complementarios:

- Flujo asistido: Profesor/Admin restablece una contraseña temporal para corredores que necesitan ayuda.
- Flujo autónomo: el corredor solicita un enlace de recuperación desde el login y define su nueva contraseña por correo.

El flujo asistido conserva la lógica de contraseña temporal y `must_change_password = True`.

El flujo autónomo usa las vistas estándar de Django para recuperación por email. Al completar correctamente el cambio, se limpia `must_change_password` para evitar que el corredor quede atrapado en el cambio obligatorio.

Variables de correo para producción en Render:

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST=smtp-relay.brevo.com`
- `EMAIL_PORT=587`
- `EMAIL_USE_TLS=True`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

En desarrollo local, el backend por defecto es `django.core.mail.backends.console.EmailBackend`, para revisar el contenido del correo en la terminal sin enviar emails reales.

## Política de Datos Strava

- Solo se almacenan datos autorizados por el usuario mediante OAuth de Strava.
- El usuario puede desconectar Strava cuando lo estime conveniente.
- Los datos obtenidos desde Strava se utilizan únicamente para funcionalidades de entrenamiento, seguimiento y estadísticas dentro de Iter Runners.
- No se comparten datos de Strava con terceros.
- Los tokens de acceso se almacenan para mantener la sincronización automática de actividades.

## Seguridad

### Fortalezas Detectadas

- La mayoría de vistas internas exige autenticación mediante `@login_required`.
- La aplicación separa roles mediante grupos Django: `Admin`, `Profesor` y `Corredor`.
- Existen helpers reutilizables para autorización y scoping, como `_is_staffish`, `_resolve_user_club` y `_perfil_belongs_to_club`.
- Varias vistas sensibles filtran datos por club, especialmente corredores, grupos, calendarios, cumplimiento y actividades Strava visibles para profesores.
- El restablecimiento asistido de contraseña valida el club del corredor antes de generar una contraseña temporal.
- La recuperación autónoma de contraseña usa tokens seguros de Django y no revela si un correo existe.
- CSRF está activo en la configuración de Django y los formularios `POST` principales incluyen `{% csrf_token %}`.
- Las acciones sensibles relacionadas con Strava, como desconectar o eliminar datos, requieren método `POST`.
- El flujo OAuth de Strava usa un `state` aleatorio guardado en sesión y validado en el callback.
- Las variables sensibles se manejan mediante entorno: `SECRET_KEY`, `DATABASE_URL`, `STRAVA_CLIENT_SECRET`, `STRAVA_REDIRECT_URI`, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.
- `.env` y `db.sqlite3` están excluidos en `.gitignore`.
- En producción, con `DEBUG=False`, se activan medidas como cookies seguras, redirección SSL, HSTS, `X_FRAME_OPTIONS = "DENY"` y `SECURE_CONTENT_TYPE_NOSNIFF`.
- Existen pruebas automatizadas para permisos por club, feed, ranking y seguridad básica del flujo OAuth de Strava.

### Riesgos Detectados

- `restablecer_password_corredor` valida que el usuario sea profesor/admin, pero debe reforzarse para validar también que el corredor pertenezca al mismo club cuando el actor no sea superuser.
- `asignar_grupo` filtra los grupos visibles por club, pero en el `POST` debe asegurar que el grupo elegido provenga del queryset ya filtrado.
- `historial_carreras_manual` y `historial_lactato_manual` deben reforzar la validación por club para profesores/admins funcionales.
- El Django Admin tiene scoping por club parcial: `GrupoAdmin` y `PerfilAdmin` filtran por club, pero otros modelos sensibles deberían revisarse.
- Los tokens de Strava se almacenan actualmente en campos normales del modelo `Perfil`; si alguien accede a la base de datos, podría leerlos.
- `DEBUG` tiene valor por defecto `True`; en producción debe estar explícitamente configurado como `False`.
- Supabase no tiene backups configurados actualmente.
- Parte importante de la lógica sensible está concentrada en `users/views.py`, lo que aumenta el riesgo de inconsistencias de permisos entre vistas.

### Mejoras Recomendadas

Estas mejoras deben trabajarse de a poco, en cambios pequeños, verificables y con pruebas.

Prioridad alta:

1. Agregar validación por club en `restablecer_password_corredor`.
2. Corregir `asignar_grupo` para que el grupo del `POST` salga del queryset filtrado por club.
3. Agregar validación por club en `historial_carreras_manual` y `historial_lactato_manual`.
4. Crear pruebas para evitar accesos cross-club en reset de contraseña, asignación de grupo e historiales.

Prioridad media:

1. Revisar y reforzar scoping por club en todos los modelos sensibles del Django Admin.
2. Evaluar cifrado de tokens Strava a nivel aplicación.
3. Confirmar en Render que `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` y variables Strava estén correctamente configuradas.
4. Activar backups en Supabase o definir un respaldo periódico externo.

Prioridad baja / mantenimiento:

1. Ejecutar `python manage.py check --deploy` en un entorno local con dependencias instaladas antes de cada despliegue relevante.
2. Separar gradualmente lógica sensible de `users/views.py` hacia helpers o servicios reutilizables para reducir duplicación de permisos.
3. Documentar en `CHANGELOG.md` los cambios importantes de seguridad.

## QA y Validación

Antes de desplegar a producción:

1. Probar funcionalidad localmente.
2. Verificar permisos por rol: Admin, Profesor y Corredor.
3. Verificar filtrado correcto por club.
4. Validar diseño responsivo en escritorio, tablet y móvil.
5. Verificar recuperación de contraseña si el cambio afecta autenticación.
6. Verificar integración Strava.
7. Revisar migraciones pendientes.
8. Confirmar compatibilidad con Render y Supabase.
9. Revisar errores en logs.
10. Validar funcionamiento en producción después del despliegue.
11. Documentar cambios importantes en `CHANGELOG.md`.

## Reglas Para Futuros Cambios

Antes de modificar código:

1. Analizar modelos, vistas, rutas y templates relacionados.
2. Verificar permisos por rol y por club.
3. Revisar si ya existe helper o lógica reutilizable.
4. Evaluar impacto en Strava, ranking, cumplimiento y feed.
5. Confirmar si el cambio requiere migración.
6. Proponer plan si el cambio es grande.
7. Implementar cambios pequeños.
8. Indicar cómo probar localmente.
9. Esperar autorización explícita antes de commit o push.

## Cómo Probar Localmente

Comandos habituales:

```bash
python manage.py runserver
python manage.py test
```
