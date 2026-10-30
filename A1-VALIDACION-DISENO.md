# A1 — Validación del diseño (configuración por programa)

**30 oct 2026.** Revisión de solo lectura del bloque A1 de `PLAN-UNIFICACION-Y-SERVICIO.md`, contrastado con `A0-RECONOCIMIENTO.md` y con el código real de `main` (producción) y `multiprograma-spa` (`spa-herramienta`). No se cambió nada.

## Veredicto
El diseño es correcto en lo central: el mecanismo de perfiles ya existe en `multiprograma-spa`, es sólido (una clave mal escrita en el JSON falla fuerte, hay tests) y SPA ya corre con él. A1 no es "construir la configuración por programa", es **fusionarla con main sin cambiarle nada a Recda** y cerrar cinco huecos que el plan no menciona. Se puede aprobar con los ajustes de abajo.

## Huecos y riesgos encontrados (por gravedad)

### 1. El calendario del 5 nov no calza (alto)
El plan pone la primera prueba real de SPA el jue 5 nov. Para eso A1 tendría que estar en `main` de producción antes del jueves en la tarde, y la única ventana permitida es **mié 4 nov 10:00 a jue 5 nov ~20:00**, justo después del cap. 82. Es demasiado justo para una fusión con 7 conflictos.
**Ajuste:** el 5 nov SPA se procesa como hoy, desde `spa-herramienta` con `PROGRAMA=spa`. La primera prueba unificada de SPA pasa al **jue 12 nov (cap. 7)** y la de Recda al lun 9 nov (cap. 83). `spa-herramienta` queda intacto como respaldo hasta A5.

### 2. Dónde se hace la fusión (alto)
A0 recomienda fusionar dentro de `rayando-cda-dev`, pero ese worktree **está en la rama `metricas-mediakit`**, no libre. Y `multiprograma-spa` no se puede abrir ahí porque Git no deja la misma rama en dos worktrees (ya la tiene `spa-herramienta`).
**Ajuste:** en `rayando-cda-dev`, confirmar `git status` limpio en `metricas-mediakit`, crear la rama nueva `unificacion` desde `multiprograma-spa` y fusionar `main` en ella. `multiprograma-spa` no se toca. Ojo: `metricas-mediakit` tampoco está en `main`; queda como tercera rama a fusionar después de A1 (no mezclarla ahora).

### 3. La tarea automática no sirve para dos programas tal como está (alto)
`auto_procesar.ps1` tiene fijas la carpeta de Recda, la ruta de producción y el nombre de la tarea; guarda su estado (`grabaciones_estado.json`, `ritmo_auto.json`) en un solo `logs_auto`, y además **cambia el intervalo de la propia tarea** cuando está ociosa. La ventana es mar 00:00 + 34 h, así que una grabación de SPA del jueves nunca se vería. Detalle: la copia del `.ps1` en `spa-herramienta` es idéntica a la de producción, o sea, si alguien la corre desde ahí, procesa producción.
**Ajuste:** el mismo script con un parámetro `-Programa` (default `rayando`), que saque carpeta base del perfil y guarde el estado en `logs_auto\<programa>\`. **Dos tareas** en Task Scheduler: `RayandoCDA_AutoProcesar` sin cambios (mar 00:00, 34 h) y una nueva `SPA_AutoProcesar` (vie 00:00, 34 h). Dos tareas es más seguro que una con dos disparadores, porque el ajuste de intervalo muta la tarea entera y las de Recda no se mezclan con las de SPA. La nueva ventana de "no tocar producción" suma jue 21:00 a sáb 10:00.

### 4. Credenciales heredadas por omisión (alto cuando SPA publique)
`.env.spa` pisa a `.env`, pero **todo lo que no esté en `.env.spa` se hereda de Recda**. Hoy funciona porque las claves de Instagram y TikTok están puestas vacías a propósito, pero cualquier clave nueva (Facebook, refresh token de YouTube, etc.) que alguien olvide en `.env.spa` haría que SPA publique en las cuentas de Recda.
**Ajuste:** en `config.py`, una lista de claves "de cuenta" (YouTube token, IG, TikTok, Facebook) que **nunca se heredan**: si el programa no las define, quedan vacías y la publicación a esa red se salta con aviso. Test que lo verifique.

### 5. La publicación no puede vivir en el JSON (medio, es de A2 pero se decide en A1)
El plan dice que `programas/<slug>.json` lleva "los destinos de publicación". Pero quien publica es la Edge Function `publicar-clip`, que corre en Supabase y no puede leer archivos del PC; hoy usa secretos globales (`YOUTUBE_REFRESH_TOKEN`, `PUBLICAR_*`) y las tablas de tokens del schema `rayando_cda`.
**Ajuste:** el JSON solo dice *qué redes usa* el programa (para la app y el pipeline). Las credenciales de publicación van en secretos de la función con sufijo (`YOUTUBE_REFRESH_TOKEN_SPA`, …) y tokens en las tablas del schema de cada programa; la función recibe `programa` y elige. A1 solo deja definido ese contrato; se construye en A2.

### 6. Capítulos atados a Recda (medio)
`capitulos.py` asume lunes (y martes antes de las 06:00) y `config.py` de main tiene fijos "Del capítulo N de Rayando el CDA" y `#RECDA{n}`. La tabla vive en `rayando_cda.capitulos`.
**Ajuste:** pasar al perfil `DIA_PROGRAMA` (0 = lunes, 3 = jueves), `CAPITULO_LINEA_YOUTUBE` y `CAPITULO_HASHTAG`. Para SPA, **misma tabla dentro de su propio schema** (`siempre_pasa_algo.capitulos` + `clips.capitulo`, migración aditiva) en vez de una columna `programa`: así no cambia nada en Recda y `SUPABASE_SCHEMA` ya hace el cambio solo. Esto choca con la regla de `CLAUDE.md` "no tocar el schema `siempre_pasa_algo`", que hay que levantar explícitamente para A1.

