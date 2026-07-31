-- Rayando el CDA: tabla de una fila con los números en vivo del media kit
-- (Instagram, TikTok, YouTube vía Windsor.ai). Correr en el SQL Editor de
-- Supabase. Idempotente: se puede correr de nuevo sin romper nada.

create table if not exists rayando_cda.media_kit_stats (
    id boolean primary key default true,
    -- Instagram
    ig_seguidores numeric,
    ig_vistas_30d numeric,
    ig_alcance_90d numeric,
    ig_interacciones_90d numeric,
    ig_actualizado_en timestamptz,
    -- TikTok
    tiktok_seguidores numeric,
    tiktok_likes numeric,
    tiktok_video_top_vistas numeric,
    tiktok_actualizado_en timestamptz,
    -- YouTube
    yt_suscriptores numeric,
    yt_vistas_historicas numeric,
    yt_vistas_30d numeric,
    yt_actualizado_en timestamptz,
    -- Manual (no es una métrica de ninguna API)
    programas_emitidos integer,
    constraint media_kit_stats_fila_unica check (id)
);

grant all on table rayando_cda.media_kit_stats to service_role;
grant select on table rayando_cda.media_kit_stats to anon;

alter table rayando_cda.media_kit_stats enable row level security;

drop policy if exists media_kit_stats_anon_select on rayando_cda.media_kit_stats;
create policy media_kit_stats_anon_select on rayando_cda.media_kit_stats
    for select
    to anon
    using (true);
-- Sin policy de insert/update/delete para anon a propósito: la página del
-- media kit es de solo lectura, únicamente la Edge Function (service_role,
-- que hace bypass de RLS) escribe acá. programas_emitidos se edita a mano
-- por el usuario directo en Supabase Studio (usa la conexión de owner del
-- proyecto, no la anon key, así que RLS no lo bloquea).

-- Fila inicial con los números actuales del media kit estático (07/2026),
-- para que la página nunca arranque vacía antes de la primera corrida del
-- cron. La Edge Function los sobreescribe con datos reales en su primera
-- corrida.
insert into rayando_cda.media_kit_stats (
    id, ig_seguidores, ig_vistas_30d, ig_alcance_90d, ig_interacciones_90d,
    tiktok_seguidores, tiktok_likes, tiktok_video_top_vistas,
    yt_suscriptores, yt_vistas_historicas, programas_emitidos
) values (
    true, 13516, 3000000, 548000, 586000,
    4455, 101000, 232000,
    null, 1400000, 70
) on conflict (id) do nothing;
