# Programas (multi-programa)

El pipeline sirve a más de un programa. Se elige con la variable de entorno `PROGRAMA`:

- `rayando` (default, o sin variable): comportamiento original, sin cambios.
- `spa`: SPAreírse (Siempre Pasa Algo). Carga `programas/spa.json` y `.env.spa`.

Windows (PowerShell), con la bandera (cualquier script de entrada):

    python procesar_programa.py "<grabacion>.mkv" --programa spa

o con la variable, para toda la sesión: `$env:PROGRAMA = "spa"`. `recda` es alias de `rayando`.
`rayando.json` es solo informativo (redes, día, tarea): Recda usa los valores de `config.py`.

## Qué trae un perfil (`programas/<n>.json`)
- `nombre`, `base_dir` (carpeta de trabajo: grabaciones, clips, transcripciones).
- `config`: pisa constantes de `config.py` (solo claves que ya existen; un typo falla fuerte).
  Rutas relativas se resuelven contra `base_dir`.
- `prompts.deteccion` / `prompts.copys_contexto`: textos propios (carpeta `programas/<n>/`).
  El de detección admite `{min_n} {max_n} {dur_min} {dur_max}`.
- `diccionario`: nombres propios (Whisper + corrector).

## Credenciales propias: `.env.<programa>`
Pisa lo que diga `.env`. Lo que no esté ahí se hereda de `.env`. Para SPA como mínimo:

    YOUTUBE_CLIENT_ID=...        # del proyecto de Google Cloud PROPIO de SPA (la cuota es por proyecto)
    YOUTUBE_CLIENT_SECRET=...
    YOUTUBE_TOKEN_FILE=youtube_token_spa.json   # token distinto, autoriza el canal de SPA

Las tres son obligatorias: si falta una, SPA no sube a YouTube (se revisa desde Storage)
en vez de usar la cuenta de Recda. El token se crea una vez con
`python autorizar_youtube.py --programa spa`, que muestra el id del canal; ese id va en
`spa.json` como `"YOUTUBE_CANAL_ID"` dentro de `config`.
    # Instagram / TikTok de SPA cuando existan (las de Rayando NO se heredan por error: déjalas vacías aquí)

## Publicar en redes desde la app (Edge Function)
El botón "Publicar en redes" llama a `publicar-clip` (Recda) o `publicar-clip-spa` (SPA, mismo
código; la app manda `programa: "spa"`). Recda usa los secretos de siempre, sin prefijo. SPA usa
solo los suyos (Supabase > Edge Functions > Secrets), nunca los de Recda:

    SPA_PUBLISH_PIN                       PIN propio de SPA
    SPA_PUBLICAR_YOUTUBE=true             pasa el video no listado a público
    SPA_YOUTUBE_CLIENT_ID / SPA_YOUTUBE_CLIENT_SECRET / SPA_YOUTUBE_REFRESH_TOKEN
    SPA_PUBLICAR_INSTAGRAM=true           Reel en Instagram (graph.facebook.com)
    SPA_PUBLICAR_FACEBOOK=true            Reel en la página de Facebook
    SPA_FACEBOOK_PAGE_ID / SPA_FACEBOOK_PAGE_TOKEN     token de PÁGINA (no vence)
    SPA_INSTAGRAM_BUSINESS_ACCOUNT_ID     Instagram vinculado a esa página

En SPA, Instagram y Facebook usan el mismo token de página (inicio de sesión con Facebook), así que
no hay refresco cada 60 días como en Recda. TikTok de SPA sigue a mano. Si falta un secreto de una
red prendida, la función lo dice antes de tocar el clip.
