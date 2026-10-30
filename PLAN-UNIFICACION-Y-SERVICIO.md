# PLAN — Unificar La Herramienta (Recda + SPA) y venderla como servicio

**Borrador del 30 oct 2026.** Hecho en el chat "Unificar herramienta SPA con Recda". Reemplaza la Fase 4 de `PLAN-ORDEN-2026-10-30.md` cuando Seba lo apruebe. Esos Viejos Pa' Buenos queda descartado (no respondieron).

## La idea central: el embudo de tres niveles
| Nivel | Qué es | Para qué | Formato |
|---|---|---|---|
| 1. Short | Cuña corta y llamativa (polémica o gancho) | Atraer | Vertical, < 60 s |
| 2. Video de la temática | Un tema completo | Crear fidelidad | Horizontal, 3 a 10 min según el programa |
| 3. Capítulo completo | El programa o la entrevista entera | Para la comunidad | Horizontal |

Cada short enlaza a su video de la temática, y cada video de la temática enlaza al capítulo (en la descripción y en el comentario fijado). El nivel 2 ya estaba decidido como "cápsulas horizontales" (22 oct, `PLAN-CAPSULAS.md`); este plan lo vuelve el estándar para todos los programas y clientes.

Cómo se detectan los temas, según el programa:
- **SPA:** el programa ya viene por temas (8 a 10 videos comentados, guion en Word). Los temas se cortan por la estructura del guion, no por IA. Es lo más fácil y lo más confiable.
- **Rayando:** es conversación libre, así que hoy la IA tiene que encontrar los temas. Si Seba estructura el programa en bloques, se vuelve como SPA.
- **Clientes de entrevista (deudas):** se usa una lista de temas que el cliente prepara antes de grabar, y la IA ordena la entrevista según esa lista.

---

## Bloque A — Una sola herramienta para Recda y SPA
**Meta:** Cristián procesa, revisa y publica un capítulo de SPA y uno de Recda **con los mismos pasos**, cada uno en sus propias redes.

- **A0. Reconocimiento (Claude Code, Sonnet, 1 sesión, sin cambios de código).** Comparar el worktree `spa-herramienta` con `main`. Revisar qué de los 17 parches ya está en `main` y qué falta. Ver en qué quedó la migración de SPA del otro chat. Listar todo lo que difiere entre los dos programas: logo, zócalo, prompt, topes de clips, layout vertical dividido, cuentas y tabla de Supabase. **Resultado:** la tabla de "qué debe ser configurable". Ojo: los archivos de `la-herramienta` aparecen como hardlinks (posible resto del traslado); Code debe verificar que las rutas viejas no sigan apuntando a los mismos archivos.
- **A1. Configuración por programa.** Una sola rama (`main`). `pipeline/programas/<slug>.json` (ya existe `spa.json`) pasa a contener todo lo de la tabla de A0, más los destinos de publicación. El pipeline recibe `--programa spa|recda`. Se retira la dependencia de parches.
- **A2. Redes propias de SPA.** YouTube, Instagram, TikTok y Facebook de SPA, cada uno con su credencial guardada en un `.env` por programa. **Paso manual de Seba:** autorizar cada cuenta (OAuth) cuando Code le dé los links. TikTok depende de la aprobación de la app (verificar el estado en `docs/tiktok-direct-post-estado.md`).
- **A2b. Video en YouTube, no en Supabase (decidido 30 oct).** La organización de Supabase (plan gratis) superó la cuota: almacenamiento 1,02 de 1 GB y tráfico desde caché 7,3 de 5 GB en el ciclo del 3 oct al 3 nov. Si sigue sobre la cuota, los proyectos quedan restringidos desde el 24 nov. Regla para los dos programas:
  - **YouTube es el archivo permanente.** SPA sube shorts, temáticas y capítulos como no listados a su canal propio, que ya está verificado, monetizado y tiene más de 45 mil seguidores, igual que Recda. La app reproduce desde YouTube.
  - **Supabase es solo un paso temporal.** El mp4 queda en el bucket solo hasta publicarse en Instagram y TikTok, porque esas plataformas necesitan un enlace directo al mp4 y no pueden tomarlo desde YouTube. Después se borra solo y la fila queda con `video_url = null`. Hay que hacerlo en Recda y en SPA.
  - **Proyecto de Google Cloud aparte para SPA.** La cuota de la API de YouTube (10.000 puntos al día, unas 6 subidas) es por proyecto de Google Cloud, no por canal. Con un solo proyecto, los dos programas se quitarían cuota entre sí. **Paso manual de Seba:** crear el proyecto, activar YouTube Data API v3, crear la credencial OAuth y autorizar el canal de SPA.
  - **Limpieza inicial:** `liberar_storage_recda.py` borra los mp4 de Recda publicados antes del 1 oct (40 videos). El plan ya está revisado; el `--apply` falta y lo corre Seba.
