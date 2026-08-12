# Registra (o re-registra) la tarea de Task Scheduler "RayandoCDA_AutoProcesar":
# dispara auto_procesar.ps1 directo cada 5 minutos (proceso nuevo y corto en
# cada corrida), en vez de depender de un solo proceso de PowerShell que corra
# sin parar durante días (auto_procesar_loop.ps1, el diseño viejo). Ese
# diseño viejo resultó frágil en la práctica: el proceso se cayó dos veces en
# la madrugada del 04/08 (código de salida típico de un cierre abrupto de
# proceso) y nadie lo notó hasta que un programa nuevo quedó sin procesar.
# Con un trigger repetitivo, si una corrida se cae o falla, la siguiente (5
# min después) se autorecupera sola — no depende de que un único proceso
# sobreviva indefinidamente.
#
# Ventana semanal (martes 00:00 a miércoles 10:00, ver $trigger abajo) en vez
# de correr sin parar: el PC no necesita quedar prendido 24/7. Fuera de esa
# ventana el equipo avisa a mano si necesita un cambio.
#
# "-MultipleInstances IgnoreNew" seguido abajo evita que se lancen dos
# corridas en paralelo si una transcripción/corte real (que sí puede tardar
# bastante) sigue corriendo cuando toca el próximo disparo cada 5 min.
#
# Idempotente: si la tarea ya existe, la borra y la vuelve a crear. Además
# mata cualquier loop viejo (auto_procesar_loop.ps1) que haya quedado
# corriendo a mano o huérfano de una versión anterior de esta tarea.
#
# Uso (una sola vez, o de nuevo si hace falta re-registrar):
#   powershell -ExecutionPolicy Bypass -File registrar_tarea_programada.ps1

$ErrorActionPreference = "Stop"

$TaskName = "RayandoCDA_AutoProcesar"
$Script = "C:\Users\sebap\rayando-cda\pipeline\auto_procesar.ps1"

Write-Host "Buscando loops viejos (auto_procesar_loop.ps1) corriendo para matarlos..."
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*auto_procesar_loop.ps1*" } |
    ForEach-Object {
        Write-Host "  Matando loop viejo (PID $($_.ProcessId))..."
        Stop-Process -Id $_.ProcessId -Force
    }

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Ya existe la tarea '$TaskName', la borro para re-registrarla..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""
# Ventana semanal fija: el PC ya no necesita quedar prendido 24/7. El
# programa se transmite en vivo los lunes y el material (transcripción +
# corte) suele quedar listo para revisión durante el martes, así que la
# herramienta de correcciones queda disponible para el equipo desde el
# martes 00:00 hasta el miércoles 10:00 (34 horas) — dentro de esa ventana
# dispara cada 5 min igual que antes; fuera de ella (jueves a lunes, y
# miércoles después de las 10am) el trigger simplemente no dispara, así que
# no importa si el PC está prendido por otro motivo. Si el equipo no llega a
# pedir cambios en esa ventana, el ajuste queda para la próxima semana o se
# hace a mano (avisan a Sebastián). Se repite sola todas las semanas — no
# hace falta volver a registrar la tarea.
#
# New-ScheduledTaskTrigger -Weekly no acepta -RepetitionInterval/
# -RepetitionDuration directamente (solo el parameter set -Once los admite) —
# se arma un trigger -Once descartable solo para heredar su objeto
# Repetition ya armado y pegarlo en el trigger semanal real.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At "00:00"
$repeticionTemporal = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Hours 34)
$trigger.Repetition = $repeticionTemporal.Repetition
# LogonType Interactive = "solo cuando el usuario tenga sesión iniciada", sin
# pedir ni guardar contraseña (igual que el trigger AtLogOn de antes).
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited
# ExecutionTimeLimit = 0 (sin límite): una corrida real de transcripción +
# corte + subida puede tardar bastante más que 5 minutos, y no debe matarse a
# mitad de camino. El límite por defecto de Task Scheduler es 3 días — sin
# esto, mataría la corrida en silencio si se pasara de eso.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Corre auto_procesar.ps1 cada 5 minutos, martes 00:00 a miércoles 10:00, mientras el usuario tenga sesión iniciada (ver pipeline/README.md)." | Out-Null

Write-Host "Tarea '$TaskName' registrada. Arrancándola ahora (sin esperar al próximo disparo)..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

Get-ScheduledTaskInfo -TaskName $TaskName | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
