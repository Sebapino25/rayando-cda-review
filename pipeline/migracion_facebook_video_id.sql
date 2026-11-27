-- 27/11/2026: id del Reel publicado en la página de Facebook (publicar-clip).
-- Evita duplicar el Reel si se reintenta. Aditiva e idempotente; ya aplicada
-- en producción el 27/11/2026 con visto bueno de Seba (SPA y Recda).
alter table siempre_pasa_algo.clips add column if not exists facebook_video_id text;
alter table rayando_cda.clips add column if not exists facebook_video_id text;
