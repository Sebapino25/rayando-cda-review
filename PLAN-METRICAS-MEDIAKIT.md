# PLAN-METRICAS-MEDIAKIT.md

Plan para que los mediakits de **Rayando el CDA** y **Siempre Pasa Algo** se alimenten solos de métricas, con una sola infraestructura para ambos programas. Escrito el 23/10/2026 desde el chat de planificación (Fable). Dejar en la raíz del repo `Sebapino25/rayando-cda-review` y subir al Proyecto de claude.ai de Rayando el CDA.

## Objetivo
Dejar de sacar pantallazos. Un trabajo semanal recoge seguidores, visualizaciones, espectadores e interacciones de Instagram, Facebook, YouTube y TikTok de los dos programas, los guarda como fotos fechadas en Supabase, y los dos mediakits (páginas HTML en GitHub Pages) leen de ahí al cargar. Si una fuente falla, el mediakit sigue mostrando el último dato bueno con su fecha de corte.

## Hitos
- Semana del 27/10: Fase 0 y 1 listas (base de datos). Mediakit SPA sigue con números fijos.
- Semana del 03/11: Meta (IG + FB) de ambos programas entrando solo (Fase 2).
- Semana del 10/11: YouTube y TikTok (Fases 3 y 4) y cron (Fase 5).
- Semana del 17/11: ambos mediakits leyendo de Supabase (Fase 6). Primera semana sin pantallazos.

## Decisiones de diseño (validar en Fase 0, no rehacer sin motivo)

**Dónde viven los datos.** Proyecto Supabase "La Herramienta Rayando el CDA" (org Sebapino25, id `qfxfwfcdgqcbmdspjvtk`), el mismo donde ya está `rayando_cda.media_kit_stats` y el schema `siempre_pasa_algo`. Se crea un schema nuevo y compartido, `mediakit`, en vez de duplicar tablas por programa: la columna `programa` distingue a cada uno. La tabla actual `rayando_cda.media_kit_stats` se migra a este schema y se deja de usar.

**Se guardan fotos, no se sobreescribe.** Cada corrida inserta una fila por programa, plataforma, fecha de corte y ventana (7, 28 o 90 días). Así se pueden calcular crecimientos ("+37% en 3 meses") sin depender de que la plataforma entregue históricos, y el tope de 30 días de Windsor deja de importar: el histórico lo acumulamos nosotros.

**Fuente por plataforma.**
- Instagram y Facebook: Meta Graph API directa, con la app de Meta que ya publica Reels desde La Herramienta. Es gratis, estable y entrega seguidores, alcance, vistas, interacciones, visitas al perfil y demografía de seguidores. Requiere que la cuenta de SPA (IG profesional + Página de Facebook) autorice la misma app (paso manual, Fase 2).
- YouTube: YouTube Analytics API con el mismo proyecto de Google que ya sube videos. Entrega vistas, horas, suscriptores ganados y demografía por rango de fechas. Requiere un consentimiento OAuth nuevo con el scope `yt-analytics.readonly`, uno por canal.
- TikTok: no hay API de analítica abierta para creadores. Primera opción Windsor.ai (`tiktok_organic`, ya conectado, plan gratis con tope de 30 días y conexión inestable, por eso cada corrida reintenta hasta 3 veces). Segunda opción, si Windsor no responde dos semanas seguidas: formulario manual de 6 campos en la app de revisión, protegido con el mismo PIN de "Publicar en redes".
- Demografía (edad, sexo, país): se guarda aparte y con menos frecuencia (mensual), porque cambia poco y Meta la entrega como porcentajes, no como conteos.

**Dónde corre.** GitHub Actions con cron, no el PC de Seba ni Task Scheduler: corre aunque el computador esté apagado y los secretos quedan en GitHub Secrets. Lunes 08:00 hora de Chile (antes del programa). Si una fuente falla, el job registra el error en una tabla `mediakit.corridas` y sigue con las demás; no aborta todo.

