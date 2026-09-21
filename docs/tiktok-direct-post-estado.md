# TikTok Direct Post — estado y pasos pendientes

_Última actualización: 21/09/2026._

Contexto completo: sección `## TikTok` de [`pipeline/README.md`](../pipeline/README.md).
Plan de implementación: `~/.claude/plans/stateful-wiggling-kay.md`.

## Sesión 21/09/2026 — hallazgo real: el frontend nunca se había desplegado

Se intentó regrabar la demo (tramos 2, 3 y 4) para reenviar. Hallazgos y avances reales:

- **El fix del 09/09 (commit `4fdf389`) nunca llegó a producción.** Estaba commiteado en
  local pero nunca se hizo `git push` — quedaron 2 commits (`4fdf389` +
  `f652b67`) sin subir a `origin/main`. Como el workflow de GitHub Pages
  (`.github/workflows/deploy.yml`) solo corre sobre push real, el sitio en
  `sebapino25.github.io/rayando-cda-review/` seguía sirviendo el build del
  28/08 — sin preview de video, sin aviso de "puede tardar unos minutos", sin
  `TikTokStatusBadge`. Se hizo `git push` (17:33) y el deploy corrió y terminó
  ok (confirmado con `gh run list`) — **el frontend corregido recién quedó
  público hoy, no el 09/09.**
- **Token de Instagram vencido, renovado.** A mitad de una prueba de
  publicación real, el token de `rayando_cda.instagram_token` falló ("se
  acabó la API"). Se generó uno nuevo desde `developers.facebook.com` → app
  **"Rayando el CDA"** (no confundir con la app nueva de Agencia del Barrio)
  → Casos de uso → API de Instagram → **"Configuración de la API con inicio
  de sesión de Instagram"** (⚠️ no la de "...con Facebook") → sección
  "Generar tokens de acceso" → cuenta `rayandoelcda` (ID
  `17841472353468522`) → botón "Generar token" (abre un popup fuera del
  navegador controlado, el login lo hace Seba a mano). Token verificado con
  `curl https://graph.instagram.com/me?fields=user_id,username&access_token=...`
  antes de guardarlo con `update rayando_cda.instagram_token set
  access_token=..., vence_en=now()+interval '60 days'`. Vence 20/11/2026.
- **2 publicaciones reales de prueba** (privadas en TikTok, **públicas e
  irreversibles en YouTube/Instagram**): clip "La doble vara con Bielsa que
  nadie se atreve a decir" (con el frontend viejo, antes del deploy — no
  sirve como evidencia del fix) y clip "Dónde vieron el título: cada uno
  tiene su historia" (con el frontend corregido ya desplegado — este sí
  mostró el preview del video, el aviso de procesamiento, y el
  `TikTokStatusBadge` pasando a "TikTok: publicado". **Este es el que había
  que grabar.**)
