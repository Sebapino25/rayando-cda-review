-- SPAreírse (Siempre Pasa Algo): tabla de candidatos a clip para revisión editorial.
-- Correr en el SQL Editor de Supabase (mismo proyecto que Rayando el CDA, schema propio).
-- Es idempotente: se puede correr de nuevo sin romper nada si el schema,
-- la tabla o las columnas ya existen.

create schema if not exists siempre_pasa_algo;

create table if not exists siempre_pasa_algo.clips (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now()
);

alter table siempre_pasa_algo.clips add column if not exists youtube_video_id text;
alter table siempre_pasa_algo.clips add column if not exists titulo text;
alter table siempre_pasa_algo.clips add column if not exists copy_instagram text;
-- copy_youtube queda como columna legacy (título+descripción juntos): ya no
-- se le escribe desde el pipeline, pero se deja para no perder los datos de
-- los clips insertados antes de separar youtube_titulo/youtube_descripcion.
alter table siempre_pasa_algo.clips add column if not exists copy_youtube text;
alter table siempre_pasa_algo.clips add column if not exists youtube_titulo text;
alter table siempre_pasa_algo.clips add column if not exists youtube_descripcion text;
alter table siempre_pasa_algo.clips add column if not exists copy_tiktok text;
alter table siempre_pasa_algo.clips add column if not exists razon text;
alter table siempre_pasa_algo.clips add column if not exists transcripcion text;
-- numeric = segundos desde el inicio de la grabación (float), no "hh:mm:ss".
-- Confirmado contra la tabla real: si la columna ya existe como numeric,
-- este ADD COLUMN IF NOT EXISTS no la toca (es un no-op), pero si la tabla
-- se crea desde cero acá, queda con el tipo correcto.
alter table siempre_pasa_algo.clips add column if not exists timestamp_inicio numeric;
alter table siempre_pasa_algo.clips add column if not exists timestamp_fin numeric;
alter table siempre_pasa_algo.clips add column if not exists semana date;
alter table siempre_pasa_algo.clips add column if not exists estado text not null default 'pendiente';
-- Campos para la herramienta de revisión de Samuel y Cristián (no los llena el pipeline):
alter table siempre_pasa_algo.clips add column if not exists revisado_por text;
alter table siempre_pasa_algo.clips add column if not exists revisado_en timestamptz;
alter table siempre_pasa_algo.clips add column if not exists notas_revision text;
alter table siempre_pasa_algo.clips add column if not exists publicado boolean not null default false;
alter table siempre_pasa_algo.clips add column if not exists publicado_en timestamptz;

-- El pipeline inserta con la service_role key, que hace bypass de RLS, pero
-- igual necesita GRANT a nivel de schema/tabla (Postgres no lo da gratis en
-- un schema custom).
grant usage on schema siempre_pasa_algo to service_role;
grant all on all tables in schema siempre_pasa_algo to service_role;
alter default privileges for role postgres in schema siempre_pasa_algo grant all on tables to service_role;

-- RLS activo y sin policies: por defecto solo service_role (bypass RLS)
-- puede leer/escribir. Si más adelante la herramienta de revisión de Samuel y Cristián
-- usa la anon/authenticated key en vez de service_role, hay que agregar acá
-- policies explícitas para esos roles (y sus GRANT correspondientes).
alter table siempre_pasa_algo.clips enable row level security;

-- --- Publicación final desde la app (ver docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md) ---
alter table siempre_pasa_algo.clips add column if not exists video_url text;
alter table siempre_pasa_algo.clips add column if not exists publicando_en timestamptz;
alter table siempre_pasa_algo.clips add column if not exists tiktok_publish_id text;

-- Corrección de drift: estas dos ya existen en la tabla real (las usa
-- publicar.py/publicar_automatico.py/la app) pero no estaban documentadas
-- en este archivo — se agregaron en algún momento fuera de este script.
alter table siempre_pasa_algo.clips add column if not exists portada_url text;
alter table siempre_pasa_algo.clips add column if not exists instagram_media_id text;

-- Token de Instagram vigente, refrescado automáticamente por la Edge
-- Function refrescar-token-instagram (cron semanal). Fila única forzada
-- por el check constraint sobre "id".
create table if not exists siempre_pasa_algo.instagram_token (
    id boolean primary key default true,
    access_token text not null,
    vence_en timestamptz,
    actualizado_en timestamptz not null default now(),
    constraint instagram_token_fila_unica check (id)
);

-- Intentos fallidos de PIN contra publicar-clip (rate limiting de un
-- endpoint público). Solo se insertan filas en intentos fallidos.
create table if not exists siempre_pasa_algo.pin_intentos (
    id bigint generated always as identity primary key,
    creado_en timestamptz not null default now()
);

grant all on table siempre_pasa_algo.instagram_token to service_role;
grant all on table siempre_pasa_algo.pin_intentos to service_role;

alter table siempre_pasa_algo.instagram_token enable row level security;
alter table siempre_pasa_algo.pin_intentos enable row level security;
-- Sin policies para anon/authenticated a propósito: instagram_token tiene
-- el access token vigente de Instagram, pin_intentos es el contador de
-- seguridad del PIN. Solo service_role (Edge Functions) las toca — nunca
-- deben quedar expuestas al schema "Exposed" que usa la app con la anon key.

-- Token de TikTok vigente, refrescado automáticamente por la Edge Function
-- refrescar-token-tiktok. A diferencia de Instagram, TikTok rota el
-- refresh_token en cada refresco, así que hay que guardar ambos.
create table if not exists siempre_pasa_algo.tiktok_token (
    id boolean primary key default true,
    access_token text not null,
    refresh_token text not null,
    vence_en timestamptz,
    actualizado_en timestamptz not null default now(),
    constraint tiktok_token_fila_unica check (id)
);

grant all on table siempre_pasa_algo.tiktok_token to service_role;
alter table siempre_pasa_algo.tiktok_token enable row level security;
-- Mismo criterio que instagram_token: sin policies para anon/authenticated,
-- solo service_role la toca.

-- Paso manual obligatorio, no se puede hacer por SQL: en el dashboard de
-- Supabase, ir a Project Settings > API > Exposed schemas y agregar
-- "siempre_pasa_algo" (junto a "public"). Sin esto, el cliente falla con un error
-- PGRST106 aunque el GRANT de arriba esté bien.

-- --- Storage propio de SPA (los buckets de Rayando NO se comparten) ---
-- Mismos nombres de ruta ({fecha}/{clip}.mp4) y upsert=true: compartir bucket
-- con Rayando podría pisar un video si coinciden fecha y número de clip.
insert into storage.buckets (id, name, public)
values ('portadas-spa', 'portadas-spa', true),
       ('clips-video-spa', 'clips-video-spa', true)
on conflict (id) do nothing;

-- Lectura pública por URL (bucket public). Escritura: solo service_role
-- (publicar.py). Para anon se deja ÚNICAMENTE DELETE sobre clips-video-spa,
-- igual que en Rayando (rechazo best-effort desde la app) — NO INSERT/UPDATE:
-- con la anon key pública cualquiera podría reemplazar un video aprobado.
drop policy if exists clips_video_spa_anon_delete on storage.objects;
create policy clips_video_spa_anon_delete on storage.objects
    for delete to anon using (bucket_id = 'clips-video-spa');

-- Paso manual (no se puede por SQL): Project Settings > API > Exposed schemas
-- y agregar "siempre_pasa_algo".
