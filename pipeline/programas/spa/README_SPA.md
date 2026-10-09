# La Herramienta para SPAreírse — estado y uso

Última actualización: 09/10/2026 (capítulo 2, 2026-10-08).

## Qué hace hoy
Toma la grabación de OBS del capítulo, detecta los mejores momentos (prompt propio: humor > cahuines > lado B), corta 12 candidatos en vertical y los sube a la app de revisión. Samuel y Cristián eligen hasta 7.

- **Rama:** `multiprograma-spa`, en el worktree `C:\Users\sebap\spa-herramienta`. No está fusionada en `main`; `main` es lo que procesa Rayando.
- **Configuración:** `programas/spa.json`, más la carpeta `programas/spa/` con el prompt, los copys, el diccionario, `layout.json`, los fondos y `clip_overrides.json`.
- **Grabaciones y clips:** `C:\Siempre pasa Algo\Grabaciones` y `C:\Siempre pasa Algo\clips\<fecha>\candidato-NN\`. Ojo: estas rutas cambian con el traslado a `C:\Audiovisual` del 14/10, y hay que actualizar `base_dir` en `spa.json`.
- **Supabase:** proyecto "La Herramienta Rayando el CDA" (org Sebapino25), schema `siempre_pasa_algo`, buckets `clips-video-spa` y `portadas-spa`.
- **YouTube:** no se usa (`SUBIR_YOUTUBE=False`). La app reproduce el video desde Storage.
- **App de revisión:** https://sebapino25.github.io/rayando-cda-review/?p=spa. Es la misma app de Rayando, con su schema, buckets y logo propios, y sin "Publicar en redes".

## Formato vertical (`layout.json`)
- **Contenido presente:** el contenido va arriba y la cámara del que habla, abajo. El cambio de cámara se decide por el volumen de cada pista.
- **Pistas de audio:** pista 2 = Samuel (cámara izquierda, marco celeste) y pista 3 = Cristián (cámara derecha, marco rosado).
- **Sin contenido** (escena Conversación): Samuel arriba y Cristián abajo, con marco de neón en el que habla.
- **Subtítulos:** justo bajo la línea celeste, para que no tapen la cara.
- **Zócalo de la mesa:** se detecta por la barra amarilla y se pone entero al pie del contenido.
- **Logo:** cuando hay contenido no se agrega, porque el video de la mesa ya trae la marca de agua.
- **Escena:** se detecta por el marcador de 24x24 en (0,1056). No hay que taparlo en OBS.
- **Título sobre el video:** solo aparece con contenido horizontal, porque con contenido vertical no queda espacio.

## Flujo por capítulo (en `pipeline\`, con `$env:PROGRAMA="spa"`)
1. Transcribir: `python transcribir.py "<grabación>"`.
2. Detectar: `python detectar_momentos.py "<grabación>" --detalle`. Guardar la lista en `clips\<fecha>\candidatos_<fecha>.json`, porque la detección no da siempre lo mismo.
3. Probar (opcional): `python cortar_clip.py "<grabación>" <ini> <fin> prueba --sin-publicar`. Después sacar la carpeta de prueba de `clips\<fecha>`.
4. Cortar y subir: `python procesar_programa.py "<grabación>"`. Debe decir "Usando lista de candidatos ya confirmada".
5. Rehacer si cambia el diseño: `python rehacer_vertical.py <fecha> [candidato-NN ...]`. Vuelve a mirar la grabación, reemplaza el video en Storage y no duplica filas.
6. Diagnóstico de un tramo: `python layout_split.py "<grabación>" <ini> <fin> --frame salida.png`.

## Diferencias con Rayando (avisadas a Cristián)
- **Subtítulos:** corregirlos en la transcripción bloquea "Aprobar", porque el reproceso automático no corre para SPA. Hay que anotarlo en "Comentarios sobre el video".
- **Corrección técnica:** el botón queda esperando, porque no hay proceso automático para SPA.
- **Publicación:** no hay "Publicar en redes". Los aprobados se descargan y se suben a mano.

## Pendientes
1. **Link propio:** un link para SPA o uno genérico "La Herramienta" que derive a los dos programas. Hoy es el de Rayando con `?p=spa`, y la pestaña del navegador dice "Rayando el CDA".
2. **Feedback del capítulo 2:** juntar lo que elijan y rechacen Samuel y Cristián, y con eso ajustar el prompt de detección.
3. **Espacio en Supabase** (plan gratis, 1 GB compartido con Rayando; unos 240 MB por capítulo): programar `limpiar_clips.py` para SPA o pasar a un plan pagado antes del capítulo 4.
4. **YouTube de SPA:** que Samuel agregue a Seba como administrador, generar `youtube_token_spa.json` y activar `SUBIR_YOUTUBE`.
5. **Correcciones automáticas en SPA:** reprocesar subtítulos y video con una tarea programada propia.
6. **Publicación a redes de SPA:** Edge Function por programa y tokens de IG y TikTok.
7. **Rutas tras el traslado del 14/10:** actualizar `base_dir` en `spa.json` y repetir el diagnóstico.
8. **Detalles visuales:** el zócalo de la mesa es semitransparente y asoma la pelota del fondo (se arregla dejándolo opaco en la mesa). Falta definir dónde va el título cuando el contenido es vertical.
9. **Fusionar con `main`:** cuando todo esté validado. Hasta entonces, el commit de la app (`263a038`) está duplicado entre las ramas `main` y `multiprograma-spa`, pero los cambios son idénticos.

## Parches aplicados en multiprograma-spa
| Parche | Contenido |
|---|---|
| 0001 | Multiprograma |
| 0002 / 0003 | Detección por ventanas |
| 0004 | Formato dividido |
| 0005 | `--sin-publicar` |
| 0006 | Sin YouTube |
| 0007 | App con `?p=spa` (también en `main`, commit `263a038`) |
| 0008 | `clip_overrides` propio y nombres de los conductores |
| 0009 | Subtítulos y `rehacer_vertical` |
| 0010 | Zócalo y logo |
| 0011 | Este README |
