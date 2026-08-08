# Copys de IA con criterio editorial (estratega + redactor)

Fecha: 2026-08-07
Estado: aprobado por el usuario (y por René en el criterio editorial), listo para plan de implementación

## Contexto

`copys_ia.py` genera con la API de Anthropic el copy de Instagram/TikTok/
YouTube y el título de portada de cada clip, a partir de la transcripción
cruda. Hoy el prompt le pide al modelo, en esencia, "editá la transcripción"
(sacar muletillas, corregir ortografía, agregar un gancho de una línea) —
funciona bien para clips con override manual en `clip_overrides.json`
(curados a mano por el equipo, con contexto/opinión propia ya escrita), pero
para la gran mayoría de los clips (sin override, generados 100% por IA) el
resultado es, en la práctica, poco más que la transcripción resumida. No
tiene ángulo editorial, no genera conversación, y los hashtags son siempre
los mismos 4 fijos (`config.COPYS_HASHTAGS_BASE`) salvo que alguien los cure
a mano por clip.

El usuario quiere que estos copys aporten más valor real: que tengan un
ángulo (no solo resumir), que puedan sumar la mirada editorial propia del
programa ("Orozquista", crítica a la dirigencia), que inviten a comentar, y
que los hashtags sean más específicos al tema del clip sin depender de
curación manual en cada uno. Se validó el criterio con René (el
periodista del programa) antes de definir este spec, en texto en lenguaje
llano (ver conversación) — confirmó que está de acuerdo con el enfoque.

## Objetivo

Que un clip generado sin override manual en `clip_overrides.json` (el caso
mayoritario) produzca copys con:
1. Un ángulo editorial explícito (por qué le importa a un hincha de la U),
   no una transcripción resumida.
2. Mirada propia del programa cuando el tema lo amerite, más asertiva/
   crítica, coherente con la línea Orozquista — sin inventar declaraciones
   que nadie hizo (esa regla no cambia).
3. Una pregunta de cierre en Instagram y TikTok que invite a comentar
   (pregunta abierta, no una encuesta con opciones).
4. Hashtags contextuales al tema del clip (rival, jugador, torneo, término
   viral), generados automáticamente, además de los 4 hashtags base fijos.

## Alcance

- `pipeline/copys_ia.py`: reescritura del `SYSTEM_PROMPT` (fase estratégica
  + fase de redacción, pregunta de cierre, tono editorial) y del `_SCHEMA`/
  `CopysGenerados` (nuevo campo `hashtags_ia`).
- `pipeline/cortar_clip.py`, función `build_copys`: usar `hashtags_ia` en
  vez de (no además de) los hashtags base solos, cuando no hay
  `hashtags_extra` en el override del clip.
- `pipeline/clip_overrides.json`: sin cambios de formato — `hashtags_extra`
  sigue funcionando exactamente igual que hoy para los clips curados a
  mano.

## No-objetivos

- No se toca `detectar_momentos.py` (criterio de selección de qué momentos
  cortar) — quedó fuera después de confirmar el criterio actual con René;
  si más adelante se quiere ajustar el orden de prioridad (humor →
  declaraciones fuertes → emoción) o agregar categorías nuevas, es un spec
  aparte.
- No se implementan encuestas nativas de Instagram (sticker de Stories con
  opciones a votar) — descartado explícitamente: este pipeline solo
  publica a Reels/feed, no a Stories, y armar esa publicación sería una
  funcionalidad nueva grande, no un ajuste de copy.
- No se cambia a un pipeline de dos llamadas a la API (estratega y redactor
  como pasos separados) — se mantiene una sola llamada por clip; el
  razonamiento estratégico vive en el `thinking: adaptive` que la llamada
  ya usa hoy, no en un campo de salida ni una llamada aparte. Ver
  "Arquitectura" para el porqué.
- No se cambia la revisión editorial existente en la app (`app/`) — los
  campos nuevos/editados se muestran y editan ahí exactamente igual que
  los actuales, sin cambios de UI.
- No se toca la regla de no inventar declaraciones o palabras que la
  persona no dijo — solo se relaja la restricción de que el copy sea
  *únicamente* edición de transcripción, permitiendo mirada editorial
  propia del programa (no atribuida a una persona específica).

