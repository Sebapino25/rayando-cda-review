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
# Trigger único cada 5 min, por 10 años (proxy de "sin fecha de fin" — Task
# Scheduler rechaza [TimeSpan]::MaxValue con "valor fuera de intervalo", así
# que se usa el máximo práctico de este módulo). No depende de un evento de
# logon puntual: Task Scheduler reintenta cada 5 min según este horario, y si
# no hay sesión de usuario activa en ese momento simplemente no corre esa vez
# (ver Principal/LogonType abajo) — se recupera sola apenas haya sesión, sin
# necesidad de que alguien vuelva a iniciar sesión.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::FromDays(3650))
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
    -Description "Corre auto_procesar.ps1 cada 5 minutos mientras el usuario tenga sesión iniciada (ver pipeline/README.md)." | Out-Null

Write-Host "Tarea '$TaskName' registrada. Arrancándola ahora (sin esperar al próximo disparo)..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

Get-ScheduledTaskInfo -TaskName $TaskName | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
