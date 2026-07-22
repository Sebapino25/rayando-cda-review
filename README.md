# Rayando el CDA

Monorepo con dos partes independientes:

- **`app/`** — app web de cola de revisión (React + Vite + Supabase). Ver [`app/README.md`](app/README.md) para setup, configuración de Supabase y datos de prueba para QA.
- **`pipeline/`** — pipeline de procesamiento de video (detección de momentos, corte, subtítulos, portadas, copys y publicación a YouTube/Supabase). Ver [`pipeline/README.md`](pipeline/README.md).

Ambas comparten el mismo proyecto de Supabase (tabla `rayando_cda.clips`): el pipeline inserta candidatos, la app los revisa.

## Deploy

Solo `app/` se despliega a GitHub Pages (`.github/workflows/deploy.yml`, disparado únicamente por cambios en `app/**`). `pipeline/` no tiene CI — corre localmente.