## Arquitectura

Se mantiene la estructura actual: una sola llamada a la API de Anthropic
por clip, con `thinking: adaptive` (ya usado hoy) y salida en JSON
estructurado vía `output_config.format.json_schema`. El cambio es de
contenido del prompt y del schema, no de arquitectura:

```
transcripción cruda del clip
        │
        ▼
copys_ia.generar_copys()  (una sola llamada, sin cambios de firma)
  SYSTEM_PROMPT reestructurado en dos fases:
    1. Fase estratégica (razonamiento interno, vía thinking — no es
       un campo de salida): ángulo editorial del clip, postura
       Orozquista si aplica, qué genera comentarios, qué hashtags
       de nicho aportan alcance real.
    2. Fase de redacción: escribe cada copy con ese ángulo,
       incluye pregunta de cierre en IG/TikTok.
        │
        ▼
CopysGenerados (schema ampliado, +hashtags_ia)
        │
        ▼
cortar_clip.build_copys()
  hashtags = base + (hashtags_extra del override, si existe,
             SI NO hashtags_ia del resultado de la IA)
```

### Por qué esta arquitectura (una sola llamada, no dos)

Se evaluó separar esto en dos llamadas reales (una "estratega" que
devuelve un JSON de estrategia, y una "redactor" que lo consume y escribe
el copy final), pero se descartó:

- **Costo y latencia duplicados** por clip, multiplicado por ~5-8 clips
  por programa semanal, sin una ganancia de calidad clara: el modelo ya
  tiene `thinking: adaptive` disponible en la llamada actual, que es
  exactamente el espacio donde un paso de "pensar la estrategia antes de
  escribir" vive de forma nativa — no hace falta materializarlo como una
  llamada aparte para que el modelo razone en ese orden.
