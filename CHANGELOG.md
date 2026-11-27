# CHANGELOG - Iter Runners

### 2026-11-27 - Correo de recuperación mediante la API de Brevo

Se añadió un backend de correo transaccional que se activa por entorno. El flujo conserva los enlaces y la respuesta genérica de recuperación de Django. Las pruebas simulan la API y comprueban el enlace y el manejo de errores.

Para probar localmente, ejecuta `python manage.py test --settings=iterrunners.settings_test` y sigue la sección de Brevo del README para la prueba de entrega.

### 2026-11-27 - Integración de Strava en el entorno académico

El callback OAuth se configura por entorno y el ejemplo local apunta a `localhost:8766`. Se validan la sesión, el permiso de lectura y los datos de autorización antes de vincular. Se guardan los tokens renovados, se reutiliza la importación de actividades sin transferir registros entre perfiles y se conservan las actividades al desconectar. Si Strava falla durante la consulta, se muestran las actividades guardadas del corredor.

Para probar, ejecuta `python manage.py test --settings=iterrunners.settings_test` y sigue la sección de Strava del README para una autorización real con la app académica.

## Formato de entradas

### YYYY-MM-DD - Nombre del cambio

Rama:
nombre-rama

Tipo:
feat / fix / style / docs

Resumen:
Explicación simple de lo que se hizo.

Archivos principales:

* archivo1
* archivo2
* archivo3

Cómo probar:

1. Paso 1
2. Paso 2
3. Resultado esperado

Pendientes:

* Pendiente 1
* Pendiente 2

---

### 2026-11-22 - Limpieza de modelos de feed y lactato

Se retiraron del ORM los modelos de likes, comentarios sociales y lactato manual, junto con el campo que marcaba actividades Strava para publicación. Los cambios de esquema de ranking, feed y lactato quedan pendientes de la migración definitiva.

Para verificar localmente, ejecutar python manage.py check y python manage.py makemigrations --dry-run --verbosity 2.

---

### 2026-11-22 - Retiro del historial manual de lactato

Se retiraron el acceso desde Gestión de corredores, la consulta y los formularios de alta y eliminación del historial manual de lactato. El modelo y las mediciones existentes se conservan hasta la migración definitiva. Las zonas de entrenamiento y los ritmos personalizados siguen disponibles.

Para probar localmente, ejecutar manage.py check y la suite con SQLite en memoria y migraciones desactivadas. Desde Gestión de corredores, verificar que el historial de carreras sigue accesible y que la antigua ruta de lactato devuelve 404.

---

### 2026-11-22 - Retiro del feed de actividades

Se retiraron el acceso al feed, los likes, los comentarios sociales y la publicación automática. Las actividades Strava siguen sincronizándose y se pueden consultar en Actividades.

Para probar localmente, ejecutar manage.py check y la suite con SQLite en memoria y migraciones desactivadas. Desde Inicio, verificar que el acceso a Actividades se mantiene.

Los modelos sociales y el campo de publicación quedan pendientes de la migración definitiva.

---

### 2026-11-10 - Aislamiento de Iterrunners-Dev

<!-- INICIO - Registro de los cambios de aislamiento -->
Tipo:
fix

Resumen:
La copia Dev usa SQLite en la raíz y correo por consola. Strava desactivado bloquea las acciones externas y el auto-cumplimiento. La consulta histórica sigue disponible y la reconstrucción manual usa SQLite con simulación por defecto. El respaldo PostgreSQL y el build de Render quedan bloqueados. El workflow manual solo informa la política local.

Cómo probar:

1. Ejecutar `python manage.py check`.
2. Ejecutar `python manage.py test`. Las pruebas usan SQLite en memoria y simulan las llamadas a Strava.
3. Verificar que una `DATABASE_URL` ficticia heredada siga resolviendo el backend SQLite sin abrir una conexión.

Pendiente:
Si se autoriza un despliegue de pruebas, preparar un servicio Render separado con credenciales propias y un workflow manual con aprobación de entorno. Revisar en ese cambio el build y la configuración de base del servicio de pruebas.
<!-- FIN - Registro de los cambios de aislamiento -->

### 2026-06-22 - Actividades Strava para Profesores

Rama:
feat/profesor-actividades-strava

Tipo:
feat

Resumen:
Se agregó una nueva funcionalidad para que profesores y administradores puedan visualizar las actividades Strava de corredores pertenecientes a su club. Además, se mejoró el diseño del listado y del detalle para mantener una experiencia visual más consistente con la vista de actividades del corredor.

Cambios realizados:

* Nueva tarjeta "Actividades Strava" en administración.
* Nueva vista de listado de corredores.
* Nueva vista de detalle por corredor.
* Listado de corredores centrado y responsivo.
* Buscador frontend para filtrar corredores por nombre, apellido o grupo.
* Visualización de nombre y apellido del corredor cuando está disponible.
* Detalle de actividades con tarjetas azules, distancia destacada, tiempo y ritmo.
* Corrección visual del ícono de running para reutilizar el estilo de la vista original del corredor.
* Reutilización de actividades Strava existentes almacenadas en base de datos.
* Sin nuevas integraciones con Strava.
* Sin nuevas migraciones.