**Cómo leen los mediakits.** Una vista `mediakit.v_actual` entrega, por programa y plataforma, el último corte y la variación contra 90 días antes. Lectura pública con la anon key y RLS de solo lectura sobre la vista; escritura solo con service_role desde el job. Cada mediakit tiene sus números "horneados" en el HTML como respaldo: si el fetch falla, se ve el último dato publicado a mano y el pie de página dice la fecha.

**Qué no cubre este plan.** No cambia La Herramienta ni la publicación. No mete métricas por clip (eso es otro plan). No decide precios ni diseño de los mediakits.

## Modelo de datos (schema `mediakit`)

```
programas      id text PK ('rayando_cda' | 'siempre_pasa_algo'), nombre, cuentas jsonb
               (ig_user_id, fb_page_id, yt_channel_id, tiktok_handle)

snapshots      id, programa FK, plataforma ('instagram'|'facebook'|'youtube'|'tiktok'),
               fecha_corte date, ventana_dias int,
               seguidores int, seguidores_nuevos int, vistas bigint, espectadores bigint,
               interacciones bigint, likes int, comentarios int, compartidos int,
               visitas_perfil int, pct_no_seguidores numeric,
               fuente ('api'|'windsor'|'manual'), raw jsonb, creado_en timestamptz
               UNIQUE (programa, plataforma, fecha_corte, ventana_dias)

demografia     id, programa, plataforma, fecha_corte, tipo ('seguidores'|'espectadores'),
               genero jsonb, edades jsonb, paises jsonb, ciudades jsonb, fuente

destacados     id, programa, plataforma, fecha_corte, titulo, vistas bigint, url
               (los "golpes" del mediakit; top 10 por corrida)

corridas       id, iniciado_en, terminado_en, programa, plataforma, ok bool, error text

v_actual       vista: por programa y plataforma, última fila de ventana 90 (28 en YouTube
               si 90 no existe), seguidores y delta vs el snapshot más cercano a 90 días atrás
```

## Fases

### Fase 0 · Reconocimiento y orden
- **Modelo:** Opus · **Sesión:** conversación nueva en Code · **Rama:** `metricas-mediakit`
- Objetivo: saber exactamente qué hay antes de tocar nada.
- Pasos: leer cómo se llena hoy `rayando_cda.media_kit_stats` (script, columnas, última fecha); listar qué permisos tiene la app de Meta y qué token usa la Edge Function de publicación; ver qué scopes tiene el OAuth de YouTube del pipeline; confirmar en Windsor qué cuentas de TikTok están conectadas; revisar el mediakit actual de Rayando (`/mediakit/`) para ver cómo carga los números. Crear `BITACORA.md` si no existe y agregar la primera entrada. No crear tablas ni cambiar código.
- Listo cuando: el reporte dice, por plataforma y programa, "tenemos acceso / falta X y lo hace Seba así".

### Fase 1 · Base de datos
- **Modelo:** Opus · **Sesión:** /clear antes
- Objetivo: schema `mediakit` con las 5 tablas y la vista, RLS, y los datos históricos de Rayando migrados desde `media_kit_stats`. Insertar también a mano el corte de SPA del 11/09/2026 (los números del informe de septiembre) como primer snapshot, para que el crecimiento se pueda calcular desde ya.
- Fuera de alcance: cualquier recolección.
- Listo cuando: `select * from mediakit.v_actual` devuelve filas para los dos programas y el anon key puede leer la vista pero no insertar.

### Fase 2 · Recolector Meta (Instagram + Facebook), ambos programas
- **Modelo:** Opus · **Sesión:** /clear antes
- Paso manual previo (Seba, con Samuel): SPA tiene que entrar a la app de Meta. Seba le pide a Samuel que lo agregue como administrador de la Página de Facebook de SPA y que la Página tenga vinculada la cuenta de Instagram profesional. Con eso Seba genera el token de página desde la misma app. Si Samuel prefiere no dar administración, la alternativa es que él autorice la app con su propio usuario; se decide en esta fase.
- Objetivo: `metricas/collect_meta.py` que, para cada programa, consulta seguidores, alcance, vistas, interacciones, visitas al perfil, origen seguidores/no seguidores (ventanas 28 y 90), top 10 de contenidos por vistas, y demografía de seguidores; inserta en `snapshots`, `destacados` y `demografia`.
- Listo cuando: corrida a mano desde el PC inserta un snapshot de hoy para los dos programas y los números coinciden razonablemente con Insights (±5%).