- **Ya existe un gate editorial humano** antes de publicar (la app de
  revisión, donde el equipo edita copy/portada antes del botón "Publicar
  en redes") — no hace falta un JSON de estrategia inspeccionable por
  separado para confiar en el resultado, porque nada se publica sin pasar
  por esa revisión.
- Mantiene `copys_ia.py` con la misma forma que tiene hoy (una función,
  una llamada, un único punto de fallo con el mismo manejo de error vía
  `CopyIAError`), sin agregar orquestación entre dos pasos.

## Cambios en el prompt (`SYSTEM_PROMPT`)

Se mantiene sin cambios:
- `CONTEXTO_PROGRAMA` (quiénes son, identidad Orozquista, tono).
- La regla de que el gancho de cada plataforma tiene que ser una
  construcción nueva, no una cita textual/parafraseada de la
  transcripción.
- La regla de que Instagram/YouTube/TikTok no pueden repetir la misma
  frase o ángulo entre sí.
- La parte de `REGLA_EDICION` sobre ortografía, voseo chileno y nombres
  propios (sin cambios).
- La regla de no inventar palabras o ideas que la persona no dijo —
  aplica a las citas/paráfrasis de lo que alguien dijo en el clip. Se
  aclara explícitamente en el prompt que esto es distinto de la mirada
  editorial propia del programa (ver siguiente punto), que no es una cita
  atribuida a nadie.

Se agrega/reemplaza:

- **Instrucción de fase estratégica**, antes de la de redacción: pedirle
  al modelo que, antes de escribir, identifique (a) el ángulo real de
  valor del momento — por qué le importa a un hincha de la U, más allá de
  "qué se dijo textualmente"; (b) si el tema amerita una postura editorial
  Orozquista explícita (crítica a la dirigencia, polémica, etc.) o si el
  clip es de otro tipo (humor, emoción, invitados) donde no corresponde
  forzarla; (c) qué 3-6 hashtags de nicho (rival, jugador, torneo, término
  viral del fútbol chileno) le suman alcance real más allá de los 4 fijos
  del programa.
- **Regla de valor agregado**: el copy de cada plataforma no puede ser
  solo la transcripción editada — tiene que aportar el ángulo/contexto
  identificado en la fase estratégica. Cuando el tema lo amerite, puede
  incluir una postura editorial propia del programa (no atribuida a
  ninguna persona del clip), coherente con la línea Orozquista, mientras
  no tergiverse ni invente lo que alguien dijo.
- **Pregunta de cierre (IG y TikTok, obligatoria)**: el copy de Instagram
  y el de TikTok tienen que terminar con una pregunta abierta relacionada
  al contenido específico del clip, pensada para generar comentarios — no
  una plantilla genérica repetida ("¿ustedes qué opinan?") sino una
  pregunta específica al tema. La pregunta de IG y la de TikTok tampoco
  pueden ser la misma frase reformulada (mismo criterio de "ángulo propio
  por plataforma" que ya aplica al gancho). No es una encuesta con
  opciones — es una pregunta de texto libre.
- **YouTube**: la descripción puede cerrar con una pregunta corta cuando
  calce natural, pero no es obligatorio — sigue siendo principalmente
  descriptiva/SEO, no un gancho de conversación.
- **Hashtags contextuales**: nueva instrucción para que el modelo
  devuelva 3-6 hashtags específicos del tema del clip (no los 4 base, que
  se siguen agregando de forma determinística en `cortar_clip.py` como
  hoy) en el nuevo campo `hashtags_ia`.

## Cambios en el schema (`_SCHEMA` / `CopysGenerados`)

Nuevo campo, agregado a los 5 existentes (que no cambian de nombre ni de
formato):

```python
"hashtags_ia": {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 3,
    "maxItems": 6,
    "description": (
        "3-6 hashtags específicos del tema del clip (rival, jugador, "
        "torneo, término viral), sin los hashtags base del programa "
        "(esos se agregan aparte, deterministicamente)."
    ),
},
```

Se agrega a `required`. `CopysGenerados` gana el campo
`hashtags_ia: list[str]`.

## Cambios en `cortar_clip.build_copys`

Reemplaza la línea actual:

```python
hashtags = list(config.COPYS_HASHTAGS_BASE) + list(overrides.get("hashtags_extra", []))
```

por:

```python
if overrides.get("hashtags_extra"):
    hashtags_tema = list(overrides["hashtags_extra"])
elif generado_ia:
    hashtags_tema = list(generado_ia.hashtags_ia)
else:
    hashtags_tema = []  # sin override y sin IA (p. ej. sin transcripción): solo hashtags base

hashtags = list(config.COPYS_HASHTAGS_BASE) + hashtags_tema
```

`hashtags_extra` del override sigue ganando tal cual — mismo patrón que ya
usan `titulo_seo`, `contexto`, `copy_instagram`, etc. (override manual
gana, IA rellena lo que falta). Para un clip completamente curado a mano
(los 5 campos de `campos_ia` con override), `generado_ia` es `None` porque
no se llama a la API — ese caso ya deja los hashtags en manos del override
como hoy, no cambia.

## Manejo de errores

Sin cambios respecto a hoy: si `copys_ia.generar_copys` falla
(`CopyIAError` — sin API key, rechazo del modelo, respuesta mal formada),
`generado_ia` queda en `None` y se usa el fallback de texto plano existente
para los campos de copy. Con el cambio de este spec, ese mismo `None`
también hace que `hashtags_tema` quede vacío (fallback: solo hashtags
base) — no se agrega ningún manejo de error nuevo, se reusa el flujo que
ya existe.

## Testing

- No hay tests unitarios de `copys_ia.py` hoy (llama a una API externa, no
  es determinístico) y este spec no cambia eso.
- Se agrega un test para la lógica determinística nueva en
  `cortar_clip.build_copys` (armado de `hashtags`), con `generado_ia`
  mockeado, cubriendo los 3 casos: override con `hashtags_extra` presente
  (gana), sin override y con `generado_ia.hashtags_ia` (se usa), y sin
  override y sin `generado_ia` (solo hashtags base) — siguiendo el patrón
  de los tests existentes del pipeline (`test_reprocesar_video_decision.py`,
  etc.), sin tocar clips reales (ver regla de aislamiento de datos de
  test del proyecto).
- Verificación manual: correr `cortar_clip.py` sobre un clip real de
  prueba (o el flujo de "Regenerar solo portadas/copys" documentado en el
  README) y revisar en consola/`copys.md` que el copy tenga ángulo,
  pregunta de cierre y hashtags contextuales razonables antes de dar el
  cambio por bueno.
