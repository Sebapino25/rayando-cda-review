# Publicación final desde la app (subsistema 1 de 4)

Fecha: 2026-07-27
Estado: aprobado por el usuario, listo para plan de implementación

## Contexto

Rayando el CDA ya tiene un pipeline que detecta momentos, corta clips, genera
subtítulos/portadas/copys y los sube a YouTube como no listado + Supabase para
revisión editorial (`pipeline/procesar_programa.py`). También existe
`pipeline/publicar_automatico.py`, que sabe pasar un video a público en
YouTube y publicar el Reel en Instagram — pero es un script Python que corre
a mano en la PC local del dueño del proyecto, con flags apagados por defecto
(`AUTO_PUBLICAR_YOUTUBE` / `AUTO_PUBLICAR_INSTAGRAM = False`), y no está
enchufado a ningún disparador.

El dueño del proyecto va a dejar de dedicarle tiempo activo a partir de esta
semana. El objetivo de este subsistema es que el único paso manual que quede
en todo el ciclo sea **su aprobación final** — un click en la app, desde
cualquier dispositivo, sin depender de que su PC esté prendida ni de correr
scripts a mano.

Este es el primero de 4 subsistemas identificados en la auditoría completa
del proyecto (ver conversación de origen):
1. **Este documento** — publicación final desde la app.
2. Disparador automático semanal del pipeline (Task Scheduler local) — pendiente.
3. Limpieza de documentación desactualizada (README/CAMBIOS/SQL migration
   fuera de sync con el código real) — pendiente, tarea liviana sin diseño propio.
4. Estrategia de difusión/crecimiento de seguidores + monetización (incluye
   contenido ya trabajado por el usuario en otra conversación de Claude,
   pendiente de que lo comparta) — pendiente, no es un subsistema técnico.

## Objetivo

El equipo revisa, edita y aprueba/pide corrección/rechaza clips en la
pestaña "Pendientes" de la app (flujo existente, sin cambios). Los clips
aprobados aparecen en "Historial". Desde ahí, el dueño del proyecto —y solo
él— puede dar la aprobación final que dispara la publicación real: YouTube
pasa de no listado a público, y se publica el Reel en Instagram. TikTok se
integra en el mismo mecanismo pero queda apagado hasta que la app de TikTok
Developers sea aprobada (hoy ni siquiera fue enviada a revisión).

## No-objetivos

- No se automatiza el disparo de `transcribir.py`/`procesar_programa.py`
  (eso es el subsistema 2).
- No se implementa un sistema de login completo (Supabase Auth) — se usa un
  PIN validado del lado servidor, decisión explícita del usuario para no
  sumar ese trabajo esta semana.
- No se automatiza el refresco del token de Instagram (vence cada ~60 días)
  — en cambio, se avisa por email antes de que venza, para que el usuario lo
  renueve a mano cuando corresponda.
- No se publica realmente a TikTok todavía — el código queda listo pero
  detrás de un flag apagado, igual que YouTube/Instagram lo estuvieron hasta
  ahora.

## Arquitectura

