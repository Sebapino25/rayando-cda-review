# Media kit vivo

Página en `https://sebapino25.github.io/rayando-cda-review/mediakit/` —
reemplaza al PDF estático como la pieza que se manda en el primer correo a
una marca. Los números de Instagram, TikTok y YouTube salen de
`rayando_cda.media_kit_stats` y **se actualizan a mano, una vez por semana**
(ver más abajo). `programas_emitidos` también.

## Estructura

- `public/` — el sitio que se manda a marcas (HTML/CSS/JS plano, sin build).
- `dashboard/` — dashboard interno de evolución, mismo dominio de datos pero
  para el equipo (no se manda a marcas). Ver "Gráficos de evolución" abajo.
- `shared/charts.js` — sparklines SVG a mano, sin librería externa, usado
  por `public/` y `dashboard/`.
- `supabase_migration_media_kit_stats.sql` — migración de la tabla
  `rayando_cda.media_kit_stats` (correr una sola vez en el SQL Editor).
- `supabase_migration_media_kit_stats_history.sql` — migración del
  historial de snapshots (ver "Gráficos de evolución" abajo).

## Gráficos de evolución

Desde el 19/08/2026 cada actualización de `media_kit_stats` (el UPDATE
semanal de siempre) deja automáticamente una foto en
`rayando_cda.media_kit_stats_history` — hay un trigger
(`media_kit_stats_snapshot`) que la llena sola, no hay que acordarse de
nada nuevo al hacer el update semanal de siempre.

Con eso se grafican sparklines en dos lugares:

- **`public/index.html`**, sección "Cómo venimos creciendo": 2 gráficos
  resumidos (alcance total y audiencia total, sumando las 3 plataformas) —
  esto sí se manda a marcas, es parte del argumento de venta.
- **`dashboard/index.html`**: los 9 números completos, uno por gráfico, más
  los 2 totales. Pensado para el equipo, no se manda a marcas (por eso
  `<meta name="robots" content="noindex, nofollow">`, aunque técnicamente
  la URL es pública igual que el resto de `mediakit/` — no hay login, es
  "no se linkea desde ningún lado", no una restricción real de acceso).

La serie histórica arranca corta: no había snapshots semana a semana antes
de esto, así que se sembraron a mano los únicos 3 puntos reales y fechados
que existían (30/07/2026, 11/08/2026 y 19/08/2026 — ver
`supabase_migration_media_kit_stats_history.sql`). Un gráfico necesita al
menos 2 puntos con valor real para dibujarse; si no los tiene, la tarjeta
muestra "Necesita más semanas de datos" (dashboard) o la sección completa
queda oculta (media kit público — nunca se le muestra a una marca un
gráfico vacío o roto). `yt_vistas_30d` es el caso típico: la columna existe
desde antes pero recién se empezó a completar el 19/08/2026, así que su
gráfico va a tardar una semana más en aparecer que el resto.

## Cómo se actualizan los números (a mano, semanal)

Todos los lunes a las 13:00 UTC (09:00 en Chile) la Edge Function
`recordatorio-stats-mediakit` manda un mail a `ALERT_EMAIL_TO` con:

- cuántos días lleva sin actualizarse cada plataforma,
- los 9 números que la página lee, con el valor publicado hoy y en qué
  panel nativo se ve cada uno,
- un `update` listo para pegar en el SQL Editor con los valores actuales
  precargados (se editan solo los que se movieron).

No escribe nada en la base: solo lee y avisa. Los números se pueden pasar a
Claude Code para que corra el `update`, o pegar el SQL directo en Supabase.

| Número | Columna | Dónde se ve |
|---|---|---|
| Seguidores IG | `ig_seguidores` | Instagram > Insights |
| Vistas IG 30d | `ig_vistas_30d` | Instagram > Insights > últimos 30 días |
| Interacciones IG 90d | `ig_interacciones_90d` | Instagram > Insights > últimos 90 días |
| Seguidores TikTok | `tiktok_seguidores` | TikTok Studio > Analytics |
| Likes TikTok | `tiktok_likes` | TikTok Studio > Analytics |
| Vistas TikTok 30d | `tiktok_video_top_vistas` | TikTok Studio > últimos 30 días |
| Suscriptores YT | `yt_suscriptores` | YouTube Studio |
| Vistas totales YT | `yt_vistas_historicas` | YouTube Studio > todo el tiempo |
| Vistas YT 28/30d | `yt_vistas_30d` | YouTube Studio > últimos 28 días |

`ig_alcance_90d` sigue existiendo en la tabla pero **ningún elemento del
HTML lo muestra** (ver `public/app.js`) — no hace falta juntarlo.

Nombre engañoso, a propósito: `tiktok_video_top_vistas` ya no es "vistas del
video más visto" sino "vistas de la cuenta en 30 días" (se corrigió el campo
sin renombrar la columna, ver el plan del subsistema). La etiqueta en la
página dice lo correcto.

### Si un número queda atrasado

