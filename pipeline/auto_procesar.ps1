# Disparador automático semanal: revisa si hay una grabación nueva y ya
# terminada en `grabaciones\`, y si la hay, corre transcribir.py +
# procesar_programa.py sola. Pensado para correr cada 5 minutos vía Task
# Scheduler (tarea "RayandoCDA_AutoProcesar").
#
# "Ya terminada" = el archivo pasa TRES chequeos, en este orden:
#   1. Su LastWriteTime no cambió en los últimos 5 minutos (mientras OBS
#      graba, el archivo se sigue escribiendo) — filtro rápido, sin tocar
#      disco de más.
#   2. Su tamaño coincide con el que tenía la corrida anterior (persistido
#      en grabaciones_estado.json) — es decir, "sin cambios" se confirmó en
#      DOS corridas separadas (~5 min de diferencia real entre chequeos),
#      no en una sola lectura instantánea. Un solo chequeo no alcanza: la
#      noche del 24/08 OBS tuvo una pausa de escritura de varios minutos
#      (coincidiendo con el corte de conexión del programa) mientras seguía
#      grabando, el chequeo de "5 min sin cambios" dio falso positivo, y la
#      grabación se transcribió a medio terminar.
#   3. ffprobe puede leer una duración numérica válida del archivo — última
#      red de seguridad por si los dos chequeos anteriores igual coinciden
#      con el archivo todavía inestable.
# Si falla el 2 o el 3, se espera a la próxima corrida sin alertar (no es
# un error, solo "todavía no").
#
# "Ya procesada" = ya existe transcripciones\<nombre>\<nombre>.json.
#
# Solo procesa UN archivo nuevo por corrida (si hay varios pendientes, el
# resto espera a la próxima corrida, 5 min después) para no arrancar dos
# transcripciones en paralelo si el script tarda más de 5 minutos en correr.

$ErrorActionPreference = "Continue"
# NO usar "Stop": con *>> $logFile, cualquier línea que python escriba a
# stderr (aunque sea diagnóstico normal, ej. al hacer fallback GPU->CPU)
# se convierte en un error terminante y aborta el script antes de que
# termine de procesar. La detección real de fallos ya la hacen los
# chequeos de $LASTEXITCODE de más abajo, que no dependen de esta
# preferencia.

# Fuerza UTF-8 tanto para Add-Content como para el redirect *>> (que en
# Windows PowerShell 5.1 usa Out-File por debajo, con UTF-16LE por defecto).
# Sin esto, $logFile queda con encodings mezclados y Obtener-TailLog (más
# abajo) lee texto ilegible con bytes nulos en las porciones UTF-16LE.
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'utf8'

$BaseDir = "C:\Users\sebap\OneDrive\Escritorio\RayandoelCDA"
$PipelineDir = "C:\Users\sebap\rayando-cda\pipeline"
$GrabacionesDir = Join-Path $BaseDir "grabaciones"
$TranscripcionesDir = Join-Path $BaseDir "transcripciones"
$LogsDir = Join-Path $PipelineDir "logs_auto"
$TaskName = "RayandoCDA_AutoProcesar"

function Get-DotEnvValue($key, $envFile) {
    if (-not (Test-Path $envFile)) { return $null }
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -split "=", 2)[1].Trim().Trim('"')
}

if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir | Out-Null }

$ResendApiKey = Get-DotEnvValue "RESEND_API_KEY" (Join-Path $PipelineDir ".env")
if (-not $ResendApiKey) {
    $msg = "Falta RESEND_API_KEY en pipeline\.env (copiá .env.example y completá el valor)."
    Add-Content -Path (Join-Path $LogsDir "auto_procesar_errores.log") -Value "$(Get-Date -Format o) $msg"
    throw $msg
}
$AlertEmail = "seba.pino.v@gmail.com"
$TeamEmails = @($AlertEmail, "Cristian.fajardoc@gmail.com", "arriagada.rene@gmail.com")
$AppUrl = "https://sebapino25.github.io/rayando-cda-review/"

