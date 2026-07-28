# Registra (o re-registra) la tarea de Task Scheduler "RayandoCDA_AutoProcesar":
# arranca auto_procesar_loop.ps1 al iniciar sesión de este usuario, sin pedir
# ni guardar contraseña. Idempotente: si la tarea ya existe, la borra y la
# vuelve a crear. Además mata cualquier loop que haya quedado corriendo a
# mano, para no terminar con dos loops en paralelo.
#
# Uso (una sola vez, o de nuevo si hace falta re-registrar):
#   powershell -ExecutionPolicy Bypass -File registrar_tarea_programada.ps1

$ErrorActionPreference = "Stop"

$TaskName = "RayandoCDA_AutoProcesar"
$LoopScript = "C:\Users\sebap\rayando-cda\pipeline\auto_procesar_loop.ps1"

Write-Host "Buscando loops manuales corriendo para matarlos..."
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*auto_procesar_loop.ps1*" } |
    ForEach-Object {
        Write-Host "  Matando loop manual previo (PID $($_.ProcessId))..."
        Stop-Process -Id $_.ProcessId -Force
    }

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Ya existe la tarea '$TaskName', la borro para re-registrarla..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$LoopScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
# ExecutionTimeLimit = 0 (sin límite): el loop corre indefinidamente hasta
# que se cierre sesión. El límite por defecto de Task Scheduler es 3 días —
# sin esto, mataría el loop en silencio a los 3 días, el mismo tipo de fallo
# silencioso que ya se vio hoy con RepetitionDuration en triggers repetitivos.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Arranca el loop de procesamiento automático de Rayando el CDA al iniciar sesión (ver pipeline/README.md)." | Out-Null

Write-Host "Tarea '$TaskName' registrada. Arrancándola ahora (sin esperar al próximo login)..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

Get-ScheduledTaskInfo -TaskName $TaskName | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
