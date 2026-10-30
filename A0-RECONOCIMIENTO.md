# A0 — Reconocimiento para unificar La Herramienta (Recda + SPA)

**30 oct 2026.** Solo lectura, sin cambios de código. Sigue a `PLAN-UNIFICACION-Y-SERVICIO.md`, bloque A.

## 1. Estado de las ramas
- `main` (producción, `C:\Audiovisual\la-herramienta\rayando-cda`): 13 commits que no están en `multiprograma-spa` (Fase 1 cápsulas, métricas mediakit, docs, rutas del traslado, y 2 de la app SPA).
- `multiprograma-spa` (worktree `spa-herramienta`): 21 commits que no están en `main`. Base común: `62b3064` (1 oct).
- La app SPA (`?p=spa`, commit `263a038`) y "Ya lo publiqué" (`99b22cb`) **ya están en `main`**: por eso la app desplegada sirve a los dos programas. En la rama SPA el mismo cambio de la app está como `b4caf6d` (idéntico, otro hash).
- Prueba de fusión en memoria (`git merge-tree`, sin tocar archivos): **7 archivos con conflicto**: `app/src/components/ClipCard.jsx`, `app/src/lib/programa.js`, `pipeline/config.py`, `pipeline/cortar_clip.py`, `pipeline/publicar.py`, `pipeline/reprocesar_subtitulos.py`, `pipeline/reprocesar_video.py`. Casi todos vienen de la Fase 1 (capítulo en los shorts) contra los cambios multiprograma. Se resuelven a mano en A1.

## 2. Los 17 parches
Comparados por contenido (`git patch-id`) contra los commits:
- **Todos los parches están en `multiprograma-spa`.** 0002, 0003, 0005, 0006, 0008 a 0012, 0013b, 0014, 0015 y 0016 coinciden exacto. 0004, 0007 y 0017 tienen otra huella (el commit se ajustó al aplicarlo), pero su contenido está en la rama (`cc6d02c`, `b4caf6d`, `413292e`). 0013 fue reemplazado por 0013b.
- La rama tiene además 2 commits sin parche: `6c9593e` (zócalo más bajo) y `291bcf4` (limpieza automática de la cola, quedan 2 capítulos).
- **En `main` solo están 0007 (app SPA) y 0016 (Ya lo publiqué).**
- Conclusión: `parches-herramienta` ya no aporta nada que no esté en la rama. Sirve como historial; se puede archivar en A5.

## 3. La "migración de SPA del otro chat"
Era el chat del plan de unificación (terminado). No dejó cambios de código. El procesamiento real de SPA sigue a mano desde `spa-herramienta` con `PROGRAMA=spa` (ver memoria `herramienta-spa-flujo`).

## 4. Hardlinks
Revisados todos los archivos de `C:\Audiovisual\la-herramienta` (sin `node_modules` ni `.git`): **0 hardlinks.** `config.py` y `.env` de producción y SPA tienen un solo nombre cada uno. Las rutas viejas no apuntan a los mismos archivos.

## 5. Qué ya es configurable (en la rama SPA)
`config.py` lee `PROGRAMA` (env, default `rayando`) y carga `programas/<slug>.json` + `.env.<slug>` (existe `.env.spa`). Para Rayando no hay JSON: usa los valores por defecto del código. Ya configurable por programa:

| Tema | Recda (default) | SPA (`spa.json`) |
|---|---|---|
| Carpeta base | `C:\Audiovisual\rayando-el-cda` | `C:\Audiovisual\siempre-pasa-algo` |
| Nombre, contexto Whisper, diccionario | Rayando | propios |
| Prompt de detección / contexto copys | en el código | `spa/prompt_deteccion.md`, `spa/contexto_copys.md` |
| Detección | una llamada al programa entero | ventanas de 10 min, 4 por ventana, pool 12 |
| Topes de clips | por defecto | mín 4, máx 7, duración mín 15 s |
| Vertical | `blur` | `split` + `spa/layout.json` (zócalo, pistas de audio, marcos neón) |
| Logo / cierre vertical | logo Recda + cierre | `logo_spa.png` arriba a la derecha, sin cierre |
| Portadas | colores Recda | colores synthwave, marca "SIEMPRE PASA ALGO" |
| Hashtags y título YouTube | Recda | `#SiemprePasaAlgo`… / "SPAreírse - candidato…" |
| Supabase | schema `rayando_cda`, buckets `clips-video`, `portadas` | `siempre_pasa_algo`, `clips-video-spa`, `portadas-spa` |
| `clip_overrides` | `clip_overrides.json` | `spa/clip_overrides.json` |
| Subir a YouTube para revisar | sí | no (`SUBIR_YOUTUBE=false`, video desde Storage) |
| Publicación automática | sí | no |
| Limpieza de la cola | por estado (`auto_procesar.ps1`) | mantener 2 capítulos |
| App (`programa.js`, en `main`) | `puedePublicar`, limpieza, guía | sin publicar, sin limpieza, sin guía |

## 6. Qué falta volver configurable (trabajo de A1 a A4)
- **Recda sin perfil propio:** crear `programas/recda.json` para que los dos programas sean iguales (hoy Recda vive en los valores por defecto).
- **Tarea programada:** `auto_procesar.ps1` solo procesa Recda (no lee `PROGRAMA`) y es la que corre `reprocesar_video` y `reprocesar_subtitulos`. Para SPA no hay tarea: correcciones y títulos se aplican a mano.
- **Capítulos:** `capitulos.py` usa fijo `rayando_cda.capitulos` y el hashtag `#RECDA<N>`. SPA necesita su tabla (o columna programa) y su hashtag.
- **Publicación:** la Edge Function `publicar-clip` está atada a Recda (credenciales y `rayando_cda.tiktok_token`). Falta una por programa o una que reciba el programa (A2).
- **Credenciales SPA:** no hay `youtube_token_spa.json` ni tokens de IG/TikTok/Facebook de SPA. Pendiente que Samuel agregue a Seba como administrador del YouTube de SPA (A2). TikTok: el estado de aprobación está en `docs/tiktok-direct-post-estado.md` (última actualización 21 sep; revisar en A2).
- **App:** sigue siendo `?p=spa` y la pestaña dice "Rayando el CDA". Falta `/spa` y `/recda` con su marca (A3).
- **Rutas viejas:** los `metadata.json` de clips SPA anteriores al 30 oct apuntan a `C:\Siempre pasa Algo\...` (3 ya corregidos en el cap. 5). Conviene un script único que los corrija todos en A1.
- **Espacio Supabase:** plan gratis de 1 GB compartido; SPA ocupa ~240 MB por capítulo. Revisar antes de sumar el nivel 2 del embudo (videos horizontales).

## 7. Recomendación para A1
Fusionar `main` en `multiprograma-spa` dentro de `rayando-cda-dev` (no en producción), resolver los 7 conflictos, agregar `recda.json` y correr los tests de los dos programas. Recién con eso validado, la fusión a `main` fuera de la ventana lun 23:00 – mié 10:00. Validar este diseño en un chat nuevo con Fable antes de escribir código, como dice el plan.