- **A3. Módulo propio en la app.** En vez de `?p=spa`, una entrada por programa (ej. `/spa` y `/recda`), con su marca: SPA en synthwave (azul noche, magenta, cian). La misma interfaz y los mismos botones, para que Cristián no tenga que aprender dos cosas.
- **A4. Embudo en los dos programas.** El video de la temática se genera para SPA por guion y para Recda por IA. Se enlazan short → tema → capítulo. Verificar si la API de YouTube permite fijar el "video relacionado" de un Short; si no, ese paso lo hace Cristián a mano y queda en el checklist de la app.
- **A5. Paso a producción y limpieza.** Se archivan el worktree `spa-herramienta` y `parches-herramienta`. Se actualizan `CLAUDE.md`, `BITACORA.md` y la ficha 3.

**Calendario:** no se toca producción entre el lunes 23:00 y el miércoles 10:00 (la tarea automática). A1 a A3 se hacen en `rayando-cda-dev`. La primera prueba real de SPA es con el capítulo del jueves 5 nov (SPAreírse #6; meta de Seba: llegar con la unificación lista y, si no alcanza, decidir qué se mantiene y qué se aplaza); la de Recda, con el lunes siguiente.

**Antes de partir:** hacer push de `main` de producción (quedó adelante de GitHub con el commit de rutas del 30 oct).

---

## Bloque B — La Herramienta como servicio (módulo para el cliente de Daniela Rivas)
**Meta:** un cliente nuevo se agrega en ~30 min, como un programa más del bloque A, sin tocar código.

- **B0. Definición con Daniela y el cliente (sin código, puede ir en paralelo a A).** Hay que cerrar tres cosas:
  - **Piezas por mes.** Propuesta para conversar: 1 entrevista → 8 shorts, 3 videos de temática y 1 capítulo.
  - **Criterios de cuña.** Llamativa sí, consejo concreto no: en deudas, una cuña fuera de contexto puede sonar a asesoría.
  - **Preparación.** El cliente trae una lista de temas antes de grabar, y firma una aprobación escrita antes de publicar.
- **B1. El cliente como programa.** Un `programas/<cliente>.json` con su logo, colores y prompt educativo (con la regla "nada que suene a consejo concreto"). Sin publicación automática.
- **B2. Revisión en dos etapas.** Estados nuevos en la app: "revisado por Seba" y después "aprobado por el cliente". El cliente ve una galería de solo lectura con PIN, sin marca Rayando, donde aprueba o comenta.
- **B3. Piloto.** Primera entrevista real (Canon + micrófonos DJI). Medir las horas de revisión, porque eso define si los $100.000 de la herramienta dejan margen.
- **B4. Plantilla para clientes nuevos.** Un checklist de alta (logo, colores, prompt, temas, PIN) para replicarlo con 2, 3 o 4 clientes más.

**Precio inicial (29 oct):** $100.000 al mes por la herramienta + $100.000 por grabación y entrevista. Si el cliente se graba solo, paga solo la herramienta.

**Sirve también para:** los videos horizontales que quieren René (Recda) y Samuel (SPA); es el mismo nivel 2 del embudo.

**Después (no ahora):** Paso 2, un módulo de agencia para Daniela, solo después de afinar los agentes de la agencia a mediados de noviembre. Paso 3, el nicho de Ads, solo si lo anterior funciona en grande.

---

## Orden y modelos
1. Push de `main` (Claude Code, Sonnet, 5 min).
2. A0 reconocimiento (Claude Code, Sonnet).
3. Validar el diseño de A1 con la tabla de A0: **un chat nuevo con Fable, una sola vez** (es la decisión grande del multicliente, como decía la Fase 4 del plan de orden).
4. A1 a A5 por fases en Claude Code (Opus para A1 y A4, que son lo difícil; Sonnet para el resto).
5. B0 con Daniela en paralelo; B1 a B4 cuando A1 esté en producción.