### Fase 3 · Recolector YouTube
- **Modelo:** Sonnet · **Sesión:** /clear antes
- Paso manual previo: consentimiento OAuth con `yt-analytics.readonly` para el canal de Rayando (Seba) y para el de SPA (Samuel abre un link que genera el script y pega el código).
- Objetivo: `metricas/collect_youtube.py` con vistas, horas, suscriptores ganados y perdidos, demografía por sexo y edad, países; ventanas 28 y 90.
- Listo cuando: snapshot de YouTube para los dos programas con los mismos números que YouTube Studio.

### Fase 4 · Recolector TikTok
- **Modelo:** Sonnet · **Sesión:** /clear antes
- Objetivo: `metricas/collect_tiktok.py` vía Windsor.ai (`tiktok_organic`), con 3 reintentos y registro en `corridas`. Más el formulario manual en la app de revisión (6 campos: seguidores, vistas, espectadores, likes, comentarios, compartidos) que escribe con `fuente='manual'`.
- Listo cuando: una corrida con Windsor caído deja la fila en `corridas` con el error y el formulario manual inserta correctamente.

### Fase 5 · Cron en GitHub Actions
- **Modelo:** Sonnet · **Sesión:** /clear antes
- Objetivo: workflow `.github/workflows/metricas.yml`, lunes 08:00 Chile, secretos en GitHub (Supabase service_role, token Meta, refresh tokens de YouTube, API key Windsor). Al terminar, si alguna plataforma falló, enviar un correo a Seba (Gmail vía SMTP con app password) con el detalle.
- Listo cuando: el workflow corre a mano desde la pestaña Actions y aparecen snapshots nuevos.

### Fase 6 · Conectar los mediakits
- **Modelo:** Sonnet · **Sesión:** /clear antes
- Objetivo: los dos mediakits (SPA y el nuevo de Rayando) hacen fetch de `v_actual`, `destacados` y `demografia` con la anon key y rellenan los elementos `data-k`; si falla el fetch, quedan los valores horneados. Formato chileno (152.129; 21,2 M). Pie de página con la fecha de corte real. Publicar SPA en `/mediakit-spa/` del mismo GitHub Pages (o repo propio si SPA lo prefiere).
- Listo cuando: al abrir cada mediakit se ven los números del último lunes sin tocar el HTML.

## Trabajo en paralelo: rediseño del mediakit de Rayando
Es diseño, no pipeline, y no depende de las fases 0 a 5. Se hace en un chat aparte (Proyecto Rayando el CDA, modelo Sonnet; Opus solo si el diseño se traba). Insumos: el HTML del mediakit de SPA como base de estructura, los números actuales de Rayando, la línea gráfica navy/rojo/dorado/azul eléctrico con Big Shoulders Display, y el cambio de modelo comercial: tarifario por pieza y packs en vez de planes mensuales (misma lógica que SPA, con valores proporcionales a su audiencia: reel integrado ~$180k, mención en vivo ~$120k, programa presentado por ~$700k, packs Golpe y Temporada). Entregable: `mediakit/index.html` nuevo con los mismos `data-k` que SPA, para que la Fase 6 conecte los dos igual.

## Reglas
- Una fase por sesión de Code. /clear entre fases. Reporte de máximo 10 líneas al cerrar.
- Nunca guardar tokens en el repo: `.env` local y GitHub Secrets.
- Toda tabla nueva lleva comentario SQL con qué guarda y quién la escribe.
- Si Sonnet falla dos veces en una fase, se repite con Opus.
