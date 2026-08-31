# TikTok Direct Post — estado y pasos pendientes

_Última actualización: 30/08/2026._

Contexto completo: sección `## TikTok` de [`pipeline/README.md`](../pipeline/README.md).
Plan de implementación: `~/.claude/plans/stateful-wiggling-kay.md`.

## Objetivo

Retomar la **publicación automática a TikTok**. Hoy los clips se suben a mano
(botones "Descargar clip" / "Descargar portada" en la app). El bloqueo es la
**auditoría de Direct Post de TikTok**, que nunca se envió, y que revisa la UX
de publicación de la app.

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
| Secret `PUBLICAR_TIKTOK` | cargado 30/08 en `true` para probar; **volver a `false`** tras enviar (paso 5b) |
| Prueba end-to-end | ✅ OK — clip real publicado con `tiktok_publish_id` guardado |
| **Auditoría de Direct Post** | ✅ **ENVIADA el 30/08/2026** — respuesta en 2–4 semanas. Revisar estado en `developers.tiktok.com` → Manage apps |
| Cuenta @rayando.el.cda | privada durante la grabación — **volver a pública** (paso 5b) |

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

Falta la cuenta en **público** de nuevo (dejarla privada hasta grabar la demo
del resultado, paso 4).

### 4. Grabar las demos para la auditoría

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

### 5. Enviar la auditoría

Ir a `developers.tiktok.com/app/7666642864034072596/live` → panel izquierdo
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

### 5b. Después de enviar

- **Volver la cuenta @rayando.el.cda a pública.**
- Con la auditoría pendiente y la cuenta pública, `PUBLICAR_TIKTOK=true` es
  benigno: un clip sin config de TikTok en el panel se saltea en silencio. Pero
  si alguien llena el panel y publica, va a fallar con `403
  unaudited_client_can_only_post_to_private_accounts` (y manda mail de alerta —
  que hoy no llega a nadie, ver `resend_sandbox_pendiente`). Decisión a tomar:
  dejar `PUBLICAR_TIKTOK=true` y avisarle al equipo que no usen el toggle de
  TikTok hasta la aprobación, o volver a ponerlo en `false` hasta entonces.

### 6. Cuando TikTok apruebe (o rechace)

- **Aprobada:** setear `TIKTOK_AUDITORIA_APROBADA=true` + redeployar
  `publicar-clip` (CLI con legacy token — ver paso 1) + poner
  `PUBLICAR_TIKTOK=true`. Ahí el panel empieza a ofrecer "Todos" y los posts
  salen públicos.
- **Rechazada:** TikTok manda el motivo por mail / en Manage apps. Suele ser un
  detalle de UX en la demo. Ajustar y volver a Apply (mismo formulario).

## Notas

- `PUBLICAR_TIKTOK` es el kill-switch maestro. Con la auditoría aún pendiente,
  se puede dejar en `true` sin drama: un clip sin config de TikTok en el panel
  se saltea en silencio, no genera error ni mail.
- El gap "frontend nuevo + función vieja" es benigno pero conviene cerrarlo
  pronto (paso 1) para no confundir a quien use la app.
- [`resend_sandbox_pendiente`] sigue sin resolver: los mails de alerta del
  pipeline no llegan a nadie.
