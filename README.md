# Proyecto_integrado_grupo_Iterrunners

## Propuesta de Arquitectura - Gaspar (DEV)

### Arquitectura por capas para Iterrunners

Se propone estructurar Iterrunners mediante una arquitectura por capas utilizando Django, separando la presentación, la lógica de negocio y el acceso a los datos para mejorar la organización y el mantenimiento del sistema.

### Capas propuestas

- **Capa de presentación:** interfaces HTML, plantillas Django y archivos CSS que permiten la interacción de Administradores, Profesores y Corredores.
- **Capa de lógica de negocio:** vistas, formularios y servicios encargados de gestionar clubes, grupos, planificaciones y entrenamientos.
- **Capa de acceso a datos:** modelos Django y ORM para consultar, registrar y actualizar la información del sistema.
- **Capa de integración externa:** comunicación con servicios como Strava mediante OAuth 2.0 y sincronización de actividades deportivas.

### Justificación técnica

Esta propuesta favorece la **separación de responsabilidades**, la **organización del código** y la **facilidad de mantenimiento**.

La arquitectura por capas permite identificar con mayor claridad las responsabilidades técnicas de cada parte del sistema y facilita la implementación de pruebas y futuras mejoras.

Esta propuesta representa una posible reorganización de la arquitectura actual de Iterrunners.
