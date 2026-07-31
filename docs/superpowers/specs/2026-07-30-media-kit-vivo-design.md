# Media kit vivo (subsistema 4, parte A)

Fecha: 2026-07-30
Estado: aprobado por el usuario, listo para plan de implementación

## Contexto

El media kit y pitch deck actuales (`RayandoElCDA_MediaKit_07_2026.pdf`,
`RayandoElCDA_PitchDeck_07_2026.pptx`) son piezas estáticas: cada vez que
pasa una semana los números quedan desactualizados, y actualizarlos
significa volver a tocar HTML/PPTX a mano. El usuario ya tuvo 2 reuniones
reales con marcas y recibió dos objeciones concretas:

1. **"Tienen pocos seguidores"** — 13.516 en Instagram, 4.455 en TikTok.
2. **"Son muy de nicho, no sé si nos queremos casar con un solo club"**.

Este subsistema resuelve ambos problemas con una sola pieza nueva: una
página web con marca propia que (a) trae los números de Instagram y
YouTube solos, sin que nadie los edite a mano, y (b) reescribe el relato
para responder directamente esas dos objeciones con datos ya investigados
en esta conversación (ver más abajo). El PDF/PPTX actuales quedan como
están — esta página nueva es la pieza principal que se manda de ahora en
adelante; el deck sigue disponible para reuniones presenciales si hace
falta profundizar.

## Objetivo

Un link único (`https://.../mediakit` o similar) que el usuario manda en
el primer correo en vez de adjuntar el PDF. Cualquiera que lo abre ve los
números de la semana actual, no los de cuando se generó el archivo. Tiene
un botón para descargarlo como PDF cuando haga falta adjuntarlo.

## Alcance

- Página web nueva, con el mismo sistema de diseño de marca (navy, dorado,
  rojo, "marcador LED", tickets) pero con tratamiento más editorial —
  esta es la pieza que ve la marca antes de cualquier reunión.
- Instagram, TikTok y YouTube se traen solos, los tres, vía la cuenta de
  Windsor.ai que el usuario ya tiene conectada a las tres plataformas
  (cambio de plan: originalmente TikTok iba a cargarse a mano porque su
  API pública no expone esos datos sin cuenta de partner — Windsor.ai ya
  tiene esa conexión resuelta y probada con datos reales).
- Botón "Descargar PDF" que exporta la página tal cual se ve.
- Nuevo contenido narrativo que responde directo a las dos objeciones:
  - **Alcance vs. seguidores**: el multiplicador real (vistas mensuales /
    seguidores) como prueba de que el contenido, no el tamaño de cuenta,
    genera resultado — más la prueba externa (publicaciones de Cristián
    en otro medio superando los 5 millones de vistas).
  - **No es nicho, es una de las dos hinchadas más grandes de Chile**:
    18-21% de los chilenos se declara hincha de la U (encuestas Cadem /
    La Cosa Nostra), y en asistencia real a estadios en 2024 la U convocó
    más público que Colo-Colo (549 mil vs 405 mil espectadores, fuente
    Estadio Seguro) — la hinchada que más se mueve, no solo la que más
    declara preferencia. Más el encuadre de que "casarse con un club" ya
    es la norma del sponsoring deportivo chileno (12 de 16 clubes de
    Primera tienen una casa de apuestas como sponsor exclusivo).

## No-objetivos

- No se reconstruye el pitch deck de 13 slides — sigue existiendo tal
  cual para reuniones presenciales si el usuario lo pide.
- No se cambian los planes de auspicio ni sus precios en esta pieza — el
  ajuste de precio (recomendación del análisis anterior) es una decisión
  del usuario, separada de esto.
- No hay autenticación de visitantes: el link es público, como el PDF de
  hoy (cualquiera con el link lo ve). No expone nada que el PDF actual no
  exponga ya.

## Arquitectura

