# Media kit vivo

Página en `https://sebapino25.github.io/rayando-cda-review/mediakit/` —
reemplaza al PDF estático como la pieza que se manda en el primer correo a
una marca. Los números de Instagram, TikTok y YouTube se actualizan solos
todos los días vía Windsor.ai; `programas_emitidos` se edita a mano en
Supabase Studio cuando cambie.

## Estructura

- `public/` — el sitio que se despliega (HTML/CSS/JS plano, sin build).
- `supabase_migration_media_kit_stats.sql` — migración de la tabla
  `rayando_cda.media_kit_stats` (correr una sola vez en el SQL Editor).

## Cómo se actualizan los números

La Edge Function `actualizar-stats-mediakit` corre todos los días a las
8:00 UTC (`pg_cron`, programado a mano en el SQL Editor — ver el plan de
implementación para el `cron.schedule` exacto), trae datos de los 3
connectors de Windsor.ai ya conectados (`instagram`, `tiktok_organic`,
`youtube`) y los guarda en `media_kit_stats`.

**Requiere** el secreto `WINDSOR_API_KEY` cargado en Project Settings >
Edge Functions > Secrets, y una cuenta de Windsor.ai activa (hoy en
trial — pasar a plan pago antes de que venza, o los 3 números dejan de
actualizarse).

## Actualizar `programas_emitidos` a mano

En el SQL Editor de Supabase:

```sql
update rayando_cda.media_kit_stats set programas_emitidos = <número> where id = true;
```
