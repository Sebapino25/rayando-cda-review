# Cambios aplicados — corregir los gaps de UX que rechazaron la auditoría de TikTok Direct Post (09/09)

La auditoría de Direct Post enviada el 30/08 fue rechazada el 08/09 (ref
`20260831034842`). El motivo específico no está en el mail — se encontró
en el tooltip del botón "Reapply" de `developers.tiktok.com` → app → Content
Posting API → Direct Post: cita los puntos 1 y 5 de "Required UX
Implementation in Your App" (Content Sharing Guidelines) y agrega "the ending
must show that had been post under TikTok". Comparando los sub-incisos contra
el código, había gaps reales de implementación, no solo de la demo grabada.
Detalle completo en `docs/tiktok-direct-post-estado.md`.

- **`supabase/functions/publicar-clip/tiktok.ts`**: `publicarTiktok` ahora
  recibe `videoDurationSec` y lanza error si excede `max_video_post_duration_sec`
  de `creator_info`, antes de descargar o subir nada (punto 1c — antes el dato
  se pedía pero nunca se comparaba). El `init` reconoce los códigos de error
  de límite de posteo (`spam_risk_too_many_posts`,
  `spam_risk_too_many_pending_share`, `rate_limit_exceeded`) y da un mensaje
  de "reintentá más tarde" en vez de un error genérico (punto 1b). Nueva
  `consultarEstadoPublicacion` (`POST /v2/post/publish/status/fetch/`) para
  monitorear el estado real del post (punto 5e — antes el código asumía éxito
  apenas terminaba la subida, sin confirmar que TikTok lo haya procesado).
- **`supabase/functions/publicar-clip/index.ts`**: calcula la duración real
  del clip (`timestamp_fin - timestamp_inicio`, ya en la tabla `clips`) y se
  la pasa a `publicarTiktok`; si algún clip viejo no tuviera esos timestamps
  (daría `NaN`), corta con un error explícito en vez de saltear el chequeo de
  duración en silencio. Nueva acción `tiktok_publish_status` (sin PIN, solo
  lectura) que usa la app para hacer polling del estado.
- **`app/src/components/TikTokPublishPanel.jsx`**: muestra el `<video>` del
  clip antes de publicar (punto 5a — antes no había preview de qué se iba a
  postear). Si la duración excede el máximo de la cuenta, avisa y saltea
  TikTok automáticamente (publica igual en YouTube/Instagram) en vez de
  bloquear todo. Agrega el texto "TikTok puede tardar unos minutos en
  procesar..." (punto 5d).
- **`app/src/components/TikTokStatusBadge.jsx`** (nuevo): hace polling de
  `tiktok_publish_status` cada 5s (hasta 10 min) y muestra "procesando" /
  "publicado" / "falló (motivo)" en la tarjeta del clip publicado — es lo que
  responde a "the ending must show that had been post under TikTok". Un error
  de red o de la Edge Function al consultar no corta el polling: se muestra
  el error pero se sigue reintentando hasta los 10 min o hasta que se
  recupere.
- **`tiktok_test.ts`** (+8 casos): duración excedida, duración justo en el
  límite, mensaje de "reintentá más tarde" ante los códigos de límite, y 3
  tests de `consultarEstadoPublicacion`.

No cambia nada del comportamiento normal para YouTube/Instagram, ni la lógica
de privacidad/permisos de TikTok ya validada en el rechazo anterior.

**Pendiente de Seba:**
- Correr `deno test --allow-net supabase/functions/publicar-clip/` — este
  entorno no tiene `deno` instalado, el código se revisó a mano pero no se
  corrió localmente.
- `npm run lint` y `npm run build` en `app/` ya se corrieron limpios acá.
- Deployar `publicar-clip`, regrabar el tramo 2 de la demo (con preview) +
  grabar un tramo nuevo del badge de estado, y reenviar con "Reapply" —
  checklist completo en `docs/tiktok-direct-post-estado.md`.