```
cortar_clip.py → publicar.py:
  sube a YouTube (no listado)
  sube vertical.mp4 a Supabase Storage (bucket clips-video)   ← NUEVO, movido
    acá desde publicar_automatico.py (antes se subía recién al
    publicar; ahora se sube apenas el archivo existe localmente,
    porque la Edge Function que publica después no tiene acceso
    al disco del usuario)
  inserta en Supabase: video_url (NUEVO), youtube_video_id, estado='pendiente',
    publicado=false
        │
        ▼
App (React, GitHub Pages) — pestaña "Pendientes":
  equipo revisa, edita copys/transcripción, aprueba / pide corrección /
  rechaza (flujo existente sin cambios)
        │  estado='aprobado'
        ▼
App — pestaña "Historial":
  clips con estado='aprobado' AND publicado=false muestran botón
  "Publicar en redes" (NUEVO)
        │  click → modal de confirmación (NUEVO): muestra plataformas
        │  habilitadas, título de YouTube y copy de Instagram tal como van
        │  a publicarse — última instancia humana antes de algo público
        │  e irreversible
        │  confirmar + PIN
        ▼
Supabase Edge Function `publicar-clip` (NUEVO, TypeScript/Deno):
  1. valida PIN contra secreto de la función (PUBLISH_PIN); un intento
     fallido no cuenta contra el estado del clip pero sí queda registrado
     (ver "Manejo de errores" — límite de intentos y alerta)
  2. lee la fila del clip (service role)
  3. valida estado='aprobado' AND publicado=false (defensa server-side,
     no confía solo en que la UI ya filtró)
  4. por cada plataforma con su flag habilitado — la Edge Function tiene sus
     propios flags como secretos de Supabase (`PUBLICAR_YOUTUBE` /
     `PUBLICAR_INSTAGRAM` / `PUBLICAR_TIKTOK`; no lee `pipeline/config.py`,
     que es un archivo local y no está desplegado en Supabase). YouTube e
     Instagram quedan en `true` desde el arranque de este subsistema, porque
     ya no hay una corrida automática sin supervisión que temer: la
     publicación real solo ocurre si alguien apretó el botón + puso el PIN.
     TikTok queda en `false` hasta que la app sea aprobada:
     - YouTube: PATCH del video (privacyStatus=public, title, description)
       usando un refresh token de larga duración guardado como secreto
       de la función (ya no depende de youtube_token.json local)
     - Instagram: crea contenedor REELS con video_url + portada_url
       (cover_url), espera a que termine de procesar, publica, guarda
       instagram_media_id
     - TikTok: mismo patrón (Content Posting API, PULL_FROM_URL con
       video_url) pero solo se ejecuta si AUTO_PUBLICAR_TIKTOK=true
  5. si todas las plataformas habilitadas terminan bien: publicado=true,
     publicado_en=now()
  6. si alguna falla: publicado sigue false (reintentable con otro click),
     se envía un email de alerta (Resend) con el detalle
```

Adicionalmente, una segunda Edge Function programada (`revisar-token-instagram`,
cron semanal vía Supabase scheduled functions) chequea si el token de
Instagram vence dentro de los próximos ~10 días y, si es así, envía un email
de aviso con el link para renovarlo manualmente.

## Verificación previa requerida (antes de implementar)

- **Publishing status del proyecto de Google Cloud (OAuth de YouTube).** Si
  el proyecto sigue en modo "Testing" (no verificado/publicado) en Google
  Cloud Console > OAuth consent screen, el refresh token vence solo a los 7
  días — mucho antes que el problema ya conocido de Instagram (60 días). Hay
  que chequear el "Publishing status" antes de asumir que el refresh token
  de YouTube es estable sin supervisión. Si está en Testing, pasarlo a
  producción (o, si no es viable esta semana, agregar YouTube al mismo aviso
  semanal de vencimiento de token que ya se construye para Instagram).

## Componentes nuevos/modificados

| Componente | Cambio |
|---|---|
| `pipeline/publicar.py` | suma la subida de `vertical.mp4` a Supabase Storage (lógica movida desde `publicar_automatico.py`) y guarda `video_url` al insertar |
| `pipeline/supabase_migration_clips.sql` | agrega columna `video_url text`; **además** se corrige para reflejar el schema real (`portada_url`, `instagram_media_id` ya existen en la tabla real pero no estaban en este archivo — drift a corregir) |
| `supabase/functions/publicar-clip/` | nuevo, Edge Function que hace la publicación real |
| `supabase/functions/revisar-token-instagram/` | nuevo, Edge Function programada de aviso de vencimiento |
| `app/src/components/HistoryCard.jsx` | botón "Publicar en redes" (visible en clips aprobados no publicados) + modal de confirmación (resumen de qué se va a publicar y dónde) + prompt de PIN + estados de carga/error |
| Secretos de la Edge Function (Supabase) | `PUBLICAR_YOUTUBE=true`, `PUBLICAR_INSTAGRAM=true`, `PUBLICAR_TIKTOK=false`, `PUBLISH_PIN`, credenciales de YouTube/Instagram/TikTok, `RESEND_API_KEY`, email destino |
| `pipeline/config.py` | sin cambios en los flags `AUTO_PUBLICAR_*` (siguen gobernando solo el fallback manual `publicar_automatico.py`, en False por defecto) |
| `pipeline/publicar_automatico.py` | pasa a ser fallback manual documentado, ya no el camino principal; se documenta ese cambio de rol |