## Ajustes al diseño (resumen)
1. **Nombre del programa:** mantener `rayando` como nombre interno (es el default, el de los tests y el de la tarea; renombrarlo no aporta y arriesga producción). Aceptar `recda` como alias en `--programa`, y usar `/recda` solo como ruta de la app (A3).
2. **`--programa`:** como `config.py` se evalúa al importarse, la bandera tiene que fijar `PROGRAMA` antes de cualquier `import config`. Hacerlo en un helper chico que usen todos los scripts de entrada, y que la variable de entorno siga funcionando.
3. **`rayando.json`:** crearlo casi vacío (solo lo que no está en el código: redes, día del programa, tarea). Los valores de Recda siguen siendo los default del código.
4. **Red de seguridad para Recda:** un test "foto" que compare *todas* las constantes de `config.py` de `main` con las de `unificacion` sin `PROGRAMA` (salvo las claves nuevas). Si cambia una sola, falla. Más el `--dry-run` del mkv del 26/10, que debe dar capítulo 81 y las mismas descripciones con `#RECDA81`.
5. **dotenv en un solo lugar:** `publicar.py` vuelve a cargar `.env` después de `config`. Hoy funciona por el orden de imports; dejar toda la carga en `config.py`.
6. **Rutas viejas de SPA** (`metadata.json` con `C:\Siempre pasa Algo\...`): script aparte e idempotente, fuera de A1, antes del 12 nov.
7. **Partir A1 en dos sesiones:**
   - **A1a (sin cambio de comportamiento):** rama `unificacion`, fusión de `main`, 7 conflictos, alias `recda`, `--programa`, `rayando.json`, test foto, tests de los dos programas, dry-run Recda y SPA. Puede ir a `main` el mié 4 nov después de las 10:00.
   - **A1b:** capítulos por programa + migración SPA, `auto_procesar.ps1 -Programa` + tarea `SPA_AutoProcesar`, bloqueo de credenciales heredadas, contrato de publicación. A `main` entre el 5 y el 9 nov, fuera de ventanas; prueba real con cap. 83 (Recda) y cap. 7 (SPA).

## Decisiones abiertas para Seba
- **Fecha (decidido 30 oct, noche):** se intenta llegar al cap. 6 (jue 5 nov) con A1a en `main`; SPA se procesa ese día a mano desde producción con `PROGRAMA=spa`. Si A1a no está en `main` el mié 4 nov a las 10:00, el cap. 6 sale desde `spa-herramienta` como hoy y la prueba pasa al cap. 7 (12 nov). A1b (tarea de SPA, capítulos, credenciales) va para el 12 nov en cualquiera de los dos casos.
- **Capítulo de SPA (decidido 30 oct):** el hashtag es `#SPAreírse6` (confirmado por Seba: "SPAreírse #6" es el hashtag, sin espacio al ponerlo); la línea de descripción puede ser "SPAreírse #6". Numeración: cap. 5 = 29 oct, 6 = 5 nov, 7 = 12 nov.
- Levantar la regla "no tocar `siempre_pasa_algo`" para la migración de capítulos de SPA.
- `MANTENER_CAPITULOS=2` borra filas de SPA aunque estén publicadas. Hoy da igual (Cristián descarga y publica a mano), pero cuando SPA publique solo se pierden ids de YouTube y métricas. Revisarlo en A2.
- Espacio Supabase (1 GB gratis): SPA ~240 MB por capítulo × 2 + Recda. Antes de A4 (videos horizontales) hay que ver si se paga el plan Pro o se sacan los videos de Storage.

## Espacio en Supabase (revisado 30 oct, 21:50)
Storage: **701 MB de 1 GB** (plan gratis). Base de datos: 15 MB. El repo en GitHub pesa ~10 MB: no es problema.
| Bucket | MB | Qué es |
|---|---|---|
| `clips-video-spa` | 358 | 2 capítulos de SPA (22 y 29 oct, 11 clips c/u, ~175 MB por capítulo) + 1 archivo huérfano del 15 oct (8 MB) |
| `clips-video` | 213 | 47 clips de Recda **ya publicados** desde julio; el video sigue en Storage aunque ya está en YouTube |
| `portadas` | 96 | 81 MB son 42 portadas personalizadas (`custom/`) |
| `dr-fotos-equipos` | 30 | Doctor Rino (otro proyecto comparte este Supabase) |
| `portadas-spa` | 5 | |

