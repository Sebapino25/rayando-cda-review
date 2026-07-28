# Disparador automático semanal del pipeline (subsistema 2 de 4)

Fecha: 2026-07-28
Estado: aprobado por el usuario, listo para plan de implementación

## Contexto

Rayando el CDA ya tiene un pipeline que transcribe, corta clips y los sube a
YouTube (no listado) + Supabase para revisión editorial
(`pipeline/transcribir.py` + `pipeline/procesar_programa.py`, ver
`pipeline/README.md`). Hasta ahora, correr ese pipeline sobre una grabación
nueva era un paso manual.

En una sesión anterior se empezó a resolver esto con dos scripts
(`pipeline/auto_procesar.ps1` y `pipeline/auto_procesar_loop.ps1`, hoy sin
commitear) pensados para correr como tarea de Task Scheduler ("mientras se
resuelve el registro en Task Scheduler" — no quedó documentado qué bloqueó
ese registro), con un loop de respaldo mientras tanto.

El 2026-07-28 esto se puso a prueba: la grabación del programa del
2026-07-27 no se procesó sola. La causa raíz combinó tres problemas
independientes, todos corregidos en esta misma sesión (ver
`pipeline/auto_procesar.ps1` y commits del día):

1. La grabación cayó en la carpeta equivocada (`Partidos\` en vez de
   `grabaciones\`) porque OBS tenía la ruta de salida cambiada de cuando se
   grabó un partido — corregido en la config de OBS, no es parte de este
   subsistema.
2. `auto_procesar.ps1` tenía `$ErrorActionPreference = "Stop"` combinado con
   redirección `*>> $logFile` de la salida de python — cualquier línea que
   python escriba a stderr (incluso un aviso normal, como el fallback de GPU
   a CPU) aborta el script como si fuera un error fatal, y el mensaje
   capturado queda truncado a esa primera línea. Ya corregido (cambiado a
   `"Continue"`, verificado con una prueba mínima).
3. El loop de respaldo (`auto_procesar_loop.ps1`) sí venía corriendo bien,
   pero nunca se completó el registro real en Task Scheduler — dependía de
   que alguien lo arrancara a mano cada vez que se reiniciara la PC.

Este es el subsistema 2 de los 4 identificados en la auditoría original del
proyecto (ver [[rayando_cda_publicacion_final_status]] / spec de subsistema
1: `docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md`).

## Objetivo

Que una grabación nueva en `grabaciones\` se procese sola (transcripción +
corte + subida a YouTube/Supabase para revisión) sin que nadie tenga que
acordarse de arrancar nada a mano — ni siquiera después de que la PC se
reinicie — y que si algo falla, el aviso llegue con suficiente contexto para
diagnosticarlo sin tener que ir a buscar el log a mano. Además, que cuando
el procesamiento termine bien, el resto del equipo (no solo el dueño del
proyecto) se entere y pueda entrar a revisar.

## No-objetivos

- No se cambia la lógica de detección/procesamiento en sí
  (`transcribir.py`/`procesar_programa.py` ya funcionan, se verificó hoy
  corriendo el pipeline completo a mano sobre la grabación real).
- No se implementa un watchdog separado que verifique "¿corrió el
  procesamiento esta semana?" — si Task Scheduler no dispara la tarea en
  absoluto (no solo si el script falla), este subsistema no lo detecta.
  Fuera de alcance por ahora.
- No se resuelve el porqué exacto de que Avast haya bloqueado el acceso a
  GPU específicamente en el proceso automático de hoy (funcionó bien al
  correrlo manualmente) — se investiga si vuelve a pasar.
- No se toca la limpieza de documentación desactualizada (README/CAMBIOS)
  más allá de documentar lo que este subsistema agrega — eso es el
  subsistema 3.

## Arquitectura

```
Windows Task Scheduler ("RayandoCDA_AutoProcesar")
  Trigger: al iniciar sesión de sebap (sin guardar contraseña)
  Acción: powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden
          -File pipeline\auto_procesar_loop.ps1
  Config: "No iniciar una nueva instancia" si ya hay una corriendo
        │
        ▼
auto_procesar_loop.ps1  (ya existe y viene corriendo desde el 2026-07-27
                          sin problemas — while infinito, Start-Sleep 300s)
        │  cada 5 min
        ▼
auto_procesar.ps1  (ya corregido hoy: $ErrorActionPreference = "Continue")
        →  busca en grabaciones\*.mkv un archivo sin transcripción
           (transcripciones\<nombre>\<nombre>.json inexistente) y con más
           de 5 min desde su última escritura
        →  corre transcribir.py + procesar_programa.py, log en
           pipeline\logs_auto\<nombre>.log
        →  manda mail de éxito o de fallo (ver "Notificaciones")
```

Por qué un trigger "al iniciar sesión" + loop en vez de un trigger repetitivo
nativo de Task Scheduler (`-RepetitionInterval`): el loop ya está probado
funcionando; un trigger repetitivo tiene un gotcha conocido en
`New-ScheduledTaskTrigger` (si no se fija `-RepetitionDuration`
explícitamente, Windows deja de repetir la tarea después de 1 día, sin
error visible) que podría explicar por qué el registro anterior no quedó
funcionando. Usar Task Scheduler solo para el caso simple ("arrancar esto al
loguearme") reduce la superficie de algo que ya mostró ser propenso a fallar
en silencio.

## Componentes

### 1. Tarea de Task Scheduler

Se registra con `Register-ScheduledTask` (o `schtasks`), trigger
`AtLogOn` para el usuario `sebap`, acción apunta a
`auto_procesar_loop.ps1`. Al registrarla, se mata cualquier proceso del loop
que haya quedado corriendo manualmente (para no tener dos loops en
paralelo) y se dispara la tarea una vez para dejarlo corriendo de forma
"oficial" sin esperar al próximo reinicio.

### 2. `auto_procesar.ps1` — notificaciones enriquecidas

- **Mail de éxito** ("procesamiento automático completo"): destinatarios
  `seba.pino.v@gmail.com`, `Cristian.fajardoc@gmail.com`,
  `arriagada.rene@gmail.com`. Cuerpo incluye el link a la app
  (`https://sebapino25.github.io/rayando-cda-review/`) para que el equipo
  entre a revisar los clips nuevos.
- **Mail de fallo**: sigue yendo solo a `seba.pino.v@gmail.com`. Se le suma
  el tail (últimas ~30 líneas) del log de esa corrida al cuerpo del mail,
  además del mensaje de excepción — así el mail mismo da una pista sin
  tener que ir a revisar el archivo en la PC.

### 3. `transcribir.py` — fallback de CPU con manejo de errores propio

`load_model_and_start()` intenta GPU, y si falla cae a CPU (líneas 92-100).
Hoy el camino de CPU no tiene try/except propio: si también falla (como
parece haber pasado hoy, aunque no se confirmó la causa exacta), explota
con un traceback crudo sin ningún mensaje de contexto. Se envuelve ese
tramo en su propio try/except que imprime un mensaje claro ("Falló también
en CPU: ...") antes de volver a lanzar la excepción — no cambia el
comportamiento (el script igual termina con código de error si ambos
caminos fallan), solo mejora el diagnóstico.

### 4. Commit de los scripts

`pipeline/auto_procesar.ps1` y `pipeline/auto_procesar_loop.ps1` (hoy sin
trackear en git) se agregan al repositorio como parte de este subsistema.

## Manejo de errores

Sin cambios de fondo respecto al mecanismo ya corregido hoy (chequeo
explícito de `$LASTEXITCODE`, sin depender de `$ErrorActionPreference`). La
diferencia es la cantidad de contexto que llega en el mail de fallo (tail
del log) y que el fallback de CPU ya no explota en seco.

## Testing

- Registrar la tarea y dispararla manualmente ("Ejecutar" desde Task
  Scheduler o `Start-ScheduledTask`) para confirmar que levanta el loop sin
  necesitar reiniciar la PC; confirmar con `Get-ScheduledTaskInfo`
  (`LastTaskResult`).
- Confirmar que solo queda un proceso del loop corriendo (matar el manual
  antes de disparar la tarea registrada).
- La lógica de detección/procesamiento en sí ya quedó verificada hoy
  corriendo el pipeline completo a mano sobre una grabación real.
- No se fuerza un fallo real de GPU/CPU a propósito (depende de que Avast
  bloquee el acceso, no es reproducible a demanda); el cambio en
  `transcribir.py` se verifica por lectura de código y porque no rompe el
  camino feliz (ya se corrió manualmente hoy usando GPU sin problemas).
