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
- Instagram y YouTube se traen solos (API), TikTok se carga a mano (su API
  pública no expone seguidores/vistas sin cuenta de partner).
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
- No se automatiza TikTok — se carga a mano (ver "Datos manuales").
- No se cambian los planes de auspicio ni sus precios en esta pieza — el
  ajuste de precio (recomendación del análisis anterior) es una decisión
  del usuario, separada de esto.
- No hay autenticación de visitantes: el link es público, como el PDF de
  hoy (cualquiera con el link lo ve). No expone nada que el PDF actual no
  exponga ya.

## Arquitectura

```
Instagram Graph API (graph.instagram.com)          YouTube Data API v3
  mismo token que ya usa                              nueva API key
  publicar-clip (instagram_token)                     (solo lectura,
        │                                              sin OAuth)
        ▼                                                    │
Edge Function nueva: actualizar-stats-mediakit  ◄─────────────┘
  corre 1 vez por día (pg_cron)
  trae: seguidores IG, vistas 30d, alcance 90d,
  interacciones 90d (Instagram Insights) +
  suscriptores YT, vistas históricas del canal
        │
        ▼
rayando_cda.media_kit_stats (fila única, como instagram_token)
  campos de Instagram/YouTube: escritos por la Edge Function
  campos de TikTok + "programas emitidos": editados a mano
  por el usuario directo en Supabase Studio (tabla ya visible
  ahí, sin UI nueva que mantener para esto)
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

- **Reusa todo lo que ya existe**: el token de Instagram, el patrón
  Edge-Function-con-cron (idéntico a `refrescar-token-instagram`), el
  mismo repo/deploy de GitHub Pages. Nada de infraestructura nueva que
  aprender.
- **Sin build tool para el frontend**: es una página de solo lectura, sin
  interactividad más allá de "Descargar PDF" — HTML/CSS/JS plano es más
  simple de mantener que meter React para esto, y carga más rápido (le
  importa a alguien abriendo un link desde el celular en una reunión).
- **YouTube con API key, no OAuth**: `channels.list` con las estadísticas
  del canal es público, no necesita el flujo OAuth que ya usa
  `publicar.py` para subir videos — una API key nueva y simple alcanza.
- **Datos manuales en Supabase Studio, no una UI nueva**: TikTok y
  "programas emitidos" cambian poco y el usuario ya sabe usar el editor
  de tablas de Supabase (lo usa para todo lo demás) — construir una
  pantalla de administración solo para 3-4 campos que se tocan cada tanto
  no se justifica.

## Datos por plataforma

| Campo | Fuente | Frecuencia |
|---|---|---|
| `ig_seguidores` | Instagram Graph API (`/{ig-user-id}?fields=followers_count`) | Diaria (cron) |
| `ig_vistas_30d`, `ig_alcance_90d`, `ig_interacciones_90d` | Instagram Insights API | Diaria (cron) |
| `yt_suscriptores`, `yt_vistas_historicas` | YouTube Data API (`channels.list?part=statistics`) | Diaria (cron) |
| `tiktok_seguidores`, `tiktok_likes`, `tiktok_video_top_vistas` | Manual (Supabase Studio) | Cuando el usuario quiera |
| `programas_emitidos` | Manual (Supabase Studio) | Cuando el usuario quiera |
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

- Edge Function: si Instagram o YouTube fallan, seguir con la otra
  plataforma y guardar lo que sí se pudo traer — no todo o nada. Alerta
  por mail al usuario solo si una plataforma lleva más de 3 días sin
  actualizarse (para no generar ruido por una falla de un día).
- Página: si `media_kit_stats` no tiene fila todavía (primera vez, antes
  de la primera corrida del cron), muestra los últimos números conocidos
  del media kit actual como valores por defecto en el HTML, para que la
  página nunca se vea rota o vacía.

## Testing

- Edge Function: tests unitarios con fetch mockeado (mismo patrón que
  `refresh_test.ts`/`instagram_test.ts`), verificando el parseo de la
  respuesta de Instagram Insights y de YouTube `channels.list`, y que una
  plataforma fallando no bloquea que se guarde la otra.
- Página: verificación manual en el navegador (no hay suite de tests de
  frontend en este repo) contra datos reales de `media_kit_stats`
  (lectura, no escritura — sin riesgo de tocar datos de producción) y
  contra el botón de exportar a PDF.