function Enviar-Alerta($asunto, $cuerpo, $destinatarios = @($AlertEmail)) {
    try {
        $body = @{
            from    = "Rayando el CDA <onboarding@resend.dev>"
            to      = @($destinatarios)
            subject = $asunto
            text    = $cuerpo
        } | ConvertTo-Json
        Invoke-RestMethod -Uri "https://api.resend.com/emails" -Method Post `
            -Headers @{ Authorization = "Bearer $ResendApiKey"; "Content-Type" = "application/json" } `
            -Body $body | Out-Null
    } catch {
        Add-Content -Path (Join-Path $LogsDir "auto_procesar_errores.log") -Value "$(Get-Date -Format o) No se pudo enviar alerta ('$asunto'): $_"
    }
}

function Obtener-TailLog($logFile, $lineas = 30) {
    if (-not (Test-Path $logFile)) { return "(no se encontró el log)" }
    return (Get-Content -Path $logFile -Tail $lineas -Encoding UTF8) -join "`n"
}

# --- Estado persistido de "tamaño visto la corrida anterior", por archivo,
# para el chequeo doble de "grabación terminada" (ver comentario arriba). ---
$EstadoGrabacionesPath = Join-Path $LogsDir "grabaciones_estado.json"

function Get-EstadoGrabaciones {
    if (-not (Test-Path $EstadoGrabacionesPath)) { return @{} }
    try {
        $raw = Get-Content -Path $EstadoGrabacionesPath -Raw -Encoding UTF8
        if (-not $raw) { return @{} }
        $obj = $raw | ConvertFrom-Json
        $ht = @{}
        foreach ($prop in $obj.PSObject.Properties) { $ht[$prop.Name] = [int64]$prop.Value }
        return $ht
    } catch {
        return @{}
    }
}

function Set-EstadoGrabaciones($ht) {
    ($ht | ConvertTo-Json) | Set-Content -Path $EstadoGrabacionesPath -Encoding utf8
}

function Test-DuracionValida($path) {
    $salida = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$path" 2>$null
    if (-not $salida) { return $false }
    $numero = 0.0
    return [double]::TryParse($salida.Trim(), [ref]$numero) -and ($numero -gt 0)
}

$candidatos = Get-ChildItem -Path $GrabacionesDir -Filter "*.mkv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending

# Si hay una grabación nueva todavía sin transcribir (recién terminado el
# programa), esta corrida se dedica solo a eso — la corrección automática de
# pedidos anteriores (más abajo) queda pausada hasta que no haya ninguna
# grabación pendiente, para no competir por atención justo cuando acaba de
# salir el programa. En un flujo sano esto no debería importar (todo pedido
# de la semana anterior ya debería estar cerrado antes del próximo programa),
# pero sirve de resguardo si algo quedó pendiente.
$hayGrabacionPendiente = $false

# Para el ritmo adaptativo del disparador (bloque al final): $seProcesoGrabacion
# marca que esta corrida arrancó una transcripción real; los tres exit codes
# quedan en -1 (sentinela "no idle") por si el bloque `else` de más abajo no
# llega a correr — así una corrida con grabación pendiente nunca cuenta como
# ociosa.
$seProcesoGrabacion = $false
$exitCode = -1
$exitCodeSubtitulos = -1
$exitLimpieza = -1

# Solo conserva estado de archivos todavía pendientes en esta corrida — así
# no crece para siempre con grabaciones ya procesadas o borradas.
$estadoPrevio = Get-EstadoGrabaciones
$estadoGrabaciones = @{}
foreach ($rec in $candidatos) {
    $transcriptJson = Join-Path $TranscripcionesDir "$($rec.BaseName)\$($rec.BaseName).json"
    if ((Test-Path $transcriptJson) -or (-not $estadoPrevio.ContainsKey($rec.Name))) { continue }
    $estadoGrabaciones[$rec.Name] = $estadoPrevio[$rec.Name]
}