## Manejo de errores

- **Falla parcial por plataforma**: cada plataforma es independiente; el
  fallo de una no reintenta las que ya salieron bien (mismo chequeo de
  idempotencia ya existente: `instagram_media_id` seteado = no volver a
  publicar ahí). El clip queda `publicado=false` y reintentable.
- **PIN incorrecto**: la función devuelve 401, la app muestra el error
  inline, no se toca la fila. La Edge Function queda expuesta como endpoint
  público en internet, protegida solo por el PIN — se agrega un límite de
  intentos fallidos por ventana de tiempo (ej. 5 intentos / 10 minutos,
  usando una tabla simple en Supabase para contarlos) y un email de alerta
  si se supera, para tener visibilidad de intentos de fuerza bruta.
- **`video_url` ausente**: puede pasar en clips que quedaron `aprobado`/
  `publicado=false` de antes de este cambio (no tenían `video_url` porque
  recién se empieza a llenar con este subsistema). La función corta con un
  error explícito ("falta video_url — re-procesar el clip o subir el video a
  Storage a mano") en vez de fallar con un error críptico de la API de
  Instagram.
- **Edge Function inalcanzable / error de red**: la app muestra el error,
  ningún estado cambia en Supabase — reintentable.
- **Cualquier falla de publicación**: dispara email de alerta con el detalle
  del error (mismo mecanismo/servicio, Resend, usado por el aviso de
  vencimiento de token).
- **Token de Instagram vencido**: se distingue explícitamente en el mensaje
  de error (vs. un fallo transitorio de red) para que el email sea accionable.

## Testing

1. **Dry-run de la Edge Function** invocada directo (no desde la UI) contra
   el clip fixture (`estado='prueba'`, ver protocolo de aislamiento de datos
   de prueba ya documentado en `app/README.md`) para validar la lógica sin
   publicar nada real.
2. **Verificación real única**, hecha a mano por el usuario: marcar el
   fixture como `aprobado`/`publicado=false`, usar el botón real desde la
   app, confirmar que publicó donde correspondía, y devolver el fixture a
   `estado='prueba'` al terminar. No se automatiza en CI porque implica
   tocar cuentas reales de redes sociales.

## Decisiones explícitas (para no reabrir la discusión después)

- Edge Function (Supabase) en vez de un servicio Python aparte: sin
  infraestructura nueva que mantener, funciona sin depender de la PC local.
- PIN simple en vez de Supabase Auth: proporcional al alcance (un solo
  publicador) y al tiempo disponible.
- Botón visible a cualquier revisor en la UI, pero el PIN es lo que
  realmente restringe quién puede publicar — no se oculta el botón por
  nombre de revisor porque hoy no hay autenticación real de "quién es quién"
  en la app.
- Publicación es "todo lo habilitado a la vez" por clip, no hay selección
  de plataformas por clip individual — mismo modelo mental que los flags
  `AUTO_PUBLICAR_*` ya existentes.
- TikTok se construye pero no se activa esta semana: la app de TikTok
  Developers ni siquiera fue enviada a revisión (el formulario quedó en
  Draft al perderse los datos al pasar de Sandbox a Production).
- **Expectativa honesta sobre TikTok**: se construye contra la documentación
  actual de la Content Posting API sin poder probarlo en producción (la app
  no está aprobada). Es probable que cuando se apruebe — probablemente
  semanas después, sin el dueño del proyecto activo — haga falta un ajuste
  antes de que funcione de verdad. No se promete "activar y listo".
