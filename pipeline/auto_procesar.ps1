# Disparador automático semanal: revisa si hay una grabación nueva y ya
# terminada en `grabaciones\`, y si la hay, corre transcribir.py +
# procesar_programa.py sola. Pensado para correr cada 5 minutos vía Task
# Scheduler (tarea "RayandoCDA_AutoProcesar").
#
# "Ya terminada" = el archivo no cambió su LastWriteTime en los últimos 5
# minutos (mientras OBS graba, el archivo se sigue escribiendo).
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

$candidatos = Get-ChildItem -Path $GrabacionesDir -Filter "*.mkv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending

foreach ($rec in $candidatos) {
    $stem = $rec.BaseName
    $transcriptJson = Join-Path $TranscripcionesDir "$stem\$stem.json"
    if (Test-Path $transcriptJson) { continue }

    $minutosDesdeUltimaEscritura = (New-TimeSpan -Start $rec.LastWriteTime -End (Get-Date)).TotalMinutes
    if ($minutosDesdeUltimaEscritura -lt 5) {
        # Probablemente todavía se está grabando (o se acaba de terminar) —
        # esperar a que se estabilice en la próxima corrida.
        continue
    }

    $logFile = Join-Path $LogsDir "$stem.log"
    Add-Content -Path $logFile -Value "$(Get-Date -Format o) Iniciando procesamiento automático de $($rec.Name)"

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