foreach ($rec in $candidatos) {
    $stem = $rec.BaseName
    $transcriptJson = Join-Path $TranscripcionesDir "$stem\$stem.json"
    if (Test-Path $transcriptJson) { continue }

    $hayGrabacionPendiente = $true

    $minutosDesdeUltimaEscritura = (New-TimeSpan -Start $rec.LastWriteTime -End (Get-Date)).TotalMinutes
    if ($minutosDesdeUltimaEscritura -lt 5) {
        # Probablemente todavía se está grabando (o se acaba de terminar) —
        # esperar a que se estabilice en la próxima corrida.
        continue
    }

    if ($estadoGrabaciones[$rec.Name] -ne $rec.Length) {
        # Primera vez que se ve este tamaño estable — confirmar en la
        # próxima corrida antes de tocarlo (ver comentario arriba).
        $estadoGrabaciones[$rec.Name] = $rec.Length
        continue
    }

    if (-not (Test-DuracionValida $rec.FullName)) {
        Add-Content -Path (Join-Path $LogsDir "auto_procesar_errores.log") `
            -Value "$(Get-Date -Format o) $($rec.Name) parece estable (tamaño sin cambios en dos corridas) pero ffprobe no le pudo leer una duración válida -- se espera a la próxima corrida."
        continue
    }

    $estadoGrabaciones.Remove($rec.Name)

    $logFile = Join-Path $LogsDir "$stem.log"
    Add-Content -Path $logFile -Value "$(Get-Date -Format o) Iniciando procesamiento automático de $($rec.Name)"
    $seProcesoGrabacion = $true

    Push-Location $PipelineDir
    try {
        & python transcribir.py "$($rec.Name)" *>> $logFile
        if ($LASTEXITCODE -ne 0) { throw "transcribir.py devolvió código $LASTEXITCODE" }

        & python procesar_programa.py "$($rec.Name)" *>> $logFile
        if ($LASTEXITCODE -ne 0) { throw "procesar_programa.py devolvió código $LASTEXITCODE" }

        Enviar-Alerta "Rayando el CDA: procesamiento automático completo" "Se procesó $($rec.Name) automáticamente. Entrá a la app para revisar y aprobar los clips: $AppUrl`n`nLog: $logFile" $TeamEmails
    } catch {
        $tail = Obtener-TailLog $logFile
        Enviar-Alerta "Rayando el CDA: falló el procesamiento automático" "Falló procesando $($rec.Name): $_`n`nÚltimas líneas del log ($logFile):`n$tail`n`nRevisar el log completo y correr los pasos a mano si hace falta (ver pipeline/README.md)."
    } finally {
        Pop-Location
    }

    break
}

Set-EstadoGrabaciones $estadoGrabaciones

