# Limpieza pendiente (solo lista, NO se borró nada)

Generada el 22/10/2026 (Fase 0 de PLAN-CAPSULAS.md) desde `rayando_cda.clips`.
Criterio: `publicado = false`. No hay filas en estado `rechazado` (limpiar_clips.py ya las borra al entrar un programa nuevo).

| id (clips) | semana | estado | youtube_video_id | título | nota |
|---|---|---|---|---|---|
| 4d36ff1c-4f4f-43b1-b128-b8c5965d2e04 | 2026-09-21 | aprobado | zhNcchyvKdI | El medio chileno siempre es anti #UdeChile | En "Antiguas"; limpiar_clips.py lo borra solo al pasar 30 días de su semana (~21/10 ya cumplidos, revisar por qué sigue) |
| 876d29c3-81fd-4636-a319-25bc0a843a86 | 2026-10-19 | pendiente | 6M-fcPci1Pg | Así está el clima laboral en Rayando | Programa vigente, en revisión: NO es limpieza |
| 98f60c11-45e4-45c7-bf26-aa474062c9f8 | qa-fixture | prueba | dQw4w9WgXcQ | [CLIP DE PRUEBA] Fixture para tests | Fixture de tests; el id de YouTube NO es del canal. No borrar el video |

Resumen de estados: aprobado/publicado 46, aprobado/no publicado 1, pendiente 1, prueba 1.

Pendiente de revisar a mano (no verificable desde la BD): videos huérfanos en YouTube
(subidos como no listados por reprocesar_video.py cuyo registro ya no existe en `clips`).
Hace falta listar el canal por la API de YouTube para detectarlos.