No se rompe nada y no se ve ningún error: la Edge Function nunca escribe
`NULL`, así que quedan publicados los últimos valores buenos, y `app.js` cae
al snapshot horneado en `index.html` si Supabase no responde. La página
tampoco muestra fecha de actualización, así que un número viejo no se
delata solo — el único control es el mail del lunes.

## Qué pasó con Windsor.ai

Los números se traían solos vía Windsor.ai (connectors `instagram`,
`tiktok_organic`, `youtube`) hasta que **venció el trial el 09/08/2026**. Se
decidió no pagar: el plan que alcanzaba (Basic, 3 data sources, US$19/mes
anual) refresca una sola vez al día del lado de Windsor, así que ni pagando
daba números hora a hora, y los 9 números están gratis en los paneles
nativos.

El código quedó en el repo, funcionando y con tests
(`supabase/functions/actualizar-stats-mediakit/`), listo para volver a
activarse si algún día se contrata el plan:

```sql
-- Reactivar el cron de Windsor.ai (solo si se paga el plan de nuevo)
select cron.schedule(
  'actualizar-stats-mediakit-diario',
  '0 8 * * *',
  $$
  select net.http_post(
    url := 'https://qfxfwfcdgqcbmdspjvtk.supabase.co/functions/v1/actualizar-stats-mediakit',
    headers := jsonb_build_object('Authorization', 'Bearer <SERVICE_ROLE_KEY>')
  );
  $$
);
```

Y hay que desprogramar el recordatorio manual (`select
cron.unschedule('recordatorio-stats-mediakit-lunes');`) para no recibir un
mail pidiendo números que ya se actualizan solos.

El secreto `WINDSOR_API_KEY` se puede dejar cargado o borrar — con el cron
desprogramado no lo lee nadie.

**Por qué había que desprogramar el cron viejo y no simplemente dejarlo
fallar:** `actualizar-stats-mediakit` manda un mail de alerta cuando algún
dato lleva más de 3 días sin actualizarse, y su cron corría **cada hora** —
con el trial vencido eso son 24 mails por día para siempre, sobre la misma
cuota de Resend que usan todas las alertas del pipeline.

## Actualizar `programas_emitidos` a mano

El mail del lunes ya lo incluye (y sugiere el siguiente número). Suelto:

```sql
update rayando_cda.media_kit_stats set programas_emitidos = <número> where id = true;
```

## Actualizar la composición de audiencia a mano

`audiencia_hombres_pct`, `audiencia_fuera_santiago_pct` y
`audiencia_hombres_25_44_pct` (sección "Y no es cualquier audiencia" de la
página) no van en el mail del lunes: la composición demográfica de una
cuenta cambia en semanas/meses, no en días. Recalcular cada 2-3 meses, o si
el equipo pide un dato más fresco antes de una reunión con una marca.

`audiencia_hombres_pct` y `audiencia_fuera_santiago_pct` se leen desde
Meta Business Suite → Estadísticas → Público → Datos demográficos: el
gráfico "Edad y sexo" da el % de hombres directo, y "Principales ciudades"
da el % en Santiago de Chile (`audiencia_fuera_santiago_pct` = 100 menos
ese número). Ojo: es por **ciudad**, no por región — "fuera de Santiago"
no es exactamente lo mismo que "fuera de la Región Metropolitana", por eso
la página dice "vive fuera de Santiago" y no "fuera de la RM". Este panel
es nativo de Meta (no depende de Windsor.ai), así que se puede volver a
mirar cuando se quiera, sin plan pago de por medio.

`audiencia_hombres_25_44_pct` (el cruzado, hombres **y** de 25 a 44) es
distinto: ese panel muestra género y edad en el mismo gráfico de barras
pero sin el cruce exacto en un número — solo visualmente. Para un número
preciso hace falta la API (`follower_demographics` con
`breakdown=age,gender`, o el connector de Windsor si alguna vez se
reactiva) — mientras no se pueda recalcular así, es preferible dejar el
último valor bueno antes que estimarlo a ojo desde el gráfico de barras.

```sql
update rayando_cda.media_kit_stats
set audiencia_hombres_pct = <pct>,
    audiencia_fuera_santiago_pct = <pct>,
    audiencia_hombres_25_44_pct = <pct>
where id = true;
```

`audiencia_25_44_pct` (el marginal de edad, "entre 25 y 44 años") sigue
existiendo en la tabla pero **ningún elemento del HTML lo muestra** desde
el 20/08/2026 — se reemplazó por `audiencia_fuera_santiago_pct` porque
las dos tarjetas de al lado, "54% hombres de 25 a 44" y "67% entre 25 y 44
años", decían "25 a 44 años" con números distintos (una es el cruce, la
otra el marginal) y confundía a quien mira la página rápido. No hace falta
seguir juntando este número.

Última actualización: 2026-08-20. `audiencia_hombres_pct` (81%) y
`audiencia_fuera_santiago_pct` (46%) salen del panel nativo de Meta
Business Suite descrito arriba, sobre un total de 14.308 seguidoras/es de
Instagram. `audiencia_hombres_25_44_pct` (54%, el cruzado) sigue congelado
desde el 2026-07-31 con el último dato real de Windsor.ai — no se ha
podido recalcular desde que venció el trial.