if ($hayGrabacionPendiente) {
    Add-Content -Path (Join-Path $LogsDir "loop.log") -Value "$(Get-Date -Format o) Hay una grabación nueva pendiente de transcribir/cortar — se pausa la corrección automática de pedidos anteriores hasta que no quede ninguna."
} else {
    # --- Corrección automática de in/out points pedida por el equipo editorial ---
    # Un solo clip por corrida (--uno), igual que el procesamiento de
    # grabaciones más arriba: si hay más de uno pendiente, la siguiente
    # corrida (5 min después) procesa el resto.
    $logCorreccion = Join-Path $LogsDir "correccion_video.log"
    # Centinela: si el bloque de abajo ni siquiera logra LANZAR python (exe no
    # encontrado, permisos, etc.), $ErrorActionPreference="Continue" deja seguir y
    # $LASTEXITCODE conservaría el valor del bloque de grabaciones de más arriba —
    # potencialmente 0, que acá se leería como "nada pendiente" y se tragaría el
    # fallo en silencio. -1 no lo devuelve nunca reprocesar_video.py, así que cae
    # en la rama de alerta de abajo.
    $exitCode = -1
    Push-Location $PipelineDir
    try {
        & python reprocesar_video.py --apply --uno *>> $logCorreccion
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($exitCode -eq 3) {
        Enviar-Alerta "Rayando el CDA: se aplicó una corrección de video" `
            "Se aplicó un pedido de corrección de video automáticamente. Entrá a la app para revisar el clip corregido: $AppUrl`n`nLog: $logCorreccion" `
            $TeamEmails
    } elseif ($exitCode -ne 0) {
        # Cualquier código distinto de 0 y 3 es un fallo: 1 (abortó o falló un
        # paso técnico), el centinela -1 (ni siquiera arrancó python) o un código
        # inesperado. Alerta solo al dueño del proyecto.
        $tail = Obtener-TailLog $logCorreccion
        $cuerpo = "Falló o no se pudo interpretar con confianza un pedido de corrección de video (código $exitCode)."
        $cuerpo += "`n`nÚltimas líneas del log ($logCorreccion):`n$tail"
        $cuerpo += "`n`nEl clip queda en estado='correccion_video': si abortó antes de tocar archivos (pedido ambiguo, carpeta no encontrada) quedó tal cual estaba, y si falló a mitad del reproceso se restauró automáticamente a su versión anterior. El log de arriba dice cuál de los dos casos fue."
        $cuerpo += "`n`nOJO: este pedido NO se vuelve a intentar solo mientras el texto de comentarios_video no cambie (para no gastar API ni saturar los mails cada 5 minutos). Corregí el pedido en la app, o corré la corrección a mano con --clip-id (ver pipeline/README.md)."
        Enviar-Alerta "Rayando el CDA: falló la corrección automática de video" $cuerpo
    }
    # exitCode 0 (nada pendiente, o todo lo pendiente ya falló antes con el mismo
    # texto): no se manda mail.

    # --- Corrección automática de subtítulos (transcripcion != transcripcion_original) ---
    # A diferencia de la corrección de in/out (arriba), esto no llama a la API
    # de Anthropic (es una redistribución de texto determinística), así que no
    # hace falta --uno: se procesan todas las filas pendientes en la misma
    # corrida. Sin este bloque, editar la transcripción en la app nunca se
    # aplicaba sola al video — quedaba anotado para "reprocesar" pero nada
    # disparaba ese reproceso (había que acordarse de correr
    # reprocesar_subtitulos.py a mano).
    $logSubtitulos = Join-Path $LogsDir "correccion_subtitulos.log"
    $exitCodeSubtitulos = -1
    Push-Location $PipelineDir
    try {
        & python reprocesar_subtitulos.py --apply *>> $logSubtitulos
        $exitCodeSubtitulos = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($exitCodeSubtitulos -eq 3) {
        Enviar-Alerta "Rayando el CDA: se corrigieron subtítulos" `
            "Se aplicó una corrección de subtítulos automáticamente (transcripción editada en la app). Entrá a la app para revisar: $AppUrl`n`nLog: $logSubtitulos" `
            $TeamEmails
    } elseif ($exitCodeSubtitulos -ne 0) {
        $tail = Obtener-TailLog $logSubtitulos
        $cuerpo = "Falló la corrección automática de subtítulos (código $exitCodeSubtitulos)."
        $cuerpo += "`n`nÚltimas líneas del log ($logSubtitulos):`n$tail"
        $cuerpo += "`n`nRevisar el log completo y correr reprocesar_subtitulos.py a mano con --clip-id si hace falta (ver pipeline/README.md)."
        Enviar-Alerta "Rayando el CDA: falló la corrección automática de subtítulos" $cuerpo
    }
    # exitCode 0 (nada pendiente): no se manda mail.

    # --- Limpieza automática de la cola de clips ---
    # Borra del todo (fila de Supabase + video/portada de Storage + video no
    # listado de YouTube) lo que ya no se va a usar cuando entra un programa
    # nuevo: 'pendiente' y 'rechazado' sin publicar de programas anteriores, y
    # 'aprobado' sin publicar cuya `semana` pasó los config.DIAS_RESERVA_ANTIGUAS
    # días. No toca publicados ni 'correccion_video'. Mismo esquema de exit
    # codes que los bloques de arriba.
    $logLimpieza = Join-Path $LogsDir "limpiar_clips.log"
    $exitLimpieza = -1
    Push-Location $PipelineDir
    try {
        & python limpiar_clips.py --apply *>> $logLimpieza
        $exitLimpieza = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($exitLimpieza -eq 3) {
        $tail = Obtener-TailLog $logLimpieza
        Enviar-Alerta "Rayando el CDA: se limpiaron clips de la cola" `
            "Se borraron clips que ya no se iban a usar: pendientes/rechazados sin publicar de programas anteriores, y aprobados sin publicar de más de 30 días (registro de Supabase + video/portada de Storage + video no listado de YouTube).`n`nDetalle ($logLimpieza):`n$tail" `
            $TeamEmails
    } elseif ($exitLimpieza -ne 0) {
        $tail = Obtener-TailLog $logLimpieza
        $cuerpo = "Falló la limpieza automática de la cola de clips (código $exitLimpieza)."
        $cuerpo += "`n`nÚltimas líneas del log ($logLimpieza):`n$tail"
        $cuerpo += "`n`nRevisar el log completo y, si hace falta, correr limpiar_clips.py a mano (ver pipeline/README.md)."
        Enviar-Alerta "Rayando el CDA: falló la limpieza de la cola de clips" $cuerpo
    }
    # exitCode 0 (nada que limpiar): no se manda mail.
}

# --- Ritmo adaptativo del disparador -------------------------------------------
# Cuando una corrida no encuentra NADA que hacer (ni grabación nueva, ni
# corrección de video/subtítulos, ni limpieza pendiente), no tiene sentido
# seguir despertando la tarea cada 5 minutos. Tras $UMBRAL_OCIOSAS corridas
# ociosas seguidas se amplía el intervalo de repetición de la tarea de Task
# Scheduler a $INTERVALO_LENTO_MIN; la primera corrida que vuelve a tener
# trabajo real (o encuentra algo pendiente, o falla algún paso) lo baja de
# nuevo a $INTERVALO_RAPIDO_MIN.
#
# El contador de ociosas vive en ritmo_auto.json; el intervalo real se lee de
# la tarea misma (fuente de verdad). Si el intervalo cambió por fuera de este
# script (típicamente re-registrar la tarea con registrar_tarea_programada.ps1,
# que la deja en 5 min) el contador se reinicia — o sea, re-registrar funciona
# como botón de reset.
#
# Costo del compromiso: mientras la cola está tranquila, un pedido del equipo
# en la app puede tardar hasta $INTERVALO_LENTO_MIN en procesarse, y la
# grabación semanal puede tardar hasta ese tiempo en detectarse la primera vez
# al abrir la ventana del martes (después baja a 5 min sola apenas ve la
# grabación pendiente). Aceptable para trabajo a ritmo humano dentro de una
# ventana de 34 h.
$UMBRAL_OCIOSAS = 3
$INTERVALO_RAPIDO_MIN = 5
$INTERVALO_LENTO_MIN = 30
$RitmoPath = Join-Path $LogsDir "ritmo_auto.json"

$corridaOciosa = (-not $hayGrabacionPendiente) -and (-not $seProcesoGrabacion) `
    -and ($exitCode -eq 0) -and ($exitCodeSubtitulos -eq 0) -and ($exitLimpieza -eq 0)

function Get-RitmoPrevio {
    if (-not (Test-Path $RitmoPath)) { return @{ ociosas = 0; intervaloMin = $null } }
    try {
        $o = Get-Content -Path $RitmoPath -Raw -Encoding UTF8 | ConvertFrom-Json
        return @{ ociosas = [int]$o.ociosas; intervaloMin = $o.intervaloMin }
    } catch {
        return @{ ociosas = 0; intervaloMin = $null }
    }
}

function Set-Ritmo($ociosas, $intervaloMin) {
    try {
        @{ ociosas = $ociosas; intervaloMin = $intervaloMin; actualizado = (Get-Date -Format o) } |
            ConvertTo-Json | Set-Content -Path $RitmoPath -Encoding utf8
    } catch {
        Add-Content -Path (Join-Path $LogsDir "auto_procesar_errores.log") -Value "$(Get-Date -Format o) No se pudo escribir ritmo_auto.json: $_"
    }
}

function Get-IntervaloTareaMin {
    # Intervalo de repetición actual de la tarea, en minutos. $null si la tarea
    # no existe o no tiene repetición (corrida a mano fuera de Task Scheduler,
    # tarea sin registrar) -> en ese caso no se toca nada.
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        foreach ($trg in $task.Triggers) {
            if ($trg.Repetition -and $trg.Repetition.Interval -match '^PT(?:(\d+)H)?(?:(\d+)M)?$') {
                return ([int]$Matches[1] * 60 + [int]$Matches[2])
            }
        }
    } catch {}
    return $null
}

function Set-IntervaloTareaMin($minutos) {
    # Muta SOLO el Interval de la repetición, preservando StartBoundary y el
    # resto del trigger semanal. Reconstruir el trigger desde cero correría el
    # riesgo de empujar el StartBoundary al próximo martes y dejar la tarea sin
    # disparar el resto de la ventana en curso.
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $cambiados = 0
    foreach ($trg in $task.Triggers) {
        if ($trg.Repetition -and $trg.Repetition.Interval) {
            $trg.Repetition.Interval = ("PT{0}M" -f $minutos)
            $cambiados++
        }
    }
    if ($cambiados -eq 0) {
        throw "la tarea '$TaskName' no tiene ningún trigger con repetición (re-registrala con registrar_tarea_programada.ps1)"
    }
    Set-ScheduledTask -TaskName $TaskName -Trigger $task.Triggers -ErrorAction Stop | Out-Null
}

$intervaloActual = Get-IntervaloTareaMin
if ($null -ne $intervaloActual) {
    $previo = Get-RitmoPrevio
    $ociosasPrevias = $previo.ociosas
    if ($null -ne $previo.intervaloMin -and [int]$previo.intervaloMin -ne $intervaloActual) {
        # El intervalo cambió por fuera de este script -> conteo desde cero.
        $ociosasPrevias = 0
    }

    if ($corridaOciosa) {
        $ociosas = $ociosasPrevias + 1
        if (($ociosas -ge $UMBRAL_OCIOSAS) -and ($intervaloActual -ne $INTERVALO_LENTO_MIN)) {
            try {
                Set-IntervaloTareaMin $INTERVALO_LENTO_MIN
                Add-Content -Path (Join-Path $LogsDir "loop.log") -Value "$(Get-Date -Format o) $ociosas corridas ociosas seguidas -> intervalo del disparador ampliado a $INTERVALO_LENTO_MIN min (vuelve a $INTERVALO_RAPIDO_MIN apenas haya trabajo)."
                Set-Ritmo $ociosas $INTERVALO_LENTO_MIN
            } catch {
                Add-Content -Path (Join-Path $LogsDir "auto_procesar_errores.log") -Value "$(Get-Date -Format o) No se pudo ampliar el intervalo del disparador a $INTERVALO_LENTO_MIN min: $_"
                Set-Ritmo $ociosas $intervaloActual
            }
        } else {
            Set-Ritmo $ociosas $intervaloActual
        }
    } elseif ($intervaloActual -ne $INTERVALO_RAPIDO_MIN) {
        try {
            Set-IntervaloTareaMin $INTERVALO_RAPIDO_MIN
            Add-Content -Path (Join-Path $LogsDir "loop.log") -Value "$(Get-Date -Format o) Hay trabajo -> intervalo del disparador vuelto a $INTERVALO_RAPIDO_MIN min."
            Set-Ritmo 0 $INTERVALO_RAPIDO_MIN
        } catch {
            Add-Content -Path (Join-Path $LogsDir "auto_procesar_errores.log") -Value "$(Get-Date -Format o) No se pudo volver el intervalo del disparador a $INTERVALO_RAPIDO_MIN min: $_"
            Enviar-Alerta "Rayando el CDA: el disparador quedó en ritmo lento" "Hubo trabajo real pero no se pudo devolver el intervalo de la tarea programada a $INTERVALO_RAPIDO_MIN min (sigue en $intervaloActual min), así que los próximos pedidos del equipo pueden tardar hasta ese tiempo en procesarse.`n`nError: $_`n`nRe-registrar la tarea a mano:`npowershell -ExecutionPolicy Bypass -File pipeline\registrar_tarea_programada.ps1"
            Set-Ritmo 0 $intervaloActual
        }
    } else {
        Set-Ritmo 0 $INTERVALO_RAPIDO_MIN
    }
}