- **La grabación de la toma buena se perdió.** Xbox Game Bar (`Win`+`Alt`+`R`)
  grabó la ventana que tenía el foco en ese momento — que era la terminal de
  Claude Code, no Chrome — dos veces seguidas (intento con el clip "La doble
  vara" antes del fix de Instagram, y el intento bueno con el clip "Dónde
  vieron el título" después del deploy). Las únicas grabaciones de navegador
  reales que quedaron son: una del clip "La doble vara" ya publicado pero
  **con el panel viejo** (no sirve, no muestra preview/aviso/badge), y el
  tramo 3 (resultado en el perfil, ese sí generico y reutilizable). **Antes
  de regrabar: confirmar con un clic en la ventana de Chrome que Game Bar
  está capturando el navegador, no el terminal.**
- `PUBLICAR_TIKTOK` quedó de vuelta en `false` al cerrar la sesión (kill-switch
  seguro, como siempre entre pruebas).
- **Pendiente real, pospuesto a mañana:** regrabar tramos 2 y 4 (el panel
  corregido + el badge de estado) con un clip nuevo — el clip "Dónde vieron
  el título" ya quedó público en YouTube/Instagram esta sesión, no se puede
  reusar para una demo "antes de publicar". Tramos 1 y 3 pueden reusarse tal
  cual (1: el del 17/08 ya guardado; 3: el de hoy, genérico).

## Objetivo

Retomar la **publicación automática a TikTok**. Hoy los clips se suben a mano
(botones "Descargar clip" / "Descargar portada" en la app). El bloqueo es la
**auditoría de Direct Post de TikTok**, que revisa la UX de publicación de la
app.

## Rechazo del 08/09/2026 (referencia `20260831034842`) — causa y corrección

La auditoría enviada el 30/08 (ver más abajo) fue rechazada. El texto de
TikTok (visible en `developers.tiktok.com` → Notifications, y en el tooltip
del botón "Reapply" de la fila Direct Post) es genérico:

> Your application did not follow our UX Guidelines. Please refer to point
> No. 1 & 5 under 'Required UX Implementation in Your App' in the Content
> Sharing Guidelines. The ending must show that had been post under TikTok.

Comparando esos dos puntos (con sus sub-incisos a–e) contra el código, había
**gaps reales de implementación**, no solo de la demo grabada:

| Punto | Requisito | Estado antes del 09/09 |
|---|---|---|
| 1a | Mostrar nickname/username del creador | ✅ ya cumplía |
| 1b | Si `creator_info`/el intento de post indica que se llegó al límite de posteo, cancelar y avisar "reintentá más tarde" | ❌ sin manejo |
| 1c | Validar la duración del clip contra `max_video_post_duration_sec` antes de postear | ❌ el dato se pedía pero nunca se comparaba |
| 5a | Preview de qué se va a publicar | ❌ el panel no mostraba el video |
| 5b | Sin marca de agua propia, texto editable | ✅ ya cumplía |
| 5c | Consentimiento explícito antes de subir | ✅ ya cumplía (PIN + botón) |
| 5d | Avisar que el procesamiento puede tardar varios minutos | ❌ sin ese texto |
| 5e | Usar `publish/status/fetch` para monitorear el estado real del post | ❌ el código asumía éxito apenas terminaba la subida |

**Corregido el 09/09/2026:**

| Archivo | Cambio |
|---|---|
| `supabase/functions/publicar-clip/tiktok.ts` | `publicarTiktok` ahora recibe `videoDurationSec` y lanza error si excede `max_video_post_duration_sec` de `creator_info` (1c), antes de descargar/subir nada. El `init` reconoce los códigos de error de límite de posteo (`spam_risk_too_many_posts`, `spam_risk_too_many_pending_share`, `rate_limit_exceeded`) y da un mensaje de "reintentá más tarde" en vez de un error genérico (1b). Nueva `consultarEstadoPublicacion` que llama `POST /v2/post/publish/status/fetch/` (5e). |
| `supabase/functions/publicar-clip/index.ts` | Calcula la duración real del clip (`timestamp_fin - timestamp_inicio`) y se la pasa a `publicarTiktok`. Nueva acción `tiktok_publish_status` (sin PIN, solo lectura) que la app usa para hacer polling del estado. |
| `app/src/components/TikTokPublishPanel.jsx` | Muestra el `<video>` del clip antes de publicar (5a). Si la duración excede el máximo de la cuenta, avisa y saltea TikTok automáticamente (publica igual en YouTube/Instagram) en vez de bloquear todo. Agrega el texto "TikTok puede tardar unos minutos en procesar..." (5d). |
| `app/src/components/TikTokStatusBadge.jsx` | **Nuevo.** Hace polling de `tiktok_publish_status` cada 5s (hasta 10 min) y muestra "procesando" / "publicado" / "falló (motivo)" en la tarjeta del clip publicado (5e). |

Tests nuevos en `tiktok_test.ts`: duración excedida, duración justo en el
límite (no lanza), mensaje de "reintentá más tarde" ante los códigos de
límite, y 3 tests de `consultarEstadoPublicacion`. **No se pudo correr `deno
test` en el entorno donde se escribió esto** (no hay `deno` instalado) —
correrlo antes de deployar.

**Pendiente para reenviar (actualizado 21/09/2026):**
1. ~~Deployar `publicar-clip`~~ — ✅ hecho, v31 en producción (confirmado).
   ~~Deployar el frontend~~ — ✅ hecho recién hoy (ver sesión 21/09 arriba;
   antes de hoy seguía corriendo el build del 28/08 pese a estar commiteado
   desde el 09/09).
2. **Regrabar el tramo 2 y el tramo 4** (flujo + badge de estado) — el panel
   corregido ya está confirmado funcionando en producción (probado en vivo
   hoy con el clip "Dónde vieron el título"), pero la grabación se perdió
   (Game Bar capturó el terminal). Repetir con OTRO clip nuevo, confirmando
   antes que la grabación apunta a la ventana de Chrome.
3. Tramos 1 (OAuth, del 17/08) y 3 (resultado en el perfil, grabado hoy)
   están listos, no hace falta regrabarlos.
4. Reenviar con "Reapply" (mismo wizard que "Apply", ver paso 5 más abajo).

## Qué se hizo el 28/08/2026 (commit `422cfc2`)

Se construyó la pantalla de publicación a TikTok que exigen las Content Sharing
Guidelines. Sin esto la auditoría se rechaza.

| Archivo | Cambio |
|---|---|
| `app/src/components/TikTokPublishPanel.jsx` | **Nuevo.** Panel inline que se despliega al tocar "Publicar en redes": cuenta de destino, caption editable, selector de privacidad **sin valor por defecto** (opciones de `creator_info` en vivo), toggles comentarios/dúo/stitch (off por defecto, deshabilitados si la cuenta los restringe), toggle "divulgar contenido comercial" + checkboxes "tu marca" / "contenido de marca", texto de cumplimiento con enlaces a Music Usage Confirmation / Branded Content Policy. Botón bloqueado hasta elegir privacidad. |
| `supabase/functions/publicar-clip/index.ts` | Branch `action: 'tiktok_creator_info'` (sin PIN, no reclama fila) para alimentar el panel. El body acepta `tiktok` con las elecciones del usuario. TikTok pasa a **opt-in por clip**: solo se publica si `PUBLICAR_TIKTOK=true` **y** hay config de TikTok en el body; sin config se saltea en silencio (sin error ni mail). Gate por secret `TIKTOK_AUDITORIA_APROBADA`. |
| `supabase/functions/publicar-clip/tiktok.ts` | `publicarTiktok` nueva firma `(videoUrl, config, opciones, fetch)`. Valida server-side lo que manda el cliente: privacidad ∈ opciones de `creator_info`, no `PUBLIC_TO_EVERYONE` sin auditoría, respeta `comment/duet/stitch_disabled` de la cuenta, contenido de marca no puede ser privado. Nueva `obtenerCreatorInfoParaUI` que filtra `PUBLIC_TO_EVERYONE` mientras no haya auditoría. **Se eliminó la constante `AUDITORIA_APROBADA`** — ahora el gate es el secret. |
| `app/src/components/HistoryCard.jsx` | "Publicar en redes" despliega un panel inline (resumen YT/IG + `TikTokPublishPanel` + input de PIN) en vez de `window.confirm` / `window.prompt`. |
| `app/src/App.jsx` | `handlePublicar(id, { pin, tiktok })`. |

Verificación al momento del commit: `deno test supabase/functions/publicar-clip/`
→ 27/27; `npm run lint` + `npm run build` → limpios; `deno check` → sin errores.

## Estado (30/08/2026) — AUDITORÍA ENVIADA

| Cosa | Estado |
|---|---|
| Frontend (GitHub Pages) | ✅ **deployado** (commit `422cfc2`, workflow en verde) |
| Edge Function `publicar-clip` | ✅ **deployada con el código nuevo** (v24, 30/08/2026) |
| Secret `TIKTOK_AUDITORIA_APROBADA` | `false` (cargado 30/08) |
| Secret `PUBLICAR_TIKTOK` | ✅ de vuelta en `false` (30/08, verificado: `tiktok_creator_info` → `habilitado:false`) |
| Prueba end-to-end | ✅ OK — clip real publicado con `tiktok_publish_id` guardado |
| **Auditoría de Direct Post** | ✅ **ENVIADA el 30/08/2026** — respuesta en 2–4 semanas. Revisar estado en `developers.tiktok.com` → Manage apps |
| Cuenta @rayando.el.cda | ✅ de vuelta en pública (30/08) |
| Paso 5b (cerrar) | ✅ completo |

Formulario enviado: App ID `7666642864034072596`, 3 MP4 (OAuth 17/08 + flujo de
publicación + resultado en el perfil), org website
`https://www.tiktok.com/@rayando.el.cda`, cap de usuarios "Less than 100".

## Pasos pendientes

### 1. Deployar la Edge Function — ✅ HECHO (30/08/2026)

Se deployó v24 con:

```
SUPABASE_ACCESS_TOKEN="sbp_..." npx supabase functions deploy publicar-clip --project-ref qfxfwfcdgqcbmdspjvtk
```

(el `import_map` ya está en `supabase/config.toml`). El MCP de Supabase
(`deploy_edge_function`) queda bloqueado por el clasificador de permisos de
Claude Code — hay que usar el CLI con un legacy token de
https://supabase.com/dashboard/account/tokens, y **revocarlo después**.

### 2. Cargar los secrets

Supabase → Project Settings → Edge Functions → Secrets:

| Secret | Valor |
|---|---|
| `TIKTOK_AUDITORIA_APROBADA` | `false` |
| `PUBLICAR_TIKTOK` | `true` |

Se toman en la próxima invocación, sin redeploy.

### 3. Probar end-to-end — ✅ HECHO (30/08/2026)

Confirmado en vivo:
- `tiktok_creator_info` responde `habilitado: true`, `auditoria_aprobada: false`,
  carga la cuenta real (@rayando.el.cda), `privacy_level_options`
  `["MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]` (cuenta en privado).
- Panel en la app: `<select>` sin default, dúo/stitch deshabilitados con el
  texto "Deshabilitado en la configuración de la cuenta", texto de Music Usage
  Confirmation con link, botón "Publicar" bloqueado hasta elegir privacidad + PIN.
- Publicado un clip real con "Solo yo": quedó `publicado=true`,
  `tiktok_publish_id = v_pub_file~v2-1.7679852661344045074`, video visible en el
  perfil privado de TikTok.

### 4. Grabar las demos para la auditoría — ✅ HECHO (30/08/2026)

Se grabaron y subieron 3 MP4: OAuth (17/08), flujo de publicación en el panel,
y resultado en el perfil. Guía de grabación abajo, por si hay que regrabar tras
un rechazo.

**Antes de grabar:**
- Cuenta @rayando.el.cda **en privado** (ya está).
- Cerrar pestañas/ventanas con info personal. Grabar solo la ventana del navegador.
- Grabador: **Xbox Game Bar** (`Win`+`Alt`+`R`, graba la ventana activa, sale
  MP4 en `Vídeos\Capturas`) o la **Herramienta de Recortes** (`Win`+`Shift`+`S`
  → ícono de cámara de video, permite elegir región). Cursor visible, sin audio
  hace falta, texto legible (no achicar la ventana).
- Cada tramo, un archivo aparte. Sin cortes ni edición dentro de un tramo.

**Tramo 1 — OAuth / consentimiento (archivo `1-oauth.mp4`)**
Ya hay uno del 17/08. Regrabar solo si no se ve nítida la pantalla de permisos.
El OAuth de TikTok **no está en la app** — es el flujo manual de dos scripts
(`pipeline/tiktok_oauth_generar_url.py` + `..._intercambiar_codigo.py`). Para
regrabar solo el consentimiento:
1. `cd pipeline && python tiktok_oauth_generar_url.py` → imprime una URL de
   `https://www.tiktok.com/v2/auth/authorize/?...` con
   `scope=user.info.basic,video.publish,video.upload`.
2. En el navegador, ya logueado como @rayando.el.cda en tiktok.com, empezar a
   grabar y pegar esa URL.
3. Se abre la **pantalla de permisos de TikTok**: nombre de la app "Rayando el
   CDA" + los permisos pedidos. Click en **Authorize**.
4. Redirige a `sebapino25.github.io/.../tiktok-callback.html?code=...` que
   muestra el code. Cortar la grabación ahí.
5. **NO correr `tiktok_oauth_intercambiar_codigo.py`.** Sin el intercambio, el
   token vivo en `rayando_cda.tiktok_token` (el que hoy funciona) queda intacto.
   Re-autorizar en TikTok no revoca los tokens existentes; solo un intercambio
   nuevo los rota.
~30–60 s.

**Tramo 2 — flujo de publicación completo (archivo `2-flujo.mp4`)** — el más
importante, hacerlo **despacio**:
1. App abierta en la tab "Por publicar", con un clip aprobado a la vista.
2. Click en **"Publicar en redes"** → se despliega el panel.
3. Pausar ~2 s sobre el panel de TikTok: se ve la cuenta (@rayando.el.cda), la
   descripción/caption editable.
4. Mostrar el `<select>` **"¿Quién puede ver este video?"** en su estado inicial
   **"Elegí una opción"** (sin nada preseleccionado). Abrir el desplegable para
   que se vean las opciones, elegir **"Solo yo"** a mano.
5. Pasar despacio por **"Permisos de interacción"**: comentarios en OFF, Dúo y
   Stitch en OFF y **deshabilitados** con el texto "Deshabilitado en la
   configuración de la cuenta".
6. Mostrar el toggle **"Divulgar contenido comercial"** en OFF (tocarlo y
   destocarlo si se quiere mostrar que despliega los sub-checkboxes; dejarlo en
   OFF para publicar).
7. Mostrar el texto de cumplimiento con el **link "Confirmación de uso de
   música"** (pasar el mouse por encima, no hace falta clickear).
8. Escribir el PIN → el botón **"Publicar"** se habilita → click.
9. Esperar el resultado en pantalla (éxito / el clip pasa a "Publicados").
~90–120 s.

**Tramo 3 — resultado en TikTok (archivo `3-resultado.mp4`)**
Abrir el perfil de @rayando.el.cda en tiktok.com (o la app de TikTok en el
navegador) → mostrar el video recién publicado en la grilla del perfil →
abrirlo → que se vea que está publicado (aunque sea privado, se ve el post).
~20–40 s.

### 5. Enviar la auditoría — ✅ HECHO (30/08/2026)

Enviada. Referencia del wizard por si hay que reenviar tras un rechazo:
`developers.tiktok.com/app/7666642864034072596/live` → panel izquierdo
**Products** → sección **Content Posting API** → fila **Direct Post** → link
**Apply** (rojo, a la derecha del texto "Usage:"). Abre el wizard
`developers.tiktok.com/application/content-posting-api` con 4 pasos:

1. **General Information** — Full Name (opcional), Organization name*,
   Organization website* (poné el canal de YouTube o el TikTok
   @rayando.el.cda), "Describe your organization's work as it relates to
   TikTok"*, email de representante de TikTok (dejar vacío).
2. **API client information** — qué APIs/scopes se usan (Direct Post),
   descripción de la integración, regiones.
3. **Supporting documents** — acá van los 3 MP4 (`1-oauth.mp4`, `2-flujo.mp4`,
   `3-resultado.mp4`).
4. **Review** — revisar y enviar.

Puntos a cubrir en las descripciones (en inglés):
   - Qué hace la app: herramienta interna del canal "Rayando el CDA" para
     revisar y publicar clips cortos de su propio programa a YouTube, Instagram
     y TikTok.
   - Cómo se usa Direct Post: al aprobar un clip, un editor abre la pantalla de
     publicación, **elige manualmente** el nivel de privacidad (no hay valor por
     defecto), revisa los permisos de interacción y la divulgación de contenido
     comercial, y confirma. El post se crea vía `/v2/post/publish/video/init/`
     con `source: FILE_UPLOAD`.
   - Cumplimiento UX: el selector de privacidad no viene preseleccionado;
     comentarios/dúo/stitch salen de `creator_info` y se respetan; se muestra la
     Music Usage Confirmation y la Branded Content Policy; sólo publica una
     persona, con PIN.
   - Sólo se publica contenido propio del canal (no de terceros).
4. Marcar los checkboxes de conformidad con las UX Guidelines / Content Sharing
   Guidelines.
5. Enviar. El botón "Apply" sigue sin tocar (confirmado 26/08). La revisión de
   Direct Post suele tardar más que la aprobación general de la app.

### 5b. Después de enviar — ✅ HECHO (30/08/2026)

- ✅ Cuenta @rayando.el.cda de vuelta en **pública**.
- ✅ `PUBLICAR_TIKTOK` de vuelta en **`false`** (verificado: `tiktok_creator_info`
  → `habilitado:false`). Se eligió dejarlo en `false` en vez de `true` + aviso al
  equipo: con la cuenta pública y la auditoría pendiente, cualquier publicación a
  TikTok desde el panel daría `403
  unaudited_client_can_only_post_to_private_accounts` + mail de alerta (que hoy no
  llega a nadie, ver `resend_sandbox_pendiente`).

### 6. Cuando TikTok apruebe (o rechace)

- **Aprobada:** setear `TIKTOK_AUDITORIA_APROBADA=true` + redeployar
  `publicar-clip` (CLI con legacy token — ver paso 1) + poner
  `PUBLICAR_TIKTOK=true`. Ahí el panel empieza a ofrecer "Todos" y los posts
  salen públicos.
- **Rechazada:** TikTok manda el motivo por mail / en Manage apps. Suele ser un
  detalle de UX en la demo. Ajustar y volver a Apply (mismo formulario).

## Notas

- `PUBLICAR_TIKTOK` es el kill-switch maestro. Hoy en `false` — con la cuenta
  pública y la auditoría pendiente, ponerlo en `true` haría fallar (403)
  cualquier publicación a TikTok que alguien intente desde el panel.
- [`resend_sandbox_pendiente`] sigue sin resolver: los mails de alerta del
  pipeline no llegan a nadie.