```
Windsor.ai (connectors.windsor.ai) — ya conectado a Instagram,
TikTok Orgánico y YouTube de Rayando el CDA (cuenta del usuario,
hoy en trial, pasa a plan pago antes de que venza)
  GET https://connectors.windsor.ai/{connector}?api_key=...&fields=...
  probado en vivo durante el diseño: devuelve datos reales
        │
        ▼
Edge Function nueva: actualizar-stats-mediakit
  corre 1 vez por día (pg_cron, mismo mecanismo que ya usa
  refrescar-token-instagram)
  3 llamadas GET (instagram, tiktok_organic, youtube), una por
  plataforma — si una falla, las otras dos igual se guardan
        │
        ▼
rayando_cda.media_kit_stats (fila única, como instagram_token)
  todos los campos de las 3 plataformas los escribe la Edge
  Function — no queda ningún campo manual de audiencia/alcance
        │
        ▼
mediakit/ (sitio estático nuevo, HTML/CSS/JS sin build,
           mismo patrón que app/ pero sin React — es una sola
           página de solo lectura, no necesita estado ni rutas)
  lee rayando_cda.media_kit_stats vía anon key (solo SELECT)
  botón "Descargar PDF" → window.print() + CSS @media print
        │
        ▼
GitHub Pages (nuevo path, ej. /rayando-cda-review/mediakit/,
              mismo repo y workflow que ya despliega app/)
```

### Por qué esta arquitectura

- **Reusa todo lo que ya existe**: el patrón Edge-Function-con-cron
  (idéntico a `refrescar-token-instagram`), el mismo repo/deploy de
  GitHub Pages. La única pieza nueva de verdad es la API key de
  Windsor.ai como secreto.
- **Una sola fuente para las 3 plataformas** en vez de dos integraciones
  directas (Instagram Graph API, YouTube Data API) más carga manual de
  TikTok — menos código, menos puntos de falla, y de paso trae datos más
  ricos (edad/género/ciudad de la audiencia) que ya calzan con lo que
  hoy muestra el media kit a mano.
- **Sin build tool para el frontend**: es una página de solo lectura, sin
  interactividad más allá de "Descargar PDF" — HTML/CSS/JS plano es más
  simple de mantener que meter React para esto, y carga más rápido (le
  importa a alguien abriendo un link desde el celular en una reunión).
- **Riesgo a tener presente**: Windsor.ai es un servicio pago de
  terceros, hoy en trial (vence en unos días). Si el usuario no lo
  convierte a plan pago antes de que venza, la Edge Function empieza a
  fallar sus 3 llamadas — no rompe la página (ver "Manejo de errores"),
  pero los números dejan de actualizarse hasta que se reactive la cuenta.

## Datos por plataforma

Los tres connectors ya están conectados y probados (`instagram`,
`tiktok_organic`, `youtube` — nombres exactos de connector en Windsor.ai).
Todos con `date_preset` según corresponda (lifetime para seguidores,
`last_30d`/`last_90d` para lo acumulado del período).

| Campo | Connector · fields de Windsor.ai | Frecuencia |
|---|---|---|
| `ig_seguidores` | `instagram` · `followers_count` | Diaria (cron) |
| `ig_vistas_30d` | `instagram` · `views` (últimos 30 días) | Diaria (cron) |
| `ig_alcance_90d` | `instagram` · `reach_1d` sumado (últimos 90 días) | Diaria (cron) |
| `ig_interacciones_90d` | `instagram` · `total_interactions` (últimos 90 días) | Diaria (cron) |
| `tiktok_seguidores` | `tiktok_organic` · `total_followers_count` | Diaria (cron) |
| `tiktok_likes` | `tiktok_organic` · `total_likes` | Diaria (cron) |
| `tiktok_video_top_vistas` | `tiktok_organic` · `video_views_count` (máximo, tabla `Video`) | Diaria (cron) |
| `yt_suscriptores` | `youtube` · `subscriber_count` | Diaria (cron) |
| `yt_vistas_historicas` | `youtube` · `view_count` | Diaria (cron) |
| `programas_emitidos` | Manual (Supabase Studio) — no es una métrica de ninguna plataforma | Cuando el usuario quiera |
| `actualizado_en` | Seteado por la Edge Function en cada corrida | Diaria |

