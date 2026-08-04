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

La Edge Function `actualizar-stats-mediakit` corre **cada hora, en punto**
(`pg_cron`, job id 3, schedule `0 * * * *` — antes corría una sola vez al
día a las 8:00 UTC, pero eso dejaba los números visiblemente atrasados
durante el resto del día; se subió la frecuencia el 04/08), trae datos de
los 3 connectors de Windsor.ai ya conectados (`instagram`, `tiktok_organic`,
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

## Actualizar la composición de audiencia a mano

`audiencia_hombres_pct`, `audiencia_25_44_pct` y `audiencia_hombres_25_44_pct`
(sección "Y no es cualquier audiencia" de la página) tampoco los toca el cron
diario — la composición demográfica de una cuenta cambia en semanas/meses,
no en horas. Recalcular cada 2-3 meses, o si el equipo pide un dato más
fresco antes de una reunión con una marca:

1. Traer la tabla completa de género × edad de Instagram desde Windsor.ai
   (connector `instagram`, campos `audience_gender_age_name` y
   `audience_gender_age_size` — trae un valor por combinación, ej. `M.25-34`).
2. Sumar todos los valores para el total, sumar los que empiezan con `M.`
   para el % de hombres, sumar los rangos `25-34` + `35-44` (de ambos
   géneros) para el % de 25-44, y sumar `M.25-34` + `M.35-44` para el %
   de hombres de 25 a 44 (el dato más específico y más vendedor).
3. Redondear a entero y actualizar:

```sql
update rayando_cda.media_kit_stats
set audiencia_hombres_pct = <pct>,
    audiencia_25_44_pct = <pct>,
    audiencia_hombres_25_44_pct = <pct>
where id = true;
```

Última actualización: 2026-07-31, con datos reales de Windsor.ai (73%
hombres, 67% entre 25 y 44 años, 54% hombres de 25 a 44 años, sobre un
total de ~13.650 seguidoras/es de Instagram).
