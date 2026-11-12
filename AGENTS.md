# Iter Runners - Reglas para agentes

## Contexto del proyecto
Iter Runners es una aplicación Django para gestión de clubes de running.

Tecnologías principales:
- Django
- SQLite para desarrollo local
- Supabase para producción
- Render para despliegue
- Integración con Strava

Roles principales:
- Admin
- Profesor
- Corredor

## Reglas obligatorias
- No hacer push sin autorización explícita.
- No hacer commit sin autorización explícita.
- No crear migraciones sin autorización explícita.
- No modificar modelos sin explicar antes el impacto.
- Reutilizar lógica existente antes de crear código nuevo.
- No duplicar integración con Strava.
- No tocar producción directamente.
- Mantener compatibilidad con Render y Supabase.
- Trabajar por cambios pequeños y verificables.
- Después de modificar archivos, explicar qué cambió.
- Indicar siempre cómo probar localmente.
- Documentar cambios importantes en CHANGELOG.md.
- Si una tarea es grande, primero proponer un plan por commits y esperar confirmación.

## Responsividad
- Todo cambio visual debe ser responsivo.
- La aplicación debe verse correctamente en computador, tablet y celular.
- No romper la vista móvil.
- Evitar anchos fijos innecesarios.
- Usar layouts flexibles con CSS responsive cuando corresponda.
- Probar mentalmente el diseño en pantalla pequeña antes de finalizar.

## Uso de recursos
- Evitar generar archivos temporales o logs innecesarios.
- No crear reportes, dumps, backups o archivos de depuración sin autorización.
- Eliminar archivos temporales creados durante la tarea.
- Informar comandos ejecutados y archivos modificados.
- Evitar procesos largos o repetitivos sin aprobación.

## Flujo recomendado
1. Analizar.
2. Proponer plan.
3. Implementar solo el paso autorizado.
4. Probar localmente.
5. Esperar autorización para commit.
6. No hacer push salvo que se indique expresamente.

## Convenciones Git
- feat/ para funcionalidades nuevas.
- fix/ para correcciones de errores.
- style/ para cambios visuales.
- Commits pequeños y descriptivos.
