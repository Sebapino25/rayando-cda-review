# TikTok Direct Post — estado y pasos pendientes

_Última actualización: 28/08/2026._

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

## Estado del deploy (28/08/2026, fin del día)

| Cosa | Estado |
|---|---|
| Frontend (GitHub Pages) | ✅ **deployado** (commit `422cfc2`, workflow en verde) |
| Edge Function `publicar-clip` | ❌ **NO deployada con el código nuevo** — sigue la versión del deploy anterior de hoy |
| Secret `TIKTOK_AUDITORIA_APROBADA` | ❌ no existe todavía |
| Secret `PUBLICAR_TIKTOK` | `false` (sin cambios) |
| Cuenta @rayandoelcda | pública |

**Consecuencia del gap:** con el frontend nuevo y la función vieja, abrir el
panel de TikTok muestra un error ("Faltan clip_id…") porque la función vieja no
conoce `action: 'tiktok_creator_info'`. **Publicar en YouTube/Instagram sigue
funcionando** (la función vieja lee `body.pin` e ignora `body.tiktok`). El gap
se cierra deployando la función (paso 1 de abajo).

## Pasos para mañana

### 1. Deployar la Edge Function

Generar un legacy token en https://supabase.com/dashboard/account/tokens y:

```
SUPABASE_ACCESS_TOKEN="sbp_..." npx supabase functions deploy publicar-clip --project-ref qfxfwfcdgqcbmdspjvtk
```

(el `import_map` ya está en `supabase/config.toml`; si falla, agregar
`--import-map supabase/functions/deno.json`). **Revocar el token después.**

### 2. Cargar los secrets

Supabase → Project Settings → Edge Functions → Secrets:

| Secret | Valor |
|---|---|
| `TIKTOK_AUDITORIA_APROBADA` | `false` |
| `PUBLICAR_TIKTOK` | `true` |

Se toman en la próxima invocación, sin redeploy.

### 3. Probar end-to-end

1. Poner @rayandoelcda **en privado** en TikTok (única forma de que la API deje
   postear sin auditar).
2. App → tab "Por publicar" → clip fixture (`estado='prueba'` puesto en
   `aprobado`) → "Publicar en redes".
3. Verificar el panel: carga la cuenta real, `<select>` de privacidad sin
   elegir, dúo/stitch deshabilitados (cuenta privada), texto de Music Usage
   Confirmation con link, botón "Publicar" bloqueado hasta elegir privacidad +
   PIN.
4. Elegir "Solo yo", PIN, publicar. Confirmar: el clip queda `publicado`,
   `tiktok_publish_id` guardado, el video aparece en el perfil de TikTok.
5. Probar el toggle de contenido comercial: al tildar "contenido de marca", la
   opción "Solo yo" se deshabilita y el texto de cumplimiento cambia.
6. Volver la cuenta a **público**.
7. Confirmar que con el toggle de TikTok en OFF, publicar sigue andando para
   YT/IG.

### 4. Grabar las demos para la auditoría

Pantalla completa, sin cortes, texto legible, hasta 5 archivos:

- **OAuth / consentimiento de TikTok** — ya hay un tramo del 17/08; regrabar si
  no se ve la pantalla de permisos de TikTok.
- **Flujo de publicación completo** — clip aprobado → "Publicar en redes" →
  panel de TikTok mostrando **despacio** la elección manual de privacidad, los
  toggles apagados, el texto de cumplimiento → PIN → éxito.
- **Resultado en TikTok** — el video publicado, visto en el perfil de
  @rayandoelcda.

### 5. Enviar la auditoría

`developers.tiktok.com/app/7666642864034072596/live` → Content Posting API →
Direct Post → **Apply** (acepta hasta 5 archivos). El botón "Apply" sigue sin
tocar (confirmado 26/08).

### 6. Cuando TikTok apruebe

Setear `TIKTOK_AUDITORIA_APROBADA=true` + redeployar `publicar-clip`. Ahí el
panel empieza a ofrecer "Todos" y los posts salen públicos automáticamente.

## Notas

- `PUBLICAR_TIKTOK` es el kill-switch maestro. Con la auditoría aún pendiente,
  se puede dejar en `true` sin drama: un clip sin config de TikTok en el panel
  se saltea en silencio, no genera error ni mail.
- El gap "frontend nuevo + función vieja" es benigno pero conviene cerrarlo
  pronto (paso 1) para no confundir a quien use la app.
- [`resend_sandbox_pendiente`] sigue sin resolver: los mails de alerta del
  pipeline no llegan a nadie.