Archivos principales:

* views.py
* urls.py
* strava_activities.html
* strava_activities_runner_detail.html

Cómo probar:

1. Iniciar sesión como Profesor o Admin.
2. Ir a Administración.
3. Entrar a Actividades Strava.
4. Verificar que el listado aparece centrado y muestra nombre y apellido cuando existe.
5. Buscar un corredor por nombre, apellido o grupo.
6. Seleccionar un corredor.
7. Verificar que aparecen sus actividades sincronizadas en tarjetas azules.
8. Confirmar que no aparece el botón "Subir al ranking".
9. Revisar la vista en escritorio y móvil.

Pendientes:

* Seguir ajustando detalles visuales menores si aparecen nuevos casos reales de actividades.
* Validar con más corredores y grupos antes de desplegar a producción.

---

### 2026-06-23 - Recuperación Autónoma de Contraseña

Rama:
main

Tipo:
feat / fix / docs

Resumen:
Se agregó un flujo autónomo para que corredores puedan recuperar su contraseña por correo electrónico desde la pantalla de login, manteniendo el flujo actual donde Profesor/Admin puede restablecer una contraseña temporal.

Cambios realizados:

* Enlace "¿Olvidaste tu contraseña?" en el login.
* Templates propios para solicitar recuperación, confirmar envío, crear nueva contraseña y confirmar cambio exitoso.
* Envío de correo mediante el flujo estándar de Django.
* Configuración compatible con Brevo SMTP en producción y backend de consola en desarrollo local.
* Variables SMTP de Brevo configuradas en Render.
* Limpieza de `must_change_password` después de una recuperación autónoma exitosa.
* Refuerzo de permisos para que Profesor/Admin solo restablezca contraseñas de corredores de su propio club.
* Flujo validado en producción con envío real de correo.
* Sin nuevas migraciones.

Archivos principales:

* settings.py
* urls.py
* views.py
* login.html
* templates de recuperación de contraseña
* tests.py
* PROJECT_CONTEXT.md

Cómo probar:

1. Ir al login.
2. Entrar a "¿Olvidaste tu contraseña?".
3. Ingresar el correo de un corredor activo.
4. Revisar el enlace en la terminal local o en el correo configurado.
5. Abrir el enlace y definir una nueva contraseña.
6. Iniciar sesión con la nueva contraseña.
7. Confirmar que el corredor no queda atrapado en cambio obligatorio de contraseña.
8. Como Profesor/Admin, restablecer una contraseña temporal y confirmar que el flujo asistido sigue funcionando.

Pendientes:

* Evaluar más adelante si conviene agregar envío asistido por correo desde el panel del Profesor/Admin.
* Monitorear posibles errores de entrega de correo en logs de Render y Brevo.

---

### 2026-07-26 - Validación de Grupo por Club

Rama:
main

Tipo:
fix

Resumen:
Se reforzó la seguridad al asignar grupos a corredores para asegurar que Profesor/Admin solo pueda asignar grupos permitidos por su club.

Cambios realizados:

* La asignación de grupo ahora valida el grupo seleccionado contra el listado filtrado por club.
* Se evita que un grupo de otro club pueda ser asignado manipulando el formulario.
* Se agregaron pruebas para asignación válida dentro del mismo club y bloqueo de asignación cross-club.
* Sin nuevas migraciones.

Archivos principales:

* views.py
* tests.py

Cómo probar:

1. Iniciar sesión como Profesor/Admin.
2. Ir a Gestión de corredores.
3. Asignar a un corredor un grupo de su mismo club.
4. Confirmar que la asignación funciona correctamente.
5. Ejecutar pruebas automatizadas de asignación de grupo.

Pendientes:

* Revisar validación por club en historiales manuales de carrera y lactato.

---

### 2026-07-28 - Filtro de Grupos en Formularios de Corredor

Rama:
fix/filtro-grupos-form-corredor

Tipo:
fix

Resumen:
Se corrigió el selector de grupos en los formularios de creación y edición de corredores para que Profesor/Admin funcional solo vea grupos pertenecientes a su propio club.

Cambios realizados:

* El formulario de creación de corredor filtra grupos por el club del usuario actual.
* El formulario de edición de corredor filtra grupos por el club del usuario actual.
* La vista de edición ahora entrega el usuario y club actual al formulario.
* Se evita crear un corredor asignándolo a un grupo de otro club mediante POST manipulado.
* Se agregaron pruebas para validar que no se muestran grupos de otros clubes.
* Sin nuevas migraciones.

Archivos principales:

* forms.py
* views.py
* tests.py

Cómo probar:

1. Iniciar sesión como Profesor/Admin funcional de un club.
2. Ir a Crear corredor.
3. Confirmar que el campo Grupo muestra solo grupos del club del usuario.
4. Ir a Editar corredor.
5. Confirmar que el campo Grupo muestra solo grupos del club del usuario.
6. Ejecutar las pruebas automatizadas del filtro de grupos.

Pendientes:

* Validar el comportamiento en producción después del merge.
