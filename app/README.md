# Rayando el CDA — Cola de revisión

App para revisar, editar y aprobar/rechazar clips antes de publicarlos. React + Vite + Tailwind v4, sin backend propio: todo el estado vive en Supabase.

## Setup local

```bash
npm install
cp .env.example .env   # completar con tu URL y anon key de Supabase
npm run dev
```

## Configuración de Supabase

La tabla `clips` vive en el schema `rayando_cda` (no en `public`). Pasos necesarios en el proyecto de Supabase:

1. **Exponer el schema**: Project Settings → Data API → Exposed schemas → agregar `rayando_cda`.
2. **Row Level Security**: si RLS está activo en `clips`, crear policies que permitan `select`/`update` con la anon key (esta app usa la anon key desde el navegador, sin login).
3. **Si `estado` tiene un `CHECK` constraint**: agregar `'correccion_video'` a los valores permitidos, por ejemplo:
   ```sql
   ALTER TABLE rayando_cda.clips DROP CONSTRAINT IF EXISTS clips_estado_check;
   ALTER TABLE rayando_cda.clips
     ADD CONSTRAINT clips_estado_check
     CHECK (estado IN ('pendiente', 'aprobado', 'correccion_video', 'rechazado'));
   ```
   (ajustá el nombre del constraint al real de tu tabla — si `estado` es texto libre sin constraint, este paso no hace falta).
4. **Columnas esperadas** en `rayando_cda.clips`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid/int | PK |
| `estado` | text | `'pendiente' \| 'aprobado' \| 'correccion_video' \| 'rechazado'` |
| `created_at` | timestamptz | usada para ordenar pendientes (ver `src/lib/constants.js` si tu columna se llama distinto) |
| `youtube_video_id` | text | id del video de YouTube para el embed |
| `copy_instagram` | text | editable |
| `copy_tiktok` | text | editable |
| `youtube_titulo` | text | editable |
| `youtube_descripcion` | text | editable |
| `razon` | text | solo lectura |
| `transcripcion` | text | editable, colapsable — corregirla no regenera el subtítulo del video, queda anotada para reprocesar |
| `transcripcion_original` | text | solo lectura, no la toca la app. Se copia de `transcripcion` automáticamente al insertar (trigger) y nunca se edita después salvo por `scripts/reprocesar_subtitulos.py`, que la resincroniza una vez que reprocesó el video. Sirve para detectar `transcripcion != transcripcion_original` = corrección pendiente de aplicar al video |
| `comentarios_video` | text | editable; obligatoria si se elige "Corrección de video". Un pedido de ajustar el in/out point se aplica solo (IA interpreta el texto y re-corta, ver `pipeline/reprocesar_video.py`); otros tipos de pedido siguen siendo manuales |
| `notas_revision` | text | notas al rechazar |
| `revisado_por` | text | seteado por la app al aprobar, pedir corrección o rechazar; se limpia si una corrección de video se aplica sola (vuelve a `pendiente` para revisión fresca) |
| `revisado_en` | timestamptz | seteado por la app al aprobar, pedir corrección o rechazar; mismo comportamiento que `revisado_por` en una corrección automática |
| `publicado` | boolean | `true` una vez que la Edge Function `publicar-clip` publicó de verdad — la app usa esto para no mostrar el botón "Publicar en redes" en un clip ya publicado |
| `publicado_en` | timestamptz | seteado junto con `publicado=true` |
| `video_url` | text | URL pública del `vertical.mp4` en Supabase Storage (bucket `clips-video`) — la usa la Edge Function `publicar-clip` para publicar de verdad |
| `portada_url` | text | URL pública de la portada en Supabase Storage (bucket `portadas`) |
| `publicando_en` | timestamptz | claim atómico: seteado por la Edge Function `publicar-clip` al empezar a publicar, para evitar dos publicaciones simultáneas del mismo clip |
| `instagram_media_id` | text | id del media de Instagram publicado, seteado por `publicar-clip` |
| `tiktok_publish_id` | text | id de publicación de TikTok, seteado por `publicar-clip` cuando la persona configura el panel de TikTok al publicar (hoy `PUBLICAR_TIKTOK=false`, ver `pipeline/README.md`) |

## Datos de prueba (QA)

Cualquier prueba automatizada (Playwright u otra) que edite datos **nunca debe correr contra filas de contenido real curado**. Para eso existe un clip fixture dedicado en `rayando_cda.clips`:

- `estado = 'prueba'` — es un valor centinela fuera del ciclo real (`pendiente` / `aprobado` / `correccion_video` / `rechazado`), así que **no aparece ni en "Pendientes" ni en "Historial"** sin necesidad de tocar código (ninguna de las dos queries en `App.jsx` lo incluye).
- `youtube_titulo` empieza con `[CLIP DE PRUEBA]` para que sea inconfundible si alguna vez se lo ve directamente en la tabla.

Protocolo para un test automatizado:

1. Antes de probar, poné el `estado` de ese clip en `'pendiente'` (y los campos de texto en un baseline conocido) para que aparezca en la cola.
2. Corré el flujo que necesites contra **ese** clip únicamente.
3. Al terminar (pase lo que pase, éxito o falla del test), volvé a poner su `estado` en `'prueba'` para que no quede visible en la cola real.

Si no existe ninguna fila con `estado = 'prueba'`, creá una primero con el mismo patrón antes de correr cualquier test.

## Deploy a GitHub Pages

El workflow en `.github/workflows/deploy.yml` builda y publica en cada push a `main` usando GitHub Actions (no hace falta rama `gh-pages`).

Antes del primer deploy:

1. En el repo de GitHub: **Settings → Pages → Source → GitHub Actions**.
2. **Settings → Secrets and variables → Actions**, agregar:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`
3. El `base` en `vite.config.js` está seteado a `/rayando-cda-review/`. Si el repo se llama distinto, actualizalo ahí.

La app queda en `https://<tu-usuario>.github.io/rayando-cda-review/`.
