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
3. **Columnas esperadas** en `rayando_cda.clips`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid/int | PK |
| `estado` | text | `'pendiente' \| 'aprobado' \| 'rechazado'` |
| `created_at` | timestamptz | usada para ordenar pendientes (ver `src/lib/constants.js` si tu columna se llama distinto) |
| `youtube_video_id` | text | id del video de YouTube para el embed |
| `copy_instagram` | text | editable |
| `copy_tiktok` | text | editable |
| `youtube_titulo` | text | editable |
| `youtube_descripcion` | text | editable |
| `razon` | text | solo lectura |
| `transcripcion` | text | solo lectura, colapsable |
| `comentarios_video` | text | editable, pedidos manuales (no se ejecutan solos) |
| `notas_revision` | text | notas al rechazar |
| `revisado_por` | text | seteado por la app al aprobar/rechazar |
| `revisado_en` | timestamptz | seteado por la app al aprobar/rechazar |

## Deploy a GitHub Pages

El workflow en `.github/workflows/deploy.yml` builda y publica en cada push a `main` usando GitHub Actions (no hace falta rama `gh-pages`).

Antes del primer deploy:

1. En el repo de GitHub: **Settings → Pages → Source → GitHub Actions**.
2. **Settings → Secrets and variables → Actions**, agregar:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`
3. El `base` en `vite.config.js` está seteado a `/rayando-cda-review/`. Si el repo se llama distinto, actualizalo ahí.

La app queda en `https://<tu-usuario>.github.io/rayando-cda-review/`.
