# Loop de respaldo mientras se resuelve el registro en Task Scheduler
# (ver auto_procesar.ps1 para la lógica real de detección/procesamiento).
# Corre indefinidamente, revisando cada 5 minutos. Pensado para lanzarse
# como proceso independiente (Start-Process -WindowStyle Hidden), no como
# hijo de una sesión de Claude Code, para que sobreviva aunque esa sesión
# termine.

$ScriptReal = "C:\Users\sebap\rayando-cda\pipeline\auto_procesar.ps1"
$LogLoop = "C:\Users\sebap\rayando-cda\pipeline\logs_auto\loop.log"

if (-not (Test-Path (Split-Path $LogLoop))) {
    New-Item -ItemType Directory -Path (Split-Path $LogLoop) | Out-Null
}

Add-Content -Path $LogLoop -Value "$(Get-Date -Format o) Loop de respaldo iniciado (PID $PID)."

while ($true) {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptReal
    } catch {
        Add-Content -Path $LogLoop -Value "$(Get-Date -Format o) Error en la corrida: $_"
    }
    Start-Sleep -Seconds 300
}
