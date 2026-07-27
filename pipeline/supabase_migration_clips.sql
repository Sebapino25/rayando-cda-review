-- Rayando el CDA: tabla de candidatos a clip para revisión editorial.
-- Correr en el SQL Editor de Supabase (proyecto compartido con otro uso).
-- Es idempotente: se puede correr de nuevo sin romper nada si el schema,
-- la tabla o las columnas ya existen.

create schema if not exists rayando_cda;

create table if not exists rayando_cda.clips (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now()
);

alter table rayando_cda.clips add column if not exists youtube_video_id text;
alter table rayando_cda.clips add column if not exists titulo text;
alter table rayando_cda.clips add column if not exists copy_instagram text;
-- copy_youtube queda como columna legacy (título+descripción juntos): ya no
-- se le escribe desde el pipeline, pero se deja para no perder los datos de
-- los clips insertados antes de separar youtube_titulo/youtube_descripcion.
alter table rayando_cda.clips add column if not exists copy_youtube text;
alter table rayando_cda.clips add column if not exists youtube_titulo text;
alter table rayando_cda.clips add column if not exists youtube_descripcion text;
alter table rayando_cda.clips add column if not exists copy_tiktok text;
alter table rayando_cda.clips add column if not exists razon text;
alter table rayando_cda.clips add column if not exists transcripcion text;
-- numeric = segundos desde el inicio de la grabación (float), no "hh:mm:ss".
-- Confirmado contra la tabla real: si la columna ya existe como numeric,
-- este ADD COLUMN IF NOT EXISTS no la toca (es un no-op), pero si la tabla
-- se crea desde cero acá, queda con el tipo correcto.
alter table rayando_cda.clips add column if not exists timestamp_inicio numeric;
alter table rayando_cda.clips add column if not exists timestamp_fin numeric;
alter table rayando_cda.clips add column if not exists semana date;
alter table rayando_cda.clips add column if not exists estado text not null default 'pendiente';
-- Campos para la herramienta de revisión de René (no los llena el pipeline):
alter table rayando_cda.clips add column if not exists revisado_por text;
alter table rayando_cda.clips add column if not exists revisado_en timestamptz;
alter table rayando_cda.clips add column if not exists notas_revision text;
alter table rayando_cda.clips add column if not exists publicado boolean not null default false;
alter table rayando_cda.clips add column if not exists publicado_en timestamptz;

-- El pipeline inserta con la service_role key, que hace bypass de RLS, pero
-- igual necesita GRANT a nivel de schema/tabla (Postgres no lo da gratis en
-- un schema custom).
grant usage on schema rayando_cda to service_role;
grant all on all tables in schema rayando_cda to service_role;
alter default privileges for role postgres in schema rayando_cda grant all on tables to service_role;

-- RLS activo y sin policies: por defecto solo service_role (bypass RLS)
-- puede leer/escribir. Si más adelante la herramienta de revisión de René
-- usa la anon/authenticated key en vez de service_role, hay que agregar acá
-- policies explícitas para esos roles (y sus GRANT correspondientes).
alter table rayando_cda.clips enable row level security;

-- --- Publicación final desde la app (ver docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md) ---
alter table rayando_cda.clips add column if not exists video_url text;
alter table rayando_cda.clips add column if not exists publicando_en timestamptz;
alter table rayando_cda.clips add column if not exists tiktok_publish_id text;

-- Corrección de drift: estas dos ya existen en la tabla real (las usa
-- publicar.py/publicar_automatico.py/la app) pero no estaban documentadas
-- en este archivo — se agregaron en algún momento fuera de este script.
alter table rayando_cda.clips add column if not exists portada_url text;
alter table rayando_cda.clips add column if not exists instagram_media_id text;

-- Token de Instagram vigente, refrescado automáticamente por la Edge
-- Function refrescar-token-instagram (cron semanal). Fila única forzada
-- por el check constraint sobre "id".
create table if not exists rayando_cda.instagram_token (
    id boolean primary key default true,
    access_token text not null,
    vence_en timestamptz,
    actualizado_en timestamptz not null default now(),
    constraint instagram_token_fila_unica check (id)
);

-- Intentos fallidos de PIN contra publicar-clip (rate limiting de un
-- endpoint público). Solo se insertan filas en intentos fallidos.
create table if not exists rayando_cda.pin_intentos (
    id bigint generated always as identity primary key,
    creado_en timestamptz not null default now()
);

grant all on table rayando_cda.instagram_token to service_role;
grant all on table rayando_cda.pin_intentos to service_role;

alter table rayando_cda.instagram_token enable row level security;
alter table rayando_cda.pin_intentos enable row level security;
-- Sin policies para anon/authenticated a propósito: instagram_token tiene
-- el access token vigente de Instagram, pin_intentos es el contador de
-- seguridad del PIN. Solo service_role (Edge Functions) las toca — nunca
-- deben quedar expuestas al schema "Exposed" que usa la app con la anon key.

-- Paso manual obligatorio, no se puede hacer por SQL: en el dashboard de
-- Supabase, ir a Project Settings > API > Exposed schemas y agregar
-- "rayando_cda" (junto a "public"). Sin esto, el cliente falla con un error
-- PGRST106 aunque el GRANT de arriba esté bien.

-- --- Corrección de seguridad: políticas de Storage en clips-video ---
-- Hallazgo Crítico de la revisión final del branch de publicación final: el
-- bucket clips-video (Storage) tenía policies que le daban a "anon" DELETE,
-- INSERT y UPDATE sin restricción sobre todo el bucket. Con INSERT/UPDATE,
-- cualquiera con la anon key pública (embebida en el bundle de GitHub Pages)
-- podía reemplazar el video de un clip aprobado por contenido arbitrario,
-- que después se publicaría de verdad al aprobar con el PIN. No hay ningún
-- flujo legítimo del lado del navegador que necesite insertar o actualizar
-- en este bucket (la subida real la hace publicar.py con la service role
-- key). Se deja DELETE para anon (necesario para el rechazo best-effort de
-- la app, ver handleReject en app/src/App.jsx). Ya aplicado contra el
-- proyecto real; este bloque documenta el cambio para que quede reproducible
-- si las policies del bucket se recrean desde cero.
drop policy if exists clips_video_anon_insert on storage.objects;
drop policy if exists clips_video_anon_update on storage.objects;