Proyección para la semana: cap. 82 de Recda (+~30 MB) y cap. 6 de SPA (+~175 MB **antes** de que la limpieza borre el del 22 oct) → pico ~910 MB. Pasa, pero sin margen. Si el cap. 6 trae más clips o más largos, se corta.
Qué liberar sin tocar código: borrar de Storage los videos de los clips de Recda publicados hace más de 30 días (~190 MB; YouTube los tiene) y el huérfano de SPA. Requiere confirmación de Seba. Las portadas `custom/` se dejan. Egreso (5 GB/mes en el plan gratis) no se pudo medir desde aquí: revisarlo en el panel de Supabase, Settings > Usage.

## Egreso de Supabase (pantallazos de Seba del 29 oct)
El aviso de la organización es por **egreso**, no por espacio: "exceeded its quota in the previous billing cycle; projects will be restricted from 24 Nov 2026". Plan gratis: 5 GB de egreso al mes para toda la organización. Ciclo 3 oct a 3 nov, estimado desde los gráficos: La Herramienta ~1,2 GB sin caché + ~4,3 GB con caché; Agencia del Barrio ~0,8 + ~1,8 GB; Finanzas Hogar 0. Falta confirmar si el egreso con caché cuenta dentro de los 5 GB (ver "Egress: X / 5 GB" arriba de la página Usage).
Causa principal en La Herramienta: los videos se sirven desde Storage cada vez que se abren o reproducen en la app; SPA no sube a YouTube y Cristián descarga los clips desde Historial.
Cifras exactas (Usage de la organización, 30 oct 19:48): egreso con caché **7,28 / 5 GB (146 %)**, almacenamiento **1,02 / 1 GB (102 %)**, egreso sin caché 2,05 / 5 GB. La Herramienta: 5,22 GB caché, 1,24 GB egreso, 0,59 GB storage. Agencia: 2,06 / 0,81 / 0,43. Ritmo actual ~270 MB/día: el próximo ciclo (3 nov a 3 dic) también cerraría pasado.
De dónde sale: la app ya previsualiza Recda con YouTube; el mp4 de Supabase se baja solo para clips sin YouTube (todos los de SPA), en el panel de TikTok, en el botón de descarga, y cuando Instagram/TikTok van a buscar el archivo al publicar.
Qué hacer: (1) borrar los 40 videos de Recda publicados antes del 1 oct (aprobado 30 oct; script `liberar_storage_recda.py`, pendiente de correr con permiso); (2) en A1, borrar de Supabase el mp4 de cada clip cuando ya está publicado en todas las redes (limpieza semanal), y revisar SPA con un mp4 más liviano; (3) decisión de Seba pendiente (tarjeta 30 oct): Pro ahora (US$25/mes, 100 GB storage, 250 GB egreso), seguir gratis recortando (SPA con 1 capítulo, limpiar Agencia), o Pro cuando entre el primer cliente.

## Decisión de Seba (30 oct, 22:50): YouTube como bodega, Supabase de paso
Sin Pro. SPA pasa a subir a su propio canal de YouTube como no listado (`SUBIR_YOUTUBE=true` + `youtube_token_spa.json`), igual que Recda; la app previsualiza desde YouTube. Supabase guarda el mp4 solo hasta que el clip está publicado en todas las redes (IG y TikTok lo toman de ahí) y después se borra, en los dos programas. El embudo (videos de temática, capítulos) va directo a YouTube, nunca a Supabase.
Esto adelanta a A1 la parte de YouTube de A2. El canal de SPA ya está verificado y monetizado (+45.000 suscriptores), así que no hay trámite de verificación. Pasos de Seba (confirmados 30 oct): (1) que Samuel lo agregue como administrador del canal de SPA; (2) crear un proyecto de Google Cloud propio para SPA con la API de YouTube Data v3 habilitada y credenciales OAuth de escritorio (mismo tipo que las de Recda); Code le da los pasos exactos en A1a y Seba lo hace a mano. Cuota: 10.000 unidades/día por proyecto, ~1.600 por subida; con proyecto propio SPA sube hasta 6 clips por día de cuota, así que en A1a hay que ver si Recda tiene cuota ampliada y pedirla para SPA, o repartir las subidas. Si el acceso al canal no llega antes del mié 4 nov, el cap. 6 sale como hoy y SPA entra por YouTube con el cap. 7.
A1a suma: subida de SPA a YouTube con token propio, borrado automático del mp4 tras publicar (Recda y SPA), y ajustar `MANTENER_CAPITULOS`. Regla "no tocar `siempre_pasa_algo` ni su app" del CLAUDE.md: Seba la levanta para la unificación (pedido del 30 oct).

## Modelo y chats
- **A1a:** sesión nueva de Claude Code con **Opus**, en `rayando-cda-dev`, pasándole este archivo y A0. `/clear` antes de A1b.
- **A1b:** otra sesión nueva de Claude Code con **Opus**.
- No hace falta otro chat de validación: este documento cumple el paso 3 del plan.