Si la Edge Function falla un día (token vencido, límite de API, etc.), la
página sigue mostrando el último valor guardado — nunca se cae a cero ni
muestra un error a la marca que la está mirando. Falla silenciosa desde
la perspectiva del visitante, con alerta por mail al usuario (mismo
patrón que `refrescar-token-instagram`).

## Contenido de la página

Estructura (una sola página larga, con ancla para el botón de PDF):

1. **Hero**: mismo masthead que el media kit actual (foto Estadio
   Nacional, logo, cifra hero de vistas mensuales — ahora en vivo).
2. **Quiénes somos** (sin cambios de fondo respecto al PDF actual).
3. **Nueva sección — "No vendemos seguidores, vendemos contenido que
   funciona"**: el multiplicador vistas/seguidores calculado en vivo
   desde los datos reales, + la prueba externa de Cristián (5M+ vistas
   en otro medio) como cita/dato destacado.
4. **Plataformas** (igual que el media kit actual, pero con los números
   ya viniendo de `media_kit_stats` en vez de estar hardcodeados).
5. **Nueva sección — "La hinchada de la U no es un nicho"**: el dato de
   18-21% de preferencia + el dato de asistencia real a estadios (549 mil
   vs 405 mil), con la comparación de que 12/16 clubes de Primera ya
   tienen sponsor exclusivo de rubro.
6. **Propuesta / planes** (igual que hoy — no se tocan precios acá).
7. **Botón "Descargar PDF"** flotante o en el header, visible en toda la
   página.

## Manejo de errores

- Edge Function: cada una de las 3 llamadas a Windsor.ai (`instagram`,
  `tiktok_organic`, `youtube`) es independiente — si una falla (API key
  vencida, cuenta de Windsor no pagada, límite de la API), las otras dos
  igual se guardan. Nunca todo-o-nada por una sola plataforma caída.
- Alerta por mail al usuario solo si una plataforma lleva más de 3 días
  sin actualizarse (para no generar ruido por una falla de un día). Si
  las 3 fallan el mismo día con un error de autenticación (401/403), el
  mensaje de la alerta lo dice explícito: "revisar si venció el trial de
  Windsor.ai" — es la causa más probable dado que la cuenta hoy está en
  trial.
- Página: si `media_kit_stats` no tiene fila todavía (primera vez, antes
  de la primera corrida del cron), muestra los últimos números conocidos
  del media kit actual como valores por defecto en el HTML, para que la
  página nunca se vea rota o vacía.

## Configuración inicial (una sola vez)

La API key de Windsor.ai (ya generada y probada durante el diseño de
este spec) se carga como secreto del proyecto de Supabase — nunca en
código ni en git, mismo criterio que `RESEND_API_KEY`/`PUBLISH_PIN`. El
plan de implementación deja el paso exacto (nombre del secreto y dónde
cargarlo) como su primer step, porque el usuario tiene que hacerlo a
mano desde el dashboard de Supabase — no es algo que se pueda automatizar
desde acá.

## Testing

- Edge Function: tests unitarios con fetch mockeado (mismo patrón que
  `refresh_test.ts`/`instagram_test.ts`), verificando el parseo de la
  respuesta de Windsor.ai para cada connector (`{"data": [{...}]}`), y
  que una plataforma fallando no bloquea que se guarden las otras dos.
- Página: verificación manual en el navegador (no hay suite de tests de
  frontend en este repo) contra datos reales de `media_kit_stats`
  (lectura, no escritura — sin riesgo de tocar datos de producción) y
  contra el botón de exportar a PDF.
