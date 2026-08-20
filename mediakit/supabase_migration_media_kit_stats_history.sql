-- Rayando el CDA: historial de snapshots del media kit, para graficar
-- evolución (mediakit/dashboard/ y la sección "Cómo venimos creciendo" del
-- media kit público). Correr en el SQL Editor de Supabase. Idempotente.

create table if not exists rayando_cda.media_kit_stats_history (
    id bigint generated always as identity primary key,
    snapshot_en timestamptz not null default now(),
    ig_seguidores numeric,
    ig_vistas_30d numeric,
    ig_interacciones_90d numeric,
    tiktok_seguidores numeric,
    tiktok_likes numeric,
    tiktok_video_top_vistas numeric,
    yt_suscriptores numeric,
    yt_vistas_historicas numeric,
    yt_vistas_30d numeric,
    programas_emitidos integer
);

grant select on table rayando_cda.media_kit_stats_history to anon;
grant all on table rayando_cda.media_kit_stats_history to service_role;

alter table rayando_cda.media_kit_stats_history enable row level security;

drop policy if exists media_kit_stats_history_anon_select on rayando_cda.media_kit_stats_history;
create policy media_kit_stats_history_anon_select on rayando_cda.media_kit_stats_history
    for select
    to anon
    using (true);
-- Solo lectura para anon, igual que media_kit_stats: la tabla no tiene
-- nada sensible (son los mismos números que ya se muestran en el media
-- kit público) y la lee tanto la página pública (2 sparklines resumidos)
-- como el dashboard interno (gráficos completos).

-- Cada UPDATE (o INSERT) a media_kit_stats deja acá una foto del estado
-- resultante. Así el historial se llena solo con la actualización manual
-- semanal de siempre — no hace falta acordarse de nada nuevo ni tocar el
-- README del proceso semanal.
create or replace function rayando_cda.snapshot_media_kit_stats()
returns trigger
language plpgsql
as $$
begin
  insert into rayando_cda.media_kit_stats_history (
    ig_seguidores, ig_vistas_30d, ig_interacciones_90d,
    tiktok_seguidores, tiktok_likes, tiktok_video_top_vistas,
    yt_suscriptores, yt_vistas_historicas, yt_vistas_30d, programas_emitidos
  ) values (
    new.ig_seguidores, new.ig_vistas_30d, new.ig_interacciones_90d,
    new.tiktok_seguidores, new.tiktok_likes, new.tiktok_video_top_vistas,
    new.yt_suscriptores, new.yt_vistas_historicas, new.yt_vistas_30d, new.programas_emitidos
  );
  return new;
end;
$$;

drop trigger if exists media_kit_stats_snapshot on rayando_cda.media_kit_stats;
create trigger media_kit_stats_snapshot
after insert or update on rayando_cda.media_kit_stats
for each row execute function rayando_cda.snapshot_media_kit_stats();

-- Reconstrucción de los únicos 3 puntos históricos reales y fechados que
-- existen (no había snapshots semana a semana antes de este historial, así
-- que la serie arranca corta y crece de a un punto por semana desde acá):
-- la carga inicial de la migración base (30/07/2026, ver
-- supabase_migration_media_kit_stats.sql), el snapshot horneado en
-- index.html el 11/08/2026 (última vez que se copiaron números frescos al
-- HTML a mano) y el UPDATE real corrido el 19/08/2026 con los números de
-- esa fecha. Solo se siembra si la tabla está vacía, para que re-correr
-- esta migración no duplique filas.
insert into rayando_cda.media_kit_stats_history (
    snapshot_en, ig_seguidores, ig_vistas_30d, ig_interacciones_90d,
    tiktok_seguidores, tiktok_likes, tiktok_video_top_vistas,
    yt_suscriptores, yt_vistas_historicas, yt_vistas_30d, programas_emitidos
)
select * from (values
    ('2026-07-30T12:00:00Z'::timestamptz, 13516::numeric, 3000000::numeric, 586000::numeric, 4455::numeric, 101000::numeric, 232000::numeric, null::numeric, 1400000::numeric, null::numeric, 70),
    ('2026-08-11T12:00:00Z'::timestamptz, 13944::numeric, 3315337::numeric, 555122::numeric, 4800::numeric, 113000::numeric, 495400::numeric, 2401::numeric, 1553578::numeric, null::numeric, 73),
    ('2026-08-19T18:38:41Z'::timestamptz, 14280::numeric, 4539071::numeric, 651487::numeric, 4987::numeric, 119600::numeric, 648200::numeric, 2618::numeric, 1874193::numeric, 464112::numeric, 73)
) as seed(snapshot_en, ig_seguidores, ig_vistas_30d, ig_interacciones_90d, tiktok_seguidores, tiktok_likes, tiktok_video_top_vistas, yt_suscriptores, yt_vistas_historicas, yt_vistas_30d, programas_emitidos)
where not exists (select 1 from rayando_cda.media_kit_stats_history);
