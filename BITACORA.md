# BITÁCORA

## 22/10/2026 — Fase 0 (reconocimiento de cápsulas), rama feature/capsulas
- Sin cambios de código. Se creó la rama, esta bitácora, `limpieza_pendiente.md` y se incorporó `PLAN-CAPSULAS.md`.
- No existe `CLAUDE.md` en el repo (el plan lo da por existente): falta crearlo.
- Pipeline: tarea `RayandoCDA_AutoProcesar` (mar 00:00 a mié 10:00, cada 5 min) -> `auto_procesar.ps1` -> `transcribir.py <archivo>` + `procesar_programa.py <archivo>`.
- Corte horizontal actual: `cortar_clip.py` (`cut_horizontal` / `cut_recode`, libx264 crf18 con pad 0.4 s y fade 0.25 s) -> `horizontal_original.mp4`.
- `clips`: 28 columnas; `semana` es text; no hay `capitulo` ni `formato`.
- OBS (perfil `Rayando_el_CDA_lunes`): mkv, h264 High 1080p30, keyframe cada 8,33 s (250 frames, default NVENC).
